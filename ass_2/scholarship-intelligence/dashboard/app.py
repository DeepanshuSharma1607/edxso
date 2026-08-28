"""
Streamlit dashboard for the Scholarship Intelligence Crawler.

Run with:
    streamlit run dashboard/app.py

Reads directly from data/scholarship.db (same SQLite file the FastAPI
backend and scripts/run_crawler.py use) -- no separate API server needs
to be running. Set DASHBOARD_USE_API=1 to instead call the FastAPI
endpoints at API_BASE_URL (default http://localhost:8000) if you'd
rather demonstrate the dashboard talking to the live API.
"""
import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "scholarship.db"
USE_API = os.environ.get("DASHBOARD_USE_API", "0") == "1"
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Scholarship Intelligence Crawler",
    page_icon="🎓",
    layout="wide",
)


# --------------------------------------------------------------------------
# Data access -- either direct SQLite reads or calls to the FastAPI backend
# --------------------------------------------------------------------------

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=10)
def load_stats() -> dict:
    if USE_API:
        r = requests.get(f"{API_BASE_URL}/api/stats", timeout=10)
        r.raise_for_status()
        return r.json()

    conn = get_connection()
    rows = [dict(r) for r in conn.execute(
        "SELECT status, verification_label, confidence_score FROM scholarships"
    ).fetchall()]
    total = len(rows)
    verified = len([r for r in rows if r["verification_label"] == "VERIFIED"])
    active = len([r for r in rows if r["status"] == "ACTIVE"])
    expiring_soon = len([r for r in rows if r["status"] == "EXPIRING_SOON"])
    expired = len([r for r in rows if r["status"] == "EXPIRED"])
    no_longer_verifiable = len([r for r in rows if r["status"] == "NO_LONGER_VERIFIABLE"])
    avg_confidence = round(sum(r["confidence_score"] for r in rows) / total, 1) if total else 0.0
    changes_count = conn.execute("SELECT COUNT(*) c FROM change_history").fetchone()["c"]
    conn.close()

    return {
        "total_discovered": total,
        "verified": verified,
        "review_required": total - verified,
        "active": active,
        "expiring_soon": expiring_soon,
        "expired": expired,
        "no_longer_verifiable": no_longer_verifiable,
        "average_confidence": avg_confidence,
        "total_changes_detected": changes_count,
    }


@st.cache_data(ttl=10)
def load_scholarships(
    q: str = "",
    status: str = "All",
    source_type: str = "All",
    verification_label: str = "All",
    min_confidence: float = 0.0,
) -> pd.DataFrame:
    if USE_API:
        params = {"limit": 500}
        if q:
            params["q"] = q
        if status != "All":
            params["status"] = status
        if source_type != "All":
            params["source_type"] = source_type
        if verification_label != "All":
            params["verification_label"] = verification_label
        if min_confidence:
            params["min_confidence"] = min_confidence
        r = requests.get(f"{API_BASE_URL}/api/scholarships", params=params, timeout=10)
        r.raise_for_status()
        return pd.DataFrame(r.json()["results"])

    conn = get_connection()
    sql = "SELECT * FROM scholarships WHERE 1=1"
    params: list = []
    if q:
        sql += " AND (name LIKE ? OR provider LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    if status != "All":
        sql += " AND status = ?"
        params.append(status)
    if source_type != "All":
        sql += " AND source_type = ?"
        params.append(source_type)
    if verification_label != "All":
        sql += " AND verification_label = ?"
        params.append(verification_label)
    if min_confidence:
        sql += " AND confidence_score >= ?"
        params.append(min_confidence)
    sql += " ORDER BY confidence_score DESC"

    df = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return df


@st.cache_data(ttl=10)
def load_scholarship_detail(scholarship_id: str) -> dict:
    if USE_API:
        r = requests.get(f"{API_BASE_URL}/api/scholarships/{scholarship_id}", timeout=10)
        r.raise_for_status()
        return r.json()

    conn = get_connection()
    row = conn.execute("SELECT * FROM scholarships WHERE id = ?", (scholarship_id,)).fetchone()
    if not row:
        conn.close()
        return {}
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
    row["confidence_breakdown_parsed"] = confidence_meta.get("breakdown", {})
    row["why_this_score"] = confidence_meta.get("reasons", {})
    row["evidence_parsed"] = evidence
    row["change_history"] = changes
    return row


