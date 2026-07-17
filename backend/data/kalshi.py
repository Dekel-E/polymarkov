"""Kalshi cross-venue client: keyless search with embedded live prices.

The v1 search endpoint returns events with yes_bid/yes_ask/last_price embedded
in cents; the unauthenticated v2 strips prices. Matching is conservative token
overlap. Degrades to None on any failure.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from backend import config

SEARCH_URL = "https://api.elections.kalshi.com/v1/search/series"
_HEADERS = {"User-Agent": "polymarkov/0.1", "Accept": "application/json"}

_STOPWORDS = {
    "will", "the", "a", "an", "of", "to", "in", "on", "at", "by", "be", "is",
    "are", "does", "do", "did", "for", "with", "before", "after", "this",
    "that", "their", "there", "it", "its", "and", "or", "any", "than", "more",
    "less", "who", "what", "when", "how", "?",
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS}


def match_score(question: str, candidate_text: str) -> float:
    """Fraction of the question's content tokens found in the candidate."""
    q = _tokens(question)
    if not q:
        return 0.0
    return len(q & _tokens(candidate_text)) / len(q)


def _cents(value: Any) -> Optional[float]:
    try:
        return round(float(value) / 100, 3)
    except (TypeError, ValueError):
        return None


def parse_search(body: dict, question: str) -> Optional[dict]:
    """Best-matching Kalshi event with priced markets, or None (pure)."""
    best: Optional[dict] = None
    best_score = 0.0
    for item in body.get("current_page") or []:
        if item.get("type") != "contract":
            continue
        text = " ".join(
            str(item.get(k) or "")
            for k in ("event_title", "event_subtitle", "series_title")
        )
        score = match_score(question, text)
        if score > best_score:
            best, best_score = item, score
    if best is None or best_score < config.KALSHI_MATCH_MIN:
        return None

    markets = []
    for m in (best.get("markets") or [])[: config.KALSHI_MAX_MARKETS]:
        yes_bid, yes_ask, last = _cents(m.get("yes_bid")), _cents(m.get("yes_ask")), _cents(m.get("last_price"))
        if yes_bid is None and yes_ask is None and last is None:
            continue
        markets.append(
            {
                "outcome": m.get("yes_subtitle") or m.get("ticker") or "",
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "last_price": last,
            }
        )
    if not markets:
        return None
    series = str(best.get("series_ticker") or "").lower()
    return {
        "venue": "Kalshi",
        "event_title": best.get("event_title") or best.get("series_title") or "",
        "event_subtitle": best.get("event_subtitle") or "",
        "url": f"https://kalshi.com/markets/{series}" if series else "",
        "match_score": round(best_score, 2),
        "markets": markets,
    }


async def find_matching_event(question: str) -> Optional[dict]:
    """Search Kalshi for the same event as `question`. None on any failure."""
    if not question.strip():
        return None
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            resp = await client.get(SEARCH_URL, params={"query": question.strip()[:120]})
            resp.raise_for_status()
            return parse_search(resp.json() or {}, question)
    except (httpx.HTTPError, ValueError):
        return None
