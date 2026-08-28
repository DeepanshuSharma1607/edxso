"""
Live-internet crawl path (the counterpart to scripts/run_crawler.py's
fixture-replay path). This is what you switch to once the project is
running somewhere with normal outbound internet access.

  discovery.find_candidate_links()  -> candidate scholarship URLs on an
                                        approved domain
  http_crawler.fetch()              -> raw HTML per candidate URL
  http_crawler.extract_visible_text -> plain text (script/style stripped)
  llm_extractor.extract_with_llm()  -> ScholarshipRecord via Mistral, for
                                        pages that are NOT already
                                        structured enough for a rule-based
                                        parser (rule_extractor.py stays the
                                        right tool for a source like NSP
                                        whose listing page is already
                                        semi-structured)
  services.crawl_runner.run_crawl() -> same verify/score/store/update
                                        pipeline used by the fixture path

Nothing about verification, scoring, storage, change detection or expiry
differs between this path and the fixture-replay path -- only how the
ScholarshipRecord list is produced differs.
"""
import logging
from typing import List
from backend.discovery.source_registry import SourceDef
from backend.discovery.discovery import find_candidate_links
from backend.crawler.http_crawler import fetch, extract_visible_text
from backend.extraction.schemas import ScholarshipRecord
from backend.extraction.llm_extractor import extract_with_llm
from backend.services.crawl_runner import run_crawl

logger = logging.getLogger("live_crawl")


def crawl_source_live(source: SourceDef, entry_url: str, max_pages: int = 25) -> List[ScholarshipRecord]:
    """Discover + crawl + extract every scholarship-like page under
    `entry_url` on `source`'s approved domain. Requires real internet
    access and a valid MISTRAL_API_KEY. Any page that fails to fetch or
    fails to parse as valid JSON is skipped and logged -- it is never
    silently guessed at."""
    records: List[ScholarshipRecord] = []

    entry_html = fetch(entry_url)
    if entry_html is None:
        logger.warning("Entry point %s returned no HTML (binary or fetch error) -- aborting discovery", entry_url)
        return records

    candidate_urls = find_candidate_links(entry_url, entry_html, source.approved_domains)
    logger.info("Discovered %d scholarship-like candidate links under %s", len(candidate_urls), entry_url)

    for url in candidate_urls[:max_pages]:
        try:
            html = fetch(url)
            if html is None:
                logger.info("Skipping non-HTML candidate: %s", url)
                continue
            text = extract_visible_text(html)
            record = extract_with_llm(text, official_source_url=url, source_type=source.source_type,
                                       discovery_url=entry_url)
            records.append(record)
        except Exception as e:
            logger.warning("Failed to extract %s: %s (skipped, not guessed)", url, e)
            continue

    return records


def run_live_crawl(source: SourceDef, entry_url: str, simulated_now=None) -> dict:
    """Full discover -> crawl -> extract -> verify -> score -> store -> update
    for one approved source, using real internet + Mistral."""
    records = crawl_source_live(source, entry_url)
    return run_crawl(source.id, records, simulated_now=simulated_now)
