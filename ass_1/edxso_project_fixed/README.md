# Automated Micro-Influencer Outreach System

An end-to-end automated pipeline for discovering relevant micro-influencers, scoring & filtering them across multi-dimensional criteria, enriching their profiles with real contact and content themes, generating tailored AI pitches via Google Gemini, and tracking outreach with built-in duplicate prevention.

Built for the **EDXSO AI Engineer Intern Assignment**.

---

## 🏗 Architecture & System Workflow

```
       YouTube Data API v3 (/search)
                     ↓
          Stage 1: Influencer Discovery
          (500 raw channels queried → 80 micro-influencers: 5k–100k subs)
          Output: data/raw_channels.csv, data/raw_channels.json
                     ↓
          Stage 2: Filtering & Classification
          (Scoring rubric: Engagement, Geo, Niche fit, Maturity, Sub range)
          Output: data/filtered_channels.csv, data/shortlisted.csv (78 PASS, 2 FAIL)
                     ↓
          Stage 3: Profile Enrichment
          (Branding API + Video Details + External link-in-bio scan)
          Output: data/enriched_profiles.csv, data/enriched_profiles.json
                     ↓
          Stage 4: AI Message Personalization
          (Google Gemini 2.5 Flash: 60–90 word Email Pitch + 15–30 word Instagram DM)
          Output: data/personalized_messages.csv, data/personalized_messages.json
                     ↓
          Stage 5: Sending Layer & Duplicate Prevention
          (Live SMTP / Simulation + Persistent Deduplication Check)
                     ↓
          Stage 6: Outreach Tracker
          Output: data/outreach_tracker.csv, data/outreach_tracker.json
```

## 📁 Project Directory Structure

```
edx/
├── src/
│   ├── __init__.py
│   ├── discovery/
│   │   ├── __init__.py
│   │   └── discover.py        # Stage 1: Influencer Discovery (YouTube Data API v3)
│   ├── filtering/
│   │   ├── __init__.py
│   │   └── filter.py          # Stage 2: 5-Factor Scoring & Classification Rubric
│   ├── enrichment/
│   │   ├── __init__.py
│   │   └── enrich.py          # Stage 3: Profile Enrichment (Themes, Emails, Socials)
│   ├── personalization/
│   │   ├── __init__.py
│   │   └── personalize.py     # Stage 4: AI Personalization (Google Gemini 2.5 Flash)
│   ├── sending/
│   │   ├── __init__.py
│   │   └── send.py            # Stage 5: Sending Layer & Duplicate Prevention
│   └── utils/
│       ├── __init__.py
│       └── config.py          # Central Environment & Path Configuration
├── tests/
│   ├── __init__.py
│   └── test_1.py              # Initial API Connectivity Unit Test
├── data/                      # Structured Output Datasets (CSV & JSON)
│   ├── raw_channels.csv / .json
│   ├── filtered_channels.csv
│   ├── shortlisted.csv / .json
│   ├── enriched_profiles.csv / .json
│   ├── personalized_messages.csv / .json
│   └── outreach_tracker.csv / .json
├── main.py                    # Unified CLI Pipeline Entrypoint
├── discover.py                # Root module wrapper
├── filter.py                  # Root module wrapper
├── enrich.py                  # Root module wrapper
├── personalize.py             # Root module wrapper
├── send.py                    # Root module wrapper
├── .env                       # API Credentials (never committed)
├── .gitignore                 # Ignore secrets & runtime artifacts
├── requirements.txt           # Project dependencies
├── PROGRESS.md                # Progress tracking document
└── README.md                  # Comprehensive Documentation
```

---

## 🚀 Key Highlights & Highlights Against SPEC

1. **Two-Step Discovery Strategy**:
   - Fixed the fundamental limitation of `/search` endpoint (which does not return subscriber counts) by chaining batched `/channels?part=snippet,statistics` calls.
   - Discovered **80 micro-influencers** across **5 distinct niches** (Technology, Fitness, Beauty, Gaming, Finance).

2. **Transparent, Multi-Dimensional Filtering Rubric**:
   - **Engagement Rate (40 pts)**: `(views_per_video / subscribers) * 100`.
   - **Geography (20 pts)**: Full marks for India (`IN`) based creators.
   - **Niche Fit (20 pts)**: Keyword density in channel metadata.
   - **Channel Maturity (10 pts)**: Account age thresholding.
   - **Subscriber Sweet-spot (10 pts)**: 10k–80k sweet spot.
   - Strict gate: Total Score $\ge 40$ **and** Engagement Rate $\ge 1.0\%$.

3. **Honest, Multi-Tier Enrichment Fallback Chain**:
   - Strictly obeys SPEC rule: *No fabricated data, no guessed emails*.
   - Tier 1: YouTube API `brandingSettings.channel.contactEmail`.
   - Tier 2: Channel description regex scan.
   - Tier 3: Recent video descriptions scan (top 5 videos).
   - Tier 4: External link-in-bio page fetch & scan (Linktree, Beacons, personal websites).
   - Unfound fields marked honestly as `"Not Found"` or `"Not Available"`.

