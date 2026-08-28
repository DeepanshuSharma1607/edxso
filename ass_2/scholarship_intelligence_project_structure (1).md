# Scholarship Intelligence Crawler

## 1. Project Goal

Build an automated scholarship intelligence system for Indian students that:

**Discovers → Crawls → Extracts → Verifies → Scores → Stores → Updates**

The system should maintain a continuously updated repository of authentic scholarship opportunities from approved official sources.

The assignment requires:
- 20+ real scholarship records
- 15+ verified against primary/official sources
- 10+ confidence score >= 95%
- 3+ different source types
- 2+ change-detection examples
- 2+ expired/stale examples

---

# 2. High-Level Architecture

```text
                         APPROVED SOURCES
                                |
                                v
                        DAILY SCHEDULER
                                |
                                v
                           DISCOVERY
                                |
                                v
                            CRAWLER
                                |
                    +-----------+-----------+
                    |           |           |
                    v           v           v
                  HTML      JS HTML      PDF/Image
                    |           |           |
                    v           v           v
              BeautifulSoup  Playwright   SOURCE LINK
                    |           |           |
                    +-----------+-----------+
                                |
                                v
                         DATA EXTRACTION
                                |
                                v
                           VERIFICATION
                                |
                                v
                       CONFIDENCE SCORING
                                |
                                v
                            DATABASE
                                |
                                v
                       CHANGE DETECTION
                                |
                                v
                           DASHBOARD
```

## Important source-format decision

For the initial implementation:

- HTML webpage: extract and structure the information.
- HTML tables: extract and structure the information.
- JavaScript-rendered HTML: use Playwright when necessary.
- PDF: detect it and preserve the official link. Do not perform PDF extraction.
- Image: detect it and preserve the official link. Do not perform OCR.
- Scanned PDF: preserve the official document link.
- Other documents/brochures: preserve the official source link.

If sufficient information cannot be reliably extracted, **do not invent it**. Show the official source/document link and mark the record appropriately.

---


# 3. Actual System Architecture

The system has **two main operating flows** that share the same database.

## Flow A: Daily Background Crawler

This flow keeps the scholarship database continuously updated.

```text
                         DAILY CRON
                            |
                            v
                  +--------------------+
                  | Approved Sources   |
                  | Registry           |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Source Discovery   |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Web Crawler        |
                  | Requests first     |
                  | Playwright if      |
                  | JavaScript needed  |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Scholarship Page   |
                  | Discovery          |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Content Extraction |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Verification       |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Confidence Score   |
                  +---------+----------+
                            |
                            v
                  +--------------------+
                  | Compare With DB    |
                  +---------+----------+
                            |
              +-------------+-------------+
              |             |             |
              v             v             v
           NEW          CHANGED       UNCHANGED
              |             |             |
              v             v             |
           INSERT       UPDATE +         |
                        HISTORY           |
              |             |             |
              +-------------+-------------+
                            |
                            v
                     Updated Database
```

### What happens during the daily run

For every approved source:

1. Open the official source.
2. Discover scholarship-related pages.
3. Follow relevant internal links.
4. Extract readable scholarship information.
5. Identify individual scholarship records.
6. Verify every record against the official source.
7. Calculate the confidence score.
8. Compare the new record with the existing database record.
9. Insert new scholarships.
10. Update changed scholarships and create `change_history` records.
11. Mark expired or no-longer-verifiable scholarships.
12. Record the crawler execution in `crawl_runs`.

The crawler does not need to run continuously. It runs once per day.

---

# 4. User Query Architecture

The user-facing system has a separate flow.

## Step 1: User sends a query

Example:

```text
"I want B.Tech scholarships with JEE score above 90."
```

or:

```text
"Show scholarships available at XYZ University."
```

The request goes to FastAPI.

```text
USER
  |
  v
FastAPI
  |
  v
Query Understanding
  |
  v
Database Search
```

## Step 2: Check whether the database already contains relevant information

