"""Resolves a scholarship's lifecycle `status` from its closing_date and
whether it was found again in the latest crawl. Never deletes a record --
expired/unverifiable scholarships are kept so stale-data detection is
demonstrable and auditable."""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

EXPIRING_SOON_WINDOW_DAYS = 10


def resolve_status(
    closing_date_iso: Optional[str],
    currently_present: bool,
    now: Optional[date] = None,
    verification_label: str = "VERIFIED",
) -> str:
    now = now or datetime.now(timezone.utc).date()

    if not currently_present:
        return "NO_LONGER_VERIFIABLE"

    if verification_label == "REVIEW_REQUIRED":
        return "REVIEW_REQUIRED"

    if not closing_date_iso or closing_date_iso == "NOT_SPECIFIED":
        return "ACTIVE"

    try:
        closing = date.fromisoformat(closing_date_iso)
    except ValueError:
        return "ACTIVE"

    if closing < now:
        return "EXPIRED"
    if closing - now <= timedelta(days=EXPIRING_SOON_WINDOW_DAYS):
        return "EXPIRING_SOON"
    return "ACTIVE"