@st.cache_data(ttl=10)
def load_sources() -> pd.DataFrame:
    if USE_API:
        r = requests.get(f"{API_BASE_URL}/api/sources", timeout=10)
        r.raise_for_status()
        return pd.DataFrame(r.json()["results"])

    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM sources", conn)
    counts = pd.read_sql_query(
        "SELECT source_id, COUNT(*) as scholarship_count FROM scholarships GROUP BY source_id", conn
    )
    conn.close()
    df = df.merge(counts, left_on="id", right_on="source_id", how="left")
    df["scholarship_count"] = df["scholarship_count"].fillna(0).astype(int)
    return df


@st.cache_data(ttl=10)
def load_crawl_runs() -> pd.DataFrame:
    if USE_API:
        r = requests.get(f"{API_BASE_URL}/api/crawl/runs", timeout=10)
        r.raise_for_status()
        return pd.DataFrame(r.json()["results"])

    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM crawl_runs ORDER BY started_at DESC", conn)
    conn.close()
    return df


@st.cache_data(ttl=10)
def load_all_changes() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        """
        SELECT ch.*, s.name AS scholarship_name
        FROM change_history ch
        LEFT JOIN scholarships s ON s.id = ch.scholarship_id
        ORDER BY ch.detected_at DESC
        """,
        conn,
    )
    conn.close()
    return df


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------

if not DB_PATH.exists():
    st.error(
        f"No database found at `{DB_PATH}`. Run `python -m scripts.run_crawler --run 1` "
        "(and optionally `--run 2`) first to populate it."
    )
    st.stop()

st.title("🎓 Scholarship Intelligence Crawler")
st.caption(
    "Discover → Crawl → Extract → Verify → Score → Store → Update — "
    f"reading from `{'API at ' + API_BASE_URL if USE_API else 'data/scholarship.db'}`"
)

tab_overview, tab_browse, tab_changes, tab_sources = st.tabs(
    ["📊 Overview", "🔍 Browse Scholarships", "🔁 Change History", "🌐 Sources & Crawl Runs"]
)

# ---------------- Overview ----------------
with tab_overview:
    stats = load_stats()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Discovered", stats["total_discovered"])
    c2.metric("Verified", stats["verified"])
    c3.metric("Review Required", stats["review_required"])
    c4.metric("Avg. Confidence", f"{stats['average_confidence']}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Active", stats["active"])
    c6.metric("Expiring Soon", stats["expiring_soon"])
    c7.metric("Expired", stats["expired"])
    c8.metric("No Longer Verifiable", stats["no_longer_verifiable"])

    st.metric("Total Changes Detected", stats["total_changes_detected"])

    st.divider()

    df_all = load_scholarships()
    if not df_all.empty:
        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader("By Verification Label")
            st.bar_chart(df_all["verification_label"].value_counts())
        with col_b:
            st.subheader("By Source Type")
            st.bar_chart(df_all["source_type"].value_counts())

        st.subheader("By Status")
        st.bar_chart(df_all["status"].value_counts())

