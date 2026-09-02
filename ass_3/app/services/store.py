"""
JSON-file-backed session store.

Was pure in-memory (a module-level dict), which meant every ``uvicorn --reload``
restart silently wiped all sessions — the browser tab kept a now-dead
session_id in memory and every subsequent call 404'd with "Session not found".

This keeps the exact same in-memory dict as a hot cache (so normal request
handling is still just dict access) but adds write-through persistence to a
JSON file under ``settings.data_dir``, and reloads that file on process start.
That's enough to survive --reload / crashes without pulling in a real DB yet —
still an MVP store, just one that isn't erased by the dev server's own reload
loop.
"""
import json
from pathlib import Path
from threading import Lock
from typing import Dict, Optional

from app.config import settings
from app.models.schemas import Session

_LOCK = Lock()
_STORE_PATH = Path(settings.data_dir) / "sessions.json"


def _load_from_disk() -> Dict[str, Session]:
    if not _STORE_PATH.exists():
        return {}
    try:
        raw = json.loads(_STORE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable store shouldn't crash startup — start fresh
        # rather than take the whole app down.
        return {}
    sessions: Dict[str, Session] = {}
    for session_id, data in raw.items():
        try:
            sessions[session_id] = Session.model_validate(data)
        except Exception:
            continue
    return sessions


def _flush_to_disk() -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {sid: session.model_dump(mode="json") for sid, session in _sessions.items()}
    tmp_path = _STORE_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(payload))
    tmp_path.replace(_STORE_PATH)  # atomic on POSIX — avoids truncated reads


_sessions: Dict[str, Session] = _load_from_disk()


def create_session() -> Session:
    session = Session()
    with _LOCK:
        _sessions[session.id] = session
        _flush_to_disk()
    return session


def get_session(session_id: str) -> Optional[Session]:
    return _sessions.get(session_id)


def save_session(session: Session) -> None:
    with _LOCK:
        _sessions[session.id] = session
        _flush_to_disk()


def delete_session(session_id: str) -> None:
    with _LOCK:
        _sessions.pop(session_id, None)
        _flush_to_disk()
