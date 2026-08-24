# Automated Micro-Influencer Outreach System

An end-to-end pipeline that discovers micro-influencers on YouTube, scores and
filters them against transparent criteria, enriches the survivors with real
contact details and content themes, generates tailored outreach with Google
Gemini, and tracks sending with built-in duplicate prevention.

Built for the **EDXSO AI Engineer Intern — Assignment 1**. The assignment brief
lives in [`SPEC.md`](SPEC.md) and is the source of truth this implementation is
measured against.

---

## Results from the latest full run

| Stage | Output | Count |
|---|---|---|
| 1. Discovery | micro-influencers found (5k–100k subs) | **78** |
| 2. Filtering | scored → **PASS / FAIL** | **69 PASS / 9 FAIL** |
| 3. Enrichment | shortlisted profiles enriched | **69** |
| — | ↳ contact emails verified | **37 / 69 (53%)** |
| — | ↳ Instagram handles found | **49 / 69 (71%)** |
| 4. Personalization | email pitch + IG DM per creator | **69** |
| 5. Sending / Tracker | one row per influencer, deduped | **69** |
| Export | SPEC §7-B flat dataset (all 9 required fields) | **69** |

Engagement rate across the shortlisted set ranges **1.10% – 14.97%** (median
~3.9%), the realistic band for genuine micro-influencer audiences — the 1.0%
floor is the pass gate, so nothing below it survives Stage 2.

All 69 messages are **word-count compliant**: email pitches land in 62–89 words
against the required 60–90, DMs in 22–30 against 15–30, at an average of 1.30
generation attempts. All 69 subject lines are unique.

> Every figure above is produced by running the code against live APIs — none of
> it is hand-entered. Emails that could not be verified are marked `Not Found`,
> never guessed (SPEC §3, §10). Each row records which model wrote it in a
> `generated_by` column, so the dataset never implies a single-model run.

**The single deliverable file is [`data/influencer_dataset.csv`](data/influencer_dataset.csv)**
— 69 influencers with all nine fields SPEC §7-B asks for. See
[`demo/`](demo/README.md) for captured proof of a run, and
[`data/outreach_tracker.csv`](data/outreach_tracker.csv) for the SPEC §7-D
outreach log.

---

## Architecture

```
        YouTube Data API v3
                │
  Stage 1  Discovery ......... search.list → channels.list (full metadata)
                │             data/raw_channels.{csv,json}          (78 channels)
                ▼
  Stage 2  Filtering ......... 5-factor score + hard pass gate + reason
                │             data/filtered_channels.csv  (all 78, audit trail)
                │             data/shortlisted.{csv,json}          (69 PASS)
                ▼
  Stage 3  Enrichment ....... recent-video themes, email/IG/website extraction
                │             data/enriched_profiles.{csv,json}     (69 profiles)
                ▼
  Stage 4  Personalization .. Gemini Flash (Mistral fallback), verified words
                │             data/personalized_messages.{csv,json} (69 × 2 msgs)
                ▼
  Stage 5  Sending + Tracker  SMTP or simulate, upsert-by-channel, dedupe
                              data/outreach_tracker.{csv,json}      (69 rows)
                              data/instagram_dm_queue.csv  (manual DM hand-off)
```

A shared API layer, [`src/utils/youtube.py`](src/utils/youtube.py), centralises
quota accounting and a **disk-backed recent-video cache** so Stages 2 and 3 each
fetch a channel's videos only once. A complete run of Stages 1–3 spends roughly
**160 quota units** of the 10,000/day free allowance.

---

## Project structure

```
edx/
├── src/
│   ├── discovery/discover.py        # Stage 1 — YouTube discovery
│   ├── filtering/filter.py          # Stage 2 — scoring & classification
│   ├── enrichment/enrich.py         # Stage 3 — email/IG/theme extraction
│   ├── personalization/personalize.py  # Stage 4 — Gemini message generation
│   ├── sending/send.py              # Stage 5 — sending layer & tracker
│   └── utils/
│       ├── config.py                # paths + env-only API keys
│       ├── youtube.py               # shared API layer, quota, video cache
│       └── export_dataset.py        # SPEC 7-B dataset join (no API calls)
├── tests/test_pipeline.py           # offline unit tests (19 cases, no keys)
├── data/                            # all committed CSV/JSON deliverables
│   └── influencer_dataset.csv       # ← the SPEC 7-B deliverable (69 rows)
├── demo/                            # captured run output + screenshots
├── main.py                          # unified CLI — the only entrypoint
├── SPEC.md                          # the assignment (read-only reference)
├── PROMPTS.md                       # prompt engineering write-up
├── PROGRESS.md                      # build log / status
├── .env.example                     # copy to .env and fill in keys
└── requirements.txt
```

