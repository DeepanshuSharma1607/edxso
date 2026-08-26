"""
filter.py — Stage 2: Filtering & Classification
================================================
Reads data/raw_channels.csv, scores every channel against SPEC criteria,
and writes pass/fail results.
"""

import csv
import json
import logging
import os
from datetime import datetime, timezone

from ass_1.src.utils.config import (
    RAW_CHANNELS_CSV,
    FILTERED_CHANNELS_CSV,
    SHORTLISTED_CSV,
    SHORTLISTED_JSON,
)

PASS_THRESHOLD        = 40
MIN_ENGAGEMENT_RATE   = 1.0

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


def engagement_score(subscribers: int, view_count: int, video_count: int) -> tuple[float, float, float, bool]:
    """
    Engagement is approximated as (lifetime views / video count) relative to
    current subscribers, since only channel-level lifetime stats are available
    at this stage (no per-recent-video breakdown without extra YouTube Data
    API calls). For old or formerly-viral channels this raw ratio can exceed
    100% even though it's not a meaningful "engagement rate" in that regime —
    it just means the channel's average views per video are large relative to
    its current subscriber count, not that current content gets 100+ engagement.

    We keep the raw ratio for transparency but cap the value used for scoring
    and display at 100%, and flag when a value was capped so this can be
    disclosed in the README as a known approximation.
    """
    if video_count == 0 or subscribers == 0:
        return 0.0, 0.0, 0.0, False
    views_per_video = view_count / video_count
    raw_rate_pct = (views_per_video / subscribers) * 100
    capped = raw_rate_pct > 100.0
    rate_pct = min(raw_rate_pct, 100.0)
    score = min(40, (rate_pct / 5.0) * 40)
    return round(score, 2), round(rate_pct, 2), round(raw_rate_pct, 2), capped


def geography_score(country: str) -> tuple[float, str]:
    if country == "IN":
        return 20.0, "India (IN)"
    elif country == "":
        return 8.0, "Unknown (partial credit)"
    else:
        return 0.0, f"Non-India ({country})"


def niche_fit_score(niche: str, description: str, name: str) -> tuple[float, int]:
    keywords = NICHE_KEYWORDS.get(niche, [])
    if not keywords:
        return 10.0, 0
    text = (name + " " + description).lower()
    hits = sum(1 for kw in keywords if kw in text)
    score = min(20, (hits / max(1, len(keywords))) * 20 * 2)
    return round(score, 2), hits


def maturity_score(published_at: str) -> tuple[float, str]:
    if not published_at:
        return 5.0, "Unknown age"
    try:
        pub = published_at.replace("Z", "+00:00")
        dt = datetime.fromisoformat(pub)
        age_days = (datetime.now(timezone.utc) - dt).days
        if age_days >= 365:
            return 10.0, f"{age_days // 365}y {(age_days % 365) // 30}m old"
        elif age_days >= 180:
            return 5.0, f"{age_days // 30}m old (< 1 year)"
        else:
            return 0.0, f"{age_days}d old (too new)"
    except Exception:
        return 5.0, "Date parse error"


def subscriber_range_score(subscribers: int) -> float:
    if 10_000 <= subscribers <= 80_000:
        return 10.0
    return 5.0