```text
                     USER QUERY
                          |
                          v
                    FastAPI API
                          |
                          v
                  Query Understanding
                          |
                          v
                    Database Search
                       /       \
                     FOUND     NOT FOUND
                      |            |
                      v            v
                Retrieve DB    Targeted Fetch
                   records         |
                      |             v
                      |       Identify Official
                      |       Source
                      |             |
                      |             v
                      |          Crawl
                      |             |
                      |             v
                      |          Extract
                      |             |
                      |             v
                      |         Verify
                      |             |
                      |             v
                      |          Score
                      |             |
                      |             v
                      |         Store DB
                      |             |
                      +-------------+
                                    |
                                    v
                            Relevant Records
                                    |
                                    v
                         RAG/LLM if required
                                    |
                                    v
                                  USER
```

---

# 5. User Query: Data Already Exists

Example:

```text
User:
"Show B.Tech scholarships."
```

The system searches the `scholarships` table.

If records exist:

```text
Database
   |
   v
Find course_level = B.Tech
   |
   v
Retrieve relevant scholarships
   |
   v
Return results
```

No website crawling is required.

For simple structured queries, use SQL/database filtering rather than RAG.

Example:

```text
course_level = B.Tech
status = ACTIVE
```

---

# 6. User Query: Data Does Not Exist

Example:

```text
User:
"Show scholarships from XYZ University."
```

The database returns no relevant records.

The system then performs a **targeted fetch**, not a crawl of the entire internet.

```text
User query
    |
    v
XYZ University identified
    |
    v
Find/confirm official XYZ University domain
    |
    v
Crawl relevant official pages
    |
    v
Discover scholarship information
    |
    v
Extract
    |
    v
Verify
    |
    v
Calculate confidence
    |
    v
Store verified/review records
    |
    v
Return newly discovered results
```

This means the user gets the result immediately after the targeted discovery process completes.

The next user asking about XYZ University can receive the stored records directly from the database.

---

# 7. Why There Are Two Crawling Modes

The project deliberately has:

### Background crawling

Purpose:

```text
Keep the repository fresh
```

Runs:

```text
Once every day
```

Scope:

```text
All approved sources
```

### Targeted crawling

Purpose:

```text
Handle information that is not already in the database
```

Runs:

```text
Only when needed
```

Scope:

```text
Only the relevant official source
```

This avoids crawling the entire internet whenever a student searches.

---

# 8. Extraction Architecture

The extraction layer accepts several types of webpage content.

```text
Official Webpage
      |
      v
+---------------------------+
| Content Type Detection    |
+-------------+-------------+
              |
      +-------+-------+
      |       |       |
      v       v       v
    HTML   JS HTML  PDF/Image
      |       |       |
      v       v       v
 Beautiful  Playwright  Fallback
 Soup
      |       |       |
      +-------+-------+
              |
              v
       Scholarship Text
              |
              v
       Structured Extractor
              |
              v
       Pydantic Validation
```

For the initial implementation:

- HTML: process.
- HTML tables: process.
- JavaScript HTML: process with Playwright when needed.
- PDF: detect and preserve official link.
- Image: detect and preserve official link.
- Scanned PDF: preserve official link.
- Other documents: preserve official link.

If enough information cannot be reliably extracted, do not invent it.

---

# 9. Scholarship Extraction Per Source

A single source can contain many scholarships.

Example:

```text
IILM University Scholarship Page
            |
            v
       Extract all schemes
            |
      +-----+-----+-----+
      |     |     |     |
      v     v     v     v
    JEE    CUET  Sports  Martyr
    Scholarship ...
      |     |     |
      +-----+-----+
            |
            v
     Verify each record
            |
            v
      Score each record
            |
            v
        Store each
```

A scholarship scheme with multiple eligibility tiers remains one scholarship record with structured eligibility information.

Example:

```json
{
  "name": "B.Tech JEE Main Scholarship",
  "eligibility": {
    "type": "JEE_MAIN",
    "rules": [
      {"range": "96-100", "benefit": "100%"},
      {"range": "86-95", "benefit": "40%"},
      {"range": "76-85", "benefit": "30%"}
    ]
  }
}
```

