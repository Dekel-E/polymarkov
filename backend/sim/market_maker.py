"""Paper market making: quote both sides, capture the spread, manage inventory.

Fill simulation is honest and conservative: a resting limit order counts as
filled only if the market actually TRADED THROUGH its price after placement
(from CLOB price history). Fills map onto the existing position model:
- bid filled  -> BUY_YES opened at our bid (strategy 'market_making')
- ask filled  -> close our open MM long at the ask (spread captured), or
                 open BUY_NO at (1 - ask) when we have no inventory
Inventory risk is the binding constraint: hard per-market cap, quote skew
against inventory, and no quoting near resolution (binary total-loss zone).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend import config
from backend.agent.pricing import taker_fee
from backend.data import supabase_client


def eligible_to_quote(market: dict, hours_to_end: Optional[float]) -> bool:
    """Which markets are safe to make (pure)."""
    if not market.get("yes_token_id"):
        return False
    if not (config.MM_MIN_MID <= market["mid"] <= config.MM_MAX_MID):
        return False
    if hours_to_end is not None and hours_to_end < config.MM_MIN_HOURS_TO_RESOLUTION:
        return False
    return True


def make_quote(mid: float, inventory_usd: float) -> Optional[tuple[float, float]]:
    """(bid, ask) around mid, skewed against inventory (pure).

    Long inventory shifts both quotes DOWN: our ask gets easier to hit (we
    unload) and our bid harder (we stop accumulating). At the cap we stop
    bidding entirely by returning a bid of 0 handled by the caller.
    """
    frac = max(-1.0, min(1.0, inventory_usd / config.MM_MAX_INVENTORY_USD))
    skew = frac * config.MM_INVENTORY_SKEW
    bid = round(mid - config.MM_HALF_SPREAD - skew, 3)
    ask = round(mid + config.MM_HALF_SPREAD - skew, 3)
    if bid <= 0.01 or ask >= 0.99 or bid >= ask:
        return None
    return bid, ask


def quote_fills(bid: float, ask: float, prices_after: list[float]) -> list[str]:
    """Which sides the market traded through (pure). Conservative: touching
    the price counts; no partial fills."""
    fills = []
    if prices_after and min(prices_after) <= bid:
        fills.append("bid")
    if prices_after and max(prices_after) >= ask:
        fills.append("ask")
    return fills


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def open_mm_position(market_id: str, side: str, price: float, category: str) -> Optional[str]:
    shares = config.MM_QUOTE_SIZE_USD / price
    fee = round(taker_fee(category, price) * shares * 0.5, 4)  # maker-ish: half taker fee
    return supabase_client.insert_position(
        {
            "market_id": market_id,
            "side": side,
            "entry_price": price,
            "size_usd": config.MM_QUOTE_SIZE_USD,
            "fee_paid": fee,
            "slippage_bps": 0,
            "fair_prob_at_entry": None,
            "user_id": None,
            "strategy": "market_making",
        }
    )


def close_mm_long(position: dict, exit_price: float, category: str) -> float:
    """Sell an MM long at our ask: realize the captured spread."""
    entry = float(position["entry_price"])
    shares = float(position["size_usd"]) / entry
    exit_fee = round(taker_fee(category, exit_price) * shares * 0.5, 4)
    pnl = round(shares * exit_price - float(position["size_usd"]) - float(position.get("fee_paid") or 0) - exit_fee, 4)
    supabase_client.resolve_position(str(position["id"]), "MM_EXIT", pnl)
    return pnl


def mm_inventory(open_positions: list[dict], market_id: str) -> tuple[float, Optional[dict]]:
    """(net long inventory USD, oldest open MM long) for one market."""
    longs = [
        p
        for p in open_positions
        if p["market_id"] == market_id
        and p.get("strategy") == "market_making"
        and p["side"] == "BUY_YES"
    ]
    total = sum(float(p["size_usd"]) for p in longs)
    oldest = min(longs, key=lambda p: p["opened_at"]) if longs else None
    return total, oldest
