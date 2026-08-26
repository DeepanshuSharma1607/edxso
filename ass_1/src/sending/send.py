"""
send.py — Stage 5: Sending Layer & Outreach Tracker
===================================================
Selects creators with a verified contact email, dispatches (or simulates) the
personalized pitch, records the outcome, and prevents duplicate outreach.

Modes
-----
    --mode simulate   (default) no network send; every eligible creator is
                      logged with a deterministic simulated delivery receipt
    --mode live       real SMTP send using SMTP_* credentials from .env

Instagram DMs
-------------
Meta provides no compliant API for unsolicited creator DMs, and automating the
web interface violates the Instagram Terms of Use. Per SPEC section 5 we do not
bypass that: the generated DM text is exported ready to send, and the tracker
records it as QUEUED_FOR_MANUAL_SEND together with the target profile URL.
`data/instagram_dm_queue.csv` is the hand-off file an operator works from.

Duplicate prevention
--------------------
The tracker is the source of truth and is upserted by channel_id, so it holds
exactly one row per influencer no matter how many times this runs. A creator
already marked SENT or SIMULATED_SUCCESS is not contacted again; the attempt is
recorded as DUPLICATE_PREVENTED. (An earlier version appended a row per attempt
and had grown to 390 rows for 78 influencers.)
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import smtplib
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ass_1.src.utils.config import (
    DATA_DIR,
    PERSONALIZED_JSON,
    OUTREACH_TRACKER_CSV,
    OUTREACH_TRACKER_JSON,
)

SMTP_SERVER  = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT    = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER    = os.environ.get("SMTP_USER", "")
SMTP_PASS    = os.environ.get("SMTP_PASS", "")
SENDER_NAME  = os.environ.get("SENDER_NAME", "EDXSO Partnerships Team")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "partnerships@edxso.com")

DM_QUEUE_CSV = os.path.join(DATA_DIR, "instagram_dm_queue.csv")

# Statuses that mean "this creator has already been contacted".
ALREADY_CONTACTED = {"SENT", "SIMULATED_SUCCESS"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TRACKER_FIELDS = [
    "outreach_id", "channel_id", "influencer_name", "platform", "niche",
    "subscriber_count", "engagement_rate_pct", "contact_email", "instagram_url",
    "collaboration_angle", "email_subject", "email_pitch", "email_word_count",
    "instagram_dm", "message_generated",
    "email_status", "dm_status", "sent_timestamp", "delivery_mode",
    "delivery_receipt", "attempt_count", "error_message",
]

DM_QUEUE_FIELDS = [
    "influencer_name", "instagram_url", "profile_url", "niche",
    "subscriber_count", "instagram_dm", "dm_word_count", "dm_status", "queued_at",
]


def outreach_id_for(channel_id: str) -> str:
    """Stable ID per influencer, so re-runs don't churn the tracker."""
    return "outreach_" + hashlib.sha1(channel_id.encode()).hexdigest()[:10]


def simulated_receipt(channel_id: str, email: str) -> str:
    """Deterministic fake delivery receipt, clearly marked as simulated."""
    digest = hashlib.sha1(f"{channel_id}:{email}".encode()).hexdigest()[:12].upper()
    return f"SIM-250-OK-{digest}"


def load_existing_tracker() -> dict[str, dict]:
    if not os.path.exists(OUTREACH_TRACKER_CSV):
        return {}
    try:
        with open(OUTREACH_TRACKER_CSV, encoding="utf-8") as f:
            return {
                row["channel_id"]: row
                for row in csv.DictReader(f)
                if row.get("channel_id")
            }
    except Exception as e:
        log.warning("Could not read existing tracker: %s", e)
        return {}