Do not create unnecessary separate scholarship records for every tier.

---

# 10. Verification Before Storage

The extraction result should not immediately become `VERIFIED`.

Use this pipeline:

```text
Raw webpage
    |
    v
Extract scholarship
    |
    v
Collect evidence
    |
    v
Verification checks
    |
    v
Confidence calculation
    |
    +------------------+
    |                  |
 >=95%              <95%
    |                  |
    v                  v
VERIFIED        REVIEW_REQUIRED
    |                  |
    +--------+---------+
             |
             v
          Database
```

The database can contain both verified and review-required records, but their status must be clear.

---

# 11. Evidence Architecture

For every important field, keep the evidence used to support it.

```text
Scholarship
    |
    +-- Name
    |     |
    |     +-- Evidence
    |
    +-- Amount
    |     |
    |     +-- Evidence
    |
    +-- Eligibility
    |     |
    |     +-- Evidence
    |
    +-- Deadline
          |
          +-- Evidence
```

Example:

```text
Field:
closing_date

Value:
31 August 2026

Evidence:
"Application deadline for scholarships is
31 August 2026."

Source:
Official university webpage
```

If the field is not present:

```text
income_criteria = NOT_SPECIFIED
```

Do not infer a value.

---

# 12. Confidence Score Architecture

The score is generated by Python verification logic.

Example:

```text
Official approved source             +30
Scholarship currently present        +20
Official application URL             +15
Eligibility evidence                 +10
Deadline evidence                    +10
Benefit evidence                      +5
Freshness                             +5
No conflicting information             +5
                                      ---
                                      100
```

Example:

```text
Official source              30/30
Present on source            20/20
Application URL              15/15
Eligibility evidence         10/10
Deadline evidence            10/10
Benefit evidence              5/5
Freshness                     5/5
No conflict                   5/5
                              ----
                              100%
```

Result:

```text
status = VERIFIED
confidence_score = 100
```

The LLM does not generate this score.

---

# 13. Database Interaction

The database is the central shared layer.

```text
                   +----------------+
                   |    SOURCES     |
                   +-------+--------+
                           |
                           v
                   +----------------+
                   |  SCHOLARSHIPS  |
                   +-------+--------+
                           |
             +-------------+-------------+
             |                           |
             v                           v
     +---------------+          +----------------+
     | CHANGE_HISTORY|          |   CRAWL_RUNS  |
     +---------------+          +----------------+
```

Both the daily crawler and user-triggered targeted crawler write to the same database.

The user query system reads from the same database.

---

# 14. Daily Update Logic

For every newly crawled scholarship:

```text
Does scholarship exist?
        |
   +----+----+
   |         |
  NO        YES
   |         |
   v         v
 INSERT   Compare fields
              |
        +-----+------+
        |            |
     Changed      Unchanged
        |            |
        v            v
 Update + history   Keep
```

If a deadline changes:

```text
Old:
31 August 2026

New:
15 September 2026

Action:
UPDATE scholarships
+
INSERT change_history
```

Never silently overwrite important historical changes.

---

# 15. Expiry and Stale Detection

After crawling:

```text
Deadline passed
      |
      v
EXPIRED
```

If the source no longer contains the scholarship:

```text
Unable to re-verify
      |
      v
NO_LONGER_VERIFIABLE
```

If conflicting information exists:

```text
Conflict detected
      |
      v
REVIEW_REQUIRED
```

The record is preserved rather than deleted.

---

# 16. RAG Architecture

RAG is an optional answer-generation layer, not the primary storage/search system.

```text
User Query
    |
    v
Database retrieval
    |
    v
Relevant scholarship records
    |
    v
RAG context
    |
    v
LLM
    |
    v
Natural-language answer
```

Example:

```text
User:
"I have 92% in Class 12, JEE 88 and family
income of ₹5 lakh. What can I apply for?"
```

System:

