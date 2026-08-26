import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("YOUTUBE_API_KEY", "AIzaSyARFy9wrMQkHvK1B5PQQFgIHGw9d0gzsoE")
url = "https://www.googleapis.com/youtube/v3/search"
params = {
    "part": "snippet",
    "q": "tech reviews india",
    "type": "channel",
    "maxResults": 5,
    "key": API_KEY
}
r = requests.get(url, params=params)
print("Status:", r.status_code)
print(r.json())
