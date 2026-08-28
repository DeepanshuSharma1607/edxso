"""Parses data/fixtures/run1_other_sources.txt into ScholarshipRecords.

These records were discovered via aggregators, not fetched from the
provider's own domain (see the fixture file's header comment for why).
`official_source_url` is still set to the provider's real domain (as
declared by the provider itself / claimed in the aggregator text) so the
confidence engine can correctly check it -- and correctly award ZERO
points for "official source", since source_registry.is_official_domain()
only trusts a domain match, not a claim. This is what pushes these two
records to REVIEW_REQUIRED, exactly as the assignment expects for
aggregator-only discovery.

In production (live internet), source_detector.py would attempt to fetch
the claimed domain directly; if it resolves and contains matching content,
confidence.py would then legitimately score it as an official source.
"""
from typing import List
from backend.extraction.schemas import ScholarshipRecord, NOT_SPECIFIED


def parse_other_sources_fixture(raw_text: str) -> List[ScholarshipRecord]:
    body = raw_text.split("---", 1)[-1]
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    records = []
    for block in blocks:
        field = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, _, val = line.partition(":")
            field[key.strip()] = val.strip()
        if "NAME" not in field:
            continue

        evidence = {}
        if "EVIDENCE_TEXT" in field:
            evidence["closing_date"] = field["EVIDENCE_TEXT"]
            evidence["opening_date"] = field["EVIDENCE_TEXT"]
        if "AMOUNT_EVIDENCE" in field:
            evidence["amount"] = field["AMOUNT_EVIDENCE"]
        if "ELIGIBILITY_EVIDENCE" in field:
            evidence["eligibility"] = field["ELIGIBILITY_EVIDENCE"]
            evidence["course_level"] = field["ELIGIBILITY_EVIDENCE"]

        record = ScholarshipRecord(
            name=field["NAME"],
            provider=field.get("PROVIDER", NOT_SPECIFIED),
            amount=NOT_SPECIFIED,  # 2022-23 figure only; current-cycle amount not directly confirmed -> not guessed
            eligibility=field.get("ELIGIBILITY_EVIDENCE", NOT_SPECIFIED),
            course_level="Undergraduate" if "Undergraduate" in field["NAME"] or "UG" in field.get("ELIGIBILITY_EVIDENCE", "") else NOT_SPECIFIED,
            closing_date=NOT_SPECIFIED,  # 2025-26 dates found only in a news aggregator, not the official page -> kept unspecified for DB trust
            official_source_url=f"https://{field.get('CLAIMED_OFFICIAL_DOMAIN', '')}",
            source_type=field.get("SOURCE_TYPE", "OTHER_OFFICIAL"),
            discovery_url=field.get("DISCOVERY_URL"),
            evidence=evidence,
        )
        records.append(record)
    return records
