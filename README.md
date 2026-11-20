# Applied AI Engineering — Monorepo

Three end-to-end AI engineering systems built from scratch—combining adaptive conversational agents, deterministic web intelligence pipelines, and automated multi-stage outreach workflows.

Each project pairs LLM reasoning with strict engineering guardrails: deterministic scoring rubrics, schema-enforced outputs, zero-fabrication defaults, local caching, and multi-model fallback chains.

---

## Repository Index

| # | Project | Summary | Live / Proof |
|---|---|---|---|
| **01** | **[Interview Accelerator](#1-interview-accelerator)** | Voice-native AI mock interviewer that maps a resume against a JD, adapts question difficulty across 3 tiers, and computes deterministic readiness scores. | [Live App](https://interview-accelerator-ahhu.onrender.com) · [Demo Video](https://drive.google.com/file/d/17mNoSwgSx_uwf1n0Ype2ps7raPVV0P3K/view?usp=drivesdk) |
| **02** | **[Scholarship Intelligence Crawler](#2-scholarship-intelligence-crawler)** | Automated crawler, extractor, 100-point confidence verifier, and change-detection engine for Indian student scholarships. | Verified `34`-record SQLite DB + FastAPI + Streamlit |
| **03** | **[Automated Micro-Influencer Outreach System](#3-automated-micro-influencer-outreach-system)** | End-to-end YouTube creator discovery, 5-factor engagement filter, contact enrichment, and word-count-verified outreach generator. | Verified `69`-creator CSV (`data/influencer_dataset.csv`) |

---

## 1. Interview Accelerator

An AI-powered interview preparation platform. Give it a **Job Description** and your **Resume**, and it tells you how well you match the role, runs a real adaptive, voice-based mock interview that gets harder or easier based on how you are doing, and finishes with a detailed performance report and prioritized prep plan.

Built for the **AI Product Engineer Intern — Interview Accelerator Challenge**.

* 🔗 **Live App:** [https://interview-accelerator-ahhu.onrender.com](https://interview-accelerator-ahhu.onrender.com)
* 📹 **Demo Video:** [Watch on Google Drive](https://drive.google.com/file/d/17mNoSwgSx_uwf1n0Ype2ps7raPVV0P3K/view?usp=drivesdk)

> **Note:** Hosted on Render's free tier — the app spins down after ~15 minutes of inactivity, so the first request after a while may take 30–60 seconds to wake up.

### What It Does
1. **Understand the role:** Paste or upload a JD (PDF, DOCX, or plain text) → extracts role title, required/preferred skills, technical and behavioural competencies, experience expectations, and key qualifications.
2. **Understand the candidate:** Paste or upload a resume → maps it against the role: strengths, missing skills, weak areas, and specific resume claims worth probing (e.g., *"improved accuracy by 18%"* — how was that measured?).
3. **Score the fit:** Generates a Job Fit percentage with a clear breakdown of strong matches, partial matches, and missing/weak skills with rationale.
4. **Run a real adaptive interview:**
   | Level | Focus |
   |---|---|
   | **Screening** | Resume walkthrough, motivation, role fit, communication |
   | **Competency** | Technical depth, problem-solving, behavioural competencies, past projects |
   | **Deep-Dive** | Follow-ups that challenge vague/weak answers, probe resume claims, and test reasoning with "why/how" and scenario questions |
5. **Voice-native experience:** Speak answers instead of typing — transcribed locally, evaluated, and followed up out loud. Saying or typing *"stop the interview"* ends the session cleanly.
6. **Performance report:** Overall score, per-level competency breakdown, strengths, weaknesses, prioritized prep plan, and readiness verdict (`80+` **Strong Candidate** · `60–79` **Interview Ready** · `40–59` **Needs Practice** · `<40` **Not Ready**).

*Intentionally excluded:* Video interview (bonus/optional requirement) was scoped out to keep focus on a solid voice-native experience.

### Screenshots

| Dashboard | Role Analysis |
|---|---|
| ![Dashboard](screenshots/ae.png) | ![Role Analysis](screenshots/aa.png) |

| AI Interview | Candidate Analysis & Job Fit |
|---|---|
| ![Interview](screenshots/ac.png) | ![Candidate Analysis](screenshots/ad.png) |

| Job Fit By Resume |
|---|
| ![Report](screenshots/ab.png) |

### Tech Stack & Architecture

| Layer | Choice | Why |
|---|---|---|
| **Backend** | FastAPI (Python) | Async-native, clean handling of LLM calls and file uploads |
| **LLM** | Google Gemini API (`gemini-3.5-flash-lite` + fallback) | Fast, low-cost, reliable JSON-mode output |
| **Speech-to-Text** | `faster-whisper` (`tiny`, CPU/int8) | Runs locally with zero STT API cost or key |
| **Text-to-Speech** | `edge-tts` | Free, no API key required, natural-sounding voices |
| **Frontend** | Jinja2 templates + vanilla JS + CSS | Zero build step, minimal overhead |
| **File Parsing** | `pypdf`, `python-docx` | Supports PDF, DOCX, and plain text uploads |
| **Session State** | In-memory store | Simple single-instance prototype; swappable for Redis/Postgres |
| **Deployment** | Render (Web Service, Free tier) | Python deployment with environment variable secret management |

```text
app/
├── main.py                  # FastAPI app, route registration, page rendering
├── config.py                # Settings (API keys, model names, voice config) via .env
├── routers/                 # Thin HTTP layer — no business logic lives here
│   ├── ingestion.py         # Session creation, JD/resume upload
│   ├── analysis.py          # Role/candidate/fit analysis
│   ├── interview.py         # Interview start/answer/stop/report
│   └── voice.py             # Voice-answer (STT) + TTS endpoints
├── services/                # All business logic
│   ├── llm.py               # Single choke point for every Gemini call
│   ├── extraction.py        # PDF/DOCX/TXT → plain text
│   ├── analysis.py          # Role analysis, candidate analysis, job fit scoring
│   ├── interview.py         # Adaptive interview state machine
│   ├── report.py            # Deterministic scoring + LLM-written narrative
│   ├── voice.py             # faster-whisper STT, edge-tts TTS
│   └── store.py             # In-memory session store
├── models/schemas.py        # Pydantic models — Session is the single source of truth
├── prompts/                 # Prompt templates separated from orchestration logic
├── templates/               # dashboard.html, interview.html
└── static/                  # style.css, app.js, interview.js
```

* **Adaptive Loop:** One LLM call per turn evaluates the submitted answer (`1–5` score + tags such as `weak_area:system_design`) **and** generates the next question grounded in the transcript. Level progression (`screening → competency → deep-dive → done`) uses the model's `advance_level` signal bounded by `MIN_QUESTIONS_PER_LEVEL` / `MAX_QUESTIONS_PER_LEVEL` guardrails. Interviews can also end immediately without an LLM call via a spoken/typed stop phrase, a 10-minute wall-clock cap, or the **Stop Interview** button (`ended_reason`).
* **Deterministic Scoring:** Overall scores and per-level averages are computed strictly in Python from the per-answer ratings—never by asking the LLM to average its own transcript.

### Setup & Environment Variables
```bash
git clone <your-repo-url>
cd interview-accelerator   # or cd ass_3
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # Set GEMINI_API_KEY
uvicorn app.main:app --reload
```
Open `http://127.0.0.1:8000` *(Requires `ffmpeg`/`libav` on your system PATH to decode browser webm/opus recordings; first voice turn downloads the ~75MB `tiny` Whisper model).*

| Variable | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | — | **Required.** Obtain from Google AI Studio |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Primary model for analysis, interview, and report calls |
| `GEMINI_FALLBACK_MODEL` | `gemini-3.6-flash` | Tried once if primary model retries are exhausted |
| `WHISPER_MODEL_SIZE` | `tiny` | CPU-friendly (`tiny.en` also supported) |
| `TTS_VOICE` | `en-US-GuyNeural` | Any `edge-tts` voice name |

*Known limitations:* Sessions are in-memory only; STT uses the lightweight `tiny` Whisper model; no user authentication; cold starts on Render's free tier take ~30–60s.

---

## 2. Scholarship Intelligence Crawler

**Edxso AI Engineer Intern — Assignment 2**

An automated end-to-end intelligence engine behind **Atlas Funding** that discovers, crawls, extracts, verifies, scores, stores, and continuously updates scholarship opportunities for Indian students.

```text
Discover → Crawl → Extract → Verify → Score → Store → Update
```

### Verified End-to-End Results
* **Run 1 (`2026-08-27`):** `31` government schemes (National Scholarship Portal) + `1` corporate + `1` university = `33` new records.
* **Run 2 (`2026-09-05`, 9 days later):**
  * `1` new scheme discovered
  * `1` field-level `CHANGE_DETECTED` (CSSS `closing_date`: `2026-09-30` → `2026-10-15`)
  * `1` status-transition change (AICTE Swanath Diploma: `ACTIVE` → `NO_LONGER_VERIFIABLE`)
  * `3` schemes marked `EXPIRED` (deadline passed) & `1` marked `NO_LONGER_VERIFIABLE` (dropped from source)
* **Final Database (`34` total records):** `18` `VERIFIED` at $\ge 95\%$ confidence (`93.5%` average confidence across all records), `16` `REVIEW_REQUIRED`, `3` source types (`GOVERNMENT`, `CORPORATE`, `UNIVERSITY`), `14` `ACTIVE`, `3` `EXPIRED`, `1` `NO_LONGER_VERIFIABLE`.

### Architecture & Anti-Hallucination Design

```text
┌────────────┐   ┌───────────┐   ┌────────────┐   ┌──────────────┐   ┌─────────┐   ┌────────────┐
│  Discovery │ → │  Crawler  │ → │ Extraction │ → │ Verification │ → │ Storage │ → │  Updates   │
│ (link      │   │ (fetch    │   │ (rules or  │   │ (confidence  │   │ (SQLite │   │ (diff +    │
│ classifier)│   │  HTML)    │   │  Mistral)  │   │  rubric)     │   │  4-table)│   │  expiry)   │
└────────────┘   └───────────┘   └────────────┘   └──────────────┘   └─────────┘   └────────────┘
                                                                                          │
                                                              ┌───────────────────────────┴─────┐
                                                              ▼                                  ▼
                                                        FastAPI backend                Streamlit dashboard
                                                     (7+ endpoints, tested)          (stats, search, drill-down)
```

* **Zero Fabrication:** Every Pydantic schema field defaults to `NOT_SPECIFIED` rather than being guessed (e.g., NSP's listing page omits rupee amounts, so `amount` remains `NOT_SPECIFIED`). Every extracted field carries a verbatim snippet in a parallel `evidence` column exposed via `/api/scholarships/{id}` (`why_this_score`). Aggregator-discovered records only earn official-source points once the claimed domain is independently confirmed (scoring `70` and `60` in the demo dataset and landing in `REVIEW_REQUIRED`).
* **Deterministic 100-Point Confidence Rubric (`backend/verification/confidence.py`):**
  | Check | Points | What It Verifies |
  |---|---:|---|
  | Official source | `30` | `official_source_url` resolves to an approved domain |
  | Currently present | `20` | Record found again on the source in the latest crawl |
  | Application URL | `15` | Concrete application URL exists |
  | Eligibility evidence | `10` | Eligibility/course-level backed by extracted evidence text |
  | Deadline evidence | `10` | Closing date backed by extracted evidence text |
  | Benefit evidence | `5` | Amount/benefit type backed by evidence text |
  | Freshness | `5` | Verified within the last 45 days |
  | No conflict | `5` | No contradicting value from another source |
  *(Scores $\ge 95$ become `VERIFIED`; below `95` become `REVIEW_REQUIRED`.)*
* **Audit-Safe Change & Expiry Tracking:** `change_detector.py` logs every field diff to `change_history` (old value, new value, timestamp, source URL, evidence) without silent overwrites. `expiry_checker.py` resolves status into `ACTIVE`, `EXPIRING_SOON` (within 10 days), `EXPIRED`, `REVIEW_REQUIRED`, or `NO_LONGER_VERIFIABLE` without deleting rows.

### Project Layout & Setup
```text
scholarship-intelligence/
├── .env.example                  # Copy to .env and add MISTRAL_API_KEY
├── requirements.txt
├── backend/
│   ├── config.py
│   ├── database/                 # schema.sql, connection.py, repository.py (4-table SQLite)
│   ├── discovery/                # source_registry.py, discovery.py (keyword link classifier)
│   ├── crawler/                  # http_crawler.py (live), fixture_loader.py (replay)
│   ├── extraction/               # schemas.py, rule_extractor.py, llm_extractor.py, other_source_extractor.py
│   ├── verification/             # confidence.py, source_detector.py
│   ├── updates/                  # change_detector.py, expiry_checker.py
│   ├── services/                 # crawl_runner.py, live_crawl_runner.py
│   └── api/main.py               # FastAPI app
├── scripts/run_crawler.py        # CLI entrypoint: --run 1 / --run 2
├── data/                         # fixtures/ + generated scholarship.db
├── dashboard/app.py              # Streamlit dashboard
└── tests/                        # test_confidence.py, test_change_detection.py, test_live_crawl_runner.py
```

```bash
cd scholarship-intelligence
pip install -r requirements.txt
cp .env.example .env                     # Add MISTRAL_API_KEY for live extraction
python -m backend.database.connection    # Creates data/scholarship.db + schema
python -m scripts.run_crawler --run 1
python -m scripts.run_crawler --run 2
python -m pytest tests/ -v               # Run test suite
uvicorn backend.api.main:app --reload --port 8000
streamlit run dashboard/app.py           # Set DASHBOARD_USE_API=1 to query FastAPI instead of SQLite
```

*API Endpoints:* `GET /api/health`, `GET /api/stats`, `GET /api/scholarships`, `GET /api/scholarships/{id}`, `GET /api/sources`, `GET /api/crawl/runs`, `POST /api/crawl/run?run_number=1|2`, `POST /api/crawl/live?source_id=...&entry_url=...`.

*Known limitations:* Live-internet extraction (`http_crawler.py` + `llm_extractor.py`) is verified via mocked network tests (`tests/test_live_crawl_runner.py`) rather than live traffic due to sandbox restrictions; 3 sources are currently registered; no Docker/cron deployment configured yet.

---

## 3. Automated Micro-Influencer Outreach System

**EDXSO AI Engineer Intern — Assignment 1**

An end-to-end Python pipeline that discovers YouTube micro-influencers (`5k–100k` subscribers), scores and filters them against transparent criteria, enriches public contact details and video themes, generates tailored outreach with Google Gemini, and tracks sending with duplicate prevention.

### Verified Run Results
| Stage | Output | Count |
|---|---|---|
| **1. Discovery** | Micro-influencers found (`5k–100k` subs) | **78** |
| **2. Filtering** | Scored → **PASS / FAIL** (`1.10% – 14.97%` engagement, ~3.9% median) | **69 PASS / 9 FAIL** |
| **3. Enrichment** | Shortlisted profiles enriched (`37` verified emails [53%], `49` IG handles [71%]) | **69** |
| **4. Personalization** | Email pitch (`62–89` words) + IG DM (`22–30` words), `1.30` avg attempts | **69** |
| **5. Sending / Tracker** | One row per influencer, deduplicated (`data/outreach_tracker.csv`) | **69** |
| **Export** | SPEC §7-B flat dataset (`data/influencer_dataset.csv`, all 9 required fields) | **69** |

### Pipeline Architecture & Stage Details

```text
        YouTube Data API v3
                │
  Stage 1  Discovery ......... search.list → channels.list (full metadata)
                │             data/raw_channels.{csv,json}          (78 channels)
                ▼
  Stage 2  Filtering ......... 5-factor score + hard pass gate + reason
                │             data/filtered_channels.csv  (all 78, audit trail)
                │             data/shortlisted.{csv,json}          (69 PASS)
                ▼
  Stage 3  Enrichment ........ recent-video themes, email/IG/website extraction
                │             data/enriched_profiles.{csv,json}     (69 profiles)
                ▼
  Stage 4  Personalization ... Gemini Flash (Mistral fallback), verified words
                │             data/personalized_messages.{csv,json} (69 × 2 msgs)
                ▼
  Stage 5  Sending + Tracker . SMTP or simulate, upsert-by-channel, dedupe
                              data/outreach_tracker.{csv,json}      (69 rows)
                              data/instagram_dm_queue.csv  (manual DM hand-off)
```

* **Stage 1 — Quota-Aware Discovery:** Queries 3 searches per niche (Technology, Fitness, Beauty, Gaming, Finance) via `search.list` and hydrates full descriptions/stats in batches of 50 via `channels.list`. Centralizes quota tracking and a disk-backed recent-video cache in `src/utils/youtube.py`, completing Stages 1–3 in **~160 of 10,000** daily free quota units.
* **Stage 2 — 100-Point Filtering Rubric:**
  | Factor | Points | Basis |
  |---|---:|---|
  | Engagement rate | `40` | Mean `(likes + comments) / views` over recent uploads, saturating at `5%` |
  | Geography | `20` | India = `20`, nearby market = `10`, undisclosed = `8`, other = `4` |
  | Niche fit | `20` | Keyword hits across channel name, description, and channel keywords |
  | Channel maturity | `10` | Account age (reliability proxy) |
  | Subscriber sweet-spot | `10` | `10k–80k` core micro band |
  *Pass gate:* engagement $\ge 1.0\%$, total score $\ge 55$, $\ge 1$ niche keyword hit, and recent-video stats available. Every PASS/FAIL includes a human-readable explanation in `filtered_channels.csv`.
* **Stage 3 — Defensive Contact Enrichment:** Scans channel descriptions, channel keywords, recent video descriptions, `/about` pages, and link-in-bio pages (Linktree/Beacons/personal sites), tagging `email_source` and rejecting YouTube CDN URLs, word-fragment IG false positives (`insight` → `ig`), and obfuscated-"at" matches inside words like *whatsapp*. Unverified emails are strictly marked `Not Found`.
* **Stage 4 — Word-Count-Verified Personalization & Two-Tier Quota Fallback:** Deterministically assigns collaboration angles and enforces strict word bounds (`60–90` words for email pitches, `15–30` words for Instagram DMs) via code verification and corrective retries. To bypass Gemini free-tier daily per-model caps (`20` requests/day), `call_llm` rotates across a pool of 5 Gemini models (retiring models only on per-day `429` errors while backing off on per-minute bursts) and falls back to `mistral-small-latest`, caching compliant messages in `data/.personalize_cache.json`.
* **Stage 5 — Deduplicated Sending & Ethical IG Queue:** Upserts `outreach_tracker.csv` by `channel_id` (recording `DUPLICATE_PREVENTED` on re-runs) and exports Instagram DMs to `instagram_dm_queue.csv` as `QUEUED_FOR_MANUAL_SEND` to comply with Meta's Terms of Service.

### Project Structure & Setup
```text
edx/
├── src/
│   ├── discovery/discover.py
│   ├── filtering/filter.py
│   ├── enrichment/enrich.py
│   ├── personalization/personalize.py
│   ├── sending/send.py
│   └── utils/                       # config.py, youtube.py, export_dataset.py
├── tests/test_pipeline.py           # 19 offline unit tests (stdlib unittest, no API keys)
├── data/influencer_dataset.csv      # Final SPEC §7-B deliverable (69 rows)
├── demo/                            # Captured run output + screenshots
├── main.py                          # Unified CLI entrypoint
├── SPEC.md / PROMPTS.md / PROGRESS.md
├── .env.example
└── requirements.txt
```

```bash
cd edx
pip install -r requirements.txt
cp .env.example .env                             # Set YOUTUBE_API_KEY and GEMINI_API_KEY
python main.py --stage all                       # Run full pipeline
python main.py --stage send --mode simulate      # Or --mode live (requires SMTP config)
python -m unittest discover -s tests -v          # Run 19 offline unit tests
```