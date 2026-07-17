"""Daily job: settle paper positions on resolved markets and grow precedents.

For every open position whose market has resolved: set resolved_outcome,
compute PnL. Every resolved market we tracked also becomes a precedent row
(+ vector in the Pinecone `precedents` namespace) for base-rate context.

Usage:
    python -m jobs.resolve_positions [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Optional

from backend.data import pinecone_client, polymarket, supabase_client
from backend.llm import embeddings


def market_outcome(market: dict) -> Optional[str]:
    """'YES' / 'NO' when a binary market has clearly resolved, else None."""
    prices = market.get("outcome_prices") or []
    if market.get("active") or len(prices) < 2:
        return None
    if prices[0] >= 0.99:
        return "YES"
    if prices[0] <= 0.01:
        return "NO"
    return None


def position_pnl(position: dict, outcome: str) -> float:
    """PnL of a settled position. entry_price is the traded token's price."""
    entry = float(position["entry_price"])
    size_usd = float(position["size_usd"])
    fee = float(position.get("fee_paid") or 0)
    shares = size_usd / entry if entry > 0 else 0.0
    won = (position["side"] == "BUY_YES") == (outcome == "YES")
    payout = shares if won else 0.0
    return round(payout - size_usd - fee, 4)


async def settle_positions(dry_run: bool) -> int:
    settled = 0
    for position in supabase_client.get_open_positions():
        market = await polymarket.get_market(str(position["market_id"]))
        if market is None:
            continue
        outcome = market_outcome(market)
        if outcome is None:
            continue
        pnl = position_pnl(position, outcome)
        print(f"  position {position['id']}: {position['side']} -> {outcome}, pnl {pnl:+.2f}")
        if not dry_run:
            supabase_client.resolve_position(str(position["id"]), outcome, pnl)
        settled += 1
    return settled


async def harvest_precedents(dry_run: bool) -> int:
    """Move tracked markets that have since resolved into precedents."""
    precedents = []
    resolved_ids = []
    for row in supabase_client.get_cached_markets(active_only=True):
        market = await polymarket.get_market(str(row["id"]))
        if market is None:
            continue
        outcome = market_outcome(market)
        if outcome is None:
            continue
        resolved_ids.append(row["id"])
        precedents.append(
            {
                "market_id": row["id"],
                "question": row["question"],
                "category": row.get("category") or "other",
                "resolution_text": row.get("resolution_text"),
                "outcome": outcome,
                "final_mid_7d_before": None,
                "resolved_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    print(f"  {len(precedents)} tracked markets have resolved")
    if dry_run or not precedents:
        return len(precedents)

    supabase_client.upsert_precedents(precedents)
    supabase_client.mark_markets_inactive(resolved_ids)
    if not (pinecone_client.is_configured() and embeddings.is_configured()):
        print("  (Pinecone/embeddings not configured — precedent rows saved, vectors skipped)")
        return len(precedents)
    vectors = embeddings.embed([p["question"] for p in precedents])
    items = [
        {
            "id": p["market_id"],
            "values": v,
            "metadata": {
                "question": p["question"][:200],
                "category": p["category"],
                "outcome": p["outcome"],
            },
        }
        for p, v in zip(precedents, vectors)
    ]
    pinecone_client.upsert_vectors("precedents", items)
    return len(precedents)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    from jobs._preflight import require

    require("SUPABASE_URL", "SUPABASE_SERVICE_KEY")

    settled = asyncio.run(settle_positions(args.dry_run))
    print(f"settled {settled} positions")
    harvested = asyncio.run(harvest_precedents(args.dry_run))
    print(f"harvested {harvested} precedents")


if __name__ == "__main__":
    main()
