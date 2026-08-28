"""
Orchestrates one full crawl run:

  Approved sources -> Discovery -> Crawl -> Extract -> Verify -> Score
  -> Compare with DB -> Insert / Update+history / Mark expired or
  no-longer-verifiable -> Record crawl_runs

This is deliberately source-agnostic: it takes a list of ScholarshipRecord
objects already produced by extraction (rule-based for NSP, LLM-based for
messier aggregator-only text) plus a `currently_present_names` set per
source, and does the compare/insert/update/history/status work described
in section 14 of the project spec. Both the fixture-replay demo and a
future live-internet run call this same function.
"""
from typing import List, Dict, Set
from datetime import date

from backend.database.connection import get_connection
from backend.database import repository as repo
from backend.discovery.source_registry import SOURCE_BY_ID, is_official_domain
from backend.verification.confidence import score_record
from backend.updates.change_detector import detect_changes
from backend.updates.expiry_checker import resolve_status
from backend.extraction.schemas import ScholarshipRecord


def run_crawl(
    source_id: str,
    records: List[ScholarshipRecord],
    simulated_now: date = None,
) -> Dict[str, int]:
    """Run discovery-through-update for one source's freshly extracted
    records. `records` = everything found on the source THIS run;
    anything previously stored for this source but absent from `records`
    is treated as no-longer-present (-> NO_LONGER_VERIFIABLE)."""
    source = SOURCE_BY_ID[source_id]
    conn = get_connection()
    run_id = repo.start_crawl_run(conn)
    repo.upsert_source(conn, source)

    stats = {"sources_checked": 1, "scholarships_found": len(records),
              "new_scholarships": 0, "updated_scholarships": 0,
              "expired_scholarships": 0, "no_longer_verifiable": 0}

    found_names: Set[str] = {r.name for r in records}
    existing_names = set(repo.get_all_scholarship_keys_for_source(conn, source_id))

    # 1. Process every currently-found record: insert new / update changed
    for record in records:
        official_ok = is_official_domain(record.official_source_url, source)
        existing = repo.find_scholarship_by_name_source(conn, record.name, source_id)

        conf = score_record(
            record,
            is_official_domain=official_ok,
            currently_present=True,
            now=simulated_now,
        )
        status = resolve_status(
            record.closing_date, currently_present=True,
            now=simulated_now, verification_label=conf.label,
        )

        if existing is None:
            sid = repo.insert_scholarship(conn, source_id, record, conf, status)
            stats["new_scholarships"] += 1
        else:
            sid = existing["id"]
            changes = detect_changes(existing, record)
            for field_name, old_val, new_val in changes:
                evidence_text = record.evidence.get(field_name, "")
                repo.insert_change(
                    conn, sid, field_name, old_val, new_val,
                    record.official_source_url, evidence_text, run_id,
                )
            if changes:
                stats["updated_scholarships"] += 1
            repo.update_scholarship(conn, sid, record, conf, status)
            repo.mark_status(conn, sid, status)

        if status == "EXPIRED":
            stats["expired_scholarships"] += 1

    # 2. Anything that existed before but wasn't found this run -> NO_LONGER_VERIFIABLE
    missing_names = existing_names - found_names
    for name in missing_names:
        row = repo.find_scholarship_by_name_source(conn, name, source_id)
        if row and row["status"] != "NO_LONGER_VERIFIABLE":
            repo.insert_change(
                conn, row["id"], "status", row["status"], "NO_LONGER_VERIFIABLE",
                row["official_source_url"], "Record no longer found on official source during latest crawl", run_id,
            )
            repo.mark_status(conn, row["id"], "NO_LONGER_VERIFIABLE")
            stats["no_longer_verifiable"] += 1

    repo.finish_crawl_run(conn, run_id, stats)
    conn.commit()
    conn.close()
    stats["run_id"] = run_id
    return stats
