from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Google AI Studio key — https://aistudio.google.com/apikey
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    # Tried once if the primary model's retries are exhausted or it 404s.
    gemini_fallback_model: str = "gemini-3.6-flash"
    whisper_model_size: str = "tiny"  # tiny.en also valid, CPU-friendly
    tts_voice: str = "en-US-GuyNeural"  # edge-tts voice for interviewer
    data_dir: str = "./data"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # stale vars (e.g. old MISTRAL_*) must not crash startup
    )


settings = Settings()
