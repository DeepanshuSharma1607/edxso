"""
FastAPI backend for the Scholarship Intelligence Crawler.

Run with:
    uvicorn backend.api.main:app --reload --port 8000

Endpoints:
    GET  /api/stats                      -> dashboard summary numbers
    GET  /api/scholarships               -> searchable/filterable list
    GET  /api/scholarships/{id}          -> full detail incl. evidence,
                                             confidence breakdown, change history
    GET  /api/sources                    -> registered sources + crawl status
    GET  /api/crawl/runs                 -> crawl_runs history
    POST /api/crawl/run?run_number=1|2   -> trigger a crawl (fixture-replay
                                             mode by default; see backend/config.py)
"""
import json
import logging
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.database.connection import get_connection, init_db
from backend.discovery.source_registry import APPROVED_SOURCES

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("scholarship_api")

app = FastAPI(
    title="Scholarship Intelligence Crawler API",
    description="Discover -> Crawl -> Extract -> Verify -> Score -> Store -> Update",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup():
    init_db()
    logger.info("Database initialised. Approved sources: %s", [s.id for s in APPROVED_SOURCES])


def _row_to_summary(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "provider": row["provider"],
        "amount": row["amount"],
        "source_type": row["source_type"],
        "status": row["status"],
        "verification_label": row["verification_label"],
        "confidence_score": row["confidence_score"],
        "closing_date": row["closing_date"],
        "last_verified": row["last_verified"],
    }


@app.get("/api/stats")
def get_stats():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT status, verification_label, confidence_score FROM scholarships").fetchall()]
    total = len(rows)
    verified = len([r for r in rows if r["verification_label"] == "VERIFIED"])
    review_required = total - verified
    active = len([r for r in rows if r["status"] == "ACTIVE"])
    expiring_soon = len([r for r in rows if r["status"] == "EXPIRING_SOON"])
    expired = len([r for r in rows if r["status"] == "EXPIRED"])
    no_longer_verifiable = len([r for r in rows if r["status"] == "NO_LONGER_VERIFIABLE"])
    avg_confidence = round(sum(r["confidence_score"] for r in rows) / total, 1) if total else 0.0

    recent = [
        dict(r) for r in conn.execute(
            "SELECT id, name, status, updated_at FROM scholarships ORDER BY updated_at DESC LIMIT 5"
        ).fetchall()
    ]
    changes_count = conn.execute("SELECT COUNT(*) c FROM change_history").fetchone()["c"]
    conn.close()

    return {
        "total_discovered": total,
        "verified": verified,
        "review_required": review_required,
        "active": active,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "no_longer_verifiable": no_longer_verifiable,
        "average_confidence": avg_confidence,
        "total_changes_detected": changes_count,
        "recently_updated": recent,
    }


@app.get("/api/scholarships")
def list_scholarships(
    q: Optional[str] = Query(None, description="Search text (name/provider)"),
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    verification_label: Optional[str] = Query(None),
    min_confidence: Optional[float] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
):
    conn = get_connection()
    sql = "SELECT * FROM scholarships WHERE 1=1"
    params: List = []
    if q:
        sql += " AND (name LIKE ? OR provider LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if source_type:
        sql += " AND source_type = ?"
        params.append(source_type)
    if verification_label:
        sql += " AND verification_label = ?"
        params.append(verification_label)
    if min_confidence is not None:
        sql += " AND confidence_score >= ?"
        params.append(min_confidence)
    sql += " ORDER BY confidence_score DESC LIMIT ? OFFSET ?"
    params += [limit, offset]

    rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
    conn.close()
    return {"count": len(rows), "results": [_row_to_summary(r) for r in rows]}


@app.get("/api/scholarships/{scholarship_id}")
def get_scholarship_detail(scholarship_id: str):
    conn = get_connection()
    row = conn.execute("SELECT * FROM scholarships WHERE id = ?", (scholarship_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Scholarship not found")
    row = dict(row)

    changes = [
        dict(r) for r in conn.execute(
            "SELECT * FROM change_history WHERE scholarship_id = ? ORDER BY detected_at DESC",
            (scholarship_id,),
        ).fetchall()
    ]
    conn.close()

    try:
        confidence_meta = json.loads(row.get("confidence_breakdown") or "{}")
    except json.JSONDecodeError:
        confidence_meta = {}
    try:
        evidence = json.loads(row.get("evidence") or "{}")
    except json.JSONDecodeError:
        evidence = {}

    return {
        "id": row["id"],
        "name": row["name"],
        "provider": row["provider"],
        "amount": row["amount"],
        "benefit_type": row["benefit_type"],
        "eligibility": row["eligibility"],
        "academic_requirements": row["academic_requirements"],
        "course_level": row["course_level"],
        "income_criteria": row["income_criteria"],
        "age_criteria": row["age_criteria"],
        "gender_criteria": row["gender_criteria"],
        "category_criteria": row["category_criteria"],
        "domicile": row["domicile"],
        "institution_requirements": row["institution_requirements"],
        "opening_date": row["opening_date"],
        "closing_date": row["closing_date"],
        "documents_required": row["documents_required"],
        "selection_process": row["selection_process"],
        "renewal_requirements": row["renewal_requirements"],
        "application_url": row["application_url"],
        "official_source_url": row["official_source_url"],
        "source_type": row["source_type"],
        "status": row["status"],
        "verification_label": row["verification_label"],
        "confidence_score": row["confidence_score"],
        "confidence_breakdown": confidence_meta.get("breakdown", {}),
        "why_this_score": confidence_meta.get("reasons", {}),
        "evidence": evidence,
        "discovery_url": row["discovery_url"],
        "last_verified": row["last_verified"],
        "first_discovered_at": row["first_discovered_at"],
        "change_history": changes,
    }


@app.get("/api/sources")
def list_sources():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM sources").fetchall()]
    counts = {
        r["source_id"]: r["c"]
        for r in conn.execute("SELECT source_id, COUNT(*) c FROM scholarships GROUP BY source_id").fetchall()
    }
    conn.close()
    for r in rows:
        r["scholarship_count"] = counts.get(r["id"], 0)
    return {"count": len(rows), "results": rows}


@app.get("/api/crawl/runs")
def list_crawl_runs():
    conn = get_connection()
    rows = [dict(r) for r in conn.execute("SELECT * FROM crawl_runs ORDER BY started_at DESC").fetchall()]
    conn.close()
    return {"count": len(rows), "results": rows}


@app.post("/api/crawl/run")
def trigger_crawl(run_number: int = Query(..., ge=1, le=2)):
    """Triggers a fixture-replay crawl run (see scripts/run_crawler.py for
    the same logic used from the CLI). In fixture mode this is fully
    deterministic and safe to call repeatedly."""
    from scripts.run_crawler import main as run_main
    try:
        run_main(run_number)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "completed", "run_number": run_number}


@app.post("/api/crawl/live")
def trigger_live_crawl(source_id: str, entry_url: str):
    """Triggers a REAL live crawl (discovery -> fetch -> Mistral extraction
    -> verify -> store) for an approved source. Requires outbound internet
    access and a valid MISTRAL_API_KEY -- this will fail fast with a clear
    error if either is unavailable, rather than silently falling back to
    fixtures. Use /api/crawl/run for the deterministic offline demo."""
    from backend.discovery.source_registry import SOURCE_BY_ID
    from backend.services.live_crawl_runner import run_live_crawl

    source = SOURCE_BY_ID.get(source_id)
    if not source:
        raise HTTPException(status_code=404, detail=f"Unknown source_id '{source_id}'. See /api/sources.")
    try:
        stats = run_live_crawl(source, entry_url)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Live crawl failed: {e}")
    return {"status": "completed", "source_id": source_id, "stats": stats}


@app.get("/api/health")
def health():
    return {"status": "ok"}
