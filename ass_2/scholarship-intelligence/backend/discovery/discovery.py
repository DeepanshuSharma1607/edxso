"""
Discovery layer.

Given an approved source, discovery does NOT hardcode "URL -> scraper".
Instead it:
  1. Fetches the source's known entry point(s) (e.g. the scheme index page).
  2. Parses internal links and classifies them as scholarship-like using
     keyword heuristics (`is_scholarship_like_link`) rather than a fixed
     per-source list of scholarship URLs.
  3. Hands the resulting page/block set to the crawler layer for extraction.

For NSP specifically, the index page (`/All-Scholarships`) already lists
every scheme block in one document, so discovery's job there collapses to
"split into blocks" (done in rule_extractor). For a generic HTML site,
`find_candidate_links` is what would be used against a live fetch.
"""
import re
from typing import List
from urllib.parse import urljoin, urlparse

SCHOLARSHIP_KEYWORDS = (
    "scholarship", "fellowship", "financial-assistance", "financial_aid",
    "stipend", "fee-waiver", "bursary", "grant-in-aid",
)


def is_scholarship_like_link(href: str, anchor_text: str = "") -> bool:
    text = f"{href} {anchor_text}".lower()
    return any(k in text for k in SCHOLARSHIP_KEYWORDS)


def find_candidate_links(base_url: str, html: str, approved_domains: tuple) -> List[str]:
    """Very small dependency-free link scanner (BeautifulSoup is used in
    http_crawler.py for real fetches; this keeps discovery testable without
    a live document)."""
    links = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        href = m.group(1)
        full = urljoin(base_url, href)
        host = urlparse(full).netloc.lower()
        if not any(host == d or host.endswith("." + d) for d in approved_domains):
            continue
        if is_scholarship_like_link(full):
            links.add(full)
    return sorted(links)
