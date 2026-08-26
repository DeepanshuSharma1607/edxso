"""
discover.py — Stage 1: Influencer Discovery
=============================================
Searches YouTube Data API v3 across 5 niches for micro-influencers
(5,000 - 100,000 subscribers).

Two modes:
  run_discovery()                -> full search + channel hydration
  run_discovery(refresh_only=1)  -> re-hydrate the channel IDs already in
                                    data/raw_channels.csv without spending
                                    any search quota

Quota note
----------
`search.list` costs 100 units per call; `channels.list` costs 1 unit per call
(up to 50 IDs each). So a full discovery run is ~1,500 units while a refresh
of an existing 80-channel dataset is 2 units. Refresh mode exists so the
dataset can be repaired cheaply when the daily 10,000-unit quota is tight.

Description integrity
---------------------
`search.list` only returns a ~100-character *truncated* description snippet.
Creator contact details (business email, Instagram) live in the *full*
channel description, so we deliberately discard the search snippet and take
`snippet.description` from `channels.list`, which is untruncated. Getting
this wrong silently caps Stage 3's email hit rate at ~0%.
"""

import argparse
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
CHANNELS_BATCH_SIZE = 50

NICHES = {
    "Technology": [
        "tech reviews india",
        "tech tips hindi youtube",
        "gadget unboxing india hindi",
    ],
    "Fitness": [
        "fitness india youtube",
        "home workout hindi channel",
        "gym trainer india hindi",
    ],
    "Beauty": [
        "skincare india youtube",
        "makeup tutorials india hindi",
        "beauty tips hindi channel",
    ],
    "Gaming": [
        "gaming india youtube channel",
        "mobile gaming hindi",
        "bgmi gameplay india",
    ],
    "Finance": [
        "personal finance india youtube",
        "stock market hindi channel",
        "mutual fund investing hindi",
    ],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


class QuotaExceeded(RuntimeError):
    """Raised when the YouTube API reports the daily quota is exhausted."""


def _check_quota(resp: requests.Response) -> None:
    if resp.status_code == 403 and "quotaExceeded" in resp.text:
        raise QuotaExceeded("YouTube Data API daily quota exhausted")


def search_channel_ids(query: str, max_results: int = MAX_RESULTS_PER_QUERY) -> list[str]:
    """Return channel IDs for a query. Snippets are ignored on purpose — see
    the module docstring; `channels.list` supplies the untruncated data."""
    collected: list[str] = []
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
        _check_quota(resp)
        resp.raise_for_status()
        data = resp.json()

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            cid = item.get("id", {}).get("channelId")
            if cid:
                collected.append(cid)

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.3)

    return collected


def fetch_channel_details(channel_ids: list[str]) -> dict[str, dict]:
    """Hydrate channel IDs with full snippet + statistics + uploads playlist.

    `contentDetails.relatedPlaylists.uploads` is captured here so Stage 3 can
    list recent videos via playlistItems (1 unit) instead of search (100 units).
    """
    details: dict[str, dict] = {}
    unique_ids = list(dict.fromkeys(channel_ids))

    for i in range(0, len(unique_ids), CHANNELS_BATCH_SIZE):
        batch = unique_ids[i : i + CHANNELS_BATCH_SIZE]
        params = {
            "part": "snippet,statistics,contentDetails,brandingSettings",
            "id": ",".join(batch),
            "key": YOUTUBE_API_KEY,
        }
        resp = requests.get(f"{BASE_URL}/channels", params=params, timeout=20)
        _check_quota(resp)
        resp.raise_for_status()

        for item in resp.json().get("items", []):
            cid = item["id"]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            branding = item.get("brandingSettings", {}).get("channel", {})
            uploads = (
                item.get("contentDetails", {})
                .get("relatedPlaylists", {})
                .get("uploads", "")
            )
            thumbs = snippet.get("thumbnails", {})

            hidden = stats.get("hiddenSubscriberCount", False)
            details[cid] = {
                "channel_id": cid,
                "name": snippet.get("title", ""),
                # Untruncated description — the primary source of contact info.
                "description": snippet.get("description", "") or "",
                "custom_url": snippet.get("customUrl", ""),
                "country": snippet.get("country", "") or "",
                "published_at": snippet.get("publishedAt", ""),
                "thumbnail_url": (
                    thumbs.get("high", {}).get("url")
                    or thumbs.get("medium", {}).get("url")
                    or thumbs.get("default", {}).get("url", "")
                ),
                "subscribers": None if hidden else int(stats.get("subscriberCount", 0)),
                "view_count": int(stats.get("viewCount", 0)),
                "video_count": int(stats.get("videoCount", 0)),
                "uploads_playlist_id": uploads,
                "channel_keywords": branding.get("keywords", "") or "",
            }
        time.sleep(0.3)

    return details


def is_micro_influencer(channel: dict) -> bool:
    subs = channel.get("subscribers")
    if subs is None:
        return False
    return MIN_SUBSCRIBERS <= subs <= MAX_SUBSCRIBERS


