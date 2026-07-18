"""Polymarket public API clients: Gamma (metadata) + CLOB (order book/prices).

No auth. Gamma returns outcomes/outcomePrices/clobTokenIds as stringified JSON
and numbers as strings, so parse defensively. CLOB book levels are unsorted.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import httpx

from backend import config
from backend.agent.types import MarketState

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

_HEADERS = {"User-Agent": "polymarkov/0.1"}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS)


def _json_list(value: Any) -> list:
    """Gamma stringified-array fields ('["Yes","No"]') -> real list."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_market_ref(text: str) -> Optional[str]:
    """Extract a market/event slug from a pasted Polymarket URL, else None."""
    match = re.search(
        r"polymarket\.com/(?:event|market)/([a-z0-9-]+)(?:/([a-z0-9-]+))?",
        text.lower(),
    )
    if not match:
        return None
    # prefer the market slug over the event slug
    return match.group(2) or match.group(1)


# Gamma's category is usually empty; infer from question text. First match wins.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("sports", (
        "world cup", "fifa", "uefa", "champions league", "premier league", "la liga",
        "nba", "nfl", "nhl", "mlb", "super bowl", "olympic", "grand slam", "wimbledon",
        "us open", "f1", "grand prix", "ufc", "heavyweight", "playoff", "finals",
        "win the match", "relegat", "world series", "stanley cup", "ballon d'or",
        # match-market phrasings
        " vs. ", " vs ", "exact score", "both teams to score", "o/u", "to advance",
        "in a draw", "clean sheet", "first goalscorer", "hat-trick", "penalty shootout",
    )),
    ("crypto", (
        "bitcoin", "btc", "ethereum", " eth ", "solana", "crypto", "dogecoin", "xrp",
        "binance", "coinbase", "stablecoin", "microstrategy", "satoshi", "memecoin",
    )),
    ("geopolitics", (
        "ceasefire", "war ", " war", "invasion", "invade", "military strike", "strike on",
        "nato", "sanction", "nuclear", "missile", "hostage", "blockade", "annex",
        "peace deal", "territory", "airspace", "border clash", "mou",
        "strait of", "idf", "hezbollah", "hamas", "kremlin",
    )),
    ("politics", (
        "election", "president", "prime minister", "senate", "congress", "parliament",
        "governor", "mayor", "minister", "impeach", "nominee", "cabinet", "coalition",
        "supreme court", "knesset", "chancellor", "referendum", "veto", "legislation",
    )),
    ("economics", (
        "fed ", "the fed", "fomc", "interest rate", "rate cut", "rate hike", "inflation",
        "cpi", "gdp", "recession", "unemployment", "tariff", "ecb", "central bank",
    )),
    ("finance", (
        "stock", "s&p", "nasdaq", "dow jones", "ipo", "market cap", "earnings",
        "shares", "acquisition", "merger", "bankrupt",
    )),
    ("tech", (
        "openai", "chatgpt", "gpt-", "anthropic", "ai model", "artificial intelligence",
        "apple", "google", "tesla", "spacex", "nvidia", "iphone", "starship", "self-driving",
    )),
    ("culture", (
        "oscar", "grammy", "emmy", "box office", "album", "movie", "netflix",
        "taylor swift", "billboard", "eurovision", "time person of the year", "spotify",
    )),
    ("weather", (
        "hurricane", "temperature", "rainfall", "snowfall", "heatwave", "tornado",
        "named storm", "degrees",
    )),
]


def infer_category(text: str) -> str:
    """Best-effort category from question/title text; 'other' when unsure."""
    haystack = f" {text.lower()} "
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(k in haystack for k in keywords):
            return category
    return "other"


