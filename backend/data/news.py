"""News & open-web intake — GDELT, Google News RSS, DuckDuckGo web search.

Three free, keyless sources with one normalized article shape
({url, title, domain, published_at, ...}); every fetcher degrades to []
instead of raising. GDELT is broad but noisy and rate-limits aggressively;
Google News search is precise and reliable; DuckDuckGo is the fallback
sense when the news feeds run thin. `fetch_article_text` turns any article
URL into readable excerpt text.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from backend import config

_HEADERS = {"User-Agent": "polymarkov/0.1 (course project)"}

# ---------------------------------------------------------------------------
# GDELT DOC 2.0 (10s timeout, one retry, fail fast on 429)
# ---------------------------------------------------------------------------

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def _quote_query(query: str) -> str:
    """GDELT treats unquoted multi-word queries as OR — quote phrases.
    English-only: multilingual results are noise the pipeline can't use."""
    query = query.strip()
    if " " in query and not query.startswith('"'):
        query = f'"{query}"'
    return f"{query} sourcelang:english"


def parse_seendate(seendate: str) -> Optional[str]:
    """'20260711T032400Z' -> ISO 8601, or None if malformed."""
    try:
        return (
            datetime.strptime(seendate, "%Y%m%dT%H%M%SZ")
            .replace(tzinfo=timezone.utc)
            .isoformat()
        )
    except (ValueError, TypeError):
        return None


def _normalize_gdelt(raw: dict) -> dict:
    return {
        "url": raw.get("url", ""),
        "title": raw.get("title", ""),
        "domain": raw.get("domain", ""),
        "published_at": parse_seendate(raw.get("seendate", "")),
        "language": raw.get("language", ""),
        "source_country": raw.get("sourcecountry", ""),
    }


async def gdelt_articles(
    query: str,
    timespan: str = config.GDELT_TIMESPAN,
    max_records: int = config.GDELT_MAX_RECORDS,
) -> list[dict]:
    """Recent GDELT articles matching `query`. Returns [] on any failure."""
    params = {
        "query": _quote_query(query),
        "mode": "ArtList",
        "maxrecords": max_records,
        "format": "json",
        "timespan": timespan,
    }
    for attempt in range(2):  # one retry
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
                resp = await client.get(GDELT_URL, params=params)
                resp.raise_for_status()
                articles = resp.json().get("articles") or []
                return [_normalize_gdelt(a) for a in articles if a.get("url")]
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError covers GDELT returning HTML/garbage instead of JSON
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                break  # rate-limited: a 1s retry cannot succeed, fail fast
            if attempt == 0:
                await asyncio.sleep(1.0)
    return []


# ---------------------------------------------------------------------------
# page crawling: URL -> readable excerpt text
# ---------------------------------------------------------------------------

_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def extract_text(html: str, max_chars: int = config.CITATION_TEXT_MAX_CHARS) -> str:
    """Cheap readable-text extraction (no heavy deps): strip tags, collapse ws."""
    text = _SCRIPT_RE.sub(" ", html)
    text = _HTML_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:max_chars]


async def fetch_article_text(url: str, max_chars: int = config.CITATION_TEXT_MAX_CHARS) -> str:
    """Fetch a page and return readable text, '' on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return extract_text(resp.text, max_chars)
    except httpx.HTTPError:
        return ""


# ---------------------------------------------------------------------------
# Google News RSS (precise, keyless, query-relevant headlines)
# ---------------------------------------------------------------------------

RSS_URL = "https://news.google.com/rss/search"


def _parse_pubdate(value: str) -> Optional[str]:
    try:
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError):
        return None


def parse_rss(xml_text: str, max_records: int) -> list[dict]:
    """RSS <item>s -> normalized articles. Malformed feed -> []."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    articles = []
    for item in root.iter("item"):
        url = (item.findtext("link") or "").strip()
        title = (item.findtext("title") or "").strip()
        if not url or not title:
            continue
        source = item.find("source")
        source_url = source.get("url", "") if source is not None else ""
        domain = urlparse(source_url).netloc or (source.text if source is not None else "") or "news.google.com"
        # Google appends " - Source Name" to titles; strip it for clean display
        if source is not None and source.text and title.endswith(f" - {source.text}"):
            title = title[: -len(f" - {source.text}")]
        articles.append(
            {
                "url": url,
                "title": title,
                "domain": domain.removeprefix("www."),
                "published_at": _parse_pubdate(item.findtext("pubDate") or ""),
            }
        )
        if len(articles) >= max_records:
            break
    return articles


async def google_news_articles(query: str, max_records: int = 10, days: int = 7) -> list[dict]:
    """Recent articles matching `query`, NEWEST FIRST. [] on failure.

    Google orders the feed by relevance, which surfaces day-old items over
    fresh ones — so we parse a wide window and re-sort by publish time."""
    params = {
        "q": f"{query} when:{days}d",
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    }
    try:
        async with httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(RSS_URL, params=params)
            resp.raise_for_status()
            articles = parse_rss(resp.text, max_records=60)
            articles.sort(key=lambda a: a["published_at"] or "", reverse=True)
            return articles[:max_records]
    except (httpx.HTTPError, ValueError):
        return []


# ---------------------------------------------------------------------------
# DuckDuckGo web search (keyless HTML endpoint — the fallback sense)
# ---------------------------------------------------------------------------

SEARCH_URL = "https://html.duckduckgo.com/html/"

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


def parse_web_results(page_html: str, max_results: int) -> list[dict]:
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


async def web_search(query: str, max_results: int = config.WEB_SEARCH_RESULTS) -> list[dict]:
    """Web results for `query`, article-shaped. [] on any failure."""
    try:
        async with httpx.AsyncClient(
            timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.get(SEARCH_URL, params={"q": query})
            resp.raise_for_status()
            return parse_web_results(resp.text, max_results)
    except (httpx.HTTPError, ValueError):
        return []
