"""
Live HTTP crawler. Uses `requests` first (cheap); a Playwright fallback
(`playwright_crawler.py`) is used only when a page is JS-rendered and
requests/BeautifulSoup cannot see the content, per the project's
source-format decision. PDFs/images are detected and never OCR'd/parsed --
the link is preserved and the record is flagged with SOURCE_FOUND /
LIMITED_DETAILS instead of guessing their contents.

NOTE: this module requires outbound internet access to the target site.
In the sandbox this project was authored in, outbound access is limited to
package registries, so `python -m scripts.run_crawler` defaults to the
fixture loader (crawler/fixture_loader.py) which replays real, previously
fetched snapshots. Point USE_LIVE_CRAWLER=1 at this module once you have
internet access from your machine/server.
"""
import requests
from bs4 import BeautifulSoup
from typing import Optional

HEADERS = {
    "User-Agent": "ScholarshipIntelligenceBot/1.0 (+educational project; contact: student)"
}

NON_HTML_EXTENSIONS = (".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx")


def fetch(url: str, timeout: int = 20) -> Optional[str]:
    """Fetch a URL, return page text, or None for non-HTML/binary content
    (which is intentionally NOT parsed -- see module docstring)."""
    if url.lower().endswith(NON_HTML_EXTENSIONS):
        return None
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type and "text" not in content_type:
        return None
    return resp.text


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)
