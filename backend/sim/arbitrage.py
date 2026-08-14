"""Arbitrage detection over Polymarket books (pure math, no LLM).

Spread arb: best YES ask + best NO ask below $1 by more than fees. Dutch book:
best YES asks across all outcomes of a negRisk event sum below $1. Paper-only,
so no latency race against real HFT bots.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from typing import Optional

from backend import config
from backend.agent.pricing import taker_fee
from backend.data import polymarket


def spread_opportunity(
    yes_asks: list[tuple[float, float]],
    no_asks: list[tuple[float, float]],
    category: str,
    market: dict,
    min_edge: float = config.ARB_MIN_EDGE,
) -> Optional[dict]:
    """YES ask + NO ask < $1 by more than fees -> guaranteed profit."""
    if not yes_asks or not no_asks:
        return None
    yes_price, yes_size = yes_asks[0]
    no_price, no_size = no_asks[0]
    if yes_price <= 0 or no_price <= 0:
        return None

    cost = yes_price + no_price
    fees = taker_fee(category, yes_price) + taker_fee(category, no_price)
    profit_per_share = 1.0 - cost - fees
    if profit_per_share < min_edge:
        return None

    shares = min(yes_size, no_size, config.ARB_MAX_SIZE_USD / max(yes_price, no_price))
    if shares <= 0:
        return None
    return {
        "type": "spread",
        "question": market["question"],
        "event_title": market.get("event_title", ""),
        "cost_per_share": round(cost, 4),
        "fees_per_share": round(fees, 4),
        "profit_per_share": round(profit_per_share, 4),
        "roi_pct": round(profit_per_share / cost * 100, 2),
        "max_shares": round(shares, 2),
        "guaranteed_profit_usd": round(profit_per_share * shares, 2),
        "legs": [
            {"slug": market["slug"], "side": "BUY_YES", "price": yes_price,
             "size_usd": round(min(shares * yes_price, config.ARB_MAX_SIZE_USD), 2)},
            {"slug": market["slug"], "side": "BUY_NO", "price": no_price,
             "size_usd": round(min(shares * no_price, config.ARB_MAX_SIZE_USD), 2)},
        ],
    }


def dutch_book_opportunity(
    event: dict,
    outcome_asks: list[tuple[dict, list[tuple[float, float]]]],
    min_edge: float = config.ARB_MIN_EDGE,
) -> Optional[dict]:
    """Sum of best YES asks across ALL outcomes of a negRisk event < $1."""
    if len(outcome_asks) < 2 or len(outcome_asks) != len(event["markets"]):
        return None  # every outcome must be buyable or the book isn't covered
    legs = []
    cost = 0.0
    fees = 0.0
    max_shares = float("inf")
    for market, asks in outcome_asks:
        if not asks or asks[0][0] <= 0:
            return None
        price, size = asks[0]
        cost += price
        fees += taker_fee(market["category"], price)
        max_shares = min(max_shares, size)
        legs.append({"slug": market["slug"], "side": "BUY_YES", "price": price})

    profit_per_share = 1.0 - cost - fees
    if profit_per_share < min_edge:
        return None
    max_shares = min(max_shares, config.ARB_MAX_SIZE_USD / max(l["price"] for l in legs))
    if max_shares <= 0:
        return None
    for leg in legs:
        leg["size_usd"] = round(min(max_shares * leg["price"], config.ARB_MAX_SIZE_USD), 2)
    return {
        "type": "dutch_book",
        "question": event["title"],
        "event_title": event["title"],
        "cost_per_share": round(cost, 4),
        "fees_per_share": round(fees, 4),
        "profit_per_share": round(profit_per_share, 4),
        "roi_pct": round(profit_per_share / cost * 100, 2),
        "max_shares": round(max_shares, 2),
        "guaranteed_profit_usd": round(profit_per_share * max_shares, 2),
        "legs": legs,
    }


_SEM = asyncio.Semaphore(5)  # be polite to the CLOB API


async def _asks(token_id: str) -> list[tuple[float, float]]:
    async with _SEM:
        try:
            book = await polymarket.get_order_book(token_id)
            return book["asks"]
        except Exception:
            return []


async def scan(
    n_markets: int = config.ARB_SCAN_MARKETS,
    n_events: int = config.ARB_SCAN_EVENTS,
) -> list[dict]:
    """Spread arbs on top markets + dutch books on negRisk events, sorted by profit."""
    opportunities: list[dict] = []

    # 1. spread arbs: need both token books
    markets = [
        m for m in await polymarket.get_trending_markets(n_markets) if m["no_token_id"]
    ]
    yes_books, no_books = await asyncio.gather(
        asyncio.gather(*(_asks(m["yes_token_id"]) for m in markets)),
        asyncio.gather(*(_asks(m["no_token_id"]) for m in markets)),
    )
    for m, yes_asks, no_asks in zip(markets, yes_books, no_books):
        opp = spread_opportunity(yes_asks, no_asks, m["category"], m)
        if opp:
            opportunities.append(opp)

    # 2. dutch books on mutually exclusive events
    events = [
        e
        for e in await polymarket.list_events(limit=n_events, neg_risk_only=True)
        if 2 <= len(e["markets"]) <= 15
    ]
    for event in events:
        asks = await asyncio.gather(*(_asks(m["yes_token_id"]) for m in event["markets"]))
        opp = dutch_book_opportunity(event, list(zip(event["markets"], asks)))
        if opp:
            opportunities.append(opp)

    # 3. correlation-graph violations (relations built by jobs/build_relations)
    from backend.data import supabase_client
    from backend.sim import correlation

    settings = supabase_client.get_agent_settings()
    if settings["strategies"].get("correlation") and supabase_client.is_configured():
        try:
            relations = (
                supabase_client.get_client()
                .table("market_relations")
                .select("*")
                .limit(40)
                .execute()
                .data
                or []
            )
        except Exception:
            relations = []
        for rel in relations:
            if rel["relation"] == "implies":
                b_yes, a_no = await asyncio.gather(_asks(rel["b_yes_token"]), _asks(rel["a_no_token"]))
                opp = correlation.implies_opportunity(rel, b_yes, a_no)
            else:
                a_no, b_no = await asyncio.gather(_asks(rel["a_no_token"]), _asks(rel["b_no_token"]))
                opp = correlation.excludes_opportunity(rel, a_no, b_no)
            if opp:
                opportunities.append(opp)

    opportunities.sort(key=lambda o: o["guaranteed_profit_usd"], reverse=True)
    return opportunities


def opportunity_signature(opportunity: dict) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Stable identity for matching a client selection to a server scan."""
    legs = opportunity.get("legs") or []
    return (
        str(opportunity.get("type") or ""),
        tuple(sorted((str(leg.get("slug") or ""), str(leg.get("side") or "")) for leg in legs)),
    )