```text
1. Retrieve relevant B.Tech scholarships.
2. Retrieve eligibility information.
3. Compare the user's stated criteria.
4. Give matching scholarships.
5. Show source and evidence.
```

The LLM should only use retrieved database information.

---

# 17. Complete System Architecture

```text
                           INTERNET
                              |
                              v
                    +--------------------+
                    | APPROVED SOURCES   |
                    +---------+----------+
                              |
                +-------------+-------------+
                |                           |
                v                           v
        DAILY CRAWLER                 USER QUERY
                |                           |
                v                           v
           DISCOVERY                   FASTAPI
                |                           |
                v                           v
             CRAWL                  QUERY UNDERSTANDING
                |                           |
                v                           v
           EXTRACTION                 DATABASE SEARCH
                |                     /           \
                v                   FOUND       NOT FOUND
           VERIFICATION               |              |
                |                     |              v
                v                     |       TARGETED CRAWL
             SCORING                  |              |
                |                     |        EXTRACT + VERIFY
                v                     |              |
             DATABASE <---------------+--------------+
                |
        +-------+--------+
        |                |
        v                v
  CHANGE HISTORY     CRAWL RUNS
        |
        v
    STREAMLIT UI
        |
        v
       USER

For natural-language questions:
Database Results -> RAG/LLM -> Final Answer
```

This is the actual implementation architecture.

---

# 18. Recommended Python Modules

```text
backend/
│
├── main.py
│
├── database/
│   ├── connection.py
│   ├── models.py
│   └── repository.py
│
├── discovery/
│   ├── source_registry.py
│   ├── discovery.py
│   └── link_finder.py
│
├── crawler/
│   ├── http_crawler.py
│   ├── playwright_crawler.py
│   └── crawler_service.py
│
├── extraction/
│   ├── html_extractor.py
│   ├── scholarship_extractor.py
│   └── schemas.py
│
├── verification/
│   ├── verifier.py
│   ├── evidence.py
│   └── confidence.py
│
├── updates/
│   ├── change_detector.py
│   ├── expiry_checker.py
│   └── updater.py
│
├── search/
│   ├── query_parser.py
│   ├── database_search.py
│   └── rag_service.py
│
└── services/
    └── scholarship_service.py
```

This separation makes the architecture easy to explain in the technical note and demo.

---

# 19. Main API Endpoints

Recommended FastAPI endpoints:

```text
GET  /api/scholarships
GET  /api/scholarships/{id}
GET  /api/search?q=...
POST /api/search
POST /api/crawl/source/{source_id}
GET  /api/crawl/status
GET  /api/crawl/runs
GET  /api/scholarships/{id}/history
GET  /api/sources
```

The user search endpoint should:

```text
1. Receive query.
2. Search database.
3. If results exist, return them.
4. If no results, trigger targeted discovery.
5. Verify extracted records.
6. Store records.
7. Return the newly discovered results.
```

---

# 20. What NOT to Build

Do not add unnecessary infrastructure:

- No PDF extraction for the MVP.
- No image OCR.
- No FAISS.
- No ChromaDB.
- No complex vector database.
- No multi-agent LangGraph system.
- No unnecessary LangChain pipeline.
- No large local LLM on 1 GB EC2.
- No microservices.
- No Kubernetes.
- No complex frontend.

The assignment evaluates whether the system produces trustworthy scholarship information, not how many technologies are used.

---

# 21. Implementation Order

Build in this exact order.

### Phase 1: Database

Create:

```text
sources
scholarships
change_history
crawl_runs
```

### Phase 2: Source registry

Add approved official scholarship sources.

### Phase 3: Basic crawler

Implement:

```text
Requests
+
BeautifulSoup
```

### Phase 4: Discovery

Find scholarship-related pages and links inside approved domains.

### Phase 5: Extraction

Convert webpage content into structured scholarship objects.

### Phase 6: Verification

Check source, evidence, completeness, freshness and conflicts.

### Phase 7: Confidence

Calculate deterministic confidence score.

