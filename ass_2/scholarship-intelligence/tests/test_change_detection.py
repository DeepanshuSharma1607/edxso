from datetime import date
from backend.extraction.schemas import ScholarshipRecord
from backend.updates.change_detector import detect_changes
from backend.updates.expiry_checker import resolve_status


def test_detect_changes_flags_deadline_change():
    old_row = {"closing_date": "2026-09-30", "amount": "NOT_SPECIFIED", "eligibility": "X"}
    new_record = ScholarshipRecord(
        name="Test", provider="P", closing_date="2026-10-15",
        official_source_url="https://scholarships.gov.in/All-Scholarships",
        source_type="GOVERNMENT",
    )
    changes = detect_changes(old_row, new_record)
    fields_changed = {c[0] for c in changes}
    assert "closing_date" in fields_changed
    change = next(c for c in changes if c[0] == "closing_date")
    assert change == ("closing_date", "2026-09-30", "2026-10-15")


def test_detect_changes_no_false_positive_when_unchanged():
    new_record = ScholarshipRecord(
        name="Test", provider="P", closing_date="2026-10-15",
        official_source_url="https://scholarships.gov.in/All-Scholarships",
        source_type="GOVERNMENT",
    )
    # old_row mirrors every tracked field at its NOT_SPECIFIED default except
    # closing_date, which matches the new record -> no field should be flagged
    from backend.updates.change_detector import TRACKED_FIELDS
    old_row = {f: "NOT_SPECIFIED" for f in TRACKED_FIELDS}
    old_row["closing_date"] = "2026-10-15"
    old_row["official_source_url"] = "https://scholarships.gov.in/All-Scholarships"
    assert detect_changes(old_row, new_record) == []


def test_resolve_status_expired():
    status = resolve_status("2026-08-31", currently_present=True, now=date(2026, 9, 5))
    assert status == "EXPIRED"


def test_resolve_status_expiring_soon():
    status = resolve_status("2026-09-10", currently_present=True, now=date(2026, 9, 5))
    assert status == "EXPIRING_SOON"


def test_resolve_status_active():
    status = resolve_status("2026-12-31", currently_present=True, now=date(2026, 9, 5))
    assert status == "ACTIVE"


def test_resolve_status_no_longer_verifiable_when_absent():
    status = resolve_status("2026-12-31", currently_present=False, now=date(2026, 9, 5))
    assert status == "NO_LONGER_VERIFIABLE"


def test_resolve_status_review_required_overrides_dates():
    status = resolve_status("2026-12-31", currently_present=True, now=date(2026, 9, 5),
                             verification_label="REVIEW_REQUIRED")
    assert status == "REVIEW_REQUIRED"
