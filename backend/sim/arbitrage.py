"""Arbitrage detection over Polymarket books (pure math, no LLM).

Spread arb: best YES ask + best NO ask below $1 by more than fees. Dutch book:
best YES asks across all outcomes of a negRisk event sum below $1. Paper-only,
so no latency race against real HFT bots.
"""

from __future__ import annotations

import asyncio
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


async def execute_legs(opportunity: dict) -> list[dict]:
    """Paper-fill every leg, reporting each so an unfilled leg stays visible."""
    from backend.agent.types import PricingResult
    from backend.llm.client import RunContext
    from backend.sim import paper_broker

    reports = []
    for leg in opportunity["legs"]:
        market = await polymarket.get_market_state(leg["slug"])
        if market is None:
            reports.append({"slug": leg["slug"], "filled": False, "error": "market gone"})
            continue
        priced = PricingResult(
            prior=market.mid, fair=market.mid, fair_adj=market.mid,
            gross_edge_pts=0.0, half_spread=(market.spread or 0) / 2, taker_fee=0.0,
            net_edge_pts=0.0, verdict=leg["side"], suggested_size_pct_bankroll=0.0,
            resolution_risk="low",
        )
        fill = await paper_broker.execute_paper_trade(
            RunContext(), market, priced, size_usd=leg["size_usd"], strategy="arbitrage",
        )
        reports.append(
            {"slug": leg["slug"], "side": leg["side"], "filled": fill is not None,
             **({"vwap": fill.vwap, "size_usd": fill.size_usd, "position_id": fill.position_id} if fill else {})}
        )
    return reports
