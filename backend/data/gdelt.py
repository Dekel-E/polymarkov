"""GDELT DOC 2.0 news client. Free, no key, notoriously flaky.

Contract: 10s timeout, one retry, and degrade gracefully to [] so the
pipeline falls back to cached news instead of failing.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend import config

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

_HEADERS = {"User-Agent": "polymarkov/0.1 (course project)"}


def _quote_query(query: str) -> str:
    """GDELT treats unquoted multi-word queries as OR — quote phrases."""
    query = query.strip()
    if " " in query and not query.startswith('"'):
        return f'"{query}"'
    return query


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


def _normalize_article(raw: dict) -> dict:
    return {
        "url": raw.get("url", ""),
        "title": raw.get("title", ""),
        "domain": raw.get("domain", ""),
        "published_at": parse_seendate(raw.get("seendate", "")),
        "language": raw.get("language", ""),
        "source_country": raw.get("sourcecountry", ""),
    }


async def fetch_articles(
    query: str,
    timespan: str = config.GDELT_TIMESPAN,
    max_records: int = config.GDELT_MAX_RECORDS,
) -> list[dict]:
    """Recent articles matching `query`. Returns [] on any failure."""
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
                return [_normalize_article(a) for a in articles if a.get("url")]
        except (httpx.HTTPError, ValueError) as exc:
            # ValueError covers GDELT returning HTML/garbage instead of JSON
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                break  # rate-limited: a 1s retry cannot succeed, fail fast
            if attempt == 0:
                await asyncio.sleep(1.0)
    return []


_TAG_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def extract_text(html: str, max_chars: int = config.CITATION_TEXT_MAX_CHARS) -> str:
    """Cheap readable-text extraction (no heavy deps): strip tags, collapse ws."""
    text = _TAG_RE.sub(" ", html)
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
