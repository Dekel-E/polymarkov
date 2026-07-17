"""Simulate a taker fill on the live book.

Walks real CLOB levels to fill the sized order, computes VWAP, slippage vs mid,
and the category fee, then records the position. BUY_NO is synthesized from the
YES bid side (buying NO at 1 - bid equals selling YES at the bid).
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
    strategy: str = "manual",
) -> Optional[FillReport]:
    """Fill the suggested size against the live book. None if nothing to trade.

    size_usd overrides the Kelly sizing; strategy attributes the trade.
    """
    if priced.verdict == "PASS":
        return None
    settings = await asyncio.to_thread(supabase_client.get_agent_settings)
    if size_usd is None:
        if priced.suggested_size_pct_bankroll <= 0:
            return None
        try:
            bankroll = float(settings["funds"]["bankroll_usd"])
        except (KeyError, TypeError, ValueError):
            bankroll = float(config.PAPER_BANKROLL_USD)
        size_usd = round(bankroll * priced.suggested_size_pct_bankroll / 100, 2)
    # The "max position $" rule caps autonomous directional fills. Manual
    # trades keep the user's size; arbitrage legs are sized as a hedged set and
    # have their own ARB_MAX_SIZE_USD cap.
    if strategy not in ("manual", "arbitrage"):
        try:
            size_usd = min(size_usd, float(settings["risk"]["max_position_usd"]))
        except (KeyError, TypeError, ValueError):
            pass
    if size_usd <= 0:
        return None
    book = await polymarket.get_order_book(market.yes_token_id)

    if priced.verdict == "BUY_YES":
        levels = book["asks"]  # best-first ascending
        ref_mid = market.mid
    else:  # BUY_NO: YES bids -> NO asks
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
        "strategy": strategy,
    }
    position_id = await asyncio.to_thread(supabase_client.insert_position, position)
    if position_id is None:  # Supabase unconfigured: still report the simulated fill
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


def split_position(position: dict, fraction: float) -> tuple[dict, dict]:
    """Split a position for a partial close.

    Returns (closed_part, remaining_updates): size and entry fee divide
    proportionally; entry price and side are unchanged."""
    fraction = max(0.01, min(1.0, fraction))
    size = float(position["size_usd"])
    fee = float(position.get("fee_paid") or 0)
    closed = {
        **{k: position[k] for k in ("market_id", "side", "entry_price") if k in position},
        "size_usd": round(size * fraction, 2),
        "fee_paid": round(fee * fraction, 4),
    }
    remaining = {
        "size_usd": round(size * (1 - fraction), 2),
        "fee_paid": round(fee * (1 - fraction), 4),
    }
    return closed, remaining


def exit_pnl(position: dict, exit_price: float, exit_fee: float) -> float:
    """Realized PnL of closing a position at `exit_price` (the traded token)."""
    entry = float(position["entry_price"])
    size_usd = float(position["size_usd"])
    shares = size_usd / entry if entry > 0 else 0.0
    proceeds = shares * exit_price
    return round(proceeds - size_usd - float(position.get("fee_paid") or 0) - exit_fee, 4)


async def close_position(position_id: str, fraction: float = 1.0) -> dict:
    """Close all or `fraction` of an open position at the current book.
    Returns a report dict with an `error` key set on failure."""
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

    market = await polymarket.get_market_state(str(position["market_id"]))
    if market is None:
        return {"error": "market no longer resolvable"}

    if position["side"] == "BUY_YES":
        exit_price = market.best_bid  # sell YES into the bid
    else:
        exit_price = (1 - market.best_ask) if market.best_ask is not None else None
    if not exit_price or exit_price <= 0:
        return {"error": "no live quote to close against"}

    fraction = max(0.01, min(1.0, fraction))
    if fraction >= 0.999:  # full close
        shares = float(position["size_usd"]) / float(position["entry_price"])
        exit_fee = round(pricing_mod.taker_fee(market.category, exit_price) * shares, 4)
        pnl = exit_pnl(position, exit_price, exit_fee)
        supabase_client.resolve_position(position_id, "CLOSED", pnl)
        return {
            "error": None, "position_id": position_id, "closed_fraction": 1.0,
            "exit_price": exit_price, "exit_fee": exit_fee, "pnl": pnl,
        }

    # partial close: realize the closed part as its own resolved row, shrink the original
    closed_part, remaining = split_position(position, fraction)
    shares = closed_part["size_usd"] / float(position["entry_price"])
    exit_fee = round(pricing_mod.taker_fee(market.category, exit_price) * shares, 4)
    pnl = exit_pnl(closed_part, exit_price, exit_fee)

    client = supabase_client.get_client()
    client.table("positions").insert(
        {
            "market_id": position["market_id"],
            "side": position["side"],
            "entry_price": position["entry_price"],
            "size_usd": closed_part["size_usd"],
            "fee_paid": closed_part["fee_paid"],
            "slippage_bps": position.get("slippage_bps") or 0,
            "fair_prob_at_entry": position.get("fair_prob_at_entry"),
            "strategy": position.get("strategy") or "manual",
            "opened_at": position.get("opened_at"),
            "status": "resolved",
            "resolved_outcome": "CLOSED_PARTIAL",
            "resolved_at": supabase_client._now(),
            "pnl": pnl,
        }
    ).execute()
    client.table("positions").update(remaining).eq("id", position_id).execute()
    return {
        "error": None, "position_id": position_id, "closed_fraction": fraction,
        "exit_price": exit_price, "exit_fee": exit_fee, "pnl": pnl,
    }
