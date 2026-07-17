"""Index GDELT news for high-volume markets into Supabase + Pinecone.

Usage:
    python -m jobs.index_news [--markets 20] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import re

from backend.data import news, pinecone_client, polymarket, supabase_client
from backend.llm import embeddings

GDELT_DELAY_S = 2.0  # GDELT 429s fast


def market_news_query(market: dict) -> str:
    """Turn a market into a GDELT-friendly phrase query."""
    text = market.get("event_title") or market.get("question") or ""
    text = re.sub(r"[?\"']", "", text).strip()
    words = text.split()
    return " ".join(words[:6])  # short phrases match more articles


async def collect_articles(markets: list[dict]) -> list[dict]:
    articles: dict[str, dict] = {}  # url -> article (dedup)
    for market in markets:
        query = market_news_query(market)
        if not query:
            continue
        for a in await news.gdelt_articles(query, max_records=15):
            existing = articles.get(a["url"])
            entities = (existing.get("entities", []) if existing else []) + [market["slug"]]
            articles[a["url"]] = {**a, "entities": sorted(set(entities))}
        await asyncio.sleep(GDELT_DELAY_S)
    return list(articles.values())


def embed_pending_articles() -> int:
    """Embed any Supabase articles not yet in Pinecone, then mark them."""
    pending = supabase_client.get_unembedded_articles()
    if not pending:
        return 0
    vectors = embeddings.embed([f"{a['title']} ({a['domain']})" for a in pending])
    items = [
        {
            "id": str(a["id"]),
            "values": v,
            "metadata": {
                "url": a["url"],
                "title": (a["title"] or "")[:200],
                "domain": a["domain"] or "",
                "date": a["published_at"] or "",
            },
        }
        for a, v in zip(pending, vectors)
    ]
    written = pinecone_client.upsert_vectors("news", items)
    supabase_client.mark_articles_embedded([str(a["id"]) for a in pending])
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", type=int, default=20, help="how many top markets to track")
    parser.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = parser.parse_args()

    if not args.dry_run:
        from jobs._preflight import require

        require(
            "LLMOD_API_KEY", "LLMOD_BASE_URL",
            "SUPABASE_URL", "SUPABASE_SERVICE_KEY", "PINECONE_API_KEY",
        )

    markets = asyncio.run(polymarket.get_trending_markets(args.markets))
    print(f"tracking {len(markets)} markets")
    articles = asyncio.run(collect_articles(markets))
    print(f"collected {len(articles)} unique articles from GDELT")

    if args.dry_run:
        for a in articles[:5]:
            print(f"  {a['domain']:24} {a['title'][:60]}")
        print("dry run — nothing written")
        return

    rows = supabase_client.upsert_articles(articles)
    print(f"supabase: upserted {rows} article rows")
    vectors = embed_pending_articles()
    print(f"pinecone: embedded {vectors} new articles into 'news'")


if __name__ == "__main__":
    main()