### Phase 8: Storage

Only then write the verified/review record to the database.

### Phase 9: Daily update

Add cron and change detection.

### Phase 10: User search

Database first.

If missing:

```text
Targeted crawl
→ Extract
→ Verify
→ Score
→ Store
→ Return
```

### Phase 11: RAG

Add only after the database search works.

### Phase 12: Dashboard

Build the minimum required Streamlit UI.

### Phase 13: Deployment

Docker + EC2 + cron.

### Phase 14: Demo

Demonstrate:

```text
Crawler starts
↓
Discovers scholarship
↓
Extracts
↓
Verifies
↓
Scores
↓
Stores
↓
User searches
↓
Gets stored result
↓
Searches unknown university
↓
Targeted crawl
↓
New result stored
↓
Run crawler again
↓
Change detected
```


# 3. Technology Stack

## Core

### Python
Main programming language.

### FastAPI
Backend API.

Responsibilities:
- Search scholarships
- Return scholarship details
- Trigger targeted discovery when data is missing
- Expose crawler/status endpoints if needed

### SQLite
Database.

Chosen because:
- Free
- Lightweight
- Simple deployment
- Suitable for this assignment
- Suitable for a 1 GB EC2 instance

---

# 4. Crawling and Discovery Tools

## Requests

Use for ordinary HTTP requests.

```text
URL -> HTML
```

Use this before Playwright because it is lightweight.

## BeautifulSoup

Use for:
- HTML parsing
- Finding scholarship links
- Extracting text
- Extracting HTML tables
- Finding PDF/image links
- Finding application URLs

## Playwright

Use only when a website is JavaScript-rendered and Requests/BeautifulSoup cannot access the useful content.

Do not use Playwright for every website because it consumes more resources.

## Discovery

The crawler should not be only:

```text
URL 1 -> scraper
URL 2 -> scraper
URL 3 -> scraper
```

Maintain an approved source registry and allow the crawler to discover relevant scholarship pages within approved domains.

---

# 5. Extraction

The extraction layer converts readable webpage information into a structured scholarship record.

Extract fields such as:

- Scholarship name
- Provider
- Amount / benefit
- Eligibility
- Academic requirements
- Course / education level
- Income criteria
- Age criteria
- Gender criteria
- Category criteria
- Domicile / state requirements
- Institution requirements
- Opening date
- Closing date
- Documents required
- Selection process
- Renewal requirements
- Application URL
- Official source URL
- Current status

## LLM usage

An open-source/local LLM can be used for structured extraction from messy webpage text.

Recommended approach:

```text
Webpage text
    |
    v
LLM structured extraction
    |
    v
JSON
    |
    v
Pydantic validation
    |
    v
Verification rules
```

The LLM should NOT decide the final confidence score.

---

# 6. Verification Engine

Verification must happen **before the scholarship is treated as verified in the database**.

Verification checks can include:

```text
Official approved source             +30
Scholarship currently present        +20
Official application URL             +15
Eligibility supported by evidence    +10
Deadline supported by evidence      +10
Amount/benefit supported              +5
Information is fresh                  +5
No conflicting information            +5
                                      ---
                                      100
```

Status:

```text
95-100  -> VERIFIED
Below 95 -> REVIEW_REQUIRED
```

The score must be deterministic and evidence-based.

Do not ask the LLM:

```text
"Give this scholarship a confidence score."
```

Instead, the application calculates the score using explicit rules.

---

# 7. Evidence and Anti-Hallucination

Every important extracted field should have traceable evidence.

Example:

```text
Field:
Deadline

Value:
31 August 2026

Source:
Official university webpage

Evidence:
"Application deadline: 31 August 2026"
```

If the official source does not specify a field:

```text
Income limit:
NOT_SPECIFIED
```

Never invent missing values.

If the webpage only provides a PDF/image/document and the system does not process that format:

```text
Status:
SOURCE_FOUND / LIMITED_DETAILS

Message:
"Limited scholarship details were available.
Please check the official source/document for complete information."

Official source:
[URL]
Document:
[URL]
```

