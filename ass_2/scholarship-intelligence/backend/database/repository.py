import json
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from backend.database.connection import get_connection
from backend.discovery.source_registry import SourceDef


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_source(conn, s: SourceDef) -> None:
    row = conn.execute("SELECT id FROM sources WHERE id = ?", (s.id,)).fetchone()
    ts = _now()
    if row:
        conn.execute(
            "UPDATE sources SET name=?, url=?, source_type=?, last_crawled=?, updated_at=? WHERE id=?",
            (s.name, s.url, s.source_type, ts, ts, s.id),
        )
    else:
        conn.execute(
            "INSERT INTO sources (id, name, url, source_type, approved, last_crawled, "
            "last_successful_crawl, created_at, updated_at) VALUES (?,?,?,?,1,?,?,?,?)",
            (s.id, s.name, s.url, s.source_type, ts, ts, ts, ts),
        )


def content_hash(record) -> str:
    payload = json.dumps(record.model_dump(exclude={"evidence"}), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def find_scholarship_by_name_source(conn, name: str, source_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT * FROM scholarships WHERE name = ? AND source_id = ?", (name, source_id)
    ).fetchone()
    return dict(row) if row else None


def get_all_scholarship_keys_for_source(conn, source_id: str) -> List[str]:
    rows = conn.execute("SELECT name FROM scholarships WHERE source_id = ?", (source_id,)).fetchall()
    return [r["name"] for r in rows]


def insert_scholarship(conn, source_id: str, record, conf_result, status: str) -> str:
    sid = f"SCH{uuid.uuid4().hex[:10].upper()}"
    ts = _now()
    conn.execute(
        """INSERT INTO scholarships (
            id, source_id, name, provider, amount, benefit_type, eligibility,
            academic_requirements, course_level, income_criteria, age_criteria,
            gender_criteria, category_criteria, domicile, institution_requirements,
            opening_date, closing_date, documents_required, selection_process,
            renewal_requirements, application_url, official_source_url, source_type,
            status, verification_label, confidence_score, confidence_breakdown,
            evidence, discovery_url, content_hash, last_verified, first_discovered_at,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            sid, source_id, record.name, record.provider, record.amount, record.benefit_type,
            record.eligibility, record.academic_requirements, record.course_level,
            record.income_criteria, record.age_criteria, record.gender_criteria,
            record.category_criteria, record.domicile, record.institution_requirements,
            record.opening_date, record.closing_date, record.documents_required,
            record.selection_process, record.renewal_requirements, record.application_url,
            record.official_source_url, record.source_type, status, conf_result.label,
            conf_result.score, json.dumps({"breakdown": conf_result.breakdown, "reasons": conf_result.reasons}),
            json.dumps(record.evidence), record.discovery_url, content_hash(record), ts, ts, ts, ts,
        ),
    )
    return sid


def update_scholarship(conn, sid: str, record, conf_result, status: str) -> None:
    ts = _now()
    conn.execute(
        """UPDATE scholarships SET
            provider=?, amount=?, benefit_type=?, eligibility=?, academic_requirements=?,
            course_level=?, income_criteria=?, age_criteria=?, gender_criteria=?,
            category_criteria=?, domicile=?, institution_requirements=?, opening_date=?,
            closing_date=?, documents_required=?, selection_process=?, renewal_requirements=?,
            application_url=?, official_source_url=?, status=?, verification_label=?,
            confidence_score=?, confidence_breakdown=?, evidence=?, content_hash=?,
            last_verified=?, updated_at=?
        WHERE id=?""",
        (
            record.provider, record.amount, record.benefit_type, record.eligibility,
            record.academic_requirements, record.course_level, record.income_criteria,
            record.age_criteria, record.gender_criteria, record.category_criteria,
            record.domicile, record.institution_requirements, record.opening_date,
            record.closing_date, record.documents_required, record.selection_process,
            record.renewal_requirements, record.application_url, record.official_source_url,
            status, conf_result.label, conf_result.score,
            json.dumps({"breakdown": conf_result.breakdown, "reasons": conf_result.reasons}),
            json.dumps(record.evidence), content_hash(record), ts, ts, sid,
        ),
    )


def mark_status(conn, sid: str, status: str) -> None:
    conn.execute("UPDATE scholarships SET status=?, updated_at=? WHERE id=?", (status, _now(), sid))


def insert_change(conn, scholarship_id: str, field_name: str, old_value: str, new_value: str,
                   source_url: str, evidence: str, crawl_run_id: str) -> None:
    cid = f"CHG{uuid.uuid4().hex[:10].upper()}"
    conn.execute(
        "INSERT INTO change_history (id, scholarship_id, field_name, old_value, new_value, "
        "detected_at, source_url, evidence, crawl_run_id) VALUES (?,?,?,?,?,?,?,?,?)",
        (cid, scholarship_id, field_name, old_value, new_value, _now(), source_url, evidence, crawl_run_id),
    )


def start_crawl_run(conn) -> str:
    rid = f"RUN{uuid.uuid4().hex[:8].upper()}"
    conn.execute(
        "INSERT INTO crawl_runs (id, started_at, status) VALUES (?,?,?)",
        (rid, _now(), "RUNNING"),
    )
    return rid


def finish_crawl_run(conn, rid: str, stats: Dict[str, int], errors: Optional[str] = None) -> None:
    conn.execute(
        """UPDATE crawl_runs SET completed_at=?, status=?, sources_checked=?, scholarships_found=?,
           new_scholarships=?, updated_scholarships=?, expired_scholarships=?, no_longer_verifiable=?,
           errors=? WHERE id=?""",
        (
            _now(), "COMPLETED", stats.get("sources_checked", 0), stats.get("scholarships_found", 0),
            stats.get("new_scholarships", 0), stats.get("updated_scholarships", 0),
            stats.get("expired_scholarships", 0), stats.get("no_longer_verifiable", 0), errors, rid,
        ),
    )
