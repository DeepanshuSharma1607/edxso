"""
This test exercises backend/services/live_crawl_runner.py -- the code path
meant for real internet access -- end-to-end, with only the two network
boundary calls mocked (http_crawler.fetch and llm_extractor.extract_with_llm).
Discovery's link classification, the crawl loop, run_crawl's insert/score/
store logic, and the database all run for real. This is what proves the
"live mode" wiring (not just the fixture-replay path) actually works.

Uses an isolated temp SQLite file (via the `isolated_db` fixture) so this
test never writes into the project's real data/scholarship.db.
"""
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import date

from backend.discovery.source_registry import SourceDef
from backend.extraction.schemas import ScholarshipRecord
from backend.services.live_crawl_runner import crawl_source_live, run_live_crawl

FAKE_SOURCE = SourceDef(
    id="S999", name="Fake Test University", url="https://example-university.edu/",
    source_type="UNIVERSITY", approved_domains=("example-university.edu",),
)

FAKE_INDEX_HTML = """
<html><body>
  <a href="/scholarships/merit-scholarship">Merit Scholarship</a>
  <a href="/scholarships/sports-scholarship">Sports Scholarship</a>
  <a href="/about-us">About Us</a>
</body></html>
"""

FAKE_DETAIL_HTML = "<html><body><p>Merit Scholarship: apply before 2026-12-01.</p></body></html>"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point the DB module at a throwaway file for the duration of the test."""
    import backend.database.connection as conn_module
    temp_db = tmp_path / "test_scholarship.db"
    monkeypatch.setattr(conn_module, "DB_PATH", temp_db)
    conn_module.init_db()
    yield temp_db


def _fake_fetch(url, timeout=20):
    if url == "https://example-university.edu/scholarships":
        return FAKE_INDEX_HTML
    if "merit-scholarship" in url or "sports-scholarship" in url:
        return FAKE_DETAIL_HTML
    return None


def _fake_extract_with_llm(raw_text, official_source_url, source_type, discovery_url=None, model="mistral-small-latest"):
    return ScholarshipRecord(
        name=f"Extracted from {official_source_url.rsplit('/', 1)[-1]}",
        provider="Fake Test University",
        closing_date="2026-12-01",
        application_url=official_source_url,
        official_source_url=official_source_url,
        source_type=source_type,
        discovery_url=discovery_url,
        evidence={"closing_date": raw_text},
    )


@patch("backend.services.live_crawl_runner.extract_with_llm", side_effect=_fake_extract_with_llm)
@patch("backend.services.live_crawl_runner.fetch", side_effect=_fake_fetch)
def test_crawl_source_live_discovers_and_extracts_both_links(mock_fetch, mock_extract):
    records = crawl_source_live(FAKE_SOURCE, "https://example-university.edu/scholarships")
    assert len(records) == 2
    names = {r.name for r in records}
    assert any("merit-scholarship" in n for n in names)
    assert any("sports-scholarship" in n for n in names)
    # the irrelevant /about-us link must never reach the extractor
    assert mock_extract.call_count == 2


@patch.dict("backend.services.crawl_runner.SOURCE_BY_ID", {"S999": FAKE_SOURCE})
@patch("backend.services.live_crawl_runner.extract_with_llm", side_effect=_fake_extract_with_llm)
@patch("backend.services.live_crawl_runner.fetch", side_effect=_fake_fetch)
def test_run_live_crawl_stores_records_through_the_real_pipeline(mock_fetch, mock_extract, isolated_db):
    stats = run_live_crawl(FAKE_SOURCE, "https://example-university.edu/scholarships",
                            simulated_now=date(2026, 9, 1))
    assert stats["scholarships_found"] == 2
    assert stats["new_scholarships"] == 2

    from backend.database.connection import get_connection
    conn = get_connection()
    rows = conn.execute("SELECT name, official_source_url FROM scholarships WHERE source_id = 'S999'").fetchall()
    conn.close()
    assert len(rows) == 2
