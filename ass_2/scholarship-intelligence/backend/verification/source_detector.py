"""
Source detector.

Aggregator-discovered records (see other_source_extractor.py) carry a
*claimed* official domain that was never actually fetched. This module is
the live-internet counterpart: given a claimed domain, it tries to fetch
it directly and confirm it's a real, reachable, scholarship-relevant page
before confidence.py is allowed to award official-source points for it.

This intentionally does NOT get called from the fixture-replay pipeline
(scripts/run_crawler.py) -- there is no internet access in that mode, so
every claimed domain would just fail to resolve and nothing would change.
It is wired into live_crawl_runner.py, which is meant to run once this
project is deployed somewhere with normal internet access.
"""
from dataclasses import dataclass
from typing import Optional
from backend.crawler.http_crawler import fetch, extract_visible_text
from backend.discovery.source_registry import is_official_domain, SourceDef

SCHOLARSHIP_SIGNAL_WORDS = ("scholarship", "fellowship", "eligibility", "apply", "financial assistance")


@dataclass
class DetectionResult:
    reachable: bool
    is_official: bool
    looks_relevant: bool
    page_text: Optional[str] = None
    error: Optional[str] = None


def verify_claimed_source(url: str, source: SourceDef) -> DetectionResult:
    """Attempt a live fetch of `url` and confirm it (a) is on the source's
    approved domain and (b) actually contains scholarship-relevant content,
    rather than just trusting the aggregator's claim."""
    if not is_official_domain(url, source):
        return DetectionResult(reachable=False, is_official=False, looks_relevant=False,
                                error="URL is not on an approved domain for this source")
    try:
        html = fetch(url)
    except Exception as e:  # network error, 404, timeout, etc.
        return DetectionResult(reachable=False, is_official=True, looks_relevant=False, error=str(e))

    if html is None:
        return DetectionResult(reachable=True, is_official=True, looks_relevant=False,
                                error="Non-HTML content (PDF/image) -- not parsed, treated as low-confidence")

    text = extract_visible_text(html)
    looks_relevant = any(w in text.lower() for w in SCHOLARSHIP_SIGNAL_WORDS)
    return DetectionResult(reachable=True, is_official=True, looks_relevant=looks_relevant, page_text=text)
