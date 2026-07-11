"""PaperBroker — deterministic tool: simulate a taker fill on the LIVE book.

Walks real CLOB levels to fill the Kelly-suggested size, computes VWAP,
slippage vs mid, and the category fee, then records the position in
Supabase. BUY_NO is synthesized from the YES bid side (buying NO at price
1 - bid is economically identical to selling YES at the bid).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

from backend import config
from backend.agent import pricing as pricing_mod
from backend.agent.types import FillReport, MarketState, PricingResult
from backend.data import polymarket, supabase_client
from backend.llm.client import RunContext

MODULE = "PaperBroker"


async def execute_paper_trade(
    ctx: RunContext, market: MarketState, priced: PricingResult
) -> Optional[FillReport]:
    """Fill the suggested size against the live book. None if nothing to trade."""
    if priced.verdict == "PASS" or priced.suggested_size_pct_bankroll <= 0:
        return None

    size_usd = round(config.PAPER_BANKROLL_USD * priced.suggested_size_pct_bankroll / 100, 2)
    book = await polymarket.get_order_book(market.yes_token_id)

    if priced.verdict == "BUY_YES":
        levels = book["asks"]  # best-first ascending
        ref_mid = market.mid
    else:  # BUY_NO: YES bids (best-first descending) -> NO asks (best-first ascending)
        levels = [(round(1 - price, 6), size) for price, size in book["bids"]]
        ref_mid = 1 - market.mid

    fill = polymarket.walk_book(levels, size_usd)
    if fill["vwap"] is None:
        ctx.add_tool_step(
            MODULE,
            f"{priced.verdict} ${size_usd:,.2f} on {market.slug}",
            {"filled": False, "reason": "order book empty — no fill simulated"},
        )
        return None

    vwap: float = fill["vwap"]
    fee_paid = round(pricing_mod.taker_fee(market.category, vwap) * fill["shares"], 4)
    slippage_bps = round((vwap - ref_mid) / ref_mid * 10_000, 2) if ref_mid else 0.0

    position = {
        "market_id": market.slug,
        "side": priced.verdict,
        "entry_price": vwap,
        "size_usd": fill["filled_usd"],
        "fee_paid": fee_paid,
        "slippage_bps": slippage_bps,
        "fair_prob_at_entry": priced.fair_adj,
    }
    position_id = await asyncio.to_thread(supabase_client.insert_position, position)
    if position_id is None:  # Supabase unconfigured — still report the simulated fill
        position_id = f"local-{uuid.uuid4()}"

    report = FillReport(
        position_id=str(position_id),
        market_id=market.slug,
        side=priced.verdict,  # type: ignore[arg-type]
        size_usd=fill["filled_usd"],
        vwap=vwap,
        slippage_bps=slippage_bps,
        fee_paid=fee_paid,
        levels_consumed=fill["levels_consumed"],
    )
    ctx.add_tool_step(
        MODULE,
        f"{priced.verdict} ${size_usd:,.2f} on {market.slug} "
        f"(bankroll ${config.PAPER_BANKROLL_USD:,}, size {priced.suggested_size_pct_bankroll:.2f}%)",
        {**report.model_dump(), "requested_usd": size_usd, "exhausted": fill["exhausted"]},
    )
    return report
