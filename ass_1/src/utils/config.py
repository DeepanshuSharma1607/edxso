"""
config.py — Central configuration & path management for all modules.
Includes standalone .env parser with zero required external dependencies.
"""
import os

# Base paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR     = os.path.join(PROJECT_ROOT, "data")
ENV_FILE     = os.path.join(PROJECT_ROOT, ".env")

# Zero-dependency .env loader fallback
def _load_env_file(filepath: str):
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip("'\"")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass

# Try python-dotenv if installed, otherwise use zero-dependency fallback
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ENV_FILE)
except ImportError:
    _load_env_file(ENV_FILE)

# API Keys — must come from .env / environment only. Never hardcode a real
# key here as a fallback default: if this file is ever committed to a public
# GitHub repo (which the assignment asks you to submit), a hardcoded key
# gets leaked and can be abused by anyone who finds the repo.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "").strip()
GEMINI_API_KEY  = os.environ.get("GEMINI_API_KEY", "").strip()
# Optional second LLM provider. Gemini's free tier allows only 20
# generateContent requests per day per model, which is far below what a
# 69-creator run needs; Mistral's free tier is metered per-minute instead of
# per-day, so it serves as the fallback once Gemini's models are exhausted.
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "").strip()

# File paths
RAW_CHANNELS_CSV       = os.path.join(DATA_DIR, "raw_channels.csv")
RAW_CHANNELS_JSON      = os.path.join(DATA_DIR, "raw_channels.json")
FILTERED_CHANNELS_CSV  = os.path.join(DATA_DIR, "filtered_channels.csv")
SHORTLISTED_CSV        = os.path.join(DATA_DIR, "shortlisted.csv")
SHORTLISTED_JSON       = os.path.join(DATA_DIR, "shortlisted.json")
ENRICHED_PROFILES_CSV  = os.path.join(DATA_DIR, "enriched_profiles.csv")
ENRICHED_PROFILES_JSON = os.path.join(DATA_DIR, "enriched_profiles.json")
PERSONALIZED_CSV       = os.path.join(DATA_DIR, "personalized_messages.csv")
PERSONALIZED_JSON      = os.path.join(DATA_DIR, "personalized_messages.json")
OUTREACH_TRACKER_CSV   = os.path.join(DATA_DIR, "outreach_tracker.csv")
OUTREACH_TRACKER_JSON  = os.path.join(DATA_DIR, "outreach_tracker.json")
CACHE_FILE             = os.path.join(DATA_DIR, ".personalize_cache.json")

# Constants
MIN_SUBSCRIBERS = 5_000
MAX_SUBSCRIBERS = 100_000
TARGET_TOTAL    = 50