---

## How each stage works

### Stage 1 — Discovery
`search.list` finds channel IDs across three queries per niche
(Technology, Fitness, Beauty, Gaming, Finance); IDs are then hydrated in batches
of 50 via `channels.list` with `part=snippet,statistics,contentDetails,brandingSettings`.

**Why two calls.** `search.list` returns neither subscriber counts nor the full
description — its `snippet.description` is truncated to ~100 characters. The full
description (where creators put their business email) comes **only** from
`channels.list`. An earlier version saved the truncated snippet and consequently
extracted 0% emails; `--refresh` re-hydrates existing IDs for ~2 units each
instead of re-running 100-unit searches.

### Stage 2 — Filtering & classification (100-point rubric)

| Factor | Points | Basis |
|---|---:|---|
| Engagement rate | 40 | mean `(likes + comments) / views` over recent uploads, saturating at 5% |
| Geography | 20 | India = 20, nearby market = 10, undisclosed = 8, other = 4 |
| Niche fit | 20 | keyword hits across name + description + channel keywords |
| Channel maturity | 10 | account age (reliability proxy) |
| Subscriber sweet-spot | 10 | 10k–80k core micro band |

**Pass gate (all must hold):** engagement ≥ 1.0%, total score ≥ 55, ≥ 1 niche
keyword hit, and recent-video stats actually available. `filtered_channels.csv`
records every channel with an explicit PASS/FAIL and a human-readable reason,
e.g. *"engagement 0.18% < 1.0% floor; brand-fit score 54.8 < 55"* — satisfying
the SPEC requirement to show **which influencers passed/failed and why**.

**What changed and why.** The first implementation computed engagement as
`(lifetime views / video count) / subscribers` — a *reach* ratio, not
engagement. It pinned 19 channels at the 100% cap (one read 22,336%) and passed
all 78, so the filter did nothing. This version reads real recent-upload
statistics; the reach ratio is still reported, honestly named
`view_to_sub_ratio_pct`.

### Stage 3 — Profile enrichment
`brandingSettings.channel.contactEmail` is now OAuth-gated and returns empty for
an API key, so contact details are recovered from public sources in priority
order, each tagged with where it came from (`email_source` column):

1. Channel description
2. Channel keywords
3. Recent video descriptions
4. Channel `/about` page
5. Link-in-bio pages (Linktree / Beacons / personal site)

Extraction is defensive — it rejects YouTube's own CDN asset URLs as "websites",
word-fragment false-positive Instagram handles (`insight` → `ig`), and
obfuscated-"at" matches inside words like *whatsapp*. Anything unverified is
`Not Found`. See the enrichment module docstring for the full list of guards.

### Stage 4 — AI personalization
Gemini Flash writes a **60–90 word** email pitch and a **15–30 word** Instagram
DM per creator, grounded in that creator's real metrics and recent video titles.
Two problems the naive approach hit — the model ignoring word limits, and
collapsing all six collaboration angles into one — are solved by **verifying word
counts in code and retrying with corrective feedback**, and by **assigning the
collaboration angle deterministically before the call**. Full detail in
[`PROMPTS.md`](PROMPTS.md).

**Surviving free-tier quotas.** Gemini's free tier allows only **20
`generateContent` requests per day, per model**, while 69 creators need ~90
requests including word-count retries. A single-model run therefore stops at 20
and returns HTTP 429 `RESOURCE_EXHAUSTED`. Stage 4 handles this with a two-tier
fallback in `call_llm`:

1. **Rotate Gemini models.** Each model has its own 20/day bucket, so the run
   walks a pool of five. A 429 whose body names a *per-day* quota retires that
   model for the run; a per-minute burst limit only triggers a backoff. This
   distinction matters — conflating them would throw away a model that was
   merely rate-limited.
