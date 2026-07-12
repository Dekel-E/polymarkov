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
    ctx: RunContext,
    market: MarketState,
    priced: PricingResult,
    size_usd: Optional[float] = None,
    user_id: Optional[str] = None,
    strategy: str = "manual",
) -> Optional[FillReport]:
    """Fill the suggested size against the live book. None if nothing to trade.

    `size_usd` overrides the Kelly sizing (manual trades from the GUI);
    `user_id` tags the position to a logged-in user (None = agent book);
    `strategy` attributes the trade (manual/ai_signal/arbitrage/copy).
    """
    if priced.verdict == "PASS":
        return None
    if size_usd is None:
        if priced.suggested_size_pct_bankroll <= 0:
            return None
        size_usd = round(config.PAPER_BANKROLL_USD * priced.suggested_size_pct_bankroll / 100, 2)
    if size_usd <= 0:
        return None
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
        "user_id": user_id,
        "strategy": strategy,
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


# ---------------------------------------------------------------------------
# Manual close (GUI "direct the agent" control)
# ---------------------------------------------------------------------------


def close_permission(owner: Optional[str], user_id: Optional[str], allow_agent: bool) -> Optional[str]:
    """Ownership rule for closing a position (pure). None = allowed.

    Agent-book positions (owner is None) are managed exclusively by the
    agent's own jobs (risk manager, thesis exits) — never from the GUI.
    User positions can only be closed by their owner.
    """
    if owner is None:
        return None if allow_agent else (
            "the agent's book is managed by its own risk rules — only your own positions can be closed"
        )
    if owner != user_id:
        return "this position belongs to another user"
    return None


def exit_pnl(position: dict, exit_price: float, exit_fee: float) -> float:
    """Realized PnL of closing a position at `exit_price` (the traded token)."""
    entry = float(position["entry_price"])
    size_usd = float(position["size_usd"])
    shares = size_usd / entry if entry > 0 else 0.0
    proceeds = shares * exit_price
    return round(proceeds - size_usd - float(position.get("fee_paid") or 0) - exit_fee, 4)


async def close_position(
    position_id: str, user_id: Optional[str] = None, allow_agent: bool = False
) -> dict:
    """Close an open paper position at the current book. Returns a report dict
    with an `error` key on failure (never raises for expected cases).
    `allow_agent=True` is for the agent's own jobs only — never the API."""
    rows = (
        supabase_client.get_client()
        .table("positions")
        .select("*")
        .eq("id", position_id)
        .limit(1)
        .execute()
        .data
        if supabase_client.is_configured()
        else []
    )
    if not rows:
        return {"error": "position not found"}
    position = rows[0]
    if position.get("status") != "open":
        return {"error": "position is already resolved"}
    denied = close_permission(position.get("user_id"), user_id, allow_agent)
    if denied:
        return {"error": denied}

    market = await polymarket.get_market_state(str(position["market_id"]))
    if market is None:
        return {"error": "market no longer resolvable"}

    if position["side"] == "BUY_YES":
        exit_price = market.best_bid  # sell YES into the bid
    else:
        exit_price = (1 - market.best_ask) if market.best_ask is not None else None
    if not exit_price or exit_price <= 0:
        return {"error": "no live quote to close against"}

    shares = float(position["size_usd"]) / float(position["entry_price"])
    exit_fee = round(pricing_mod.taker_fee(market.category, exit_price) * shares, 4)
    pnl = exit_pnl(position, exit_price, exit_fee)

    supabase_client.resolve_position(position_id, "CLOSED", pnl)

    return {
        "error": None,
        "position_id": position_id,
        "exit_price": exit_price,
        "exit_fee": exit_fee,
        "pnl": pnl,
    }
