# EDXSO AI Engineer Intern – Assignment 1
## Automated Micro-Influencer Outreach System

> This file is the source of truth for the project. Do not edit — reference only.

### Objective
Build an automated system that discovers relevant micro-influencers, filters and classifies them based on predefined criteria, enriches their profiles with useful information, and generates personalized collaboration outreach messages.

The system should demonstrate the ability to work with APIs, web scraping/data extraction, data processing, automation, AI/LLM-based personalization, and workflow design.

---

### 1. Influencer Discovery
Identify micro-influencers from a chosen niche such as: Fitness, Fintech, Beauty, Fashion, Crypto, Parenting, Gaming, Lifestyle, Technology.

Sources may include: Instagram, YouTube, TikTok, hashtag searches, public influencer directories, UGC marketplaces (Collabstr, Aspire, Grin), social media scraping/data extraction tools, creator newsletters and creator-spotlight pages.

**Definition:** A micro-influencer generally has 5,000–100,000 followers or equivalent audience engagement.

**Requirement:** Fetch at least 50 influencers for the test run.

---

### 2. Filtering & Classification
Build logic to automatically filter and classify discovered influencers, considering:
- Category / niche
- Audience demographics
- Geography (if available)
- Social media platform
- Follower count
- Engagement rate
- Brand-fit criteria
- Content relevance

**Minimum requirement:** Implement at least one complete filtering category (e.g. Fashion & Beauty influencers). Output must clearly show which influencers passed/failed and why.

---

### 3. Profile Enrichment
For every shortlisted influencer, collect:

| Field | Requirement |
|---|---|
| Influencer Name | Mandatory |
| Platform | Mandatory |
| Profile URL | Mandatory |
| Follower Count | Mandatory |
| Engagement Rate | Mandatory |
| Category / Niche | Mandatory |
| Content Themes | Mandatory |
| Contact Email | Mandatory |
| Instagram / YouTube / TikTok | Optional |
| Website | Optional |
| Audience Age | Optional |
| Audience Gender | Optional |
| Audience Geography | Optional |

**Minimum requirement:** Contact email + profile metrics + niche/content context. If an email can't be found, mark it **"Not Found"** — never guess or fabricate.

---

### 4. Message Personalization
Generate two personalized outreach messages per qualified influencer:

**A. Email Collaboration Pitch** (60–90 words)
Reference: niche, content tone/style, recent content, relevant audience, proposed collaboration, value proposition.
Collaboration angles: sponsorship, affiliate campaign, UGC content creation, brand ambassador program, paid product placement, barter collaboration.

**B. Instagram DM** (15–30 words)
Short, natural, personalized based on content/niche.

Example: instead of *"Hi, we would like to collaborate with you,"* generate something like *"Hi Sarah, loved your recent skincare routine content. Your beauty-focused audience looks like a great fit for our upcoming UGC campaign."*

Messages must be generated dynamically — not from one fixed template.

---

### 5. Sending Layer
Implement using: Gmail API, SMTP, email automation tools, Instagram/Meta APIs (where permitted), n8n, Make, Zapier, or another automation workflow.

**Requirements:**
- Select influencers with a valid contact email
- Retrieve their personalized email message
- Send or simulate sending
- Record sending status
- Prevent duplicate outreach
- Maintain a basic outreach log

For Instagram DMs: if automated sending isn't legally/technically available, do not bypass platform restrictions — demonstrate the generated DM and simulate a manual sending workflow instead.

---

### 6. Suggested Workflow
```
Social Platforms / Directories
        ↓
 Influencer Discovery
        ↓
   50+ Profiles
        ↓
Filtering & Classification
        ↓
 Profile Enrichment
        ↓
 AI Personalization
        ↓
Email + Instagram DM
        ↓
 Sending Layer
        ↓
Outreach Tracker
```

---

### 7. Expected Output
- **A. Working System** — functional prototype of the complete workflow
- **B. Influencer Dataset** — 50+ influencers (Name, Platform, Followers, Engagement, Niche, Email, Profile URL, Content Theme, Status)
- **C. Personalized Messages** — email pitch + Instagram DM for shortlisted influencers
- **D. Outreach Tracker** — Influencer, Email, Message Generated, Sent, Date, Status
- **E. Documentation (README)** — tech stack, APIs/tools, data sources, discovery methodology, filtering logic, enrichment process, AI model/prompt used, personalization logic, sending mechanism, limitations, setup instructions

---

### 8. Technical Expectations
Python / JavaScript, REST APIs, web scraping (where permitted), data processing, LLM APIs, prompt engineering, n8n/Make/Zapier, databases/structured storage, email APIs, automation workflows. Code should be modular, reusable, and reasonably error-tolerant.

---

### 9. Evaluation Criteria
Functionality · Data Quality · Automation · Filtering Logic · Profile Enrichment · AI Personalization · Engineering Quality · Error Handling · Documentation · Scalability (50 → 500+ influencers)

---

### 10. Submission Requirements
GitHub repo/project files, README/documentation, working demo (screenshots/video), influencer dataset, sample personalized messages, automation workflow (if applicable), setup instructions, list of APIs/tools used.

> **Important:** Do not submit fabricated influencer information, guessed emails, or fake engagement metrics. Clearly identify unavailable data. The goal is a working pipeline, not a static dataset or presentation.