Do not assign a high confidence score to a scholarship whose details were not sufficiently verified.

---

# 8. Database Design

Use **4 tables**.

## Table 1: `sources`

Stores approved official scholarship sources.

```text
sources
-------
id
name
url
source_type
approved
last_crawled
last_successful_crawl
created_at
updated_at
```

Example:

```text
id: S001
name: IILM University
url: https://official-domain.example
source_type: UNIVERSITY
approved: true
last_crawled: 2026-08-26
last_successful_crawl: 2026-08-26
```

Possible source types:

```text
GOVERNMENT
GOVERNMENT_BODY
UNIVERSITY
CORPORATE
FOUNDATION
NGO_TRUST
SCHOLARSHIP_PORTAL
OTHER_OFFICIAL
```

---

## Table 2: `scholarships`

Main scholarship repository.

```text
scholarships
------------
id
source_id
name
provider
amount
benefit_type
eligibility
academic_requirements
course_level
income_criteria
age_criteria
gender_criteria
category_criteria
domicile
institution_requirements
opening_date
closing_date
documents_required
selection_process
renewal_requirements
application_url
official_source_url
status
confidence_score
evidence
last_verified
created_at
updated_at
```

Example:

```text
id: SCH001
source_id: S001
name: B.Tech JEE Main Scholarship
provider: IILM University
amount: Tuition fee waiver
benefit_type: Percentage
eligibility: JEE Main score based
course_level: B.Tech
closing_date: 2026-08-31
status: VERIFIED
confidence_score: 99
official_source_url: https://official-source.example
last_verified: 2026-08-26
```

For complex tiered scholarships, eligibility can be stored as JSON.

Example:

```json
{
  "type": "JEE_MAIN",
  "rules": [
    {"min": 96, "max": 100, "benefit": "100%"},
    {"min": 86, "max": 95, "benefit": "40%"},
    {"min": 76, "max": 85, "benefit": "30%"}
  ]
}
```

Do not create a separate table for eligibility rules initially.

---

## Table 3: `change_history`

Stores changes instead of overwriting history.

```text
change_history
--------------
id
scholarship_id
field_name
old_value
new_value
detected_at
source_url
evidence
```

Example:

```text
scholarship_id: SCH001
field_name: closing_date
old_value: 2026-08-31
new_value: 2026-09-15
detected_at: 2026-08-27
source_url: official-source.example
evidence: "Applications close on 15 September 2026"
```

Possible changes:
- Deadline
- Amount
- Eligibility
- Application URL
- Status
- Other important fields

---

## Table 4: `crawl_runs`

Stores crawler execution history.

```text
crawl_runs
----------
id
started_at
completed_at
status
sources_checked
scholarships_found
new_scholarships
updated_scholarships
expired_scholarships
errors
```

Example:

```text
Run #12
Started: 2026-08-26 02:00
Completed: 2026-08-26 02:08

Sources checked: 25
Scholarships found: 184
New scholarships: 7
Updated scholarships: 4
Expired scholarships: 3
Errors: 1
```

---

# 9. Daily Crawler

Run the crawler once every day using Linux cron.

Example:

```text
0 2 * * * python -m crawler.daily_run
```

Flow:

```text
Scheduler
    |
    v
Approved sources
    |
    v
Crawl each source
    |
    v
Discover scholarship pages
    |
    v
Extract readable scholarship information
    |
    v
Verify
    |
    v
Calculate confidence
    |
    v
Compare with database
    |
    +---- New ----------> INSERT
    |
    +---- Changed ------> UPDATE + change_history
    |
    +---- Same ---------> KEEP
    |
    +---- Expired ------> EXPIRED
    |
    +---- Unverifiable -> NO_LONGER_VERIFIABLE
```

---

# 10. User Search Flow

There are two cases.

## Case A: Scholarship data already exists

```text
User query
    |
    v
Search database
    |
    v
Relevant records found
    |
    v
Return results
```

