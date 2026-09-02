from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services import store
from app.services.interview import start_interview, submit_answer, stop_interview
from app.services.report import generate_report
from app.services.llm import LLMServiceError

router = APIRouter(prefix="/api/session", tags=["interview"])


class AnswerBody(BaseModel):
    answer: str


@router.post("/{session_id}/interview/start")
async def start(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        session = await start_interview(session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    store.save_session(session)

    first = session.transcript[0]
    return {"level": first.level, "question": first.question, "interview_started_at": session.interview_started_at}


@router.post("/{session_id}/interview/answer")
async def answer(session_id: str, body: AnswerBody):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not body.answer or not body.answer.strip():
        raise HTTPException(status_code=400, detail="Answer cannot be empty.")

    try:
        result = await submit_answer(session, body.answer.strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    store.save_session(session)
    return result


@router.post("/{session_id}/interview/stop")
async def stop(session_id: str):
    """Explicit 'Stop Interview' button — ends immediately, no LLM call."""
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    try:
        result = stop_interview(session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    store.save_session(session)
    return result


@router.get("/{session_id}/interview/transcript")
async def transcript(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "current_level": session.current_level,
        "transcript": [qa.model_dump() for qa in session.transcript],
    }


@router.post("/{session_id}/report")
async def report(session_id: str):
    """Generates (and caches) the performance report once the interview has
    ended. Cheap to call repeatedly — returns the cached report instead of
    re-hitting the LLM if it's already been generated for this session."""
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if session.current_level != "done":
        raise HTTPException(status_code=400, detail="Interview has not ended yet.")
    if session.performance_report is not None:
        return session.performance_report.model_dump()

    try:
        report_data = await generate_report(session)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    session.performance_report = report_data
    store.save_session(session)
    return report_data.model_dump()
