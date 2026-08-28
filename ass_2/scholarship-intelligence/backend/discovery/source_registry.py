"""
Approved source registry.

`APPROVED_SOURCES` is the small seed list required by the assignment ("you
may start with a small number of seed sources"). Discovery (discovery.py)
then expands *within* these approved domains rather than the crawler being
a fixed URL->scraper mapping: for a portal like NSP it walks the scheme
index page and treats every scheme block as a candidate record; for a
university/corporate/NGO domain it would follow internal links matching
scholarship-like keywords (see discovery.py: `is_scholarship_like_link`).

is_official_domain() is what confidence.py calls to award the 30-point
"official source" check -- it is a plain domain match, not a guess.
"""
from urllib.parse import urlparse
from typing import Optional
from dataclasses import dataclass


@dataclass
class SourceDef:
    id: str
    name: str
    url: str
    source_type: str
    approved_domains: tuple  # domains considered "official" for this source


APPROVED_SOURCES = [
    SourceDef(
        id="S001",
        name="National Scholarship Portal (Govt. of India, MeitY)",
        url="https://scholarships.gov.in/",
        source_type="GOVERNMENT",
        approved_domains=("scholarships.gov.in", "nsp.gov.in"),
    ),
    SourceDef(
        id="S002",
        name="Reliance Foundation Scholarships",
        url="https://scholarships.reliancefoundation.org/",
        source_type="CORPORATE",
        approved_domains=("reliancefoundation.org",),
    ),
    SourceDef(
        id="S003",
        name="IILM University, Greater Noida",
        url="https://www.iilm.edu/",
        source_type="UNIVERSITY",
        approved_domains=("iilm.edu",),
    ),
]

SOURCE_BY_ID = {s.id: s for s in APPROVED_SOURCES}


def is_official_domain(url: str, source: Optional[SourceDef] = None) -> bool:
    """True only if `url`'s hostname matches one of the source's approved
    official domains. Aggregators (careers360.com, collegedunia.com,
    buddy4study.com, etc.) never match and therefore never earn the
    official-source confidence points, no matter how it was discovered."""
    if not url or url == "NOT_SPECIFIED":
        return False
    try:
        host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    except Exception:
        return False
    host = host.split(":")[0]
    domains = source.approved_domains if source else tuple(
        d for s in APPROVED_SOURCES for d in s.approved_domains
    )
    return any(host == d or host.endswith("." + d) for d in domains)