CSV_FIELDS = [
    "channel_id", "name", "niche", "query_used",
    "subscribers", "view_count", "video_count",
    "profile_url", "custom_url", "country", "published_at",
    "description", "channel_keywords", "uploads_playlist_id",
    "thumbnail_url", "fetched_at",
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
    slim = [{k: r.get(k, "") for k in CSV_FIELDS} for r in records]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
    log.info("JSON saved -> %s  (%d records)", path, len(slim))


def load_existing() -> list[dict]:
    if not os.path.exists(RAW_CHANNELS_CSV):
        return []
    try:
        with open(RAW_CHANNELS_CSV, encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _build_record(cid: str, det: dict, niche: str, query: str) -> dict:
    return {
        **det,
        "niche": niche,
        "query_used": query,
        "profile_url": f"https://www.youtube.com/channel/{cid}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def run_discovery(refresh_only: bool = False) -> list[dict]:
    log.info("=== Stage 1: Influencer Discovery ===")

    existing = load_existing()
    existing_by_id = {r["channel_id"]: r for r in existing if r.get("channel_id")}

    if refresh_only:
        if not existing_by_id:
            log.error("--refresh needs an existing %s to re-hydrate.", RAW_CHANNELS_CSV)
            return []
        log.info(
            "Refresh mode: re-hydrating %d known channels (no search quota spent)",
            len(existing_by_id),
        )
        id_to_niche = {
            cid: (r.get("niche", ""), r.get("query_used", ""))
            for cid, r in existing_by_id.items()
        }
        details = fetch_channel_details(list(existing_by_id))
    else:
        log.info(
            "Target: %d-%d subscribers, %d+ channels",
            MIN_SUBSCRIBERS, MAX_SUBSCRIBERS, TARGET_TOTAL,
        )
        id_to_niche: dict[str, tuple[str, str]] = {}
        # Preserve anything already discovered so a partial/quota-limited run
        # can only ever add to the dataset, never shrink it.
        for cid, row in existing_by_id.items():
            id_to_niche[cid] = (row.get("niche", ""), row.get("query_used", ""))

        for niche, queries in NICHES.items():
            for query in queries:
                log.info("[%s] Searching: '%s'", niche, query)
                try:
                    ids = search_channel_ids(query)
                    new = [c for c in ids if c not in id_to_niche]
                    for cid in ids:
                        id_to_niche.setdefault(cid, (niche, query))
                    log.info("  -> %d returned (%d new)", len(ids), len(new))
                except QuotaExceeded:
                    log.error("  Quota exhausted — stopping search, keeping what we have.")
                    break
                except requests.HTTPError as e:
                    log.error("  Search failed for '%s': %s", query, e)
                time.sleep(0.4)
            else:
                continue
            break

        if not id_to_niche:
            log.warning("No channels available (quota or network). Nothing written.")
            return existing

        log.info("Hydrating %d unique channel IDs via channels.list...", len(id_to_niche))
        try:
            details = fetch_channel_details(list(id_to_niche))
        except QuotaExceeded:
            log.error("Quota exhausted during hydration. Preserving existing dataset.")
            return existing

    records = []
    for cid, det in details.items():
        niche, query = id_to_niche.get(cid, ("", ""))
        records.append(_build_record(cid, det, niche, query))

    micro = [ch for ch in records if is_micro_influencer(ch)]
    log.info(
        "Hydrated %d channels; %d in micro range (%s-%s subs)",
        len(records), len(micro), f"{MIN_SUBSCRIBERS:,}", f"{MAX_SUBSCRIBERS:,}",
    )

    # Guardrail: never let a degraded run replace a healthier dataset.
    if len(micro) < len(existing_by_id) * 0.8 and existing_by_id:
        log.warning(
            "New result (%d) is much smaller than existing (%d) — merging instead of replacing.",
            len(micro), len(existing_by_id),
        )
        merged = {r["channel_id"]: r for r in existing if r.get("channel_id")}
        for r in micro:
            merged[r["channel_id"]] = r
        micro = list(merged.values())

    if not micro:
        log.error("Nothing to save — leaving %s untouched.", RAW_CHANNELS_CSV)
        return existing

    micro.sort(key=lambda x: int(x.get("subscribers") or 0), reverse=True)
    save_csv(micro, RAW_CHANNELS_CSV)
    save_json(micro, RAW_CHANNELS_JSON)

    with_desc = sum(1 for c in micro if len((c.get("description") or "").strip()) > 100)
    print("\n" + "=" * 74)
    print(f"{'Name':<35} {'Niche':<12} {'Subscribers':>11} {'Desc':>8}")
    print("-" * 74)
    for ch in micro[:15]:
        safe = str(ch["name"]).encode("ascii", "ignore").decode("ascii")
        print(
            f"{safe[:34]:<35} {str(ch['niche']):<12} "
            f"{int(ch.get('subscribers') or 0):>11,} "
            f"{len(ch.get('description') or ''):>8}"
        )
    print("=" * 74)
    print(f"\nTotal micro-influencers: {len(micro)}")
    print(f"With substantial description (>100 chars): {with_desc}/{len(micro)}")
    print(f"CSV  -> {RAW_CHANNELS_CSV}")
    print(f"JSON -> {RAW_CHANNELS_JSON}\n")

    return micro


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 1: Influencer Discovery")
    ap.add_argument(
        "--refresh",
        action="store_true",
        help="Re-hydrate existing channel IDs only (2 quota units, no search)",
    )
    args = ap.parse_args()
    run_discovery(refresh_only=args.refresh)
