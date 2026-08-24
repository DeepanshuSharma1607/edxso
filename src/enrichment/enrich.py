"""
enrich.py — Stage 3: Profile Enrichment
=========================================
For every shortlisted creator, collect the SPEC-mandated fields: contact
email, Instagram/website links, and content themes.

Sources scanned, in priority order
-----------------------------------
1. Full channel description (from Stage 1 `channels.list` snippet)
2. Recent video descriptions        (playlistItems -> videos, ~2 units/channel)
3. The public channel /about page    (HTML scrape — where the "links" section
   and business-email button actually live now that the Data API hides them)
4. Link-in-bio pages (linktr.ee, beacons.ai, ...) referenced by the above

Quota
-----
The previous version fetched recent videos with `search.list` at 100 units per
channel (78 channels = 7,800 units — nearly the whole 10k/day budget, which is
what silently starved and blanked the dataset). This version resolves recent
videos from the uploads playlist: `playlistItems.list` (1 unit) + `videos.list`
(1 unit) = ~2 units per channel, ~160 units for the whole shortlist.

Honesty
-------
Nothing is fabricated. An email is only recorded if it is literally present in
one of the scanned sources. When absent it is marked "Not Found"; audience
age/gender need the OAuth Analytics API and are marked "Not Available".
Every write is merge-safe: a re-run can add a newly found value but can never
overwrite an existing real value with a blank (the bug that zeroed the old run).
"""

import argparse
import csv
import html as html_lib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote
import requests

from src.utils.config import (
    SHORTLISTED_CSV,
    ENRICHED_PROFILES_CSV,
    ENRICHED_PROFILES_JSON,
)
from src.utils.youtube import (
    get_recent_videos,
    load_video_cache,
    save_video_cache,
)

MAX_RECENT_VIDEOS = 8
EXTERNAL_PAGE_TIMEOUT = 8
ABOUT_TIMEOUT = 12

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