def save_tracker(records: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTREACH_TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    with open(OUTREACH_TRACKER_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log.info("Outreach tracker -> %d rows (one per influencer)", len(records))


def save_dm_queue(rows: list[dict]) -> None:
    if not rows:
        return
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DM_QUEUE_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DM_QUEUE_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    log.info("Instagram DM queue -> %s (%d rows)", DM_QUEUE_CSV, len(rows))


def build_email_body(item: dict) -> str:
    """Assemble the full email. The LLM writes only the body paragraph; the
    greeting and signature are deterministic so every send is well-formed."""
    name = item.get("influencer_name", "there")
    pitch = item.get("email_pitch", "")
    return (
        f"Hi {name},\n\n"
        f"{pitch}\n\n"
        f"Best regards,\n"
        f"{SENDER_NAME}\n"
        f"{SENDER_EMAIL}"
    )


def send_live_email(to_email: str, subject: str, body: str) -> tuple[bool, str, str]:
    if not SMTP_USER or not SMTP_PASS:
        return False, "", "SMTP_USER/SMTP_PASS not configured in .env"
    try:
        msg = MIMEMultipart()
        msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True, f"SMTP-250-{SMTP_SERVER}", ""
    except Exception as e:
        return False, "", str(e)


def process_outreach(mode: str = "simulate") -> list[dict]:
    log.info("=== Stage 5: Sending Layer & Outreach Tracker ===")
    log.info("Execution mode: %s", mode.upper())

    if not os.path.exists(PERSONALIZED_JSON):
        log.error("Personalized messages not found at %s!", PERSONALIZED_JSON)
        return []

    with open(PERSONALIZED_JSON, encoding="utf-8") as f:
        messages = json.load(f)

    history = load_existing_tracker()
    current_ids = {m.get("channel_id", "") for m in messages}

    # Rows in the old tracker whose channel is no longer in the shortlist are
    # from a superseded run (e.g. the filtering rubric changed and dropped
    # them). They must not silently pad the tracker: it would then claim more
    # influencers than the dataset actually contains. History is still consulted
    # for duplicate prevention, but only current creators are written out.
    orphans = [cid for cid in history if cid not in current_ids]
    if orphans:
        log.warning(
            "Dropping %d tracker row(s) from a superseded dataset "
            "(channel no longer shortlisted).", len(orphans)
        )

    tracker = {cid: row for cid, row in history.items() if cid in current_ids}
    stats = {
        "sent": 0, "simulated": 0, "failed": 0,
        "no_email": 0, "duplicate": 0, "no_message": 0,
        "dm_queued": 0, "dm_no_handle": 0,
    }
    dm_queue: list[dict] = []
    now = datetime.now(timezone.utc).isoformat()

    for item in messages:
        cid = item.get("channel_id", "")
        email = (item.get("contact_email") or "Not Found").strip()
        ig_url = (item.get("instagram_url") or "").strip()
        subject = item.get("email_subject", "")
        pitch = item.get("email_pitch", "")
        dm = item.get("instagram_dm", "")
        has_email = bool(email) and email != "Not Found"
        has_message = bool(pitch.strip())

        prior = tracker.get(cid)
        attempt_count = int(float(prior.get("attempt_count", 0) or 0)) + 1 if prior else 1
        already_done = bool(prior) and prior.get("email_status") in ALREADY_CONTACTED

        receipt = ""
        err = ""

        if already_done:
            # Preserve the original send record; log the prevented re-attempt.
            stats["duplicate"] += 1
            email_status = "DUPLICATE_PREVENTED"
            receipt = prior.get("delivery_receipt", "")
            err = (
                f"Already contacted on {prior.get('sent_timestamp', 'unknown date')} "
                f"(status {prior.get('email_status')}); re-send suppressed."
            )
            sent_ts = prior.get("sent_timestamp", now)
        elif not has_message:
            stats["no_message"] += 1
            email_status = "SKIPPED_NO_MESSAGE"
            err = "No personalized message was generated for this creator."
            sent_ts = now
        elif not has_email:
            stats["no_email"] += 1
            email_status = "SKIPPED_NO_EMAIL"
            err = "No contact email could be verified from public sources."
            sent_ts = now
        elif mode == "live":
            ok, receipt, err = send_live_email(email, subject, build_email_body(item))
            if ok:
                stats["sent"] += 1
                email_status = "SENT"
            else:
                stats["failed"] += 1
                email_status = "FAILED"
            sent_ts = now
            time.sleep(1.0)  # be polite to the SMTP server
        else:
            stats["simulated"] += 1
            email_status = "SIMULATED_SUCCESS"
            receipt = simulated_receipt(cid, email)
            sent_ts = now

        # Instagram DM: generated and queued, never auto-sent (see docstring).
        if ig_url and dm.strip():
            dm_status = "QUEUED_FOR_MANUAL_SEND"
            stats["dm_queued"] += 1
            dm_queue.append({
                "influencer_name": item.get("influencer_name", ""),
                "instagram_url": ig_url,
                "profile_url": item.get("profile_url", ""),
                "niche": item.get("niche", ""),
                "subscriber_count": item.get("subscriber_count", ""),
                "instagram_dm": dm,
                "dm_word_count": item.get("dm_word_count", ""),
                "dm_status": dm_status,
                "queued_at": now,
            })
        elif not ig_url:
            dm_status = "NO_INSTAGRAM_HANDLE"
            stats["dm_no_handle"] += 1
        else:
            dm_status = "NO_DM_GENERATED"

        tracker[cid] = {
            "outreach_id": outreach_id_for(cid),
            "channel_id": cid,
            "influencer_name": item.get("influencer_name", ""),
            "platform": item.get("platform", "YouTube"),
            "niche": item.get("niche", ""),
            "subscriber_count": item.get("subscriber_count", ""),
            "engagement_rate_pct": item.get("engagement_rate_pct", ""),
            "contact_email": email,
            "instagram_url": ig_url,
            "collaboration_angle": item.get("collaboration_angle", ""),
            "email_subject": subject,
            "email_pitch": pitch,
            "email_word_count": item.get("email_word_count", ""),
            "instagram_dm": dm,
            "message_generated": "YES" if has_message else "NO",
            "email_status": email_status,
            "dm_status": dm_status,
            "sent_timestamp": sent_ts,
            "delivery_mode": mode.upper(),
            "delivery_receipt": receipt,
            "attempt_count": attempt_count,
            "error_message": err,
        }

    records = list(tracker.values())
    save_tracker(records)
    save_dm_queue(dm_queue)

    total = len(messages)
    print("\n" + "=" * 70)
    print(f"Stage 5 Sending Layer Summary  (mode: {mode.upper()})")
    print(f"  Influencers processed      : {total}")
    print(f"  Emails sent (live)         : {stats['sent']}")
    print(f"  Emails simulated           : {stats['simulated']}")
    print(f"  Send failures              : {stats['failed']}")
    print(f"  Skipped - no email found   : {stats['no_email']}")
    print(f"  Skipped - no message       : {stats['no_message']}")
    print(f"  Duplicates prevented       : {stats['duplicate']}")
    print(f"  Instagram DMs queued       : {stats['dm_queued']}")
    print(f"  No Instagram handle        : {stats['dm_no_handle']}")
    if orphans:
        print(f"  Stale rows dropped         : {len(orphans)} (superseded dataset)")
    print(f"  Tracker rows (1/influencer): {len(records)}")
    print(f"  Tracker  -> {OUTREACH_TRACKER_CSV}")
    if dm_queue:
        print(f"  DM queue -> {DM_QUEUE_CSV}")
    print("=" * 70 + "\n")

    return records


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 5: Sending Layer")
    ap.add_argument("--mode", choices=["simulate", "live"], default="simulate")
    args = ap.parse_args()
    process_outreach(mode=args.mode)
