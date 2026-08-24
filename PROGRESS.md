# PROGRESS

Build log and current status for the Automated Micro-Influencer Outreach
System. Numbers below are from the latest real pipeline runs, not estimates.
Last updated: 2026-08-25.

---

## Summary

| Stage | Status | Output |
|---|---|---|
| 1. Discovery | ✅ Complete | 78 micro-influencers (5k–100k subs) |
| 2. Filtering | ✅ Complete | 69 PASS / 9 FAIL, with per-channel reasons |
| 3. Enrichment | ✅ Complete | 69 profiles · 37 emails · 49 Instagram · 69 websites |
| 4. Personalization | ✅ Complete | 69 / 69 messages, all word-count compliant |
| 5. Sending & Tracker | ✅ Complete | 69 tracker rows · 37 emails · 49 DMs queued |
| Docs / tests / hygiene | ✅ Complete | README, PROMPTS, 19 unit tests, key leak removed |

---

## Stage 1: Influencer Discovery — ✅ COMPLETE

Two-call strategy: `search.list` collects channel IDs across three queries per
niche, then `channels.list` (batched, 50 IDs/call) hydrates full metadata.

**Why two calls:** `search.list` returns a description truncated to ~100 chars
and no subscriber count. The full description — where creators put their
business email — comes only from `channels.list`. An earlier version saved the
truncated snippet, which is why email extraction was 0%. `--refresh`
re-hydrates existing IDs for ~2 units each instead of re-running 100-unit
searches.

**Output:** `data/raw_channels.{csv,json}` — **78 channels**
Niches: Technology 17, Finance 22, Beauty 15, Fitness 15, Gaming 9.

---

## Stage 2: Filtering & Classification — ✅ COMPLETE

100-point rubric: engagement 40, geography 20, niche fit 20, maturity 10,
subscriber band 10. Pass gate (all four): engagement ≥ 1.0%, total ≥ 55,
≥ 1 niche keyword hit, recent-video stats available.

**Bug fixed:** the original engagement metric was `(lifetime views / video
count) / subscribers` — a reach ratio, not engagement. It pinned 19 channels at
the 100% cap (one read 22,336%) and passed all 78, so the filter did nothing.
Replaced with real recent-upload `(likes + comments) / views`; the reach ratio
is still reported, honestly renamed `view_to_sub_ratio_pct`.

**Output:** `data/filtered_channels.csv` (all 78, with PASS/FAIL + reason),
`data/shortlisted.{csv,json}` (**69 PASS**). Engagement range across the 69
shortlisted: 1.10%–14.97%, median ~3.9% (the 1.0% floor is the pass gate).

Example FAIL reasons (verbatim from the data):
- *SkinCare by Pharmacist Preet* — engagement 0.71% < 1.0% floor
- *CRAZY FITNESS WITH LAKHAN* — engagement 0.18% < 1.0% floor; brand-fit 54.8 < 55
- *Paisa Bolta Hai* — no 'Finance' keyword match in profile text

---

## Stage 3: Profile Enrichment — ✅ COMPLETE

`brandingSettings.channel.contactEmail` is OAuth-gated (empty for an API key),
so contact details are recovered from public sources in priority order, each
tagged with its origin in the `email_source` column: channel description →
channel keywords → recent video descriptions → `/about` page → link-in-bio
pages. Recent videos come from the shared cross-stage cache, so Stage 3 spends
almost no new quota.

**Output:** `data/enriched_profiles.{csv,json}` — **69 profiles**

| Field | Coverage |
|---|---|
| Contact email (verified) | **37 / 69 (53%)** |
| Instagram handle | **49 / 69 (71%)** |
| Website | 69 / 69 |
| Content themes | 69 / 69 |

Unverifiable emails are marked `Not Found` (SPEC §3), never guessed.

**Extraction bugs fixed (found by auditing the values, not just the counts):**
- Instagram false positives from word fragments — `ins**ig**ht` → `/insight`,
  `conf**ig**urable` → `/urable`. Fixed with word boundaries + a mandatory `@`
  and a minimum-length rule. This legitimately dropped the inflated 69/69 IG
  count to a real 49/69.
- "Website" values that were YouTube's own CDN assets
  (`gstatic.com/.../emojis-png-15.1.json`, ×24). Fixed with a host/suffix
  denylist and `is_creator_website()`.
- Obfuscated-"at" emails matching inside words — `www.wh@sapp.com` from
  "whatsapp", `indian@hletics` from "athletics". Fixed by requiring bracketed
  or whitespace-delimited `at`/`dot` separators.
- Labels glued to addresses — `inquiries-sk.maijul786@gmail.com`. Fixed by
  stripping known prefixes in `clean_email`.

Post-fix audit confirms zero junk handles, zero CDN "websites", zero malformed
emails; all 37 emails are unique and well-formed.

---

## Stage 4: AI Message Personalization — ✅ COMPLETE

`personalize.py` generates a 60–90 word email pitch and a 15–30 word Instagram
DM per creator, grounded in real metrics and recent video titles. Word counts
are **verified in code** and regenerated with corrective feedback until
compliant; the collaboration angle is assigned deterministically before the
call so all six angles appear (they otherwise collapse to one). Full write-up in
[`PROMPTS.md`](PROMPTS.md).

**Output:** `data/personalized_messages.{csv,json}` — **69 / 69 messages**