SCANNABLE_DOMAINS = {
    "linktr.ee", "beacons.ai", "beacons.nz", "carrd.co", "bio.link",
    "instabio.cc", "linkinbio", "about.me", "campsite.bio", "hoo.be",
    "later.com", "taplink.cc", "koji.to", "milkshake.app", "linkin.bio",
}
SOCIAL_SKIP_DOMAINS = {
    "youtube.com", "youtu.be", "instagram.com", "twitter.com", "x.com",
    "facebook.com", "t.co", "fb.com", "tiktok.com", "snapchat.com",
    "linkedin.com", "pinterest.com", "reddit.com", "discord.com",
    "discord.gg", "telegram.me", "t.me", "whatsapp.com", "wa.me",
    "threads.net", "amzn.to", "amazon.in", "amazon.com", "flipkart.com",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

EMAIL_RE = re.compile(
    r"[a-zA-Z0-9](?:[a-zA-Z0-9._%+\-]{0,62}[a-zA-Z0-9])?@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)
# Obfuscated forms like "name (at) gmail (dot) com" / "name [at] gmail dot com".
# The separators MUST be bracketed or whitespace-delimited: an unanchored "at"
# happily matches inside ordinary words, turning "www.whatsapp.com" into
# "www.wh@sapp.com" and "indianathletics.in" into "indian@hletics.in".
EMAIL_OBFUSCATED_RE = re.compile(
    r"([a-zA-Z0-9._%+\-]{2,})"
    r"\s*(?:\(\s*at\s*\)|\[\s*at\s*\]|\s+at\s+|\s*\{\s*at\s*\})\s*"
    r"([a-zA-Z0-9\-]+(?:\s*(?:\(\s*dot\s*\)|\[\s*dot\s*\]|\s+dot\s+|\.)\s*[a-zA-Z0-9\-]+)*?)"
    r"\s*(?:\(\s*dot\s*\)|\[\s*dot\s*\]|\s+dot\s+|\.)\s*"
    r"(com|in|net|org|co|io|me|info|biz|app|dev)\b",
    re.IGNORECASE,
)
INSTAGRAM_URL_RE = re.compile(
    r"instagram\.com/(?!p/|reel/|reels/|tv/|explore/|stories/)([A-Za-z0-9_.]{2,30})",
    re.IGNORECASE,
)
# Only an explicit label followed by an @handle. Requiring the "@" is what
# stops "ins-IG-ht" and "conf-IG-urable" being read as Instagram handles.
INSTAGRAM_HANDLE_RE = re.compile(
    r"\b(?:instagram|insta|ig)\b\s*(?:[:\-=>]|is|at)?\s*@([A-Za-z0-9_.]{2,30})",
    re.IGNORECASE,
)
URL_RE = re.compile(r"https?://[^\s<>\"'\\)]+", re.IGNORECASE)
# YouTube wraps outbound links as /redirect?...&q=<urlencoded target>
YT_REDIRECT_RE = re.compile(r"[?&]q=(https?%3A%2F%2F[^\"&\\]+)", re.IGNORECASE)

BAD_EMAIL_TOKENS = {
    "example", "test@", "noreply", "no-reply", "sample", "yourname",
    "domain.com", "email.com", "sentry.io", "wixpress", "godaddy",
    "@2x", ".png", ".jpg", ".gif", ".svg", "@youtube", "u00", "schema.org",
    "whatsapp", "wh@sapp", "@gstatic", "googleusercontent", "ggpht",
}
# Platform/CDN hosts that are never a creator's own website.
BAD_WEBSITE_HOSTS = {
    "gstatic.com", "googleusercontent.com", "ggpht.com", "google.com",
    "googleapis.com", "schema.org", "w3.org", "googletagmanager.com",
    "doubleclick.net", "gvt1.com", "ytimg.com",
}
# Asset extensions — a link to a .json/.png is not a creator website.
BAD_WEBSITE_SUFFIXES = (
    ".json", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".css", ".js",
    ".ico", ".woff", ".woff2", ".xml", ".webp",
)
IG_STOPWORDS = {
    "instagram", "official", "reel", "reels", "explore", "accounts",
    "about", "com", "www", "http", "https", "share", "profile",
    "ht", "urable", "nificant", "ure", "ital", "ation", "in", "on",
}

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


# --------------------------------------------------------------------------- #
# Page fetching                                                                #
# --------------------------------------------------------------------------- #
def fetch_about_page(channel_id: str, custom_url: str = "") -> str:
    """Fetch the channel /about HTML. Returns unescaped text ready for regex."""
    urls = [f"https://www.youtube.com/channel/{channel_id}/about"]
    if custom_url:
        handle = custom_url.strip().lstrip("/")
        urls.append(f"https://www.youtube.com/{handle}/about")
    for url in urls:
        try:
            r = requests.get(url, headers=HTTP_HEADERS, timeout=ABOUT_TIMEOUT)
            if r.status_code == 200 and len(r.text) > 1000:
                # The links live inside embedded JSON with \n \/ \u escapes.
                # Decode them so a naive regex does not capture a leading "n"
                # (the bug that produced e.g. "ntechinnovation@gmail.com").
                text = r.text
                text = text.replace("\\/", "/").replace("\\n", " ").replace("\\r", " ")
                text = text.replace('\\"', '"').replace("\\u0026", "&")
                text = html_lib.unescape(text)
                return text
        except Exception:
            continue
    return ""


def fetch_page_text(url: str) -> str:
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=EXTERNAL_PAGE_TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            text = r.text.replace("\\/", "/").replace("\\n", " ")
            text = html_lib.unescape(text)
            text = re.sub(r"<[^>]+>", " ", text)
            return re.sub(r"\s+", " ", text)[:60_000]
    except Exception:
        pass
    return ""


# --------------------------------------------------------------------------- #
# Extraction                                                                  #
# --------------------------------------------------------------------------- #
def _domain(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def is_scannable_link(url: str) -> bool:
    d = _domain(url)
    if not d:
        return False
    if any(s in d for s in SCANNABLE_DOMAINS):
        return True
    if any(s in d for s in SOCIAL_SKIP_DOMAINS):
        return False
    return True


def is_creator_website(url: str) -> bool:
    """A real creator site — not a CDN asset, tracker, or platform URL."""
    d = _domain(url)
    if not d or "." not in d:
        return False
    if any(bad in d for bad in BAD_WEBSITE_HOSTS):
        return False
    if any(bad in d for bad in SOCIAL_SKIP_DOMAINS):
        return False
    path = urlparse(url).path.lower()
    if path.endswith(BAD_WEBSITE_SUFFIXES):
        return False
    return True


def extract_redirect_targets(html: str) -> list[str]:
    """Pull outbound links out of YouTube's /redirect?q=... wrappers."""
    out, seen = [], set()
    for m in YT_REDIRECT_RE.finditer(html):
        url = unquote(m.group(1)).rstrip(".,;)\\\"'")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


# Words that get glued to the front of an address when a creator writes
# "For business inquiries-me@gmail.com" with no space.
GLUED_PREFIXES = (
    "inquiries-", "inquiries", "inquiry-", "enquiries-", "enquiry-",
    "contact-", "contact", "email-", "email", "mail-", "id-", "mailto:",
    "at-", "business-",
)


def clean_email(candidate: str) -> str:
    e = candidate.strip().strip(".,;:()[]<>\"'").lower()
    if e.count("@") != 1:
        return ""
    if any(bad in e for bad in BAD_EMAIL_TOKENS):
        return ""

    local, _, dom = e.partition("@")
    # Strip label text glued to the local part without a separating space.
    for pref in GLUED_PREFIXES:
        if local.startswith(pref) and len(local) > len(pref) + 2:
            local = local[len(pref):].lstrip("-._:")
            break
    if local.startswith("www."):
        return ""
    if not local or "." not in dom:
        return ""
    if dom.split(".")[-1] not in {
        "com", "in", "co", "net", "org", "io", "me", "info", "biz", "app", "dev", "email",
    }:
        return ""
    return f"{local}@{dom}"


def extract_email(texts: list[tuple[str, str]]) -> tuple[str, str]:
    """texts: list of (source_label, content). Returns (email, source)."""
    for label, text in texts:
        if not text:
            continue
        for raw in EMAIL_RE.findall(text):
            e = clean_email(raw)
            if e:
                return e, label
    # Obfuscated fall-back ("name (at) gmail (dot) com")
    for label, text in texts:
        if not text:
            continue
        for m in EMAIL_OBFUSCATED_RE.finditer(text):
            domain_part = re.sub(r"\s*(?:\(\s*dot\s*\)|\[\s*dot\s*\]|\s+dot\s+)\s*", ".", m.group(2))
            domain_part = re.sub(r"\s+", "", domain_part)
            e = clean_email(f"{m.group(1)}@{domain_part}.{m.group(3)}")
            if e:
                return e, f"{label} (obfuscated)"
    return "Not Found", ""


def _valid_ig_handle(handle: str) -> bool:
    h = handle.strip().strip("/.").lower()
    if len(h) < 3 or h in IG_STOPWORDS:
        return False
    if h.startswith(".") or h.endswith("."):
        return False
    # A handle made only of letters shorter than 4 chars is almost always a
    # fragment cut out of an ordinary word rather than a real account.
    if len(h) < 4 and h.isalpha():
        return False
    return True


def extract_instagram(texts: list[tuple[str, str]]) -> str:
    for _, text in texts:
        if not text:
            continue
        for m in INSTAGRAM_URL_RE.finditer(text):
            h = m.group(1).strip().strip("/")
            if _valid_ig_handle(h):
                return f"https://instagram.com/{h}"
    # "insta: @handle" style mentions, only if no URL was present
    for _, text in texts:
        if not text:
            continue
        for m in INSTAGRAM_HANDLE_RE.finditer(text):
            h = m.group(1).strip()
            if _valid_ig_handle(h):
                return f"https://instagram.com/{h}"
    return ""


def extract_website(texts: list[tuple[str, str]], redirect_urls: list[str]) -> str:
    """Prefer an explicitly-linked site from the about page over anything
    merely mentioned in text, and never return a CDN/platform asset URL."""
    for url in redirect_urls:
        if is_creator_website(url):
            return url.rstrip(".,;)")
    for _, text in texts:
        if not text:
            continue
        for m in URL_RE.finditer(text):
            url = m.group(0).rstrip(".,;)")
            if is_creator_website(url):
                return url
    return ""


def derive_content_themes(video_items: list[dict], channel_desc: str, niche: str) -> str:
    corpus = " ".join(
        [v.get("title", "") for v in video_items]
        + [(v.get("description", "") or "")[:400] for v in video_items]
        + [channel_desc or ""]
    ).lower()
    matched = []
    for label, keywords in THEME_MAP:
        if any(kw in corpus for kw in keywords):
            matched.append(label)
        if len(matched) == 3:
            break
    if not matched:
        matched = NICHE_THEMES.get(niche, ["General Content"])[:3]
    return " | ".join(matched[:3])


OUTPUT_FIELDS = [
    "influencer_name", "platform", "profile_url",
    "subscriber_count", "engagement_rate_pct", "avg_recent_views",
    "avg_likes", "avg_comments", "niche", "content_themes",
    "contact_email", "email_source",
    "instagram_url", "website", "custom_url",
    "audience_geography", "audience_age", "audience_gender",
    "channel_id", "view_count", "video_count", "country",
    "description", "thumbnail_url", "published_at",
    "recent_video_titles", "enriched_at",
]


def enrich_channel(ch: dict, video_cache: dict | None = None) -> dict:
    cid = ch.get("channel_id", "")
    subs = int(float(ch.get("subscribers", 0) or 0))
    view_count = int(float(ch.get("view_count", 0) or 0))
    video_count = int(float(ch.get("video_count", 0) or 0))
    ch_desc = ch.get("description", "") or ""
    niche = ch.get("niche", "")
    custom_url = ch.get("custom_url", "") or ""
    country = ch.get("country", "") or ""
    uploads = ch.get("uploads_playlist_id", "") or ""

    # Shared cache: Stage 2 already fetched these, so this is normally free.
    videos = get_recent_videos(cid, uploads, video_cache, MAX_RECENT_VIDEOS)
    video_descs = "\n".join(v.get("description", "") for v in videos)
    keywords = ch.get("channel_keywords", "") or ""

    about_html = fetch_about_page(cid, custom_url)
    redirect_urls = extract_redirect_targets(about_html)
    about_text = re.sub(r"<[^>]+>", " ", about_html)

    # Follow at most 2 link-in-bio pages for extra contact detail
    bio_texts = []
    for url in redirect_urls:
        if any(s in _domain(url) for s in SCANNABLE_DOMAINS):
            t = fetch_page_text(url)
            if t:
                bio_texts.append(("link-in-bio page", t))
        if len(bio_texts) >= 2:
            break

    email_sources = [
        ("channel description", ch_desc),
        ("channel keywords", keywords),
        ("recent video descriptions", video_descs),
        ("channel about page", about_text),
        *bio_texts,
    ]
    ig_sources = [("about page redirects", " ".join(redirect_urls))] + email_sources

    email, email_src = extract_email(email_sources)
    instagram = extract_instagram(ig_sources)
    website = extract_website(email_sources, redirect_urls)
    themes = derive_content_themes(videos, ch_desc, niche)

    return {
        "influencer_name":     ch.get("name", ""),
        "platform":            "YouTube",
        "profile_url":         ch.get("profile_url", ""),
        "subscriber_count":    subs,
        "engagement_rate_pct": float(ch.get("engagement_rate_pct", 0.0) or 0.0),
        "niche":               niche,
        "content_themes":      themes,
        "avg_recent_views":    int(float(ch.get("avg_recent_views", 0) or 0)),
        "avg_likes":           int(float(ch.get("avg_likes", 0) or 0)),
        "avg_comments":        int(float(ch.get("avg_comments", 0) or 0)),
        "contact_email":       email,
        "email_source":        email_src,
        "instagram_url":       instagram,
        "website":             website,
        "custom_url":          f"https://youtube.com/{custom_url}" if custom_url else "",
        "audience_geography":  country if country else "Not Available",
        "audience_age":        "Not Available",
        "audience_gender":     "Not Available",
        "channel_id":          cid,
        "view_count":          view_count,
        "video_count":         video_count,
        "country":             country,
        "description":         ch_desc,
        "thumbnail_url":       ch.get("thumbnail_url", ""),
        "published_at":        ch.get("published_at", ""),
        "recent_video_titles": " || ".join(v.get("title", "") for v in videos),
        "enriched_at":         datetime.now(timezone.utc).isoformat(),
    }


# --------------------------------------------------------------------------- #
# Merge-safe persistence                                                       #
# --------------------------------------------------------------------------- #
_REAL_VALUE_FIELDS = [
    "contact_email", "email_source", "instagram_url", "website",
    "recent_video_titles", "content_themes",
]
_EMPTY_VALUES = {"", "Not Found", "Not Available", "None", "nan"}


def _is_empty(v) -> bool:
    return v is None or str(v).strip() in _EMPTY_VALUES


def merge_profile(new: dict, old: dict | None) -> dict:
    """Never let a fresh blank overwrite a previously discovered real value."""
    if not old:
        return new
    for field in _REAL_VALUE_FIELDS:
        if _is_empty(new.get(field)) and not _is_empty(old.get(field)):
            new[field] = old[field]
    return new


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

    existing = {}
    if os.path.exists(ENRICHED_PROFILES_CSV):
        try:
            with open(ENRICHED_PROFILES_CSV, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    existing[row.get("channel_id", "")] = row
        except Exception:
            pass

    enriched = []
    video_cache = load_video_cache()
    log.info("Video cache holds %d channels (Stage 2 pre-warms this)", len(video_cache))

    for i, ch in enumerate(channels, 1):
        cid = ch.get("channel_id", "")
        name = str(ch.get("name", ""))[:32].encode("ascii", "ignore").decode()
        profile = enrich_channel(ch, video_cache)
        profile = merge_profile(profile, existing.get(cid))
        email_flag = "email" if profile["contact_email"] != "Not Found" else "  -  "
        ig_flag = "IG" if profile["instagram_url"] else "--"
        log.info("[%2d/%2d] %-32s %s %s", i, len(channels), name, email_flag, ig_flag)
        enriched.append(profile)
        time.sleep(0.15)

    save_video_cache(video_cache)
    save_csv(enriched, ENRICHED_PROFILES_CSV)
    save_json(enriched, ENRICHED_PROFILES_JSON)

    n_email = sum(1 for e in enriched if e["contact_email"] != "Not Found")
    n_ig = sum(1 for e in enriched if e["instagram_url"])
    n_web = sum(1 for e in enriched if e["website"])
    total = len(enriched)
    print("\n" + "=" * 70)
    print("Profile Enrichment Complete")
    print(f"  Profiles       : {total}")
    print(f"  Contact emails : {n_email}/{total}  ({100*n_email//total if total else 0}%)")
    print(f"  Instagram IDs  : {n_ig}/{total}  ({100*n_ig//total if total else 0}%)")
    print(f"  Websites       : {n_web}/{total}")
    print(f"  CSV  -> {ENRICHED_PROFILES_CSV}")
    print(f"  JSON -> {ENRICHED_PROFILES_JSON}")
    print("=" * 70 + "\n")

    return enriched


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 3: Profile Enrichment")
    ap.parse_args()
    run_enrich()
