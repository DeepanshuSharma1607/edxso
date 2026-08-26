"""
send.py — Stage 5: Outreach Sending Layer & Duplicate Prevention
================================================================
Handles email dispatch, Instagram DM workflow simulation, and duplicate prevention.
"""

import argparse
import csv
import json
import logging
import os
import smtplib
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ass_1.src.utils.config import (
    PERSONALIZED_JSON,
    OUTREACH_TRACKER_CSV,
    OUTREACH_TRACKER_JSON,
)

SMTP_SERVER   = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT     = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASS     = os.environ.get("SMTP_PASS", "")
SENDER_NAME   = os.environ.get("SENDER_NAME", "EDXSO Partnerships Team")
SENDER_EMAIL  = os.environ.get("SENDER_EMAIL", "partnerships@edxso.com")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TRACKER_FIELDS = [
    "outreach_id", "channel_id", "influencer_name", "platform", "niche",
    "subscriber_count", "contact_email", "instagram_url", "collaboration_angle",
    "email_subject", "email_pitch", "email_word_count", "instagram_dm",
    "email_status", "dm_status", "sent_timestamp", "delivery_mode", "error_message",
]

def load_existing_tracker() -> list[dict]:
    if not os.path.exists(OUTREACH_TRACKER_CSV):
        return []
    try:
        with open(OUTREACH_TRACKER_CSV, "r", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []

def get_contacted_keys(history: list[dict]) -> set[str]:
    contacted = set()
    for row in history:
        cid = row.get("channel_id")
        email = row.get("contact_email")
        if cid:
            contacted.add(cid)
        if email and email != "Not Found":
            contacted.add(email.lower())
    return contacted

def save_tracker(records: list[dict]) -> None:
    os.makedirs(os.path.dirname(OUTREACH_TRACKER_CSV), exist_ok=True)
    with open(OUTREACH_TRACKER_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACKER_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    with open(OUTREACH_TRACKER_JSON, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log.info("Updated Outreach Tracker -> %d total records", len(records))


def send_live_email(to_email: str, subject: str, body: str) -> tuple[bool, str]:
    if not SMTP_USER or not SMTP_PASS:
        return False, "SMTP credentials missing in .env"
    try:
        msg = MIMEMultipart()
        msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True, ""
    except Exception as e:
        return False, str(e)


def process_outreach(mode: str = "simulate") -> list[dict]:
    log.info("=== Stage 5: Sending Layer & Outreach Tracker ===")
    log.info("Execution Mode: %s", mode.upper())

    if not os.path.exists(PERSONALIZED_JSON):
        log.error("Personalized messages not found at %s!", PERSONALIZED_JSON)
        return []

    with open(PERSONALIZED_JSON, "r", encoding="utf-8") as f:
        messages = json.load(f)

    history = load_existing_tracker()
    contacted_keys = get_contacted_keys(history)

    new_logs = []
    sent_count = 0
    simulated_count = 0
    skipped_count = 0
    dup_count = 0
    dm_sim_count = 0

    for idx, item in enumerate(messages, 1):
        cid = item.get("channel_id")
        email = item.get("contact_email", "Not Found")
        ig_url = item.get("instagram_url", "")
        name = item.get("influencer_name", "Creator")
        subject = item.get("email_subject", "")
        pitch = item.get("email_pitch", "")
        dm = item.get("instagram_dm", "")

        outreach_id = f"outreach_{uuid.uuid4().hex[:8]}"
        now_ts = datetime.now(timezone.utc).isoformat()

        if cid in contacted_keys or (email != "Not Found" and email.lower() in contacted_keys):
            dup_count += 1
            email_status = "DUPLICATE_PREVENTED"
            dm_status = "SKIPPED_DUPLICATE"
            err_msg = "Duplicate outreach prevented based on existing tracker record."
        elif email == "Not Found":
            email_status = "SKIPPED_NO_EMAIL"
            skipped_count += 1
            err_msg = "No contact email discovered for channel."
            dm_status = "DM_SIMULATED_QUEUED" if ig_url else "NO_INSTAGRAM"
            if ig_url:
                dm_sim_count += 1
        else:
            if mode == "live":
                success, err = send_live_email(email, subject, pitch)
                if success:
                    email_status = "SENT"
                    sent_count += 1
                    err_msg = ""
                else:
                    email_status = "FAILED"
                    err_msg = err
            else:
                email_status = "SIMULATED_SUCCESS"
                simulated_count += 1
                err_msg = ""

            dm_status = "DM_SIMULATED_SENT" if ig_url else "NO_INSTAGRAM"
            if ig_url:
                dm_sim_count += 1

            contacted_keys.add(cid)
            contacted_keys.add(email.lower())

        entry = {
            "outreach_id": outreach_id,
            "channel_id": cid,
            "influencer_name": name,
            "platform": item.get("platform", "YouTube"),
            "niche": item.get("niche"),
            "subscriber_count": item.get("subscriber_count"),
            "contact_email": email,
            "instagram_url": ig_url,
            "collaboration_angle": item.get("collaboration_angle"),
            "email_subject": subject,
            "email_pitch": pitch,
            "email_word_count": item.get("email_word_count"),
            "instagram_dm": dm,
            "email_status": email_status,
            "dm_status": dm_status,
            "sent_timestamp": now_ts,
            "delivery_mode": mode.upper(),
            "error_message": err_msg,
        }
        new_logs.append(entry)

    # Upsert by channel_id instead of blindly appending — otherwise re-running
    # this script (e.g. after a duplicate-prevented attempt) keeps adding new
    # rows for the same influencer forever. Keep exactly one tracker row per
    # channel_id, updating it in place when we process that channel again.
    by_channel: dict[str, dict] = {}
    for row in history:
        cid = row.get("channel_id")
        if cid:
            by_channel[cid] = row
    for row in new_logs:
        cid = row.get("channel_id")
        if cid:
            by_channel[cid] = row
    all_records = list(by_channel.values())
    save_tracker(all_records)

    print("\nStage 5 Sending Layer Summary:")
    print(f"  Total Processed        : {len(new_logs)}")
    print(f"  Emails Dispatched/Sim  : {sent_count if mode=='live' else simulated_count}")
    print(f"  Instagram DMs Simulated: {dm_sim_count}")
    print(f"  Skipped (No Email)     : {skipped_count}")
    print(f"  Duplicates Prevented   : {dup_count}")
    print(f"  Tracker CSV            : {OUTREACH_TRACKER_CSV}\n")

    return new_logs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stage 5 Sending Layer")
    parser.add_argument("--mode", choices=["simulate", "live"], default="simulate", help="Sending mode")
    args = parser.parse_args()
    process_outreach(mode=args.mode)
