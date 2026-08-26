"""
youtube.py — Shared YouTube Data API v3 access layer
=====================================================
One place for quota accounting, retries, channel hydration and recent-video
retrieval, so Stages 1-3 cannot drift apart or double-spend quota.

Quota costs (YouTube Data API v3, 10,000 units/day default)
-----------------------------------------------------------
    search.list         100 units per call   <- avoid in per-channel loops
    channels.list         1 unit  per call   (up to 50 IDs)
    playlistItems.list    1 unit  per call
    videos.list           1 unit  per call   (up to 50 IDs)

Recent videos are therefore resolved as
    channel -> contentDetails.relatedPlaylists.uploads -> playlistItems -> videos
at ~2 units per channel, instead of 100 units per channel via search.list.

Recent videos are cached on disk (data/.video_cache.json) and shared between
the filtering and enrichment stages, so a full pipeline run fetches each
channel's videos exactly once.
"""

import json
import logging
import os
import time

import requests

from ass_1.src.utils.config import DATA_DIR, YOUTUBE_API_KEY

BASE_URL = "https://www.googleapis.com/youtube/v3"
VIDEO_CACHE_FILE = os.path.join(DATA_DIR, ".video_cache.json")
CHANNELS_BATCH_SIZE = 50
DEFAULT_RECENT_VIDEOS = 8

log = logging.getLogger(__name__)

# Running total of quota units spent in this process, for transparent logging.
_quota_spent = 0
_QUOTA_COST = {"search": 100, "channels": 1, "playlistItems": 1, "videos": 1}


class QuotaExceeded(RuntimeError):
    """The YouTube Data API reported the daily quota is exhausted."""


def quota_spent() -> int:
    return _quota_spent


def reset_quota_counter() -> None:
    global _quota_spent
    _quota_spent = 0


def api_get(endpoint: str, params: dict, timeout: int = 20, retries: int = 2) -> dict:
    """GET a Data API endpoint with quota accounting and transient retry."""
    global _quota_spent
    params = {**params, "key": YOUTUBE_API_KEY}
    last_err = None

    for attempt in range(retries + 1):
        try:
            resp = requests.get(f"{BASE_URL}/{endpoint}", params=params, timeout=timeout)
            _quota_spent += _QUOTA_COST.get(endpoint, 1)

            if resp.status_code == 403 and "quotaExceeded" in resp.text:
                raise QuotaExceeded(
                    f"Daily quota exhausted (spent ~{_quota_spent} units this run)"
                )
            if resp.status_code == 404:
                return {}
            if resp.status_code in (500, 503) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except QuotaExceeded:
            raise
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(1.0 * (attempt + 1))
                continue
    log.warning("%s request failed after retries: %s", endpoint, last_err)
    return {}


# --------------------------------------------------------------------------- #
# Channel hydration                                                            #
# --------------------------------------------------------------------------- #
def fetch_channel_details(channel_ids: list[str]) -> dict[str, dict]:
    """Hydrate channel IDs into full metadata dicts (1 unit per 50 IDs).

    Note: `snippet.description` here is the FULL channel description. The
    equivalent field on search.list results is truncated to ~100 chars and
    must never be used as a contact-detail source.
    """
    details: dict[str, dict] = {}
    unique = list(dict.fromkeys(cid for cid in channel_ids if cid))

    for i in range(0, len(unique), CHANNELS_BATCH_SIZE):
        batch = unique[i : i + CHANNELS_BATCH_SIZE]
        data = api_get(
            "channels",
            {
                "part": "snippet,statistics,contentDetails,brandingSettings",
                "id": ",".join(batch),
            },
        )
        for item in data.get("items", []):
            cid = item["id"]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            branding = item.get("brandingSettings", {}).get("channel", {})
            thumbs = snippet.get("thumbnails", {})
            hidden = stats.get("hiddenSubscriberCount", False)

            details[cid] = {
                "channel_id": cid,
                "name": snippet.get("title", ""),
                "description": snippet.get("description", "") or "",
                "custom_url": snippet.get("customUrl", "") or "",
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
                "uploads_playlist_id": (
                    item.get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads", "")
                ),
                "channel_keywords": branding.get("keywords", "") or "",
            }
        time.sleep(0.25)

    return details


