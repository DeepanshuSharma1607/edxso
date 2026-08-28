"""
Deterministic extractor for National Scholarship Portal (NSP) scheme blocks.

NSP's scheme listing is already semi-structured (ministry / scheme name /
open-till dates / spec+FAQ links), so we parse it with plain string logic
rather than an LLM. This is the "HTML with tables/structured blocks ->
process directly" path described in the project's extraction architecture.
Because every value below is read straight off the fetched page text, each
field's evidence is simply the source line itself -- nothing is invented.
"""
import re
from datetime import datetime
from typing import List, Dict
from backend.extraction.schemas import ScholarshipRecord, NOT_SPECIFIED

DATE_RE = re.compile(r"(\d{2})-(\d{2})-(\d{4})")


def _to_iso(date_str: str) -> str:
    m = DATE_RE.search(date_str or "")
    if not m:
        return NOT_SPECIFIED
    d, mo, y = m.groups()
    try:
        return datetime(int(y), int(mo), int(d)).date().isoformat()
    except ValueError:
        return NOT_SPECIFIED


def _course_level_from_name(name: str) -> str:
    n = name.lower()
    if "post graduate" in n or "pgs" in n or "srf" in n or "jrf" in n or "fellowship" in n:
        return "Postgraduate / Fellowship"
    if "pre matric" in n:
        return "Pre-Matric (School)"
    if "post matric" in n:
        return "Post-Matric (UG/Diploma)"
    if "technical degree" in n:
        return "B.Tech / B.E. (Technical Degree)"
    if "technical diploma" in n:
        return "Diploma (Technical)"
    if "college and university" in n or "csss" in n:
        return "UG/PG (College & University)"
    if "school" in n:
        return "School (Class 9-12)"
    return NOT_SPECIFIED


def parse_nsp_fixture(raw_text: str) -> List[ScholarshipRecord]:
    """Parse the pipe-delimited scheme blocks saved from scholarships.gov.in."""
    body = raw_text.split("---", 1)[-1]
    blocks = [b.strip() for b in body.split("\n\n") if b.strip() and not b.strip().startswith("#")]

    records: List[ScholarshipRecord] = []
    for block in blocks:
        lines = [l for l in block.splitlines() if l.strip() and not l.strip().startswith("#")]
        if not lines:
            continue
        field = {}
        for line in lines:
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            field.setdefault(key.strip(), val.strip())

        scheme_name = field.get("Scheme")
        if not scheme_name:
            continue

        ministry = field.get("Ministry", "National Scholarship Portal (NSP)")

        open_till_key = next((k for k in field if k.startswith("Student Application Open till")), None)
        open_from_key = next((k for k in field if k.startswith("Scheme Open from")), None)
        closing_raw = field.get(open_till_key, "") if open_till_key else ""
        opening_raw = field.get(open_from_key, "") if open_from_key else ""

        closing_date = _to_iso(closing_raw) if "NOT YET OPENED" not in closing_raw else NOT_SPECIFIED
        opening_date = _to_iso(opening_raw) if "NOT YET OPENED" not in opening_raw else NOT_SPECIFIED

        evidence = {}
        if open_till_key:
            evidence["closing_date"] = f"{open_till_key}: {field[open_till_key]}"
        if open_from_key:
            evidence["opening_date"] = f"{open_from_key}: {field[open_from_key]}"

        application_url = "https://scholarships.gov.in/ApplicationForm/"
        official_source_url = "https://scholarships.gov.in/All-Scholarships"
        spec_url = field.get("Specifications", NOT_SPECIFIED)
        if spec_url and spec_url != NOT_SPECIFIED:
            evidence["documents_required"] = f"Official scheme specification/guideline PDF: {spec_url}"

        benefit_type = "Merit Based Scheme" if "Merit Based" in scheme_name else (
            "Welfare Based Scheme" if "Welfare Based" in scheme_name else NOT_SPECIFIED
        )
        evidence["benefit_type"] = scheme_name

        record = ScholarshipRecord(
            name=re.sub(r"\s*\((Merit|Welfare) Based Scheme\)\s*$", "", scheme_name).strip(),
            provider=f"{ministry} (via National Scholarship Portal)",
            amount=NOT_SPECIFIED,  # NSP listing page does not state amounts per scheme -> never invented
            benefit_type=benefit_type,
            course_level=_course_level_from_name(scheme_name),
            opening_date=opening_date,
            closing_date=closing_date,
            documents_required=spec_url,
            application_url=application_url,
            official_source_url=official_source_url,
            source_type="GOVERNMENT",
            discovery_url="https://scholarships.gov.in/",
            evidence=evidence,
        )
        records.append(record)
    return records
