"""
filter.py — Stage 2: Filtering & Classification
================================================
Scores every discovered channel against the SPEC criteria and records an
explicit PASS/FAIL with a human-readable reason.

Scoring model (100 points)
--------------------------
    Engagement rate      40 pts   real (likes+comments)/views on recent uploads
    Geography / market    20 pts   India-targeted campaign -> IN scores highest
    Niche fit             20 pts   keyword match across name + description
    Channel maturity      10 pts   account age (proxy for reliability)
    Subscriber sweet spot 10 pts   10k-80k is the strongest micro band

Pass criteria (all must hold)
-----------------------------
    1. engagement_rate_pct >= 1.0   genuine audience interaction floor
    2. total_score         >= 55    overall brand-fit bar
    3. niche_keyword_hits  >= 1     demonstrable content relevance

Engagement rate — what changed and why
--------------------------------------
An earlier version approximated engagement as
(lifetime views / video count) / subscribers. That is a *reach* ratio, not an
engagement rate, and for older or formerly-viral channels it returned
impossible values — 19 of 78 channels pinned at the 100% cap, and one read
22,336%. It also made the filter useless: everything passed.

This version reads the actual statistics of each channel's recent uploads and
computes (likes + comments) / views, the standard public-data engagement
proxy. Results are now in the expected 0.01%-15% band with a ~3% median. The
old reach ratio is still reported as `view_to_sub_ratio_pct` under an honest
name, because it is genuinely useful for judging reach — it just was never an
engagement rate.
"""

import csv
import json
import logging
import os
from datetime import datetime, timezone

from src.utils.config import (
    RAW_CHANNELS_CSV,
    FILTERED_CHANNELS_CSV,
    SHORTLISTED_CSV,
    SHORTLISTED_JSON,
)
from src.utils.youtube import (
    QuotaExceeded,
    compute_engagement,
    get_recent_videos,
    load_video_cache,
    quota_spent,
    save_video_cache,
)

PASS_THRESHOLD      = 55
MIN_ENGAGEMENT_RATE = 1.0
MIN_KEYWORD_HITS    = 1

# Engagement rate that earns full marks. 5% is a strong figure for a
# micro-influencer; above it the score saturates rather than rewarding outliers.
ENGAGEMENT_FULL_MARKS_PCT = 5.0

# The campaign brief targets the Indian market, so geography is a brand-fit
# signal rather than a quality signal. Non-India channels are not "bad" — they
# score lower because they fit this specific campaign less well.
TARGET_COUNTRY = "IN"
NEARBY_MARKETS = {"PK", "BD", "LK", "NP", "AE"}

