from datetime import date
from backend.extraction.schemas import ScholarshipRecord
from backend.verification.confidence import score_record, VERIFIED_THRESHOLD


def _base_record(**overrides) -> ScholarshipRecord:
    data = dict(
        name="Test Scholarship",
        provider="Test Ministry",
        amount="NOT_SPECIFIED",
        closing_date="2026-12-31",
        application_url="https://scholarships.gov.in/ApplicationForm/",
        eligibility="Class 10 pass",
        course_level="UG",
        benefit_type="Merit Based Scheme",
        official_source_url="https://scholarships.gov.in/All-Scholarships",
        source_type="GOVERNMENT",
        evidence={"closing_date": "Student Application Open till : 31-12-2026",
                  "eligibility": "Class 10 pass",
                  "benefit_type": "Merit Based Scheme"},
    )
    data.update(overrides)
    return ScholarshipRecord(**data)


def test_full_marks_when_all_checks_pass():
    record = _base_record()
    result = score_record(record, is_official_domain=True, currently_present=True,
                           now=date(2026, 9, 1))
    assert result.score == 100.0
    assert result.label == "VERIFIED"


def test_aggregator_only_source_loses_official_points_and_fails_threshold():
    record = _base_record(official_source_url="https://careers360.com/some-article")
    result = score_record(record, is_official_domain=False, currently_present=True,
                           now=date(2026, 9, 1))
    assert result.breakdown["official_source"] == 0.0
    assert result.score < VERIFIED_THRESHOLD
    assert result.label == "REVIEW_REQUIRED"


def test_missing_from_latest_crawl_loses_presence_points():
    record = _base_record()
    result = score_record(record, is_official_domain=True, currently_present=False,
                           now=date(2026, 9, 1))
    assert result.breakdown["currently_present"] == 0.0
    assert result.score < 100.0


def test_no_deadline_evidence_loses_deadline_points_only():
    record = _base_record(closing_date="NOT_SPECIFIED", evidence={"eligibility": "Class 10 pass"})
    result = score_record(record, is_official_domain=True, currently_present=True,
                           now=date(2026, 9, 1))
    assert result.breakdown["deadline_evidence"] == 0.0
    assert result.breakdown["official_source"] == 30.0


def test_conflict_flag_deducts_points():
    record = _base_record()
    result = score_record(record, is_official_domain=True, currently_present=True,
                           now=date(2026, 9, 1), has_conflict=True)
    assert result.breakdown["no_conflict"] == 0.0
    assert result.score == 95.0
    assert result.label == "VERIFIED"  # 100 - 5 (conflict) still clears the 95 threshold
