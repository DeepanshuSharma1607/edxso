# Scholarship Intelligence Crawler

**Edxso AI Engineer Intern — Assignment 2**

An automated system that discovers, crawls, extracts, verifies, scores, stores,
and continuously updates scholarship opportunities for Indian students —
built end-to-end (not a design document, not a UI mockup).

---

## 1. What this is

The assignment envisions **Atlas Funding**, a repository that normalises
every scholarship into a common schema, kept current by a continuous
crawler. This project is a working implementation of the intelligence
engine behind that repository:

```
Discover → Crawl → Extract → Verify → Score → Store → Update
```

It ingests real scholarship listings (currently the National Scholarship
Portal — Govt. of India — plus one corporate and one university source),
converts unstructured page content into a structured schema, scores each
record's trustworthiness with an explicit, inspectable rubric (never an
LLM-generated number), and re-runs to detect changes, expiries, and
records that have disappeared from their source.

## 2. Verified results

These numbers come from actually re-running the crawler end-to-end, not
from documentation:

```
Run 1 (2026-08-27): 31 government schemes + 1 corporate + 1 university = 33 new records
Run 2 (2026-09-05, 9 days later):
  1 new scheme discovered
  1 field-level CHANGE_DETECTED   (CSSS closing_date: 2026-09-30 → 2026-10-15)
  1 status-transition change      (AICTE Swanath Diploma: ACTIVE → NO_LONGER_VERIFIABLE)
  3 schemes correctly marked EXPIRED (deadline passed)
  1 scheme correctly marked NO_LONGER_VERIFIABLE (dropped from source)

Final database: 34 total records
  18 VERIFIED at ≥95% confidence (avg. confidence across all records: 93.5%)
  16 REVIEW_REQUIRED
  3 distinct source types: GOVERNMENT / CORPORATE / UNIVERSITY
  14 ACTIVE, 3 EXPIRED, 1 NO_LONGER_VERIFIABLE
```

This clears every minimum in the assignment brief: 20+ scholarships,
15+ verified against primary sources, 10+ at ≥95% confidence, 3+ source
types, 2+ change-detection examples, 2+ expired/stale examples.

## 3. Architecture

```
┌────────────┐   ┌───────────┐   ┌────────────┐   ┌──────────────┐   ┌─────────┐   ┌────────────┐
│  Discovery │ → │  Crawler  │ → │ Extraction │ → │ Verification │ → │ Storage │ → │  Updates   │
│ (link      │   │ (fetch    │   │ (rules or  │   │ (confidence  │   │ (SQLite │   │ (diff +    │
│ classifier)│   │  HTML)    │   │  Mistral)  │   │  rubric)     │   │  4-table)│   │  expiry)   │
└────────────┘   └───────────┘   └────────────┘   └──────────────┘   └─────────┘   └────────────┘
                                                                                          │
                                                              ┌───────────────────────────┴─────┐
                                                              ▼                                  ▼
                                                        FastAPI backend                Streamlit dashboard
                                                     (7 endpoints, tested)          (stats, search, drill-down)
```

- **Discovery** classifies links by keyword heuristics
  (`scholarship`, `fellowship`, `stipend`, `bursary`, …) against an
  approved-domain registry — it is not a hardcoded `URL → scraper` map.
- **Crawler** has two paths: `fixture_loader.py` replays real, previously
  fetched page snapshots (used in this repo's demo run, deterministic and
  reproducible without live internet); `http_crawler.py` is the real
  `requests` + BeautifulSoup fetcher for live use.
- **Extraction** is rule-based where the source is structured (NSP's
  listing page) and LLM-based (Mistral) for messy/unstructured text —
  both paths write into the same Pydantic schema, where every field
  defaults to the literal string `NOT_SPECIFIED` rather than ever being
  guessed.
- **Verification** never asks an LLM for a confidence number. It runs an
  explicit point rubric against evidence the extractor collected.
