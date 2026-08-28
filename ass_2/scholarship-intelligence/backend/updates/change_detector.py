"""Field-level change detection between a stored scholarship row and a
freshly extracted ScholarshipRecord. Returns a list of (field, old, new)
tuples -- callers write these to change_history and update the row rather
than ever silently overwriting history."""
from typing import List, Tuple
from backend.extraction.schemas import ScholarshipRecord

TRACKED_FIELDS = [
    "amount", "benefit_type", "eligibility", "course_level",
    "income_criteria", "closing_date", "opening_date",
    "application_url", "official_source_url", "documents_required",
]


def detect_changes(old_row: dict, new_record: ScholarshipRecord) -> List[Tuple[str, str, str]]:
    changes = []
    for field_name in TRACKED_FIELDS:
        old_val = (old_row.get(field_name) or "").strip()
        new_val = (getattr(new_record, field_name, "") or "").strip()
        if new_val and old_val != new_val:
            changes.append((field_name, old_val, new_val))
    return changes