async def execute_legs(opportunity: dict) -> list[dict]:
    """Atomically simulate a complete basket against freshly fetched books.

    Every leg is preflighted for the same share count and the edge is
    recomputed after modeled fees. Nothing is recorded unless the whole basket
    remains liquid and profitable. The eventual database write is one atomic
    multi-row insert.
    """
    from backend.data import supabase_client

    legs = opportunity.get("legs") or []
    kind = opportunity.get("type")
    if kind not in {"spread", "dutch_book", "correlation"} or not (2 <= len(legs) <= 16):
        return failed_reports(legs, "invalid basket")
    try:
        requested_shares = float(opportunity.get("max_shares") or 0)
        scanned_prices = [float(leg["price"]) for leg in legs]
    except (KeyError, TypeError, ValueError):
        return failed_reports(legs, "invalid basket size or price")
    if not math.isfinite(requested_shares) or requested_shares <= 0:
        return failed_reports(legs, "invalid basket size")
    if any(not math.isfinite(price) or not 0 < price < 1 for price in scanned_prices):
        return failed_reports(legs, "invalid scanned price")
    requested_shares = min(
        requested_shares,
        *(config.ARB_MAX_SIZE_USD / price for price in scanned_prices),
    )

    prepared = await asyncio.gather(
        *(_prepare_leg(leg, requested_shares) for leg in legs)
    )
    failures = [item["error"] for item in prepared if item.get("error")]
    if failures:
        return failed_reports(legs, failures[0])

    total_cost_per_share = sum(
        item["vwap"] + item["fee_per_share"] for item in prepared
    )
    fresh_profit_per_share = 1.0 - total_cost_per_share
    if fresh_profit_per_share < config.ARB_MIN_EDGE:
        return failed_reports(legs, "edge disappeared at fresh executable prices")

    positions = [item["position"] for item in prepared]
    try:
        ids = await asyncio.to_thread(supabase_client.insert_positions, positions)
    except Exception as exc:
        return failed_reports(legs, f"basket write failed: {exc}")
    if len(ids) != len(positions):
        return failed_reports(legs, "basket write returned an incomplete result")

    reports = []
    for item, position_id in zip(prepared, ids):
        reports.append(
            {
                "slug": item["slug"],
                "side": item["side"],
                "filled": True,
                "vwap": item["vwap"],
                "size_usd": item["filled_usd"],
                "position_id": position_id or f"local-{uuid.uuid4()}",
                "fresh_profit_per_share": round(fresh_profit_per_share, 6),
            }
        )
    return reports


