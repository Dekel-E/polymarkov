"""RedditIndexer — scrape Reddit for posts about tracked markets and index
them for the AI: rows into Supabase `social_posts` (tagged with market
slugs), vectors into the Pinecone `social` namespace. SocialScanner and
MarketChat then read this warm cache alongside their live scrapes, so the
council sees chatter even when a live scrape runs thin or gets rate-limited.

Tracked = top trending markets + every market the desk holds or watches.
Works keyless (public Reddit JSON search); REDDIT_CLIENT_ID/SECRET switch
it to OAuth for higher limits.

Usage:
    python -m jobs.index_social [--markets 15] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend.data import pinecone_client, polymarket, social, supabase_client
from backend.llm import embeddings
from jobs.index_news import market_news_query

REDDIT_DELAY_S = 1.5  # keyless endpoint rate-limits fast — be polite
POSTS_PER_MARKET = 15


async def tracked_markets(n_trending: int) -> list[dict]:
    """Trending + held + watched, deduped by slug (held/watched fetched
    explicitly so a position never falls off the radar)."""
    markets = list(await polymarket.get_trending_markets(n_trending))
    have = {m["slug"] for m in markets}
    held = {p["market_id"] for p in supabase_client.get_open_positions()}
    watched = set(supabase_client.distinct_watched_market_ids())
    for slug in sorted((held | watched) - have)[:15]:
        try:
            m = await polymarket.get_market(slug)
        except Exception:
            continue
        if m and m.get("active"):
            markets.append(m)
    return markets


async def collect_posts(markets: list[dict]) -> list[dict]:
    """Search Reddit per market; dedup by url, merging entity tags."""
    posts: dict[str, dict] = {}
    for market in markets:
        query = market_news_query(market)
        if not query:
            continue
        for p in await social.fetch_reddit_posts(query, limit=POSTS_PER_MARKET):
            if not p.get("url"):
                continue
            existing = posts.get(p["url"])
            entities = (existing.get("entities", []) if existing else []) + [market["slug"]]
            posts[p["url"]] = {**p, "entities": sorted(set(entities))}
        await asyncio.sleep(REDDIT_DELAY_S)
    return list(posts.values())


def embed_pending_posts() -> int:
    """Embed indexed posts not yet in Pinecone `social`, then mark them."""
    if not (pinecone_client.is_configured() and embeddings.is_configured()):
        return 0
    pending = supabase_client.get_unembedded_social_posts()
    if not pending:
        return 0
    vectors = embeddings.embed([p["text"][:400] for p in pending])
    items = [
        {
            "id": str(p["id"]),
            "values": v,
            "metadata": {
                "url": p["url"],
                "text": (p["text"] or "")[:300],
                "source": p.get("source") or "reddit",
                "subreddit": p.get("subreddit") or "",
                "date": p.get("posted_at") or "",
            },
        }
        for p, v in zip(pending, vectors)
    ]
    written = pinecone_client.upsert_vectors("social", items)
    supabase_client.mark_social_posts_embedded([str(p["id"]) for p in pending])
    return written


async def main_async(n_markets: int, dry_run: bool) -> None:
    markets = await tracked_markets(n_markets)
    print(f"tracking {len(markets)} markets")
    posts = await collect_posts(markets)
    print(f"collected {len(posts)} unique Reddit posts")

    if dry_run:
        for p in posts[:5]:
            print(f"  r/{p.get('subreddit', ''):20} {p['text'][:60]}")
        print("dry run — nothing written")
        return

    rows = await asyncio.to_thread(supabase_client.upsert_social_posts, posts)
    print(f"supabase: upserted {rows} social_posts rows")
    vectors = await asyncio.to_thread(embed_pending_posts)
    print(f"pinecone: embedded {vectors} new posts into 'social'")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markets", type=int, default=15, help="how many top markets to track")
    parser.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    args = parser.parse_args()

    if not args.dry_run:
        from jobs._preflight import require

        require("SUPABASE_URL", "SUPABASE_SERVICE_KEY")

    asyncio.run(main_async(args.markets, args.dry_run))


if __name__ == "__main__":
    main()