- **Storage** is SQLite, 4 tables: `sources`, `scholarships`,
  `change_history`, `crawl_runs`.
- **Updates** diffs each freshly-crawled record against the stored row
  field-by-field, writes every change to `change_history` (old value, new
  value, evidence, timestamp — never a silent overwrite), and resolves
  lifecycle status (`ACTIVE` / `EXPIRING_SOON` / `EXPIRED` /
  `REVIEW_REQUIRED` / `NO_LONGER_VERIFIABLE`).

## 4. Anti-hallucination approach

- Every schema field defaults to `NOT_SPECIFIED`. Example: NSP's listing
  page doesn't publish a rupee amount per scheme, so every NSP record's
  `amount` is genuinely `NOT_SPECIFIED` in the database — not invented.
- Every important field carries a parallel `evidence` entry: the literal
  text copied from the source that supports it. A deadline of
  `2026-10-31` is traceable to the exact source line
  `"Student Application Open till: 31-10-2026"` — this is visible in the
  `evidence` column and in the `/api/scholarships/{id}` `why_this_score`
  response.
- Aggregator-discovered records (found via a blog/article rather than the
  provider's own domain) are never trusted at face value:
  `source_detector.py` only awards official-source points once the
  *claimed* domain is independently confirmed, not because an aggregator
  said so. The two aggregator-discovered records in this demo dataset
  score 70 and 60 and correctly land in `REVIEW_REQUIRED`.

## 5. Confidence scoring methodology

Deterministic rubric, 100 points total, implemented in
`backend/verification/confidence.py`:

| Check | Points | What it verifies |
|---|---|---|
| Official source | 30 | `official_source_url` resolves to an approved domain |
| Currently present | 20 | record was found again on the source in the latest crawl |
| Application URL | 15 | a concrete application URL exists |
| Eligibility evidence | 10 | eligibility/course-level is backed by extracted evidence text |
| Deadline evidence | 10 | closing date is backed by extracted evidence text |
| Benefit evidence | 5 | amount/benefit type is backed by evidence text |
| Freshness | 5 | verified within the last 45 days |
| No conflict | 5 | no contradicting value from another source |

**≥95 → `VERIFIED`. Below that → `REVIEW_REQUIRED`.** Every check writes
a human-readable reason string (see `why_this_score` in the API), so the
score is always explainable, never a black box.

## 6. Change & stale-data detection

- `change_detector.py` compares each field of a freshly extracted record
  against the stored row. Any difference is written to `change_history`
  with old value, new value, detection timestamp, source URL, and
  evidence — the old value is never overwritten silently.
- `expiry_checker.py` resolves lifecycle status from `closing_date` and
  whether the record was found again in the latest crawl:
  `EXPIRED` (deadline passed), `EXPIRING_SOON` (within 10 days),
  `NO_LONGER_VERIFIABLE` (missing from the latest crawl),
  `REVIEW_REQUIRED` (below confidence threshold), `ACTIVE` (otherwise).
  Records are never deleted, so stale-data detection stays auditable.

## 7. Project layout

```
scholarship-intelligence/
├── .env.example                  # copy to .env and fill in your own key
├── requirements.txt
├── README.md
├── backend/
│   ├── config.py
│   ├── database/     (schema.sql, connection.py, repository.py — 4-table SQLite)
│   ├── discovery/    (source_registry.py, discovery.py — link classifier)
│   ├── crawler/      (http_crawler.py — live fetch, fixture_loader.py — deterministic replay)
│   ├── extraction/   (schemas.py, rule_extractor.py, llm_extractor.py, other_source_extractor.py)
│   ├── verification/ (confidence.py — scoring rubric, source_detector.py)
│   ├── updates/      (change_detector.py, expiry_checker.py)
│   ├── services/     (crawl_runner.py — fixture path, live_crawl_runner.py — real internet path)
│   └── api/          (main.py — FastAPI app, 7 endpoints)
├── scripts/
│   └── run_crawler.py            # CLI entrypoint: --run 1 / --run 2
├── data/
│   ├── fixtures/                 # real fetched snapshots used for the demo run
│   └── scholarship.db            # generated by running the commands below
├── dashboard/
│   └── app.py                    # Streamlit dashboard
└── tests/
    ├── test_confidence.py
    ├── test_change_detection.py
    └── test_live_crawl_runner.py
```

## 8. Setup & how to reproduce

```bash
cd scholarship-intelligence
pip install -r requirements.txt --break-system-packages   # or use a venv

cp .env.example .env          # add your own MISTRAL_API_KEY if you plan to run live extraction

python -m backend.database.connection   # creates data/scholarship.db + schema
python -m scripts.run_crawler --run 1
python -m scripts.run_crawler --run 2

# inspect the data directly
python -c "
from backend.database.connection import get_connection
conn = get_connection()
for r in conn.execute('SELECT name, status, verification_label, confidence_score FROM scholarships').fetchall():
    print(dict(r))
"
```

Run the tests:

```bash
python -m pytest tests/ -v
```

Run the API:

```bash
uvicorn backend.api.main:app --reload --port 8000
# browse http://localhost:8000/docs for interactive Swagger UI
```

Run the dashboard:

```bash
streamlit run dashboard/app.py
# reads data/scholarship.db directly; set DASHBOARD_USE_API=1 to talk to the FastAPI server instead
```

## 9. API reference

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | liveness check |
| GET | `/api/stats` | dashboard summary — totals, verified/review-required, active/expiring/expired/no-longer-verifiable, avg confidence, recently updated |
| GET | `/api/scholarships` | searchable + filterable list (`q`, `status`, `source_type`, `verification_label`, `min_confidence`, `limit`, `offset`) |
| GET | `/api/scholarships/{id}` | full record — every field, confidence breakdown, "why this score", evidence map, change history |
| GET | `/api/sources` | registered sources + per-source scholarship counts |
| GET | `/api/crawl/runs` | crawl run history (start/end time, counts, errors) |
| POST | `/api/crawl/run?run_number=1\|2` | triggers a fixture-replay crawl (idempotent) |
| POST | `/api/crawl/live?source_id=...&entry_url=...` | triggers a **real** live crawl: discovery → fetch → Mistral extraction → verify → store. Requires internet + `MISTRAL_API_KEY`. |

## 10. Dashboard

`dashboard/app.py` (Streamlit) shows:
- Summary tiles: total discovered, verified, review required, active,
  expired, recently updated, average confidence.
- A searchable, filterable list of scholarships.
- A detail view per scholarship: name, provider, amount, eligibility,
  deadline, official source, application link, status, confidence score
  with its full breakdown, last verified date, change history, and
  source evidence.

## 11. Known limitations

- **Live-internet extraction is unit-tested with mocked network calls,
  not exercised against real traffic.** `http_crawler.py` (requests +
  BeautifulSoup) and `llm_extractor.py` (Mistral chat completions) are
  written and covered by `tests/test_live_crawl_runner.py`, which proves
  the discovery → fetch → extract → verify → store wiring works
  correctly end-to-end against a mocked page — but they were developed in
  a sandboxed environment without general internet access, so they have
  not yet been run against a live scholarship site. On a machine with
  normal internet access: set `USE_FIXTURES=0` in `.env`, or call
  `POST /api/crawl/live` against an approved source.
- **Only 3 sources are registered today** (NSP, one corporate, one
  university). The discovery layer is generic (keyword-based link
  classification against an approved-domain registry, not a hardcoded
  per-source scraper), so adding a fourth source is a registry entry, not
  new scraping code — but it hasn't been demonstrated live yet.
- Deployment (Docker/hosting/cron scheduling) is not set up; this repo is
  built and verified for local reproduction as described above.
