"""
export_dataset.py — build the SPEC section 7-B "Influencer Dataset" deliverable.

SPEC 7-B asks for a single dataset carrying nine specific fields:

    Name, Platform, Followers, Engagement, Niche, Email, Profile URL,
    Content Theme, Status

No single pipeline stage produces all nine: Stage 3 (`enriched_profiles`) has
the profile and contact fields but no pass/fail verdict, while Stage 2
(`filtered_channels`) holds the verdict and Stage 5 (`outreach_tracker`) holds
the outreach status. This module joins them on `channel_id` into one flat file
so the deliverable matches the brief exactly.

It performs no API calls — it only re-shapes files the pipeline already wrote,
so it is safe to re-run at any time.

    python main.py --stage export
"""

import csv
import json
import logging
import os

from ass_1.src.utils.config import (
    DATA_DIR,
    FILTERED_CHANNELS_CSV,
    ENRICHED_PROFILES_JSON,
    OUTREACH_TRACKER_CSV,
)

DATASET_CSV = os.path.join(DATA_DIR, "influencer_dataset.csv")

log = logging.getLogger(__name__)

# Column order deliberately mirrors SPEC 7-B, then adds the supporting
# evidence columns a reviewer needs to trust the first nine.
DATASET_FIELDS = [
    "name", "platform", "followers", "engagement_rate_pct", "niche",
    "email", "profile_url", "content_theme", "status",
    # supporting evidence
    "email_source", "instagram_url", "brand_fit_score", "filter_reason",
    "outreach_status", "message_generated", "channel_id",
]


def _load_csv_by_channel(path: str) -> dict[str, dict]:
    if not os.path.exists(path):
        log.warning("Missing %s — related columns will be blank.", path)
        return {}
    with open(path, encoding="utf-8") as f:
        return {r["channel_id"]: r for r in csv.DictReader(f) if r.get("channel_id")}


def export_dataset() -> list[dict]:
    log.info("=== Export: SPEC 7-B influencer dataset ===")

    if not os.path.exists(ENRICHED_PROFILES_JSON):
        log.error("Enriched profiles not found at %s.", ENRICHED_PROFILES_JSON)
        return []

    with open(ENRICHED_PROFILES_JSON, encoding="utf-8") as f:
        enriched = json.load(f)

    filtered = _load_csv_by_channel(FILTERED_CHANNELS_CSV)
    tracker = _load_csv_by_channel(OUTREACH_TRACKER_CSV)

    rows = []
    for e in enriched:
        cid = e.get("channel_id", "")
        frow = filtered.get(cid, {})
        trow = tracker.get(cid, {})
        rows.append({
            "name": e.get("influencer_name", ""),
            "platform": e.get("platform", "YouTube"),
            "followers": e.get("subscriber_count", ""),
            "engagement_rate_pct": e.get("engagement_rate_pct", ""),
            "niche": e.get("niche", ""),
            # "Not Found" is preserved verbatim, never blanked or guessed
            # (SPEC sections 3 and 10).
            "email": e.get("contact_email") or "Not Found",
            "profile_url": e.get("profile_url", ""),
            "content_theme": e.get("content_themes", ""),
            "status": frow.get("status", "PASS"),
            "email_source": e.get("email_source", ""),
            "instagram_url": e.get("instagram_url", ""),
            "brand_fit_score": frow.get("total_score", ""),
            "filter_reason": frow.get("filter_reason", ""),
            "outreach_status": trow.get("email_status", ""),
            "message_generated": trow.get("message_generated", ""),
            "channel_id": cid,
        })

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DATASET_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DATASET_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    with_email = sum(1 for r in rows if r["email"] != "Not Found")
    print("\n" + "=" * 70)
    print("SPEC 7-B Influencer Dataset exported")
    print(f"  Influencers            : {len(rows)} (brief asks for 50+)")
    print(f"  With verified email    : {with_email}")
    print(f"  Marked 'Not Found'     : {len(rows) - with_email}")
    print(f"  Columns                : {len(DATASET_FIELDS)} "
          f"(9 required by SPEC 7-B + 7 supporting)")
    print(f"  CSV -> {DATASET_CSV}")
    print("=" * 70 + "\n")

    return rows


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s",
                        datefmt="%H:%M:%S")
    export_dataset()
