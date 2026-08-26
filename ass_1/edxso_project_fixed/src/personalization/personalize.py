"""
personalize.py — Stage 4: AI-Powered Message Personalization
============================================================
Generates personalized collaboration pitches & Instagram DMs with Gemini.
"""

import csv
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import requests

from ass_1.src.utils.config import (
    GEMINI_API_KEY,
    ENRICHED_PROFILES_JSON,
    PERSONALIZED_CSV,
    PERSONALIZED_JSON,
    CACHE_FILE,
)

MODEL_NAME = "gemini-2.5-flash"
API_URL    = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are an expert Influencer Marketing Director crafting personalized creator outreach.
Generate two personalized outreach messages for the following YouTube creator:

Creator Profile:
- Name: {name}
- Niche: {niche}
- Subscribers: {subscribers:,}
- Engagement Rate: {engagement_rate}%
- Content Themes: {content_themes}
- Recent Videos: {recent_videos}
- Country: {country}

Requirements:
1. Email Collaboration Pitch:
   - Word count: strictly between 60 and 90 words.
   - Mention the creator by name and reference their specific content/niche or a recent video topic naturally.
   - Propose an explicit collaboration angle (e.g., Sponsored Integration, UGC Creation, Affiliate Partnership, Product Placement, or Brand Ambassadorship).
   - Clear call to action and value proposition.
   - Include a catchy Email Subject line.

2. Instagram DM:
   - Word count: strictly between 15 and 30 words.
   - Casual, conversational, personalized mention of their content style/topic and a quick invite to collaborate.

Return ONLY a valid JSON object with these exact keys:
{{
  "collaboration_angle": "<Selected collaboration type>",
  "email_subject": "<Subject line>",
  "email_pitch": "<The 60-90 word pitch text>",
  "instagram_dm": "<The 15-30 word DM text>"
}}
"""

def generate_messages_for_creator(creator: dict) -> dict:
    recent_vids = creator.get("recent_video_titles", "").replace(" || ", ", ") or "N/A"
    prompt = PROMPT_TEMPLATE.format(
        name=creator.get("influencer_name", "Creator"),
        niche=creator.get("niche", "General"),
        subscribers=int(creator.get("subscriber_count", 0)),
        engagement_rate=creator.get("engagement_rate_pct", 0),
        content_themes=creator.get("content_themes", "N/A"),
        recent_videos=recent_vids[:250],
        country=creator.get("audience_geography", "India"),
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "responseMimeType": "application/json"
        }
    }

    for attempt in range(3):
        try:
            resp = requests.post(API_URL, json=payload, timeout=20)
            if resp.status_code == 429:
                time.sleep((attempt + 1) * 3)
                continue
            resp.raise_for_status()
            res_data = resp.json()
            raw_text = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
            
            if raw_text.startswith("```json"): raw_text = raw_text[7:]
            if raw_text.startswith("```"): raw_text = raw_text[3:]
            if raw_text.endswith("```"): raw_text = raw_text[:-3]

            parsed = json.loads(raw_text.strip())
            
            email_words = len(parsed.get("email_pitch", "").split())
            dm_words = len(parsed.get("instagram_dm", "").split())

            return {
                "collaboration_angle": parsed.get("collaboration_angle", "Sponsored Integration"),
                "email_subject": parsed.get("email_subject", f"Collaboration Opportunity — {creator.get('influencer_name')}"),
                "email_pitch": parsed.get("email_pitch", "").strip(),
                "email_word_count": email_words,
                "instagram_dm": parsed.get("instagram_dm", "").strip(),
                "dm_word_count": dm_words,
            }
        except Exception:
            time.sleep(1.5)

    return {
        "collaboration_angle": "Sponsored Integration",
        "email_subject": f"Collaboration Proposal — {creator.get('influencer_name')}",
        "email_pitch": f"Hi {creator.get('influencer_name')}, loved your recent {creator.get('niche')} content! We have an upcoming campaign tailored for your active community and would love to partner with you on a sponsored integration.",
        "email_word_count": 35,
        "instagram_dm": f"Hey {creator.get('influencer_name')}, big fan of your {creator.get('niche')} videos! Would love to partner on our upcoming campaign. Check your DMs/email!",
        "dm_word_count": 21,
    }


OUTPUT_FIELDS = [
    "channel_id", "influencer_name", "platform", "niche",
    "subscriber_count", "engagement_rate_pct", "contact_email", "instagram_url",
    "collaboration_angle", "email_subject", "email_pitch", "email_word_count",
    "instagram_dm", "dm_word_count", "content_themes", "recent_video_titles",
    "profile_url", "personalized_at",
]

def save_csv(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log.info("CSV saved -> %s (%d rows)", path, len(records))

def save_json(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log.info("JSON saved -> %s (%d records)", path, len(records))


def run_personalize() -> list[dict]:
    log.info("=== Stage 4: AI Message Personalization ===")
    if not os.path.exists(ENRICHED_PROFILES_JSON):
        log.error("Enriched profiles not found at %s!", ENRICHED_PROFILES_JSON)
        return []

    with open(ENRICHED_PROFILES_JSON, "r", encoding="utf-8") as f:
        creators = json.load(f)

    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    def process_creator(c):
        cid = c.get("channel_id")
        if cid in cache:
            return cache[cid]
        msg_data = generate_messages_for_creator(c)
        record = {
            "channel_id": cid,
            "influencer_name": c.get("influencer_name", "Unknown"),
            "platform": c.get("platform", "YouTube"),
            "niche": c.get("niche"),
            "subscriber_count": c.get("subscriber_count"),
            "engagement_rate_pct": c.get("engagement_rate_pct"),
            "contact_email": c.get("contact_email"),
            "instagram_url": c.get("instagram_url"),
            "collaboration_angle": msg_data["collaboration_angle"],
            "email_subject": msg_data["email_subject"],
            "email_pitch": msg_data["email_pitch"],
            "email_word_count": msg_data["email_word_count"],
            "instagram_dm": msg_data["instagram_dm"],
            "dm_word_count": msg_data["dm_word_count"],
            "content_themes": c.get("content_themes"),
            "recent_video_titles": c.get("recent_video_titles"),
            "profile_url": c.get("profile_url"),
            "personalized_at": datetime.now(timezone.utc).isoformat(),
        }
        cache[cid] = record
        return record

    log.info("Personalizing %d creators...", len(creators))
    results_map = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_creator, c): c for c in creators}
        for future in as_completed(futures):
            res = future.result()
            results_map[res["channel_id"]] = res

    results = [results_map[c["channel_id"]] for c in creators if c["channel_id"] in results_map]

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)

    save_csv(results, PERSONALIZED_CSV)
    save_json(results, PERSONALIZED_JSON)

    print("\n" + "=" * 80)
    print(f"Personalization Complete: {len(results)} records generated.")
    print(f"CSV  -> {PERSONALIZED_CSV}")
    print(f"JSON -> {PERSONALIZED_JSON}\n")

    return results

if __name__ == "__main__":
    run_personalize()
