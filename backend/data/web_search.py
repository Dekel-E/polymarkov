"""Keyless web search (DuckDuckGo HTML) + page crawling.

The agent's fallback sense: when the news feeds run thin for a market, it
searches the open web and reads the pages (crawling reuses the same
readable-text extractor as news excerpts). Low volume, polite UA, degrades
to [] — never breaks a run.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from backend import config

SEARCH_URL = "https://html.duckduckgo.com/html/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; polymarkov/0.1; course project)"}

_RESULT_RE = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_url(href: str) -> Optional[str]:
    """DDG wraps results in a redirect (//duckduckgo.com/l/?uddg=<real>)."""
    href = html_lib.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc:
        target = parse_qs(parsed.query).get("uddg", [None])[0]
        return unquote(target) if target else None
    return href if parsed.scheme in ("http", "https") else None


def parse_results(page_html: str, max_results: int) -> list[dict]:
    """DDG result page -> normalized articles (pure)."""
    results = []
    seen: set[str] = set()
    for match in _RESULT_RE.finditer(page_html):
        url = _clean_url(match.group("href"))
        title = html_lib.unescape(_TAG_RE.sub("", match.group("title"))).strip()
        if not url or not title or url in seen:
            continue
        domain = urlparse(url).netloc.removeprefix("www.")
        if "duckduckgo.com" in domain:
            continue
        seen.add(url)
        results.append({"url": url, "title": title, "domain": domain, "published_at": None})
        if len(results) >= max_results:
            break
    return results


async def search(query: str, max_results: int = config.WEB_SEARCH_RESULTS) -> list[dict]:
    """Web results for `query`, article-shaped. [] on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(SEARCH_URL, params={"q": query})
            resp.raise_for_status()
            return parse_results(resp.text, max_results)
    except (httpx.HTTPError, ValueError):
        return []


async def crawl(url: str, max_chars: int = config.CITATION_TEXT_MAX_CHARS) -> str:
    """Fetch a page and return readable text ('' on failure)."""
    from backend.data.gdelt import fetch_article_text

    return await fetch_article_text(url, max_chars)
