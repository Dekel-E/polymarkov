"""Market-making cycle (hourly, no LLM): settle last hour's quotes against
what actually traded, then re-quote the most liquid eligible markets.

Usage:
    python -m jobs.market_maker [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone

from backend import config
from backend.data import polymarket, supabase_client
from backend.sim import market_maker as mm
from backend.sim.risk import strategies_allowed


async def settle_pending(dry_run: bool) -> None:
    if not supabase_client.is_configured():
        return
    pending = (
        supabase_client.get_client()
        .table("mm_quotes")
        .select("*")
        .eq("status", "pending")
        .execute()
        .data
        or []
    )
    if not pending:
        print("no pending quotes to settle")
        return
    open_positions = supabase_client.get_open_positions()

    for quote in pending:
        try:
            history = await polymarket.get_price_history(
                quote["yes_token_id"], interval="1d", fidelity=10
            )
        except Exception:
            history = []
        placed_ts = datetime.fromisoformat(quote["placed_at"].replace("Z", "+00:00")).timestamp()
        prices_after = [p for ts, p in history if ts >= placed_ts]
        fills = mm.quote_fills(float(quote["bid"]), float(quote["ask"]), prices_after)
        print(f"  {quote['market_id'][:45]} bid {quote['bid']} / ask {quote['ask']} -> fills: {fills or 'none'}")
        if dry_run:
            continue

        for side in fills:
            if side == "bid":
                mm.open_mm_position(quote["market_id"], "BUY_YES", float(quote["bid"]), quote["category"])
                print(f"    filled bid: long ${config.MM_QUOTE_SIZE_USD} @ {quote['bid']}")
            else:
                _, oldest_long = mm.mm_inventory(open_positions, quote["market_id"])
                if oldest_long is not None:
                    pnl = mm.close_mm_long(oldest_long, float(quote["ask"]), quote["category"])
                    open_positions = [p for p in open_positions if p["id"] != oldest_long["id"]]
                    print(f"    filled ask: spread captured, pnl {pnl:+.2f}")
                else:
                    mm.open_mm_position(
                        quote["market_id"], "BUY_NO", round(1 - float(quote["ask"]), 3), quote["category"]
                    )
                    print(f"    filled ask with no inventory: short via BUY_NO @ {1 - float(quote['ask']):.3f}")

        mid_at_placement = float(quote.get("mid_at_placement") or (float(quote["bid"]) + float(quote["ask"])) / 2)
        supabase_client.get_client().table("mm_quotes").update(
            {
                "status": "settled",
                "fills": "+".join(fills) if fills else "none",
                "settled_at": mm._now(),
                "reward_score": mm.reward_score(
                    mid_at_placement, float(quote["bid"]), float(quote["ask"]), float(quote["size_usd"])
                ),
            }
        ).eq("id", quote["id"]).execute()


async def place_quotes(dry_run: bool) -> None:
    strategies, allowed = strategies_allowed()
    if not strategies.get("market_making"):
        print("market_making is disabled in agent settings — not quoting")
        return
    if not allowed:
        print("circuit breaker active — not quoting")
        return

    now = datetime.now(timezone.utc)
    open_positions = supabase_client.get_open_positions()
    markets = await polymarket.get_trending_markets(60)
    placed = 0
    for m in markets:
        if placed >= config.MM_MARKETS:
            break
        hours_to_end = None
        if m.get("end_date"):
            try:
                end = datetime.fromisoformat(m["end_date"].replace("Z", "+00:00"))
                hours_to_end = (end - now).total_seconds() / 3600
            except ValueError:
                pass
        if not mm.eligible_to_quote(m, hours_to_end):
            continue
        inventory, _ = mm.mm_inventory(open_positions, m["slug"])
        if inventory >= config.MM_MAX_INVENTORY_USD:
            print(f"  {m['slug'][:45]}: inventory cap reached — not quoting")
            continue
        quote = mm.make_quote(m["mid"], inventory)
        if quote is None:
            continue
        bid, ask = quote
        print(f"  quoting {m['slug'][:45]}: {bid} / {ask} (mid {m['mid']:.3f}, inv ${inventory:.0f})")
        if not dry_run and supabase_client.is_configured():
            supabase_client.get_client().table("mm_quotes").insert(
                {
                    "market_id": m["slug"],
                    "yes_token_id": m["yes_token_id"],
                    "category": m["category"],
                    "bid": bid,
                    "ask": ask,
                    "size_usd": config.MM_QUOTE_SIZE_USD,
                    "mid_at_placement": m["mid"],
                }
            ).execute()
        placed += 1
    if placed == 0:
        print("no eligible markets to quote")


async def cycle(dry_run: bool = False) -> None:
    """One settle-then-requote pass — also called by the live watcher when
    the mid drifts away from resting quotes."""
    print("settling…")
    await settle_pending(dry_run)
    print("quoting…")
    await place_quotes(dry_run)


async def main_async(dry_run: bool) -> None:
    if not dry_run:
        from jobs._preflight import require

        require("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    await cycle(dry_run)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
