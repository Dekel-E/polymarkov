"""MarketIndexer — index top active markets into Supabase + Pinecone.

Runs every 2h via GitHub Actions (never inside Vercel functions).

Usage:
    python -m jobs.index_markets [--top 300] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend.data import pinecone_client, polymarket, supabase_client
from backend.llm import embeddings

PAGE_SIZE = 100


async def fetch_top_markets(top: int) -> list[dict]:
    markets: list[dict] = []
    seen: set[str] = set()
    for offset in range(0, top, PAGE_SIZE):
        page = await polymarket.list_markets(limit=min(PAGE_SIZE, top - offset), offset=offset)
        if not page:
            break
        for m in page:
            if m["id"] and m["id"] not in seen:
                seen.add(m["id"])
                markets.append(m)
    return markets


def embed_markets(markets: list[dict]) -> int:
    texts = [f"{m['question']}\n{(m['description'] or '')[:500]}" for m in markets]
    vectors = embeddings.embed(texts)
    items = [
        {
            "id": m["id"],
            "values": v,
            "metadata": {
                "slug": m["slug"] or "",
                "question": m["question"][:200],
                "category": m["category"] or "other",
                "end_date": m["end_date"] or "",
            },
        }
        for m, v in zip(markets, vectors)
    ]
    return pinecone_client.upsert_vectors("markets", items)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = parser.parse_args()

    markets = asyncio.run(fetch_top_markets(args.top))
    print(f"fetched {len(markets)} active markets from Gamma")
    if not markets:
        return

    if args.dry_run:
        for m in markets[:5]:
            print(f"  {m['id']}  {m['mid']:.3f}  {m['question'][:70]}")
        print("dry run — nothing written")
        return

    rows = supabase_client.upsert_markets(markets)
    print(f"supabase: upserted {rows} market rows")
    vectors = embed_markets(markets)
    print(f"pinecone: upserted {vectors} vectors into 'markets'")


if __name__ == "__main__":
    main()
