"""
Usage:
    python -m scripts.run_crawler --run 1
    python -m scripts.run_crawler --run 2

Run 1 = initial crawl (populates the database from scratch).
Run 2 = second crawl 9 days later, using data/fixtures/run2_* snapshots,
        which contain a deliberately-introduced deadline change, a removed
        scheme, and a newly-discovered scheme -- exercising change
        detection, NO_LONGER_VERIFIABLE detection and "newly discovered"
        in one pass. See the header comment in run2_nsp_all_schemes.txt
        for exactly what was edited and why.

Both runs go through the *same* discover -> crawl -> extract -> verify ->
score -> store -> update pipeline (backend/services/crawl_runner.py); nothing
about the pipeline code differs between "run 1" and "run 2".
"""
import argparse
from datetime import date

from backend.database.connection import init_db
from backend.crawler.fixture_loader import load_fixture
from backend.extraction.rule_extractor import parse_nsp_fixture
from backend.extraction.other_source_extractor import parse_other_sources_fixture
from backend.services.crawl_runner import run_crawl


def main(run_number: int):
    init_db()

    if run_number == 1:
        nsp_page = load_fixture("run1_nsp_all_schemes.txt")
        other_page = load_fixture("run1_other_sources.txt") if False else None
        simulated_now = date(2026, 8, 27)
        print(f"=== CRAWL RUN 1 ({simulated_now.isoformat()}) ===")
    elif run_number == 2:
        nsp_page = load_fixture("run2_nsp_all_schemes.txt")
        simulated_now = date(2026, 9, 5)
        print(f"=== CRAWL RUN 2 ({simulated_now.isoformat()}) ===")
    else:
        raise SystemExit("Only --run 1 or --run 2 supported")

    # --- Government source (National Scholarship Portal) ---
    nsp_records = parse_nsp_fixture(nsp_page.body)
    print(f"[Discovery->Extraction] NSP: {len(nsp_records)} scheme records parsed from {nsp_page.source_url}")
    stats = run_crawl("S001", nsp_records, simulated_now=simulated_now)
    _print_stats("S001 (National Scholarship Portal)", stats)

    # --- Corporate + University (aggregator-discovered) — only on run 1 ---
    if run_number == 1:
        from pathlib import Path
        other_raw = (Path(__file__).resolve().parent.parent / "data" / "fixtures" / "run1_other_sources.txt").read_text(encoding="utf-8")
        other_records = parse_other_sources_fixture(other_raw)
        by_type = {}
        for r in other_records:
            by_type.setdefault(r.source_type, []).append(r)
        for src_id, stype in (("S002", "CORPORATE"), ("S003", "UNIVERSITY")):
            recs = by_type.get(stype, [])
            if recs:
                stats2 = run_crawl(src_id, recs, simulated_now=simulated_now)
                _print_stats(f"{src_id} ({stype})", stats2)


def _print_stats(label: str, stats: dict):
    print(f"\n--- {label} ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=int, required=True, choices=[1, 2])
    args = parser.parse_args()
    main(args.run)
