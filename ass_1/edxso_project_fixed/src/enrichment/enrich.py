"""
enrich.py — Stage 3: Profile Enrichment
=========================================
Gathers recent video descriptions, extracts emails and Instagram links,
and derives content themes for shortlisted creators.
"""

import csv
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
import requests

from ass_1.src.utils.config import (
    YOUTUBE_API_KEY,
    SHORTLISTED_CSV,
    ENRICHED_PROFILES_CSV,
    ENRICHED_PROFILES_JSON,
)

BASE_URL = "https://www.googleapis.com/youtube/v3"
MAX_RECENT_VIDEOS = 5
EXTERNAL_PAGE_TIMEOUT = 8

SCANNABLE_DOMAINS = {
    "linktr.ee", "beacons.ai", "beacons.nz", "carrd.co", "bio.link",
    "instabio.cc", "linkinbio", "about.me", "campsite.bio", "hoo.be",
    "later.com", "taplink.cc", "koji.to", "milkshake.app",
}
SKIP_DOMAINS = {
    "youtube.com", "youtu.be", "instagram.com", "twitter.com", "x.com",
    "facebook.com", "t.co", "fb.com", "tiktok.com", "snapchat.com",
    "linkedin.com", "pinterest.com", "reddit.com", "discord.com",
    "telegram.me", "t.me",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]{2,}@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
INSTAGRAM_RE = re.compile(
    r"(?:(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9_.]{2,30})/?)"
    r"|(?:(?:^|\s|[(\[])@([A-Za-z0-9_.]{2,30}))",
    re.IGNORECASE | re.MULTILINE,
)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

NICHE_THEMES = {
    "Technology": ["Tech Reviews", "Gadget Unboxing", "Tips & Tutorials"],
    "Fitness":    ["Workout Routines", "Health & Wellness", "Yoga & Exercise"],
    "Beauty":     ["Skincare Routines", "Makeup Tutorials", "Product Reviews"],
    "Gaming":     ["Gameplay", "Mobile Gaming", "Esports"],
    "Finance":    ["Personal Finance", "Stock Market", "Investment Tips"],
}

THEME_MAP = [
    ("Product Reviews",    ["review", "unbox", "test", "honest", "worth"]),
    ("How-To / Tutorials", ["how to", "tutorial", "guide", "learn", "tips", "tricks", "step"]),
    ("Skincare",           ["skin", "skincare", "glow", "acne", "moistur", "serum"]),
    ("Makeup",             ["makeup", "foundation", "lipstick", "eyeliner", "contour", "blush"]),
    ("Workout / Fitness",  ["workout", "exercise", "gym", "yoga", "cardio", "weight", "fitness"]),
    ("Diet & Nutrition",   ["diet", "nutrition", "protein", "calories", "meal", "food"]),
    ("Stock Market",       ["stock", "nifty", "sensex", "share", "equity", "ipo", "market"]),
    ("Investment",         ["invest", "mutual fund", "sip", "portfolio", "wealth", "returns"]),
    ("Budgeting",          ["budget", "saving", "expense", "money", "salary"]),
    ("Mobile Gaming",      ["mobile", "pubg", "bgmi", "freefire", "cod", "garena"]),
    ("Gameplay",           ["gameplay", "game", "level", "boss", "mission", "stream"]),
    ("Gadgets",            ["phone", "laptop", "gadget", "smartphone", "camera", "tablet"]),
    ("Coding / Tech",      ["coding", "programming", "software", "app", "ai", "python"]),
    ("Vlogs / Lifestyle",  ["vlog", "day in", "routine", "life", "travel", "daily"]),
]


def batch_branding(channel_ids: list[str]) -> dict[str, dict]:
    result = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i : i + 50]
        params = {
            "part": "brandingSettings,snippet",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }
        try:
            resp = requests.get(f"{BASE_URL}/channels", params=params, timeout=15)
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                cid      = item["id"]
                branding = item.get("brandingSettings", {}).get("channel", {})
                snippet  = item.get("snippet", {})
                result[cid] = {
                    "api_email":  branding.get("contactEmail", ""),
                    "custom_url": snippet.get("customUrl", ""),
                    "keywords":   branding.get("keywords", ""),
                    "country":    snippet.get("country", ""),
                }
        except Exception as e:
            log.warning("Branding fetch failed for batch: %s", e)
        time.sleep(0.3)
    return result


