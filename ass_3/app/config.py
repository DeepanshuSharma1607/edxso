from pydantic_settings import BaseSettings
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

class Settings(BaseSettings):
    mistral_api_key: str = MISTRAL_API_KEY
    mistral_model: str = "mistral-small-2603"
    # Tried once, after the primary model's retries are exhausted, before
    # giving up entirely — Mistral's overload incidents are usually per-model
    # capacity, not a full-platform outage, so a lighter/different model
    # often still answers. Leave equal to mistral_model (or blank) to disable.
    mistral_fallback_model: str = "mistral-small-latest"
    whisper_model_size: str = "tiny"  # tiny.en also valid, CPU-friendly
    tts_voice: str = "en-US-GuyNeural"  # edge-tts voice for interviewer
    data_dir: str = "./data"

    class Config:
        env_file = ".env"


settings = Settings()