Do not crawl the internet unnecessarily.

For simple structured queries, use database filtering.

Example:

```text
"B.Tech scholarships"
```

can become:

```text
course_level = "B.Tech"
```

## Case B: Scholarship data does not exist

Example:

```text
User:
"Show scholarships from XYZ University"
```

Database:

```text
XYZ University -> NOT FOUND
```

Then:

```text
Identify official XYZ domain
    |
    v
Targeted crawl
    |
    v
Extract
    |
    v
Verify
    |
    v
Score
    |
    v
Store in database
    |
    v
Return newly discovered results
```

Do not crawl the entire internet for a targeted university query.

---

# 11. RAG Usage

RAG should NOT replace normal database search.

Use database filtering first for structured requests.

Use RAG/LLM when the user asks a natural-language question requiring reasoning over stored scholarship information.

Example:

```text
User:
"I have 92% in Class 12, JEE score 88,
family income of ₹5 lakh, and I want B.Tech.
Which scholarships are relevant?"
```

Flow:

```text
User query
    |
    v
Query understanding
    |
    v
Database retrieval
    |
    v
Relevant scholarship records
    |
    v
RAG/LLM explanation
    |
    v
Answer with source links and evidence
```

The LLM should only reason over retrieved information. It should not invent scholarship details.

---

# 12. Fallback for PDF/Image/Document Sources

The crawler detects non-HTML resources.

Example:

```text
Official webpage
    |
    v
"Download Scholarship Brochure"
    |
    v
PDF
```

The system does not extract the PDF in the initial MVP.

Instead:

```text
Status:
SOURCE_FOUND

Details:
LIMITED_DETAILS

Official webpage:
[URL]

Document:
[PDF URL]
```

User message:

```text
"Limited scholarship details were available on the webpage.
Please check the official scholarship document for complete
eligibility and application information."
```

This prevents hallucination and avoids heavy PDF/OCR processing.

---

# 13. Dashboard

Use Streamlit.

## Main dashboard

Show:

```text
Total discovered
Verified
Review required
Active
Expired
Recently updated
Average confidence
```

## Search

```text
Search scholarships
[ B.Tech scholarships ]
```

## Scholarship details

Show:

```text
Name
Provider
Amount / Benefit
Eligibility
Deadline
Official Source
Application Link
Status
Confidence Score
Why this score?
Last Verified
Change History
Evidence
```

Include direct links to the official source.

---

# 14. Recommended Project Structure

```text
scholarship-intelligence/
│
├── backend/
│   ├── main.py
│   ├── config.py
│   │
│   ├── database/
│   │   ├── connection.py
│   │   ├── models.py
│   │   └── schema.sql
│   │
│   ├── crawler/
│   │   ├── discovery.py
│   │   ├── crawler.py
│   │   ├── html_parser.py
│   │   ├── playwright_crawler.py
│   │   └── source_detector.py
│   │
│   ├── extraction/
│   │   ├── extractor.py
│   │   ├── llm_extractor.py
│   │   └── schemas.py
│   │
│   ├── verification/
│   │   ├── verifier.py
│   │   ├── confidence.py
│   │   └── evidence.py
│   │
│   ├── updates/
│   │   ├── change_detector.py
│   │   ├── expiry_checker.py
│   │   └── updater.py
│   │
│   └── services/
│       ├── scholarship_service.py
│       └── search_service.py
│
├── crawler_jobs/
│   └── daily_run.py
│
├── frontend/
│   └── app.py
│
├── tests/
│   ├── test_crawler.py
│   ├── test_extraction.py
│   ├── test_verification.py
│   └── test_change_detection.py
│
├── data/
│   └── scholarship.db
│
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

---

# 15. Tools Required

## Required

| Tool | Purpose |
|---|---|
| Python | Main language |
| FastAPI | Backend |
| SQLite | Database |
| Requests | HTTP requests |
| BeautifulSoup | HTML parsing |
| Playwright | JavaScript-rendered pages |
| Pydantic | Data validation |
| Streamlit | Dashboard |
| Linux cron | Daily scheduling |
| Docker | Deployment |
| Git/GitHub | Version control |
| pytest | Testing |

## Optional

| Tool | Purpose |
|---|---|
| Ollama | Local LLM |
| Hugging Face | Open-source models |
| Mistral / small open-source model | Structured extraction / answer generation |

## Not required for the initial version

- PDF extraction
- OCR
- FAISS
- ChromaDB
- LangChain
- LangGraph
- Vector database
- Multi-agent system
- Selenium

Do not add technologies just to make the architecture look more sophisticated.

---

# 16. EC2 Deployment

A 1 GB EC2 instance can run this architecture if the crawler is not permanently running.

Recommended:

```text
EC2 1 GB
    |
    +-- FastAPI
    |
    +-- Streamlit
    |
    +-- SQLite
    |
    +-- Cron
