from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional
from app.services import store
from app.services.extraction import extract_text_from_upload, validate_pasted_text

router = APIRouter(prefix="/api/session", tags=["ingestion"])


@router.post("/new")
async def new_session():
    session = store.create_session()
    return {"session_id": session.id}


@router.post("/{session_id}/jd")
async def submit_jd(
    session_id: str,
    jd_text: Optional[str] = Form(None),
    jd_file: Optional[UploadFile] = File(None),
):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if jd_file is not None:
        text = await extract_text_from_upload(jd_file)
    elif jd_text:
        text = validate_pasted_text(jd_text, "Job Description")
    else:
        raise HTTPException(status_code=400, detail="Provide jd_text or jd_file.")

    session.jd_text = text
    store.save_session(session)
    return {"ok": True, "length": len(text)}


@router.post("/{session_id}/resume")
async def submit_resume(
    session_id: str,
    resume_text: Optional[str] = Form(None),
    resume_file: Optional[UploadFile] = File(None),
):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    if resume_file is not None:
        text = await extract_text_from_upload(resume_file)
    elif resume_text:
        text = validate_pasted_text(resume_text, "Resume")
    else:
        raise HTTPException(status_code=400, detail="Provide resume_text or resume_file.")

    session.resume_text = text
    store.save_session(session)
    return {"ok": True, "length": len(text)}


@router.get("/{session_id}")
async def get_session_status(session_id: str):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {
        "session_id": session.id,
        "has_jd": bool(session.jd_text),
        "has_resume": bool(session.resume_text),
        "has_role_analysis": session.role_analysis is not None,
        "has_candidate_analysis": session.candidate_analysis is not None,
        "has_job_fit": session.job_fit is not None,
    }
