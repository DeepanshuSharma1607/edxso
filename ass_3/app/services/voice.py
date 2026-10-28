"""
Voice layer.
- STT: faster-whisper 'tiny' model, CPU/int8 — matches the no-GPU dev environment.
- TTS: edge-tts — free, no API key, decent quality, runs as an async generator.

Both are wrapped so routers never touch the underlying libraries directly.
"""
import io
import tempfile
import os

import av
import numpy as np
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


def _as_frames(result) -> list:
    """Older PyAV returns a single frame/None from resample(); newer returns a list."""
    if result is None:
        return []
    return list(result) if isinstance(result, (list, tuple)) else [result]


def _decode_audio(path: str, sampling_rate: int = 16000) -> np.ndarray:
    """
    Decode any browser recording (webm/opus, ogg, mp4, wav) to mono float32 @16kHz.

    faster-whisper's own decoder calls av.open(..., metadata_errors=...), which
    breaks when the installed PyAV doesn't match. Decoding here with plain
    av.open() works across PyAV versions.
    """
    resampler = av.AudioResampler(format="s16", layout="mono", rate=sampling_rate)
    chunks: list[np.ndarray] = []
    with av.open(path, mode="r") as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise ValueError("No audio stream found in the recording.")
        for frame in container.decode(stream):
            for out in _as_frames(resampler.resample(frame)):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in _as_frames(resampler.resample(None)):  # flush
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


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
        audio = _decode_audio(tmp_path)
        if audio.size == 0:
            return ""
        segments, _info = model.transcribe(audio, language="en", vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()
    finally:
        # On Windows the decoder can still hold the file briefly; a failed
        # cleanup must never turn a successful transcription into a 500.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def synthesize_speech(text: str) -> bytes:
    """Returns MP3 bytes for the given text using the configured edge-tts voice."""
    communicate = edge_tts.Communicate(text, settings.tts_voice)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()
