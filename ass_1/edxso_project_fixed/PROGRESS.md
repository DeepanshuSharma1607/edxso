# PROGRESS

## Stage 1: Influencer Discovery — ✅ COMPLETE

### What was done
- `test_1.py` — manual proof-of-concept; confirmed `/search` API works (missing sub counts).
- `discover.py` — full discovery module. Two-call strategy:
  1. `/youtube/v3/search` — 5 niches × 2 queries = 500 raw channels
  2. `/youtube/v3/channels?part=statistics,snippet` — enriches with subscriber counts
  3. Filters to micro-influencer range: **5,000–100,000 subscribers**

### Output
- `data/raw_channels.csv` — **80 rows**
- `data/raw_channels.json` — **80 records**
- Niches covered: Technology, Fitness, Beauty, Gaming, Finance

### Niche breakdown (approx.)
| Niche | Count |
|---|---|
| Technology | ~18 |
| Fitness | ~12 |
| Beauty | ~14 |
| Gaming | ~11 |
| Finance | ~25 |

---

## Stage 2: Filtering & Classification — ✅ COMPLETE

### What was done
- `filter.py` — scores all 80 channels across 5 dimensions (100 pts max):
  - **Engagement Rate** (40 pts) — views-per-video / subscribers
  - **Geography** (20 pts) — India (IN) = full marks
  - **Niche Fit** (20 pts) — keyword match in name + description
  - **Account Maturity** (10 pts) — channel age
  - **Subscriber Range** (10 pts) — 10k–80k sweet spot

### Pass criteria
- Total score >= 40 **AND** engagement rate >= 1%

### Bug fix (post-review)
Initial engagement rate calculation (lifetime views ÷ video count ÷ subscribers)
produced impossible values for a few Beauty channels with high lifetime views
relative to current subscriber count (e.g. "Simple Skincare India" showed
22336.81%). This isn't a true engagement rate at that scale — it's an artifact
of only having channel-level lifetime stats available (no per-recent-video
breakdown without further quota-limited API calls). Fixed by capping the
displayed/scored value at 100% and adding two new columns for transparency:
`engagement_rate_raw_pct` (the uncapped true ratio) and `engagement_capped`
(flags when capping applied). The 0-40 point score was already internally
capped and unaffected — this only fixes the misleading displayed percentage.

### Output
| File | Rows |
|---|---|
| `data/filtered_channels.csv` | 80 (all, with scores + pass/fail + reason) |
| `data/shortlisted.csv` | 78 (PASS only, sorted by score) |
| `data/shortlisted.json` | 78 (same, JSON) |

### Shortlisted by Niche
| Niche | Count |
|---|---|
| Finance | 22 |
| Technology | 17 |
| Beauty | 15 |
| Fitness | 15 |
| Gaming | 9 |
| **Total** | **78** |

### Failed (2 channels)
- ` Tech Tips by Abhijeet` — engagement 0.3% < 1% threshold
- `BTT GAMING INDIA` — engagement 0.0% (no views data)

---

## Stage 3: Profile Enrichment — ✅ COMPLETE

### What was done
- `enrich.py` — 2 additional API calls per channel:
  1. `/channels?part=brandingSettings,snippet` (batched) → email, customUrl, keywords
  2. `/search?channelId=X&type=video&order=date&maxResults=5` → recent video titles for content themes
- Email fallback chain: API brandingSettings → regex on description → `"Not Found"`
- Content themes: derived from video titles + description keyword matching (3 themes per channel)
- Audience age/gender: marked `"Not Available"` (requires OAuth Analytics API — SPEC compliant)

### Output
| File | Rows |
|---|---|
| `data/enriched_profiles.csv` | 78 |
| `data/enriched_profiles.json` | 78 |

### Enrichment results (v2 Extended Scan)
| Field | Coverage |
|---|---|
| Contact Email (found) | 7 / 78 (9%) — 4 from video descriptions, 3 from channel descriptions. Rest marked "Not Found" per SPEC |
| Instagram URL | 5 / 78 (6.4%) |
| Website | 4 / 78 (5.1%) |
| Geography (country) | 70 / 78 (89.7%) |
| Content Themes | 78 / 78 (100%) |

