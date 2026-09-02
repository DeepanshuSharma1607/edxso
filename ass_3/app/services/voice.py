"""
Voice layer.
- STT: faster-whisper 'tiny' model, CPU/int8 — matches the no-GPU dev environment.
- TTS: edge-tts — free, no API key, decent quality, runs as an async generator.

Both are wrapped so routers never touch the underlying libraries directly.
"""
import io
import tempfile
import os
from faster_whisper import WhisperModel
import edge_tts
from app.config import settings

_whisper_model: WhisperModel | None = None


def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        # int8 compute type keeps this usable on CPU-only machines.
        _whisper_model = WhisperModel(
            settings.whisper_model_size, device="cpu", compute_type="int8"
        )
    return _whisper_model


def transcribe_audio_bytes(audio_bytes: bytes, suffix: str = ".webm") -> str:
    """
    Writes the uploaded audio to a temp file (faster-whisper/PyAV needs a
    seekable file path for non-wav containers like webm/opus from the browser
    MediaRecorder API) and transcribes it.
    """
    model = _get_whisper_model()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        segments, _info = model.transcribe(tmp_path, language="en", vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()
    finally:
        os.unlink(tmp_path)


async def synthesize_speech(text: str) -> bytes:
    """Returns MP3 bytes for the given text using the configured edge-tts voice."""
    communicate = edge_tts.Communicate(text, settings.tts_voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()
