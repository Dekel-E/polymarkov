"""Copy trading — mirror new positions of followed Smart Money wallets.

For every wallet anyone follows: fetch its current on-chain positions, and
paper-buy the same side of any position we haven't mirrored yet (fixed
small size, capped per run). Mirrored keys are remembered so a position is
copied at most once; exits are handled by our own risk manager, not the
whale's (independent stop-losses).

Usage:
    python -m jobs.copy_trade [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend import config
from backend.agent.types import PricingResult
from backend.data import polymarket, smart_money, supabase_client
from backend.llm.client import RunContext
from backend.sim import paper_broker
from backend.sim.risk import strategies_allowed


def proportional_size(position_usd: float, whale_total_usd: float, bankroll: float) -> float:
    """Mirror the whale's CONVICTION, not their dollars (pure): the position's
    share of their book, applied to our bankroll, clamped to sane bounds."""
    if whale_total_usd <= 0:
        return config.COPY_MIN_USD
    fraction = position_usd / whale_total_usd
    return round(max(config.COPY_MIN_USD, min(config.COPY_MAX_USD, fraction * bankroll)), 2)


def wallet_gate(positions: list[dict]) -> bool:
    """Only mirror wallets whose current book is in profit (pure). A whale
    bleeding across their open positions is not a signal worth copying."""
    if not positions:
        return False
    return sum(p.get("pnl") or 0 for p in positions) >= 0


async def mirror_position(wallet: str, pos: dict, size_usd: float) -> bool:
    market = await polymarket.get_market_state(pos["slug"])
    if market is None:
        return False
    side = "BUY_YES" if pos["outcome"].lower() == "yes" else "BUY_NO"
    priced = PricingResult(
        prior=market.mid, fair=market.mid, fair_adj=market.mid,
        gross_edge_pts=0.0, half_spread=(market.spread or 0) / 2, taker_fee=0.0,
        net_edge_pts=0.0, verdict=side, suggested_size_pct_bankroll=0.0,
        resolution_risk="medium",
    )
    fill = await paper_broker.execute_paper_trade(
        RunContext(), market, priced,
        size_usd=size_usd, strategy="copy",
    )
    supabase_client.record_mirrored(
        wallet, pos["slug"], pos["outcome"], fill.position_id if fill else None
    )
    return fill is not None


async def main_async(dry_run: bool) -> None:
    if not dry_run:
        from jobs._preflight import require

        require("SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    strategies, allowed = strategies_allowed()
    if not strategies.get("copy_trading"):
        print("copy_trading is disabled in agent settings — skipping")
        return
    if not allowed:
        print("circuit breaker active — skipping")
        return

    wallets = supabase_client.distinct_followed_wallets()
    print(f"followed wallets: {len(wallets)}")
    copied = 0
    for wallet in wallets:
        if copied >= config.COPY_TRADES_PER_JOB:
            break
        positions = await smart_money.fetch_wallet_positions(wallet, limit=10)
        if not wallet_gate(positions):
            print(f"  {wallet[:10]}… gated: current book not in profit — not mirroring")
            continue
        whale_total = sum(p["size_usd"] for p in positions)
        for pos in positions:
            if copied >= config.COPY_TRADES_PER_JOB:
                break
            if not pos["slug"] or pos["size_usd"] < 100:
                continue  # ignore dust — only mirror meaningful convictions
            if supabase_client.already_mirrored(wallet, pos["slug"], pos["outcome"]):
                continue
            size = proportional_size(pos["size_usd"], whale_total, supabase_client.current_bankroll())
            print(
                f"  new: {wallet[:8]}… {pos['outcome']} on {pos['slug'][:50]} "
                f"(their ${pos['size_usd']:,.0f} = {pos['size_usd'] / whale_total:.0%} of book -> our ${size})"
            )
            if dry_run:
                copied += 1
                continue
            ok = await mirror_position(wallet, pos, size)
            print(f"    mirrored ${size} paper: {'filled' if ok else 'NO FILL'}")
            copied += 1
    print(f"done — {copied} position(s) {'found' if dry_run else 'mirrored'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