def classify(channel: dict) -> dict:
    subs        = int(channel.get("subscribers", 0))
    view_count  = int(channel.get("view_count", 0))
    video_count = int(channel.get("video_count", 0))
    niche       = channel.get("niche", "")
    country     = channel.get("country", "")
    description = channel.get("description", "")
    name        = channel.get("name", "")
    published   = channel.get("published_at", "")

    eng_score, eng_rate, eng_rate_raw, eng_capped = engagement_score(subs, view_count, video_count)
    geo_score, geo_label = geography_score(country)
    fit_score, kw_hits   = niche_fit_score(niche, description, name)
    mat_score, mat_label = maturity_score(published)
    sub_score            = subscriber_range_score(subs)

    total = eng_score + geo_score + fit_score + mat_score + sub_score

    fail_reasons = []
    if total < PASS_THRESHOLD:
        fail_reasons.append(f"score {total:.1f} < threshold {PASS_THRESHOLD}")
    if eng_rate < MIN_ENGAGEMENT_RATE:
        fail_reasons.append(f"engagement {eng_rate:.2f}% < {MIN_ENGAGEMENT_RATE}%")

    status = "PASS" if not fail_reasons else "FAIL"
    reason = "All criteria met" if status == "PASS" else "; ".join(fail_reasons)

    return {
        **channel,
        "engagement_rate_pct": eng_rate,
        "engagement_rate_raw_pct": eng_rate_raw,
        "engagement_capped":   eng_capped,
        "score_engagement":    eng_score,
        "score_geography":     geo_score,
        "score_niche_fit":     fit_score,
        "score_maturity":      mat_score,
        "score_subscriber":    sub_score,
        "total_score":         round(total, 2),
        "geography_label":     geo_label,
        "maturity_label":      mat_label,
        "niche_keyword_hits":  kw_hits,
        "status":              status,
        "filter_reason":       reason,
    }


ALL_FIELDS = [
    "channel_id", "name", "niche", "subscribers", "view_count", "video_count",
    "engagement_rate_pct", "engagement_rate_raw_pct", "engagement_capped",
    "profile_url", "country", "geography_label",
    "published_at", "maturity_label",
    "score_engagement", "score_geography", "score_niche_fit",
    "score_maturity", "score_subscriber", "total_score",
    "niche_keyword_hits", "status", "filter_reason",
    "description", "thumbnail_url", "query_used", "fetched_at",
]

SHORT_FIELDS = [
    "channel_id", "name", "niche", "subscribers", "view_count", "video_count",
    "engagement_rate_pct", "engagement_rate_raw_pct", "engagement_capped",
    "total_score", "profile_url", "country",
    "geography_label", "maturity_label", "description",
    "thumbnail_url", "published_at", "fetched_at",
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
    slim = [{k: r[k] for k in fields if k in r} for r in records]
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
    log.info("Loaded %d channels from %s", len(raw), RAW_CHANNELS_CSV)

    classified = [classify(ch) for ch in raw]
    classified.sort(key=lambda x: x["total_score"], reverse=True)

    passed = [ch for ch in classified if ch["status"] == "PASS"]
    failed = [ch for ch in classified if ch["status"] == "FAIL"]

    log.info("PASS: %d  |  FAIL: %d", len(passed), len(failed))

    save_csv(classified, FILTERED_CHANNELS_CSV, ALL_FIELDS)
    if passed:
        save_csv(passed, SHORTLISTED_CSV, SHORT_FIELDS)
        save_json(passed, SHORTLISTED_JSON, SHORT_FIELDS)

    print("\n" + "=" * 80)
    print(f"{'Name':<35} {'Niche':<12} {'Subs':>8} {'Eng%':>6} {'Score':>6} {'Status':<6}")
    print("-" * 80)
    for ch in classified[:10]:
        safe_name = ch["name"].encode("ascii", "ignore").decode("ascii")
        status_label = "PASS" if ch["status"] == "PASS" else "fail"
        print(
            f"{safe_name[:34]:<35} {ch['niche']:<12} "
            f"{int(ch['subscribers']):>8,} {ch['engagement_rate_pct']:>5.1f}% "
            f"{ch['total_score']:>5.1f}  {status_label}"
        )
    print("=" * 80)

    print(f"\nTotal shortlisted (PASS): {len(passed)} / {len(classified)}")
    print(f"Filtered CSV  -> {FILTERED_CHANNELS_CSV}")
    print(f"Shortlisted   -> {SHORTLISTED_CSV}\n")

    return passed

if __name__ == "__main__":
    run_filter()