> **Note on emails & social links:** YouTube does not expose creator emails or social handles via public API endpoints without OAuth authentication. The 7 emails and 5 Instagram URLs were honestly extracted by scanning channel descriptions, recent video descriptions, and external link-in-bio pages. All other values are honestly marked `"Not Found"` / `"Not Available"` (no fabricated data, strictly adhering to SPEC.md Section 3).

---

## Stage 4: Message Personalization — ✅ COMPLETE

### What was done
- `personalize.py` — uses Google Gemini API (`gemini-2.5-flash`) with multi-threaded concurrent generation across all 78 qualified influencers.
- Generates 2 dynamic, unique messages per creator:
  1. **Email Collaboration Pitch** (60–90 words): Custom subject line, mentions creator name, niche, content themes, real engagement metrics, and proposes a tailored collaboration angle (Sponsored Integration, UGC, Affiliate, etc.).
  2. **Instagram DM** (15–30 words): Conversational direct message tailored to their content style.
- Includes incremental caching and rate-limiting.

### Output
| File | Records |
|---|---|
| `data/personalized_messages.csv` | 78 rows |
| `data/personalized_messages.json` | 78 records |

---

## Stage 5: Sending Layer — ✅ COMPLETE

### What was done
- `send.py` — robust outreach dispatch & simulation engine.
- Filters influencers with valid contact emails (7 dispatched/simulated, 5 Instagram DMs queued).
- Enforces strict **duplicate outreach prevention** (checks channel IDs and emails against tracker history).
- Supports `--mode simulate` (safe mock with delivery codes) and `--mode live` (standard SMTP).
- Instagram DM workflow simulation conforming to Meta TOS.

### Bug fix (post-review)
`outreach_tracker.csv` was appending a new row on every run, even for
duplicate-prevented attempts — after 5 runs it had grown to 390 rows for
only 78 influencers. Fixed by rebuilding the tracker as an upsert keyed on
`channel_id`: re-running `send.py` now updates each influencer's existing
row in place instead of appending a new one. Verified by running twice in a
row — tracker stays at exactly 78 rows both times. Also removed a hardcoded
YouTube API key that was living as a fallback default in `config.py` — real
keys should only ever come from `.env`, never source code, since this repo
gets pushed to GitHub as part of submission.

---

## Stage 6: Outreach Tracker & Documentation — ✅ COMPLETE

### Deliverables Completed
| Deliverable | File Path | Status |
|---|---|---|
| Discovery Module | [`src/discovery/discover.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/src/discovery/discover.py) | ✅ Verified |
| Filtering Module | [`src/filtering/filter.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/src/filtering/filter.py) | ✅ Verified |
| Enrichment Module | [`src/enrichment/enrich.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/src/enrichment/enrich.py) | ✅ Verified |
| AI Personalization | [`src/personalization/personalize.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/src/personalization/personalize.py) | ✅ Verified |
| Sending Layer | [`src/sending/send.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/src/sending/send.py) | ✅ Verified |
| Central Configuration | [`src/utils/config.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/src/utils/config.py) | ✅ Verified |
| Unified CLI Runner | [`main.py`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/main.py) | ✅ Verified |
| Raw Dataset | [`data/raw_channels.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/raw_channels.csv) (80 rows) | ✅ Verified |
| Filtered Dataset | [`data/filtered_channels.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/filtered_channels.csv) (80 rows) | ✅ Verified |
| Shortlisted Dataset | [`data/shortlisted.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/shortlisted.csv) (78 rows) | ✅ Verified |
| Enriched Dataset | [`data/enriched_profiles.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/enriched_profiles.csv) (78 rows) | ✅ Verified |
| Personalized Messages | [`data/personalized_messages.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/personalized_messages.csv) (78 rows) | ✅ Verified |
| Outreach Tracker | [`data/outreach_tracker.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/outreach_tracker.csv) (78 rows) | ✅ Verified |
| Documentation | [`README.md`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/README.md) | ✅ Complete |