2. **Fall back to Mistral.** `mistral-small-latest` is metered per-minute rather
   than per-day, so it removes the daily ceiling entirely.

Completed messages are cached in `data/.personalize_cache.json` and only reused
if they actually met the word bounds, so a re-run regenerates exactly what's
missing rather than trusting stale non-compliant output.

The committed run needed **only tier 1** — model rotation alone produced all 69
(26 from `gemini-flash-lite-latest`, 22 from `gemini-3.1-flash-lite`, 1 from
`gemini-3.6-flash`, 20 reused from cache) after two models hit their daily caps.
Mistral is wired in and verified, but was not required.

### Stage 5 — Sending layer & tracker
Selects creators with a verified email, builds the full message (deterministic
greeting + LLM body + signature), and either sends via SMTP (`--mode live`) or
simulates with a clearly-marked receipt (`--mode simulate`, default). The
tracker is **upserted by `channel_id`**, so it holds exactly one row per
influencer no matter how many times it runs; an already-contacted creator is
recorded as `DUPLICATE_PREVENTED` rather than re-mailed. Instagram DMs are
**never auto-sent** (no compliant API exists) — they are exported to
`instagram_dm_queue.csv` as `QUEUED_FOR_MANUAL_SEND`, per SPEC §5.

---

## Setup

### 1. Keys
```bash
cp .env.example .env
```
Fill in `YOUTUBE_API_KEY` ([console](https://console.cloud.google.com/apis/credentials),
enable "YouTube Data API v3") and `GEMINI_API_KEY`
([AI Studio](https://aistudio.google.com/app/apikey)). SMTP values are only
needed for live sending. `.env` is gitignored — never commit real keys.

### 2. Install
```bash
pip install -r requirements.txt
```

### 3. Run
Whole pipeline:
```bash
python main.py --stage all
```
Individual stages (each reads the previous stage's output from `data/`):
```bash
python main.py --stage discover      # add --refresh to re-hydrate cheaply
python main.py --stage filter
python main.py --stage enrich
python main.py --stage personalize   # add --force to ignore the message cache
python main.py --stage send --mode simulate   # or --mode live
python main.py --stage export        # rebuild the SPEC 7-B dataset (no API calls)
```

### 4. Tests
```bash
python -m unittest discover -s tests -v
```
19 offline unit tests cover engagement scoring, word-count verification,
extraction guards, and tracker keying. They need no API keys and no pytest —
they run on the standard library alone.

---

## Tech stack

- **Python 3.10+**
- **APIs:** YouTube Data API v3 (discovery, stats, videos); Google Gemini Flash
  with a Mistral `mistral-small-latest` fallback (message generation)
- **Libraries:** `requests` (REST + link-in-bio fetching), `python-dotenv`,
  stdlib `smtplib`/`email` for sending. No pandas — data I/O uses the `csv` and
  `json` standard library.

---

## Scaling from 50 → 500+ creators

- **Quota:** discovery via cheap `channels.list` batches (1 unit / 50 IDs) plus
  the shared video cache keeps a 500-creator run well inside 10,000 units/day;
  persist the cache in SQLite/Postgres to span multiple days.
- **Enrichment:** the link-in-bio fetches are I/O-bound — move to `asyncio`/a
  worker queue and add Playwright for JS-rendered creator sites.
- **LLM:** Stage 4 already runs concurrently with an on-disk cache; raise
  `MAX_WORKERS` against Gemini's rate limits.
- **Sending:** swap SMTP for SendGrid/SES with webhook tracking for opens,
  clicks, and automated follow-ups.

---

## Limitations & ethical compliance

- **Email privacy:** every email comes from a creator's own public description or
  linked public page; unverifiable ones are marked `Not Found`, never guessed
  (SPEC §3, §10).
- **Instagram DMs:** automating Instagram DMs violates Meta's Terms without a
  verified Business App, so this project does not bypass that — it generates the
  DM and simulates a manual send workflow (SPEC §5).
- **Engagement metrics** are a public-data proxy — `(likes + comments) / views`,
  since YouTube removed public dislike counts and true audience-demographic data
  needs channel-owner OAuth.
- **API keys** are read only from `.env`; none are hardcoded, because the repo is
  submitted publicly to GitHub.