def normalize_market(raw: dict) -> dict:
    """Normalize one Gamma market object into plain, typed fields."""
    outcomes = _json_list(raw.get("outcomes"))
    prices = [_to_float(p) for p in _json_list(raw.get("outcomePrices"))]
    token_ids = [str(t) for t in _json_list(raw.get("clobTokenIds"))]

    best_bid = _to_float(raw.get("bestBid"), default=None) if raw.get("bestBid") is not None else None
    best_ask = _to_float(raw.get("bestAsk"), default=None) if raw.get("bestAsk") is not None else None
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
    elif prices:
        mid = prices[0]
    else:
        mid = 0.5

    events = raw.get("events") or []
    category = str(
        raw.get("category") or (events[0].get("category") if events else "") or ""
    ).lower()
    if not category or category == "other":
        event_title = events[0].get("title", "") if events else ""
        category = infer_category(f"{raw.get('question', '')} {event_title}")

    return {
        "id": str(raw.get("id", "")),
        "slug": raw.get("slug", ""),
        "question": raw.get("question", ""),
        "description": raw.get("description", ""),
        "category": str(category).lower(),
        "end_date": raw.get("endDate"),
        "outcomes": outcomes,
        "outcome_prices": prices,
        "yes_token_id": token_ids[0] if token_ids else "",
        "no_token_id": token_ids[1] if len(token_ids) > 1 else "",
        "mid": mid,
        "best_bid": best_bid,
        "best_ask": best_ask,
        "spread": (best_ask - best_bid) if (best_bid is not None and best_ask is not None) else None,
        "volume24h": _to_float(raw.get("volume24hr")),
        "one_day_change": (
            _to_float(raw.get("oneDayPriceChange")) if raw.get("oneDayPriceChange") is not None else None
        ),
        "liquidity": _to_float(raw.get("liquidityNum") or raw.get("liquidity")),
        "image": raw.get("image") or raw.get("icon") or "",
        "created_at": raw.get("createdAt"),
        "condition_id": raw.get("conditionId") or "",
        "active": bool(raw.get("active", True)),
        "event_id": str(events[0].get("id", "")) if events else "",
        "event_title": events[0].get("title", "") if events else "",
    }


async def list_markets(
    limit: int = 100,
    offset: int = 0,
    closed: bool = False,
    order: str = "volume24hr",
) -> list[dict]:
    """One page of markets, normalized, sorted by `order` descending."""
    params = {
        "closed": str(closed).lower(),
        "order": order,
        "ascending": "false",
        "limit": limit,
        "offset": offset,
    }
    if not closed:
        params["active"] = "true"
    async with _client() as client:
        resp = await client.get(f"{GAMMA_BASE}/markets", params=params)
        resp.raise_for_status()
        return [normalize_market(m) for m in resp.json()]


async def get_trending_markets(limit: int = 20) -> list[dict]:
    """Top active markets by 24h volume, paging past Gamma's 100-per-request cap."""
    markets: list[dict] = []
    seen: set[str] = set()
    for offset in range(0, limit, 100):
        page = await list_markets(limit=min(100, limit - offset), offset=offset)
        if not page:
            break
        for m in page:
            if m["id"] and m["id"] not in seen:
                seen.add(m["id"])
                markets.append(m)
    return markets


async def list_new_markets(limit: int = 30) -> list[dict]:
    """Most recently created active markets (early-look candidates)."""
    return await list_markets(limit=limit, order="createdAt")


async def list_events(limit: int = 20, neg_risk_only: bool = False) -> list[dict]:
    """Active events with their markets. negRisk events are mutually exclusive (one winner)."""
    async with _client() as client:
        resp = await client.get(
            f"{GAMMA_BASE}/events",
            params={
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
                "limit": limit,
            },
        )
        resp.raise_for_status()
        events = []
        for e in resp.json():
            neg_risk = bool(e.get("negRisk"))
            if neg_risk_only and not neg_risk:
                continue
            markets = [
                normalize_market({**m, "events": [e]})
                for m in e.get("markets") or []
                if m.get("active", True) and not m.get("closed", False)
            ]
            events.append(
                {
                    "id": str(e.get("id", "")),
                    "title": e.get("title", ""),
                    "slug": e.get("slug", ""),
                    "neg_risk": neg_risk,
                    "markets": [m for m in markets if m["yes_token_id"]],
                }
            )
        return events


async def search_markets(query: str, limit: int = 10) -> list[dict]:
    """Gamma public text search; returns normalized markets, best first."""
    async with _client() as client:
        resp = await client.get(
            f"{GAMMA_BASE}/public-search",
            params={"q": query, "limit_per_type": limit, "events_status": "active"},
        )
        resp.raise_for_status()
        events = resp.json().get("events") or []
        markets: list[dict] = []
        # Gamma returns events sorted by relevance. We should preserve that order
        # but pick the highest-volume market within each relevant event.
        for event in events:
            event_markets = []
            for m in event.get("markets") or []:
                m.setdefault("events", [{k: event.get(k) for k in ("id", "title", "category")}])
                event_markets.append(normalize_market(m))
            if event_markets:
                # Pick the highest volume market from this specific event
                best_in_event = max(event_markets, key=lambda m: m["volume24h"])
                markets.append(best_in_event)
                
        return markets[:limit]