NICHE_KEYWORDS = {
    "Technology": ["tech", "review", "gadget", "mobile", "laptop", "computer", "tutorial", "tips", "unboxing"],
    "Fitness":    ["fitness", "workout", "gym", "yoga", "exercise", "health", "weight", "muscle", "cardio"],
    "Beauty":     ["makeup", "skincare", "beauty", "cosmetic", "skin", "hair", "tutorial", "glow", "routine"],
    "Gaming":     ["gaming", "game", "pubg", "freefire", "bgmi", "esport", "gameplay", "stream", "play"],
    "Finance":    ["finance", "stock", "invest", "market", "money", "trading", "mutual", "sip", "wealth", "budget"],
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


def engagement_score(engagement_rate_pct: float) -> float:
    """0-40 points, saturating at ENGAGEMENT_FULL_MARKS_PCT."""
    if engagement_rate_pct <= 0:
        return 0.0
    ratio = min(engagement_rate_pct / ENGAGEMENT_FULL_MARKS_PCT, 1.0)
    return round(ratio * 40, 2)


def geography_score(country: str) -> tuple[float, str]:
    c = (country or "").strip().upper()
    if c == TARGET_COUNTRY:
        return 20.0, "India (IN) — target market"
    if c in NEARBY_MARKETS:
        return 10.0, f"Nearby market ({c})"
    if c == "":
        return 8.0, "Undisclosed (partial credit)"
    return 4.0, f"Outside target market ({c})"


def niche_fit_score(niche: str, description: str, name: str, keywords: str = "") -> tuple[float, int]:
    kws = NICHE_KEYWORDS.get(niche, [])
    if not kws:
        return 10.0, 0
    text = f"{name} {description} {keywords}".lower()
    hits = sum(1 for kw in kws if kw in text)
    score = min(20.0, (hits / max(1, len(kws))) * 20 * 2)
    return round(score, 2), hits


def maturity_score(published_at: str) -> tuple[float, str]:
    if not published_at:
        return 5.0, "Unknown age"
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days >= 365:
            return 10.0, f"{age_days // 365}y {(age_days % 365) // 30}m old"
        if age_days >= 180:
            return 5.0, f"{age_days // 30}m old (< 1 year)"
        return 0.0, f"{age_days}d old (too new)"
    except Exception:
        return 5.0, "Date parse error"


def subscriber_range_score(subscribers: int) -> tuple[float, str]:
    if 10_000 <= subscribers <= 80_000:
        return 10.0, "Core micro band (10k-80k)"
    if subscribers < 10_000:
        return 5.0, "Nano band (< 10k)"
    return 5.0, "Upper micro band (> 80k)"


def classify(channel: dict, metrics: dict) -> dict:
    subs        = int(float(channel.get("subscribers", 0) or 0))
    niche       = channel.get("niche", "")
    country     = channel.get("country", "")
    description = channel.get("description", "")
    name        = channel.get("name", "")
    keywords    = channel.get("channel_keywords", "")
    published   = channel.get("published_at", "")

    eng_rate = metrics["engagement_rate_pct"]
    eng_score            = engagement_score(eng_rate)
    geo_score, geo_label = geography_score(country)
    fit_score, kw_hits   = niche_fit_score(niche, description, name, keywords)
    mat_score, mat_label = maturity_score(published)
    sub_score, sub_label = subscriber_range_score(subs)

    total = eng_score + geo_score + fit_score + mat_score + sub_score

    fail_reasons = []
    if eng_rate < MIN_ENGAGEMENT_RATE:
        fail_reasons.append(f"engagement {eng_rate:.2f}% < {MIN_ENGAGEMENT_RATE}% floor")
    if total < PASS_THRESHOLD:
        fail_reasons.append(f"brand-fit score {total:.1f} < {PASS_THRESHOLD}")
    if kw_hits < MIN_KEYWORD_HITS:
        fail_reasons.append(f"no '{niche}' keyword match in profile text")
    if metrics["videos_sampled"] == 0:
        fail_reasons.append("no recent-video statistics available to verify engagement")

    status = "PASS" if not fail_reasons else "FAIL"
    reason = (
        f"Engagement {eng_rate:.2f}%, score {total:.1f}/100, {kw_hits} niche keyword hits"
        if status == "PASS"
        else "; ".join(fail_reasons)
    )

    return {
        **channel,
        "engagement_rate_pct":   eng_rate,
        "avg_recent_views":      metrics["avg_recent_views"],
        "avg_likes":             metrics["avg_likes"],
        "avg_comments":          metrics["avg_comments"],
        "view_to_sub_ratio_pct": metrics["view_to_sub_ratio_pct"],
        "videos_sampled":        metrics["videos_sampled"],
        "score_engagement":      eng_score,
        "score_geography":       geo_score,
        "score_niche_fit":       fit_score,
        "score_maturity":        mat_score,
        "score_subscriber":      sub_score,
        "total_score":           round(total, 2),
        "geography_label":       geo_label,
        "maturity_label":        mat_label,
        "subscriber_label":      sub_label,
        "niche_keyword_hits":    kw_hits,
        "status":                status,
        "filter_reason":         reason,
        "classified_at":         datetime.now(timezone.utc).isoformat(),
    }


ALL_FIELDS = [
    "channel_id", "name", "niche", "subscribers", "view_count", "video_count",
    "engagement_rate_pct", "avg_recent_views", "avg_likes", "avg_comments",
    "view_to_sub_ratio_pct", "videos_sampled",
    "profile_url", "custom_url", "country", "geography_label",
    "published_at", "maturity_label", "subscriber_label",
    "score_engagement", "score_geography", "score_niche_fit",
    "score_maturity", "score_subscriber", "total_score",
    "niche_keyword_hits", "status", "filter_reason",
    "description", "channel_keywords", "uploads_playlist_id",
    "thumbnail_url", "query_used", "fetched_at", "classified_at",
]

# Shortlisted rows carry everything Stage 3 needs, so enrichment never has to
# re-query the API for channel-level data.
SHORT_FIELDS = [
    "channel_id", "name", "niche", "subscribers", "view_count", "video_count",
    "engagement_rate_pct", "avg_recent_views", "avg_likes", "avg_comments",
    "view_to_sub_ratio_pct", "videos_sampled",
    "total_score", "profile_url", "custom_url", "country",
    "geography_label", "maturity_label", "description", "channel_keywords",
    "uploads_playlist_id", "thumbnail_url", "published_at", "fetched_at",
]


def save_csv(records: list[dict], path: str, fields: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log.info("Saved CSV -> %s  (%d rows)", path, len(records))


def save_json(records: list[dict], path: str, fields: list[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    slim = [{k: r.get(k, "") for k in fields} for r in records]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(slim, f, ensure_ascii=False, indent=2)
    log.info("Saved JSON -> %s  (%d records)", path, len(slim))


def run_filter() -> list[dict]:
    log.info("=== Stage 2: Filtering & Classification ===")

    if not os.path.exists(RAW_CHANNELS_CSV):
        log.error("Raw channels not found at %s!", RAW_CHANNELS_CSV)
        return []

    with open(RAW_CHANNELS_CSV, encoding="utf-8") as f:
        raw = list(csv.DictReader(f))
    log.info("Loaded %d channels", len(raw))

    cache = load_video_cache()
    cached_before = len(cache)
    log.info("Video cache holds %d channels", cached_before)

    classified = []
    for i, ch in enumerate(raw, 1):
        cid = ch.get("channel_id", "")
        subs = int(float(ch.get("subscribers", 0) or 0))
        try:
            videos = get_recent_videos(cid, ch.get("uploads_playlist_id", ""), cache)
        except QuotaExceeded as e:
            log.error("%s — scoring remaining channels from cache only.", e)
            videos = cache.get(cid, [])
        metrics = compute_engagement(videos, subs)
        classified.append(classify(ch, metrics))
        if i % 20 == 0:
            log.info("  scored %d/%d (quota spent this run: %d units)", i, len(raw), quota_spent())

    save_video_cache(cache)
    log.info(
        "Video cache: %d -> %d channels (%d fetched, %d quota units)",
        cached_before, len(cache), len(cache) - cached_before, quota_spent(),
    )

    classified.sort(key=lambda x: x["total_score"], reverse=True)
    passed = [c for c in classified if c["status"] == "PASS"]
    failed = [c for c in classified if c["status"] == "FAIL"]
    log.info("PASS: %d  |  FAIL: %d", len(passed), len(failed))

    save_csv(classified, FILTERED_CHANNELS_CSV, ALL_FIELDS)
    if passed:
        save_csv(passed, SHORTLISTED_CSV, SHORT_FIELDS)
        save_json(passed, SHORTLISTED_JSON, SHORT_FIELDS)

    print("\n" + "=" * 88)
    print(f"{'Name':<32} {'Niche':<11} {'Subs':>8} {'Eng%':>6} {'AvgViews':>9} {'Score':>6} {'Result':<6}")
    print("-" * 88)
    for ch in classified[:12]:
        safe = str(ch["name"]).encode("ascii", "ignore").decode("ascii")
        print(
            f"{safe[:31]:<32} {str(ch['niche']):<11} "
            f"{int(float(ch['subscribers'])):>8,} {ch['engagement_rate_pct']:>5.2f}% "
            f"{ch['avg_recent_views']:>9,} {ch['total_score']:>5.1f}  {ch['status']}"
        )
    print("-" * 88)
    if failed:
        print("\nRejected channels and why:")
        for ch in failed:
            safe = str(ch["name"]).encode("ascii", "ignore").decode("ascii")
            print(f"  FAIL  {safe[:34]:<36} {ch['filter_reason']}")
    print("=" * 88)
    print(f"\nShortlisted (PASS): {len(passed)} / {len(classified)}")
    print(f"Filtered CSV  -> {FILTERED_CHANNELS_CSV}")
    print(f"Shortlisted   -> {SHORTLISTED_CSV}\n")

    return passed


if __name__ == "__main__":
    run_filter()
