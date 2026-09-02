from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from fastapi.responses import Response
from app.services import store
from app.services.interview import submit_answer
from app.services.llm import LLMServiceError
from app.services.voice import transcribe_audio_bytes, synthesize_speech

router = APIRouter(prefix="/api/session", tags=["voice"])
tts_router = APIRouter(prefix="/api", tags=["voice"])


@router.post("/{session_id}/interview/voice-answer")
async def voice_answer(session_id: str, audio: UploadFile = File(...)):
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    suffix = "." + (audio.filename.rsplit(".", 1)[-1] if audio.filename and "." in audio.filename else "webm")
    try:
        transcript_text = transcribe_audio_bytes(raw, suffix=suffix)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

    if not transcript_text:
        raise HTTPException(
            status_code=400,
            detail="Could not transcribe any speech from the audio — try again and speak clearly.",
        )

    try:
        result = await submit_answer(session, transcript_text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LLMServiceError as e:
        raise HTTPException(status_code=503, detail=str(e))
    store.save_session(session)

    result["transcribed_text"] = transcript_text
    return result


class TTSBody(BaseModel):
    text: str


@tts_router.post("/tts")
async def tts(body: TTSBody):
    if not body.text or not body.text.strip():
        raise HTTPException(status_code=400, detail="text is required.")
    try:
        audio_bytes = await synthesize_speech(body.text.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="TTS produced no audio.")
    return Response(content=audio_bytes, media_type="audio/mpeg")