def get_recent_video_details(channel_id: str, max_results: int = MAX_RECENT_VIDEOS) -> list[dict]:
    search_params = {
        "part": "id",
        "channelId": channel_id,
        "type": "video",
        "order": "date",
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }
    try:
        resp = requests.get(f"{BASE_URL}/search", params=search_params, timeout=15)
        resp.raise_for_status()
        video_ids = [
            it["id"]["videoId"]
            for it in resp.json().get("items", [])
            if it.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        vid_resp = requests.get(
            f"{BASE_URL}/videos",
            params={"part": "snippet", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY},
            timeout=15,
        )
        vid_resp.raise_for_status()
        return [
            {
                "title":       it["snippet"].get("title", ""),
                "description": it["snippet"].get("description", ""),
            }
            for it in vid_resp.json().get("items", [])
        ]
    except Exception as e:
        log.warning("Video search/details failed for %s: %s", channel_id, e)
        return []


def fetch_page_text(url: str) -> str:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        r = requests.get(url, headers=headers, timeout=EXTERNAL_PAGE_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            text = re.sub(r"<[^>]+>", " ", r.text)
            return re.sub(r"\s+", " ", text)[:50_000]
    except Exception:
        pass
    return ""


def should_scan_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.lower().lstrip("www.")
        if any(s in domain for s in SCANNABLE_DOMAINS):
            return True
        if any(s in domain for s in SKIP_DOMAINS):
            return False
        return True
    except Exception:
        return False


def find_external_urls(texts: list[str]) -> list[str]:
    seen = set()
    result = []
    for text in texts:
        for m in URL_RE.finditer(text or ""):
            url = m.group(0).rstrip(".,;)")
            if url not in seen and should_scan_url(url):
                seen.add(url)
                result.append(url)
    return result[:8]


def extract_email(all_texts: list[str], api_email: str = "") -> tuple[str, str]:
    BAD = {"example", "test", "noreply", "no-reply", "sample", "yourname", "domain"}
    if api_email and "@" in api_email:
        clean = api_email.strip()
        if not any(b in clean.lower() for b in BAD):
            return clean, "brandingSettings API"

    for i, text in enumerate(all_texts):
        for m in EMAIL_RE.findall(text or ""):
            if not any(b in m.lower() for b in BAD):
                source = ["channel description", "video descriptions", "external page"][min(i, 2)]
                return m, source

    return "Not Found", ""


def extract_instagram(all_texts: list[str]) -> str:
    SKIP_IG = {"instagram", "instagram.com", "official", "reels", "p", "tv", "explore"}
    for text in all_texts:
        for m in INSTAGRAM_RE.finditer(text or ""):
            handle = (m.group(1) or m.group(2) or "").strip().rstrip("/")
            if handle and handle.lower() not in SKIP_IG and len(handle) >= 2:
                return f"https://instagram.com/{handle}"
    return ""


def extract_website(all_texts: list[str]) -> str:
    for text in all_texts:
        for m in URL_RE.finditer(text or ""):
            url = m.group(0).rstrip(".,;)")
            if should_scan_url(url):
                return url
    return ""


def derive_content_themes(video_items: list[dict], channel_desc: str, niche: str) -> str:
    if not video_items:
        return " | ".join(NICHE_THEMES.get(niche, ["General Content"])[:3])

    corpus = " ".join(
        [v.get("title", "") for v in video_items]
        + [v.get("description", "")[:500] for v in video_items]
        + [channel_desc or ""]
    ).lower()

    matched = []
    for theme_label, keywords in THEME_MAP:
        if any(kw in corpus for kw in keywords):
            matched.append(theme_label)
        if len(matched) == 3:
            break

    if not matched:
        matched = NICHE_THEMES.get(niche, ["General Content"])[:3]
    return " | ".join(matched[:3])


OUTPUT_FIELDS = [
    "influencer_name", "platform", "profile_url",
    "subscriber_count", "engagement_rate_pct", "niche", "content_themes",
    "contact_email", "email_source",
    "instagram_url", "website", "custom_url",
    "audience_geography", "audience_age", "audience_gender",
    "channel_id", "view_count", "video_count", "country",
    "description", "thumbnail_url", "published_at",
    "recent_video_titles", "enriched_at",
]


def enrich_channel(ch: dict, branding: dict, video_items: list[dict]) -> dict:
    subs        = int(ch.get("subscribers", 0))
    view_count  = int(ch.get("view_count", 0))
    video_count = int(ch.get("video_count", 0))
    ch_desc     = ch.get("description", "")
    niche       = ch.get("niche", "")
    api_email   = branding.get("api_email", "")
    custom_url  = branding.get("custom_url", "")
    country     = branding.get("country", "") or ch.get("country", "")

    video_descs = "\n".join(v.get("description", "") for v in video_items)
    ext_urls = find_external_urls([ch_desc, video_descs])
    ext_page_texts = [fetch_page_text(u) for u in ext_urls if fetch_page_text(u)]
    scan_texts = [ch_desc, video_descs] + ext_page_texts

    email, email_src = extract_email(scan_texts, api_email)
    instagram        = extract_instagram(scan_texts)
    website          = extract_website([ch_desc, video_descs])
    themes           = derive_content_themes(video_items, ch_desc, niche)
    eng              = float(ch.get("engagement_rate_pct", 0.0))

    return {
        "influencer_name":     ch.get("name", ""),
        "platform":            "YouTube",
        "profile_url":         ch.get("profile_url", ""),
        "subscriber_count":    subs,
        "engagement_rate_pct": eng,
        "niche":               niche,
        "content_themes":      themes,
        "contact_email":       email,
        "email_source":        email_src,
        "instagram_url":       instagram,
        "website":             website,
        "custom_url":          f"https://youtube.com/{custom_url}" if custom_url else "",
        "audience_geography":  country if country else "Not Available",
        "audience_age":        "Not Available",
        "audience_gender":     "Not Available",
        "channel_id":          ch.get("channel_id", ""),
        "view_count":          view_count,
        "video_count":         video_count,
        "country":             country,
        "description":         ch_desc,
        "thumbnail_url":       ch.get("thumbnail_url", ""),
        "published_at":        ch.get("published_at", ""),
        "recent_video_titles": " || ".join(v.get("title", "") for v in video_items),
        "enriched_at":         datetime.now(timezone.utc).isoformat(),
    }


def save_csv(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log.info("CSV saved -> %s  (%d rows)", path, len(records))


def save_json(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log.info("JSON saved -> %s  (%d records)", path, len(records))


def run_enrich() -> list[dict]:
    log.info("=== Stage 3: Profile Enrichment ===")

    if not os.path.exists(SHORTLISTED_CSV):
        log.error("Shortlisted CSV not found at %s!", SHORTLISTED_CSV)
        return []

    with open(SHORTLISTED_CSV, encoding="utf-8") as f:
        channels = list(csv.DictReader(f))
    log.info("Loaded %d shortlisted channels", len(channels))

    channel_ids = [ch["channel_id"] for ch in channels]

    branding_map = batch_branding(channel_ids)
    videos_map = {}
    for idx, ch in enumerate(channels, 1):
        cid = ch["channel_id"]
        videos_map[cid] = get_recent_video_details(cid)
        time.sleep(0.2)

    enriched = []
    # Load existing enriched data to preserve emails and themes if quota is exceeded
    existing_lookup = {}
    if os.path.exists(ENRICHED_PROFILES_CSV):
        try:
            with open(ENRICHED_PROFILES_CSV, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing_lookup[row["channel_id"]] = row
        except Exception:
            pass

    for ch in channels:
        cid = ch["channel_id"]
        vids = videos_map.get(cid, [])
        if not vids and cid in existing_lookup:
            # Preserve existing enriched profile data
            old = existing_lookup[cid]
            profile = {
                "influencer_name":     ch.get("name", ""),
                "platform":            "YouTube",
                "profile_url":         ch.get("profile_url", ""),
                "subscriber_count":    int(ch.get("subscribers", 0)),
                "engagement_rate_pct": float(ch.get("engagement_rate_pct", 0.0)),
                "niche":               ch.get("niche", ""),
                "content_themes":      old.get("content_themes") or derive_content_themes([], "", ch.get("niche", "")),
                "contact_email":       old.get("contact_email", "Not Found"),
                "email_source":        old.get("email_source", ""),
                "instagram_url":       old.get("instagram_url", ""),
                "website":             old.get("website", ""),
                "custom_url":          old.get("custom_url", ""),
                "audience_geography":  old.get("audience_geography", "IN"),
                "audience_age":        "Not Available",
                "audience_gender":     "Not Available",
                "channel_id":          cid,
                "view_count":          int(ch.get("view_count", 0)),
                "video_count":         int(ch.get("video_count", 0)),
                "country":             ch.get("country", "IN"),
                "description":         ch.get("description", ""),
                "thumbnail_url":       ch.get("thumbnail_url", ""),
                "published_at":        ch.get("published_at", ""),
                "recent_video_titles": old.get("recent_video_titles", ""),
                "enriched_at":         datetime.now(timezone.utc).isoformat(),
            }
        else:
            profile = enrich_channel(ch, branding_map.get(cid, {}), vids)
        enriched.append(profile)

    save_csv(enriched, ENRICHED_PROFILES_CSV)
    save_json(enriched, ENRICHED_PROFILES_JSON)

    with_email = [e for e in enriched if e["contact_email"] != "Not Found"]
    print("\n" + "=" * 80)
    print(f"Profile Enrichment Complete: {len(enriched)} profiles | Emails found: {len(with_email)}")
    print(f"CSV  -> {ENRICHED_PROFILES_CSV}")
    print(f"JSON -> {ENRICHED_PROFILES_JSON}\n")

    return enriched

if __name__ == "__main__":
    run_enrich()