```

Use lightweight Requests + BeautifulSoup wherever possible.

Run Playwright only when necessary.

Do not run a large local LLM continuously on the 1 GB machine. If an LLM is needed for extraction, use a small model only if the resource budget allows it, or keep extraction primarily deterministic.

---

# 17. Core Status Values

Use:

```text
ACTIVE
EXPIRING_SOON
EXPIRED
REVIEW_REQUIRED
NO_LONGER_VERIFIABLE
SOURCE_FOUND
```

Do not delete expired scholarships. Preserve them so the system can demonstrate stale-data detection and history.

---

# 18. Core Principles

### Principle 1: Official sources first

Aggregators can help discovery, but the authoritative source must be the official government, university, organisation, provider, or scholarship portal.

### Principle 2: Evidence before confidence

Never generate an arbitrary confidence score.

### Principle 3: Never invent missing data

Use:

```text
NOT_SPECIFIED
```

when the official source does not provide a field.

### Principle 4: Don't overwrite history

Changes go into `change_history`.

### Principle 5: Database first for user queries

Don't crawl unnecessarily.

### Principle 6: Targeted fetching for missing data

If the requested scholarship is absent, crawl the relevant official source, verify it, store it, then return the result.

### Principle 7: Fallback instead of hallucination

If a source only provides a PDF/image/document that the system does not process, provide the official link instead of guessing the contents.

---

# 19. Final System Flow

```text
                    DAILY AUTOMATION
                           |
                           v
                  APPROVED SOURCES
                           |
                           v
                       DISCOVERY
                           |
                           v
                         CRAWL
                           |
                           v
                       EXTRACT
                           |
                           v
                       VERIFY
                           |
                           v
                        SCORE
                           |
                           v
                        STORE
                           |
                           v
                       UPDATE
                           |
                           v
                      DATABASE
                           ^
                           |
                    USER SEARCH
                           |
                 +---------+---------+
                 |                   |
              FOUND              NOT FOUND
                 |                   |
                 v                   v
          Database search      Targeted crawl
                 |                   |
                 |              Extract/Verify
                 |                   |
                 |                 Store
                 |                   |
                 +---------+---------+
                           |
                           v
                    Relevant results
                           |
                           v
                    RAG/LLM if needed
                           |
                           v
                         USER
```

## 20. Assignment Success Criteria

Before submission, verify:

```text
[ ] 20+ real scholarship records
[ ] 15+ verified against official sources
[ ] 10+ confidence >= 95%
[ ] 3+ source types
[ ] 2+ change detection examples
[ ] 2+ expired/stale examples
[ ] Official source URL for verified records
[ ] Evidence stored
[ ] Confidence methodology implemented
[ ] No fabricated information
[ ] Daily crawler works
[ ] Database updates correctly
[ ] Dashboard works
[ ] User search works
[ ] Missing-data targeted crawl works
[ ] PDF/image fallback works
[ ] README complete
[ ] Technical note <= 3 pages
[ ] Demo shows second crawl and change detection
```

This structure is intentionally focused on the assignment requirements rather than adding unnecessary AI infrastructure.
