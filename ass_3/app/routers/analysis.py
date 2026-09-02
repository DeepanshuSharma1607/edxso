from fastapi import APIRouter, HTTPException
from app.services import store
from app.services.analysis import analyse_role, analyse_candidate, compute_job_fit
from app.services.llm import LLMServiceError

router = APIRouter(prefix="/api/session", tags=["analysis"])


@router.post("/{session_id}/analyse")
async def run_analysis(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not session.jd_text or not session.resume_text:
        raise HTTPException(
            status_code=400, detail="Both JD and resume must be submitted first."
        )

    try:
        session.role_analysis = await analyse_role(session.jd_text)
        session.candidate_analysis = await analyse_candidate(
            session.resume_text, session.role_analysis
        )
        session.job_fit = await compute_job_fit(session.role_analysis, session.candidate_analysis)
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    store.save_session(session)

    return {
        "role_analysis": session.role_analysis,
        "candidate_analysis": session.candidate_analysis,
        "job_fit": session.job_fit,
    }


@router.get("/{session_id}/analysis")
async def get_analysis(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    if not session.role_analysis:
        raise HTTPException(status_code=400, detail="Analysis has not been run yet.")
    return {
        "role_analysis": session.role_analysis,
        "candidate_analysis": session.candidate_analysis,
        "job_fit": session.job_fit,
    }
