-- Scholarship Intelligence Crawler — SQLite schema
-- 4 tables: sources, scholarships, change_history, crawl_runs

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL,
    url                     TEXT NOT NULL,
    source_type             TEXT NOT NULL CHECK (source_type IN (
                                'GOVERNMENT', 'GOVERNMENT_BODY', 'UNIVERSITY',
                                'CORPORATE', 'FOUNDATION', 'NGO_TRUST',
                                'SCHOLARSHIP_PORTAL', 'OTHER_OFFICIAL'
                            )),
    approved                INTEGER NOT NULL DEFAULT 1,
    last_crawled            TEXT,
    last_successful_crawl   TEXT,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scholarships (
    id                          TEXT PRIMARY KEY,
    source_id                   TEXT NOT NULL REFERENCES sources(id),
    name                        TEXT NOT NULL,
    provider                    TEXT NOT NULL,
    amount                      TEXT,               -- free text, e.g. "Rs 2,00,000" or "NOT_SPECIFIED"
    benefit_type                TEXT,                -- e.g. Percentage / Fixed / Fee waiver / NOT_SPECIFIED
    eligibility                 TEXT,                -- JSON blob of structured eligibility rules
    academic_requirements       TEXT,
    course_level                TEXT,                -- e.g. B.Tech, UG, PG, Class 8-12, Any
    income_criteria             TEXT,
    age_criteria                TEXT,
    gender_criteria             TEXT,
    category_criteria           TEXT,
    domicile                    TEXT,
    institution_requirements    TEXT,
    opening_date                TEXT,                -- ISO date or NOT_SPECIFIED
    closing_date                TEXT,
    documents_required          TEXT,
    selection_process           TEXT,
    renewal_requirements        TEXT,
    application_url             TEXT,
    official_source_url         TEXT NOT NULL,
    source_type                 TEXT NOT NULL,       -- denormalised copy of sources.source_type, for fast filtering
    status                       TEXT NOT NULL CHECK (status IN (
                                    'ACTIVE', 'EXPIRING_SOON', 'EXPIRED',
                                    'REVIEW_REQUIRED', 'NO_LONGER_VERIFIABLE',
                                    'SOURCE_FOUND'
                                )),
    verification_label           TEXT NOT NULL CHECK (verification_label IN ('VERIFIED', 'REVIEW_REQUIRED')),
    confidence_score              REAL NOT NULL,
    confidence_breakdown           TEXT,             -- JSON: per-check point breakdown, "why this score"
    evidence                        TEXT,             -- JSON: {field: {value, evidence_text, source_url}}
    discovery_url                    TEXT,            -- where it was first discovered (may be aggregator)
    content_hash                      TEXT,           -- hash of the fields used for change detection
    last_verified                      TEXT NOT NULL,
    first_discovered_at                 TEXT NOT NULL,
    created_at                           TEXT NOT NULL,
    updated_at                            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS change_history (
    id              TEXT PRIMARY KEY,
    scholarship_id  TEXT NOT NULL REFERENCES scholarships(id),
    field_name      TEXT NOT NULL,
    old_value       TEXT,
    new_value       TEXT,
    detected_at     TEXT NOT NULL,
    source_url      TEXT,
    evidence        TEXT,
    crawl_run_id    TEXT
);

CREATE TABLE IF NOT EXISTS crawl_runs (
    id                      TEXT PRIMARY KEY,
    started_at              TEXT NOT NULL,
    completed_at            TEXT,
    status                  TEXT NOT NULL DEFAULT 'RUNNING',
    sources_checked         INTEGER DEFAULT 0,
    scholarships_found      INTEGER DEFAULT 0,
    new_scholarships        INTEGER DEFAULT 0,
    updated_scholarships    INTEGER DEFAULT 0,
    expired_scholarships    INTEGER DEFAULT 0,
    no_longer_verifiable    INTEGER DEFAULT 0,
    errors                  TEXT
);

CREATE INDEX IF NOT EXISTS idx_scholarships_status ON scholarships(status);
CREATE INDEX IF NOT EXISTS idx_scholarships_source ON scholarships(source_id);
CREATE INDEX IF NOT EXISTS idx_scholarships_course_level ON scholarships(course_level);
CREATE INDEX IF NOT EXISTS idx_change_history_scholarship ON change_history(scholarship_id);