# --------------------------------------------------------------------------- #
# Recent videos (cached, shared across stages)                                 #
# --------------------------------------------------------------------------- #
def load_video_cache() -> dict:
    if not os.path.exists(VIDEO_CACHE_FILE):
        return {}
    try:
        with open(VIDEO_CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_video_cache(cache: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(VIDEO_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        log.warning("Could not write video cache: %s", e)


def fetch_recent_videos(
    uploads_playlist_id: str,
    max_results: int = DEFAULT_RECENT_VIDEOS,
) -> list[dict]:
    """Recent uploads with snippet + statistics. ~2 quota units."""
    if not uploads_playlist_id:
        return []

    pl = api_get(
        "playlistItems",
        {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": max_results,
        },
    )
    video_ids = [
        it["contentDetails"]["videoId"]
        for it in pl.get("items", [])
        if it.get("contentDetails", {}).get("videoId")
    ]
    if not video_ids:
        return []

    vids = api_get("videos", {"part": "snippet,statistics", "id": ",".join(video_ids)})
    out = []
    for it in vids.get("items", []):
        sn = it.get("snippet", {})
        st = it.get("statistics", {})
        out.append(
            {
                "video_id": it.get("id", ""),
                "title": sn.get("title", ""),
                "description": sn.get("description", "") or "",
                "published_at": sn.get("publishedAt", ""),
                "views": int(st.get("viewCount", 0) or 0),
                "likes": int(st.get("likeCount", 0) or 0),
                "comments": int(st.get("commentCount", 0) or 0),
            }
        )
    return out


def get_recent_videos(
    channel_id: str,
    uploads_playlist_id: str,
    cache: dict | None = None,
    max_results: int = DEFAULT_RECENT_VIDEOS,
) -> list[dict]:
    """Cache-aware recent-video lookup. Pass the same `cache` dict across a
    stage (and persist it) so filtering and enrichment share one fetch."""
    if cache is not None and channel_id in cache:
        return cache[channel_id]
    videos = fetch_recent_videos(uploads_playlist_id, max_results)
    if cache is not None and videos:
        cache[channel_id] = videos
    return videos


# --------------------------------------------------------------------------- #
# Engagement metrics                                                           #
# --------------------------------------------------------------------------- #
def compute_engagement(videos: list[dict], subscribers: int) -> dict:
    """Real engagement metrics from recent-video statistics.

    engagement_rate_pct = mean over recent videos of
                          (likes + comments) / views * 100

    This is the standard public-data engagement proxy: YouTube removed public
    dislike counts, so likes + comments over views is the strongest signal
    available without OAuth channel-owner access. Videos with 0 views are
    skipped rather than counted as 0% so a brand-new upload cannot drag the
    average down.

    Also returns avg_recent_views and view_to_sub_ratio_pct (reach relative to
    audience size) as a separate, clearly-named metric — this is what the
    earlier implementation was mislabelling as "engagement rate", where
    lifetime-views maths produced impossible values above 100%.
    """
    usable = [v for v in videos if v.get("views", 0) > 0]
    if not usable:
        return {
            "engagement_rate_pct": 0.0,
            "avg_recent_views": 0,
            "avg_likes": 0,
            "avg_comments": 0,
            "view_to_sub_ratio_pct": 0.0,
            "videos_sampled": 0,
        }

    rates = [
        (v["likes"] + v["comments"]) / v["views"] * 100
        for v in usable
    ]
    avg_views = sum(v["views"] for v in usable) / len(usable)
    return {
        "engagement_rate_pct": round(sum(rates) / len(rates), 2),
        "avg_recent_views": int(avg_views),
        "avg_likes": int(sum(v["likes"] for v in usable) / len(usable)),
        "avg_comments": int(sum(v["comments"] for v in usable) / len(usable)),
        "view_to_sub_ratio_pct": round(avg_views / subscribers * 100, 2) if subscribers else 0.0,
        "videos_sampled": len(usable),
    }
