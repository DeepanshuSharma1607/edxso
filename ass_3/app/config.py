from pydantic_settings import BaseSettings
from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

class Settings(BaseSettings):
    gemini_api_key: str = GEMINI_API_KEY
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.0-flash"
    whisper_model_size: str = "tiny" # tiny.en also valid, CPU-friendly
    tts_voice: str = "en-US-GuyNeural" # edge-tts voice for interviewer
    data_dir: str = "./data"

    class Config:
        env_file = ".env"

settings = Settings()
