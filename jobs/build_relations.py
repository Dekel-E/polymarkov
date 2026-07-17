"""Maintain the correlation graph: pair similar markets, classify logical
relations (implies / excludes / none) with one LLM call, store confident ones.

Usage:
    python -m jobs.build_relations [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend.data import polymarket, supabase_client
from backend.llm import client as llm_client
from backend.llm import embeddings
from backend.sim import correlation


async def main_async(dry_run: bool) -> None:
    if not llm_client.is_configured() or not embeddings.is_configured():
        print("LLM/embeddings not configured — aborting")
        return

    markets = [
        m for m in await polymarket.get_trending_markets(150) if m["yes_token_id"] and m["no_token_id"]
    ]
    vectors = await asyncio.to_thread(embeddings.embed, [m["question"] for m in markets])
    pairs = correlation.candidate_pairs(markets, vectors)
    print(f"{len(markets)} markets -> {len(pairs)} candidate pairs")
    if not pairs:
        return
    if dry_run:
        for a, b in pairs[:10]:
            print(f"  {a['question'][:50]}  <->  {b['question'][:50]}")
        print("dry run — no LLM call")
        return

    ctx = llm_client.RunContext()
    raw = await ctx.call_llm(
        "RelationMapper",
        correlation.RELATION_SYSTEM_PROMPT,
        correlation.build_classification_prompt(pairs),
    )
    rows = correlation.normalize_classification(pairs, raw)
    print(f"classified: {len(rows)} confident relation(s)")
    for row in rows:
        print(f"  {row['relation']}: {row['a_question'][:45]} -> {row['b_question'][:45]}")
        if supabase_client.is_configured():
            try:
                supabase_client.get_client().table("market_relations").upsert(
                    row, on_conflict="relation,a_slug,b_slug"
                ).execute()
            except Exception as exc:
                print(f"    store failed: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
