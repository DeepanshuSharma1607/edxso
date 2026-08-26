"""
discover.py — Stage 1: Influencer Discovery
=============================================
Searches YouTube Data API v3 across 5 niches for micro-influencers
(5,000 – 100,000 subscribers).
"""

import csv
import json
import logging
import os
import time
from datetime import datetime, timezone
import requests

from ass_1.src.utils.config import (
    YOUTUBE_API_KEY,
    RAW_CHANNELS_CSV,
    RAW_CHANNELS_JSON,
    MIN_SUBSCRIBERS,
    MAX_SUBSCRIBERS,
    TARGET_TOTAL,
)

BASE_URL = "https://www.googleapis.com/youtube/v3"
MAX_RESULTS_PER_QUERY = 50

NICHES = {
    "Technology": ["tech reviews india", "tech tips hindi youtube"],
    "Fitness":    ["fitness india youtube", "home workout hindi channel"],
    "Beauty":     ["skincare india youtube", "makeup tutorials india hindi"],
    "Gaming":     ["gaming india youtube channel", "mobile gaming hindi"],
    "Finance":    ["personal finance india youtube", "stock market hindi channel"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def search_channels(query: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list[dict]:
    collected = []
    page_token = None

    while len(collected) < max_results:
        params = {
            "part": "snippet",
            "q": query,
            "type": "channel",
            "maxResults": min(50, max_results - len(collected)),
            "key": YOUTUBE_API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        resp = requests.get(f"{BASE_URL}/search", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            channel_id = item.get("id", {}).get("channelId")
            snippet = item.get("snippet", {})
            if channel_id:
                collected.append({
                    "channel_id": channel_id,
                    "name": snippet.get("title", ""),
                    "description": snippet.get("description", ""),
                    "thumbnail_url": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
                })

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.3)

    return collected


def enrich_with_statistics(channels: list[dict]) -> list[dict]:
    enriched = []
    seen = {}
    for ch in channels:
        cid = ch["channel_id"]
        if cid not in seen:
            seen[cid] = ch

    unique_channels = list(seen.values())
    unique_ids = [ch["channel_id"] for ch in unique_channels]

    for i in range(0, len(unique_ids), 50):
        batch_ids = unique_ids[i : i + 50]
        params = {
            "part": "snippet,statistics",
            "id": ",".join(batch_ids),
            "key": YOUTUBE_API_KEY,
        }
        resp = requests.get(f"{BASE_URL}/channels", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        stats_lookup = {}
        for item in data.get("items", []):
            cid = item["id"]
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            stats_lookup[cid] = {
                "subscribers": int(stats.get("subscriberCount", 0))
                if not stats.get("hiddenSubscriberCount", False)
                else None,
                "view_count": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "country": snippet.get("country", ""),
                "published_at": snippet.get("publishedAt", ""),
            }

        for ch in unique_channels:
            if ch["channel_id"] in stats_lookup:
                ch.update(stats_lookup[ch["channel_id"]])

        time.sleep(0.3)

    for ch in unique_channels:
        if ch.get("subscribers") is not None:
            enriched.append(ch)

    return enriched


def is_micro_influencer(channel: dict) -> bool:
    subs = channel.get("subscribers")
    if subs is None:
        return False
    return MIN_SUBSCRIBERS <= subs <= MAX_SUBSCRIBERS


CSV_FIELDS = [
    "channel_id", "name", "niche", "query_used",
    "subscribers", "view_count", "video_count",
    "profile_url", "country", "published_at",
    "description", "thumbnail_url", "fetched_at",
]

def save_csv(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log.info("CSV saved -> %s  (%d rows)", path, len(records))

def save_json(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log.info("JSON saved -> %s  (%d records)", path, len(records))


def run_discovery() -> list[dict]:
    log.info("=== Stage 1: Influencer Discovery ===")
    log.info("Target: %d-%d subscribers, %d+ channels", MIN_SUBSCRIBERS, MAX_SUBSCRIBERS, TARGET_TOTAL)

    all_raw: list[dict] = []

    for niche, queries in NICHES.items():
        for query in queries:
            log.info("[%s] Searching: '%s'", niche, query)
            try:
                results = search_channels(query)
                for r in results:
                    r["niche"] = niche
                    r["query_used"] = query
                    r["profile_url"] = f"https://www.youtube.com/channel/{r['channel_id']}"
                    r["fetched_at"] = datetime.now(timezone.utc).isoformat()
                log.info("  -> %d channels returned", len(results))
                all_raw.extend(results)
            except requests.HTTPError as e:
                log.error("  Search failed for '%s': %s", query, e)
            time.sleep(0.5)

    log.info("Total raw (before dedup + enrich): %d channels", len(all_raw))

    if not all_raw:
        log.warning("No channels fetched from API (Quota limit or network issue).")
        if os.path.exists(RAW_CHANNELS_CSV):
            log.info("Preserving existing dataset in %s", RAW_CHANNELS_CSV)
            with open(RAW_CHANNELS_CSV, "r", encoding="utf-8") as f:
                return list(csv.DictReader(f))
        return []

    log.info("Enriching with /channels statistics (2nd API call)...")
    try:
        enriched = enrich_with_statistics(all_raw)
    except requests.HTTPError as e:
        log.error("Enrichment failed: %s", e)
        return []

    micro = [ch for ch in enriched if is_micro_influencer(ch)]
    log.info("Micro-influencers (5k-100k subs): %d channels", len(micro))

    if micro:
        save_csv(micro, RAW_CHANNELS_CSV)
        save_json(micro, RAW_CHANNELS_JSON)

    print("\n" + "=" * 70)
    print(f"{'Name':<35} {'Niche':<12} {'Subscribers':>11}")
    print("-" * 70)
    for ch in sorted(micro, key=lambda x: x.get("subscribers", 0), reverse=True):
        safe_name = ch['name'].encode('ascii', 'ignore').decode('ascii')
        print(f"{safe_name[:34]:<35} {ch['niche']:<12} {ch.get('subscribers', 0):>11,}")
    print("=" * 70)
    print(f"\nTotal micro-influencers discovered: {len(micro)}")
    print(f"CSV  -> {RAW_CHANNELS_CSV}")
    print(f"JSON -> {RAW_CHANNELS_JSON}\n")

    return micro

if __name__ == "__main__":
    run_discovery()
