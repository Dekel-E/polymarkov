"""One-time backfill of resolved binary markets into precedents (Supabase +
Pinecone). Pages Gamma's closed markets, keeps unambiguous YES/NO outcomes.

Usage:
    python -m scripts.seed_precedents [--count 250] [--skip-history] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.data import pinecone_client, polymarket, supabase_client
from backend.llm import embeddings

PAGE_SIZE = 100
MAX_PAGES = 30
HISTORY_DELAY_S = 0.3


def resolved_outcome(market: dict) -> Optional[str]:
    prices = market.get("outcome_prices") or []
    outcomes = [str(o).lower() for o in market.get("outcomes") or []]
    if outcomes[:2] != ["yes", "no"] or len(prices) < 2:
        return None
    if prices[0] >= 0.99:
        return "YES"
    if prices[0] <= 0.01:
        return "NO"
    return None


async def mid_7d_before_end(market: dict) -> Optional[float]:
    """Price ~7 days before the market's end date, from CLOB history."""
    end_date = market.get("end_date")
    if not end_date or not market.get("yes_token_id"):
        return None
    try:
        target = datetime.fromisoformat(end_date.replace("Z", "+00:00")) - timedelta(days=7)
        history = await polymarket.get_price_history(
            market["yes_token_id"], interval="max", fidelity=720
        )
        if not history:
            return None
        ts, price = min(history, key=lambda pt: abs(pt[0] - target.timestamp()))
        # only accept a point within ~2 days of the target
        if abs(ts - target.timestamp()) > 2 * 86400:
            return None
        return price
    except Exception:
        return None


async def collect(count: int, with_history: bool) -> list[dict]:
    precedents: list[dict] = []
    seen: set[str] = set()
    for page in range(MAX_PAGES):
        markets = await polymarket.list_markets(
            limit=PAGE_SIZE, offset=page * PAGE_SIZE, closed=True, order="volumeNum"
        )
        if not markets:
            break
        for m in markets:
            if len(precedents) >= count:
                return precedents
            outcome = resolved_outcome(m)
            if outcome is None or not m["id"] or m["id"] in seen:
                continue
            seen.add(m["id"])
            final_mid: Optional[float] = None
            if with_history:
                final_mid = await mid_7d_before_end(m)
                await asyncio.sleep(HISTORY_DELAY_S)
            precedents.append(
                {
                    "market_id": m["id"],
                    "question": m["question"],
                    "category": m["category"] or "other",
                    "resolution_text": (m["description"] or "")[:2000],
                    "outcome": outcome,
                    "final_mid_7d_before": final_mid,
                    "resolved_at": m["end_date"],
                }
            )
        print(f"page {page + 1}: {len(precedents)}/{count} precedents so far")
    return precedents


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=250)
    parser.add_argument(
        "--skip-history", action="store_true", help="skip CLOB final_mid_7d_before lookups (faster)"
    )
    parser.add_argument("--dry-run", action="store_true", help="collect and report, write nothing")
    args = parser.parse_args()

    precedents = asyncio.run(collect(args.count, with_history=not args.skip_history))
    yes = sum(1 for p in precedents if p["outcome"] == "YES")
    print(f"collected {len(precedents)} resolved markets ({yes} YES / {len(precedents) - yes} NO)")

    if args.dry_run:
        for p in precedents[:5]:
            print(f"  {p['outcome']:3} {p['question'][:70]}")
        print("dry run — nothing written")
        return

    rows = supabase_client.upsert_precedents(precedents)
    print(f"supabase: upserted {rows} precedent rows")
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
    written = pinecone_client.upsert_vectors("precedents", items)
    print(f"pinecone: upserted {written} vectors into 'precedents'")


if __name__ == "__main__":
    main()