# ---------------- Browse ----------------
with tab_browse:
    st.subheader("Filter & Search")
    df_full = load_scholarships()

    fcol1, fcol2, fcol3, fcol4, fcol5 = st.columns([2, 1, 1, 1, 1])
    with fcol1:
        q = st.text_input("Search name / provider", "")
    with fcol2:
        status_opt = ["All"] + (sorted(df_full["status"].dropna().unique().tolist()) if not df_full.empty else [])
        status_f = st.selectbox("Status", status_opt)
    with fcol3:
        source_opt = ["All"] + (sorted(df_full["source_type"].dropna().unique().tolist()) if not df_full.empty else [])
        source_f = st.selectbox("Source Type", source_opt)
    with fcol4:
        label_opt = ["All"] + (sorted(df_full["verification_label"].dropna().unique().tolist()) if not df_full.empty else [])
        label_f = st.selectbox("Verification", label_opt)
    with fcol5:
        min_conf = st.slider("Min confidence", 0, 100, 0, step=5)

    df = load_scholarships(q=q, status=status_f, source_type=source_f, verification_label=label_f, min_confidence=min_conf)
    st.caption(f"{len(df)} result(s)")

    if df.empty:
        st.info("No scholarships match these filters.")
    else:
        display_cols = ["name", "provider", "source_type", "status", "verification_label", "confidence_score", "closing_date"]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("Inspect a Scholarship")
        options = dict(zip(df["name"] + "  (" + df["id"] + ")", df["id"]))
        picked_label = st.selectbox("Choose a record to see full evidence & confidence breakdown", list(options.keys()))
        if picked_label:
            detail = load_scholarship_detail(options[picked_label])
            if detail:
                dcol1, dcol2 = st.columns([2, 1])
                with dcol1:
                    st.markdown(f"### {detail.get('name')}")
                    st.write(f"**Provider:** {detail.get('provider')}")
                    st.write(f"**Amount:** {detail.get('amount')}")
                    st.write(f"**Eligibility:** {detail.get('eligibility')}")
                    st.write(f"**Course level:** {detail.get('course_level')}")
                    st.write(f"**Opening date:** {detail.get('opening_date')}  |  **Closing date:** {detail.get('closing_date')}")
                    st.write(f"**Application URL:** {detail.get('application_url')}")
                    st.write(f"**Official source URL:** {detail.get('official_source_url')}")
                with dcol2:
                    st.metric("Confidence score", f"{detail.get('confidence_score')}%")
                    st.write(f"**Status:** {detail.get('status')}")
                    st.write(f"**Verification label:** {detail.get('verification_label')}")
                    st.write(f"**Last verified:** {detail.get('last_verified')}")
                    st.write(f"**First discovered:** {detail.get('first_discovered_at')}")

                with st.expander("Confidence breakdown"):
                    breakdown = detail.get("confidence_breakdown_parsed") or detail.get("confidence_breakdown") or {}
                    st.json(breakdown)

                with st.expander("Evidence"):
                    evidence = detail.get("evidence_parsed") or detail.get("evidence") or {}
                    st.json(evidence)

                change_hist = detail.get("change_history") or []
                with st.expander(f"Change history ({len(change_hist)})"):
                    if change_hist:
                        st.dataframe(pd.DataFrame(change_hist), use_container_width=True, hide_index=True)
                    else:
                        st.caption("No changes detected for this record yet.")

# ---------------- Change History ----------------
with tab_changes:
    st.subheader("All Detected Changes")
    df_changes = load_all_changes()
    if df_changes.empty:
        st.info("No changes detected yet. Run a second crawl pass (`--run 2`) to see change detection in action.")
    else:
        display_cols = ["scholarship_name", "field_name", "old_value", "new_value", "detected_at", "crawl_run_id"]
        display_cols = [c for c in display_cols if c in df_changes.columns]
        st.dataframe(df_changes[display_cols], use_container_width=True, hide_index=True)
        for _, row in df_changes.iterrows():
            with st.expander(f"{row.get('scholarship_name')} — {row.get('field_name')}"):
                st.write(f"**Old value:** {row.get('old_value')}")
                st.write(f"**New value:** {row.get('new_value')}")
                st.write(f"**Detected at:** {row.get('detected_at')}")
                st.write(f"**Evidence:** {row.get('evidence')}")
                st.write(f"**Source URL:** {row.get('source_url')}")

# ---------------- Sources & Crawl Runs ----------------
with tab_sources:
    st.subheader("Registered Sources")
    df_sources = load_sources()
    if df_sources.empty:
        st.info("No sources registered.")
    else:
        cols = [c for c in ["id", "name", "url", "source_type", "approved", "last_crawled", "scholarship_count"] if c in df_sources.columns]
        st.dataframe(df_sources[cols], use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Crawl Run History")
    df_runs = load_crawl_runs()
    if df_runs.empty:
        st.info("No crawl runs recorded yet.")
    else:
        st.dataframe(df_runs, use_container_width=True, hide_index=True)