| Metric | Result |
|---|---|
| Word-count compliant | **69 / 69** |
| Email pitch length | 62–89 words (bound 60–90) |
| Instagram DM length | 22–30 words (bound 15–30) |
| Unique subject lines | 69 / 69 |
| Avg generation attempts | 1.30 |
| Failed / empty | 0 |

Angle mix: Brand Ambassador 19, Sponsored 15, UGC 13, Affiliate 9, Paid
Placement 7, Barter 6.

### The quota problem and how it was solved

Gemini's free tier allows a hard **20 `generateContent` requests per day, per
model**, while 69 creators need ~90 requests including retries. A single-model
run stopped at exactly 20 and returned HTTP 429 `RESOURCE_EXHAUSTED` for
everything after — this was a quota wall, not a code defect, and switching
`gemini-2.5-flash` → `gemini-3.5-flash` confirmed the cap applies per model.

`call_llm` now falls back in two tiers:

1. **Rotate Gemini models** — each has its own 20/day bucket, so the run walks a
   pool of five. A 429 naming a *per-day* quota retires that model for the run; a
   per-minute burst limit only backs off and retries. Conflating the two would
   discard a model that was merely rate-limited.
2. **Fall back to Mistral** (`mistral-small-latest`) — metered per-minute rather
   than per-day, removing the daily ceiling entirely.

The final run needed **only tier 1**: `gemini-3.5-flash` and `gemini-3.6-flash`
hit their caps and were retired, after which `gemini-flash-lite-latest` (26) and
`gemini-3.1-flash-lite` (22) finished the job, plus 1 from `gemini-3.6-flash`
before it retired and 20 reused from cache. Mistral is wired in and verified
against the live API, but was not required. Each row records its model in a
`generated_by` column so the dataset never implies a single-model run.

The cache (`data/.personalize_cache.json`) only reuses an entry if it actually
met the word bounds, so a re-run regenerates exactly what is missing rather than
trusting stale non-compliant output.

---

## Stage 5: Sending Layer & Tracker — ✅ COMPLETE

Selects creators with a verified email, builds the full message (deterministic
greeting + LLM body + signature), sends via SMTP (`--mode live`) or simulates
(`--mode simulate`, default). The tracker is **upserted by `channel_id`** — one
row per influencer no matter how many runs — and an already-contacted creator is
logged `DUPLICATE_PREVENTED` instead of re-mailed. Instagram DMs are never
auto-sent; they export to `data/instagram_dm_queue.csv` as
`QUEUED_FOR_MANUAL_SEND` (SPEC §5).

**Bug fixed earlier:** the tracker appended a row per attempt and had grown to
390 rows for 78 influencers; rebuilt as an upsert. Also removed a hardcoded
YouTube API key that was sitting as a fallback default in `tests/test_1.py` —
keys must come only from `.env` since the repo is pushed publicly.

**Output:** `data/outreach_tracker.{csv,json}` — **69 rows, one per influencer**
(69 unique `channel_id`s, verified). Simulate-mode run: 23 emails simulated,
14 `DUPLICATE_PREVENTED` (already contacted in an earlier run), 32
`SKIPPED_NO_EMAIL`, 0 `SKIPPED_NO_MESSAGE`, 0 failures. 23 + 14 = the 37
verified emails. `data/instagram_dm_queue.csv` holds **49 DMs**
`QUEUED_FOR_MANUAL_SEND`; the other 20 creators have no discoverable handle.

**Bug fixed:** rows whose channel had left the shortlist were being carried over
from a superseded 78-channel run, so the tracker claimed 78 processed
influencers against a 69-creator dataset. History is still consulted for
duplicate prevention, but only current creators are written out.

---

## Documentation, tests & hygiene — ✅ COMPLETE

- [`README.md`](README.md) — rewritten to real numbers, full methodology.
- [`PROMPTS.md`](PROMPTS.md) — prompt engineering, failure modes, fixes.
- [`tests/test_pipeline.py`](tests/test_pipeline.py) — 19 offline unit tests
  (no API keys, no pytest — standard library only); all passing.
- `.gitignore` now commits the `data/` deliverables (ignoring only the large
  regenerable caches); `.env.example` added; `main.py` exposes `--refresh` and
  `--force`.
- Hardcoded API key removed from the test file.
- `requirements.txt` trimmed: `google-generativeai` was listed but never
  imported (Gemini is called over plain REST via `requests`).

---

## Submission status — ✅ READY

All five stages run end to end against live APIs and every deliverable in
`data/` is current and mutually consistent:

| File | Rows | Note |
|---|---|---|
| `raw_channels.csv` | 78 | Stage 1 discovery |
| `filtered_channels.csv` | 78 | audit trail, PASS/FAIL + reason |
| `shortlisted.csv` | 69 | passed the gate |
| `enriched_profiles.csv` | 69 | 37 emails, 49 Instagram |
| `personalized_messages.csv` | 69 | all word-count compliant |
| `influencer_dataset.csv` | 69 | **SPEC §7-B dataset** — all 9 required fields |
| `outreach_tracker.csv` | 69 | **SPEC §7-D tracker** — the primary deliverable |
| `instagram_dm_queue.csv` | 49 | manual DM hand-off |

Optional polish, not blocking: capture a screenshot or short demo of a full
`--stage all` run.