4. **Dynamic AI Personalization (Google Gemini 2.5 Flash)**:
   - High-speed concurrent worker generation (< 1 min for all 78 creators).
   - Generates 2 customized messages per creator:
     - **Email Pitch (60–90 words)** with tailored collaboration angles (Sponsored Integrations, UGC, Affiliates, Brand Ambassadorship).
     - **Instagram DM (15–30 words)** conversational hook.

5. **Bulletproof Sending Layer & Duplicate Prevention**:
   - Cross-checks channel IDs and emails against persistent history (`outreach_tracker.csv`) before any dispatch.
   - Safe simulation mode + production-ready live SMTP mode.
   - Compliant Instagram DM workflow simulation.

---

## 📊 Dataset Deliverables Summary

All generated datasets are stored in the [`data/`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data) directory:

| Deliverable | File Path | Records | Description |
|---|---|---|---|
| **Raw Discovery** | [`data/raw_channels.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/raw_channels.csv) | 80 rows | All discovered micro-influencers (5k–100k subs) |
| **Filtered Channels** | [`data/filtered_channels.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/filtered_channels.csv) | 80 rows | Complete scoring audit trail with pass/fail reasons |
| **Shortlisted** | [`data/shortlisted.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/shortlisted.csv) | 78 rows | Qualified candidates meeting brand-fit criteria |
| **Enriched Profiles** | [`data/enriched_profiles.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/enriched_profiles.csv) | 78 rows | Full profiles with emails, social links, and themes |
| **Personalized Messages** | [`data/personalized_messages.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/personalized_messages.csv) | 78 rows | Custom AI email pitch + Instagram DM per creator |
| **Outreach Tracker** | [`data/outreach_tracker.csv`](file:///c:/Users/Deepanshu%20sharma/Desktop/edx/data/outreach_tracker.csv) | 78 rows | Live dispatch status, timestamps, and deduplication log |

---

## 🛠 Tech Stack & Dependencies

- **Language**: Python 3.10+
- **APIs**:
  - [Google YouTube Data API v3](https://developers.google.com/youtube/v3)
  - [Google Gemini API](https://ai.google.dev/) (`gemini-2.5-flash`)
- **Libraries**:
  - `requests` (REST API communication & link-in-bio scraping)
  - `python-dotenv` (environment configuration management)
  - `smtplib` / `email.mime` (email dispatching)

---

## ⚙️ Setup & Execution Guide

### 1. Environment Configuration
Create a `.env` file in the project root:
```env
# YouTube Data API v3
YOUTUBE_API_KEY=your_youtube_api_key_here

# Google Gemini API
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: SMTP Configuration (for live email dispatch)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
SENDER_NAME=EDXSO Partnerships Team
SENDER_EMAIL=partnerships@edxso.com
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run Pipeline Stages

#### Stage 1: Influencer Discovery
```bash
python discover.py
```
*Queries YouTube Data API across 5 niches and fetches 80 micro-influencers (5k-100k subs).*

#### Stage 2: Filtering & Classification
```bash
python filter.py
```
*Applies multi-factor scoring rubric and creates shortlisted dataset.*

#### Stage 3: Profile Enrichment
```bash
python enrich.py
```
*Gathers recent video descriptions, extracts emails/socials, and derives content themes.*

#### Stage 4: AI Message Personalization
```bash
python personalize.py
```
*Uses Gemini 2.5 Flash to generate custom email pitches and Instagram DMs.*

#### Stage 5 & 6: Outreach Dispatch & Tracker
```bash
# Safe simulation mode (Default)
python send.py --mode simulate

# Live SMTP sending mode (when SMTP credentials are configured)
python send.py --mode live
```

---

## 📈 Scalability Analysis (Scaling from 50 → 500+ Creators)

1. **API Quota Management**:
   - YouTube Data API has a standard quota of 10,000 units/day.
   - `search.list` costs 100 units per page (50 results).
   - `channels.list` costs only 1 unit per batch of 50 IDs.
   - **Optimization**: Batch multiple channel queries and cache responses in SQLite/PostgreSQL to discover 500+ creators within a single daily quota.

2. **Distributed Enrichment & Scraping**:
   - Use asynchronous worker queues (Celery / Redis / asyncio) for link-in-bio page scraping and headless browser rendering (Playwright) for protected creator sites.

3. **LLM Batching & Rate Limits**:
   - The current concurrent multi-worker architecture (`ThreadPoolExecutor` + caching) easily scales to 500+ influencers in under 5 minutes without hitting Gemini RPM caps.

4. **Production Sending Layer**:
   - Integrate dedicated email delivery infrastructure (SendGrid, Resend, or Amazon SES) with webhook tracking for open rates, click-through rates, and automated follow-ups.

---

## 🔒 Limitations & Ethical Compliance

- **YouTube API Privacy**: YouTube intentionally restricts public email retrieval via API to protect creator privacy. All extracted emails in this project are retrieved strictly from publicly shared creator descriptions or linked public pages.
- **Instagram Direct Messaging**: Automated Instagram DM dispatching violates Meta Terms of Service without verified Business App approval. As specified in the project requirements, Instagram DM outreach is demonstrated via structured workflow simulation.
