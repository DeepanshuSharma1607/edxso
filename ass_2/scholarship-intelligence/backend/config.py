import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")

# When True (default in this repo), the crawler replays real, previously
# fetched snapshots from data/fixtures/ instead of hitting the internet at
# run time. Flip to False once running with live internet access; the same
# extraction/verification/storage pipeline consumes backend/crawler/http_crawler.py
# fetches instead of fixture_loader.py -- see scripts/run_crawler.py.
USE_FIXTURES = os.environ.get("USE_FIXTURES", "1") == "1"

API_HOST = os.environ.get("API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("API_PORT", "8000"))