def failed_reports(legs: list[dict], error: str) -> list[dict]:
    return [
        {
            "slug": str(leg.get("slug") or ""),
            "side": leg.get("side"),
            "filled": False,
            "error": error,
        }
        for leg in legs
    ]


def _walk_shares(asks: list[tuple[float, float]], requested_shares: float) -> Optional[dict]:
    remaining = requested_shares
    cost = 0.0
    consumed = 0
    for price, available in asks:
        if not (math.isfinite(price) and math.isfinite(available) and 0 < price < 1 and available > 0):
            continue
        take = min(remaining, available)
        cost += take * price
        remaining -= take
        consumed += 1
        if remaining <= 1e-9:
            break
    if remaining > 1e-9 or requested_shares <= 0:
        return None
    return {
        "shares": requested_shares,
        "filled_usd": round(cost, 6),
        "vwap": round(cost / requested_shares, 6),
        "levels_consumed": consumed,
    }


async def _prepare_leg(leg: dict, shares: float) -> dict:
    slug = str(leg.get("slug") or "")
    side = leg.get("side")
    if not slug or side not in {"BUY_YES", "BUY_NO"}:
        return {"error": "invalid basket leg"}
    market = await polymarket.get_market(slug)
    if market is None:
        return {"error": f"market {slug!r} is no longer available"}
    token_id = market["yes_token_id"] if side == "BUY_YES" else market["no_token_id"]
    if not token_id:
        return {"error": f"{side.removeprefix('BUY_')} book unavailable for {slug!r}"}
    try:
        book = await polymarket.get_order_book(token_id)
    except Exception as exc:
        return {"error": f"book unavailable for {slug!r}: {exc}"}
    fill = _walk_shares(book["asks"], shares)
    if fill is None:
        return {"error": f"full basket size is no longer fillable on {slug!r}"}

    vwap = fill["vwap"]
    fee_per_share = taker_fee(market["category"], vwap)
    scanned = float(leg["price"])
    reference_mid = market["mid"] if side == "BUY_YES" else 1 - market["mid"]
    position = {
        "market_id": slug,
        "side": side,
        "entry_price": vwap,
        "size_usd": fill["filled_usd"],
        "fee_paid": round(fee_per_share * shares, 4),
        "slippage_bps": round((vwap - scanned) / scanned * 10_000, 2),
        "fair_prob_at_entry": reference_mid,
        "strategy": "arbitrage",
    }
    return {
        "error": None,
        "slug": slug,
        "side": side,
        "vwap": vwap,
        "filled_usd": fill["filled_usd"],
        "fee_per_share": fee_per_share,
        "position": position,
    }