async def get_market(slug_or_id: str) -> Optional[dict]:
    """Resolve one market by slug (or numeric Gamma id). None if not found."""
    params: dict[str, Any]
    if slug_or_id.isdigit():
        params = {"id": slug_or_id}
    else:
        params = {"slug": slug_or_id}
    async with _client() as client:
        resp = await client.get(f"{GAMMA_BASE}/markets", params=params)
        resp.raise_for_status()
        rows = resp.json()
        if rows:
            return normalize_market(rows[0])
        # maybe an event slug; take its highest-volume market
        resp = await client.get(f"{GAMMA_BASE}/events", params={"slug": slug_or_id})
        resp.raise_for_status()
        events = resp.json()
        if not events:
            return None
        markets = [normalize_market({**m, "events": [events[0]]}) for m in events[0].get("markets") or []]
        markets = [m for m in markets if m["active"]]
        if not markets:
            return None
        return max(markets, key=lambda m: m["volume24h"])


async def get_order_book(token_id: str) -> dict:
    """Return {'bids': [(price, size)...best-first], 'asks': [...best-first]}."""
    async with _client() as client:
        resp = await client.get(f"{CLOB_BASE}/book", params={"token_id": token_id})
        resp.raise_for_status()
        raw = resp.json()

    def levels(key: str) -> list[tuple[float, float]]:
        return [(_to_float(l.get("price")), _to_float(l.get("size"))) for l in raw.get(key) or []]

    return {
        "bids": sorted(levels("bids"), key=lambda l: l[0], reverse=True),
        "asks": sorted(levels("asks"), key=lambda l: l[0]),
    }


async def get_price_history(token_id: str, interval: str = "1w", fidelity: int = 180) -> list[tuple[float, float]]:
    """[(unix_ts, price), ...] oldest first."""
    async with _client() as client:
        resp = await client.get(
            f"{CLOB_BASE}/prices-history",
            params={"market": token_id, "interval": interval, "fidelity": fidelity},
        )
        resp.raise_for_status()
        points = resp.json().get("history") or []
        return [(_to_float(p.get("t")), _to_float(p.get("p"))) for p in points]


def depth_usd(levels: list[tuple[float, float]]) -> float:
    """Total notional (price * size) resting on the given side of the book."""
    return sum(price * size for price, size in levels)


def walk_book(asks: list[tuple[float, float]], size_usd: float) -> dict:
    """Simulate a taker buy of size_usd against ask levels (best-first)."""
    if size_usd <= 0 or not asks:
        return {
            "filled_usd": 0.0, "shares": 0.0, "vwap": None,
            "levels_consumed": 0, "slippage_pts": 0.0, "slippage_bps": 0.0,
            "exhausted": bool(asks),
        }
    best_ask = asks[0][0]
    remaining = size_usd
    shares = 0.0
    levels_consumed = 0
    for price, size in asks:
        if remaining <= 0:
            break
        level_notional = price * size
        take_usd = min(remaining, level_notional)
        shares += take_usd / price
        remaining -= take_usd
        levels_consumed += 1
    filled_usd = size_usd - remaining
    vwap = filled_usd / shares if shares else None
    slippage_pts = (vwap - best_ask) if vwap is not None else 0.0
    return {
        "filled_usd": round(filled_usd, 6),
        "shares": round(shares, 6),
        "vwap": round(vwap, 6) if vwap is not None else None,
        "levels_consumed": levels_consumed,
        "slippage_pts": round(slippage_pts, 6),
        "slippage_bps": round(slippage_pts / best_ask * 10_000, 2) if best_ask else 0.0,
        "exhausted": remaining > 1e-9,
    }


async def get_market_state(slug_or_id: str) -> Optional[MarketState]:
    market = await get_market(slug_or_id)
    if market is None or not market["yes_token_id"]:
        return None

    book = {"bids": [], "asks": []}
    history: list[tuple[float, float]] = []
    try:
        book = await get_order_book(market["yes_token_id"])
    except httpx.HTTPError:
        pass
    try:
        history = await get_price_history(market["yes_token_id"])
    except httpx.HTTPError:
        pass

    best_bid = book["bids"][0][0] if book["bids"] else market["best_bid"]
    best_ask = book["asks"][0][0] if book["asks"] else market["best_ask"]
    if best_bid is not None and best_ask is not None:
        mid = (best_bid + best_ask) / 2
        spread = best_ask - best_bid
    else:
        mid, spread = market["mid"], market["spread"]

    return MarketState(
        question=market["question"],
        slug=market["slug"],
        event_id=market["event_id"],
        end_date=market["end_date"],
        resolution_criteria=market["description"],
        category=market["category"] if market["category"] in config.FEE_RATE else "other",
        yes_token_id=market["yes_token_id"],
        condition_id=market.get("condition_id", ""),
        mid=mid,
        best_bid=best_bid,
        best_ask=best_ask,
        spread=spread,
        depth_at_ask_usd=round(depth_usd(book["asks"]), 2),
        volume24h=market["volume24h"],
        price_history_7d=history,
        bids=book["bids"],
        asks=book["asks"],
    )
