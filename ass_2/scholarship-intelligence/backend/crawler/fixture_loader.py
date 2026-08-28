"""
Fixture-replay "crawler".

Reads the real snapshot files under data/fixtures/ (each one is text
genuinely retrieved from the listed SOURCE_URL, see the header of every
fixture file) and returns them in the exact shape the live crawler would
return via http_crawler.fetch(). This lets the rest of the pipeline
(extraction -> verification -> storage -> change detection) run for real,
deterministically, without requiring outbound internet access from this
process.

Swap USE_FIXTURES=False (backend/config.py) once running with real
internet access, and the same downstream code will consume live pages
from http_crawler.py instead.
"""
from pathlib import Path
from dataclasses import dataclass

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures"


@dataclass
class FixturePage:
    source_url: str
    fetched_at: str
    body: str


def load_fixture(filename: str) -> FixturePage:
    path = FIXTURES_DIR / filename
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    source_url, fetched_at = "", ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("SOURCE_URL:"):
            source_url = line.split(":", 1)[1].strip()
        elif line.startswith("FETCHED_AT:"):
            fetched_at = line.split(":", 1)[1].strip()
        elif line.strip() == "---":
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:])
    return FixturePage(source_url=source_url, fetched_at=fetched_at, body=body)
