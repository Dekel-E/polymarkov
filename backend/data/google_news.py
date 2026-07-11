"""Google News RSS client — free, keyless, query-relevant headlines.

Second live news source next to GDELT: GDELT is broad but noisy and
rate-limits aggressively; Google News search is precise and reliable.
Same normalized article shape; degrades to [] on any failure.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urlparse

import httpx

from backend import config

RSS_URL = "https://news.google.com/rss/search"
_HEADERS = {"User-Agent": "polymarkov/0.1 (course project)"}


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


async def fetch_articles(query: str, max_records: int = 10, days: int = 7) -> list[dict]:
    """Recent articles matching `query`, newest first. [] on failure."""
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
            return parse_rss(resp.text, max_records)
    except (httpx.HTTPError, ValueError):
        return []
