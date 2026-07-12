"""Sentinel — the agent's perception loop (NO LLM calls, runs every ~30 min).

Watches the world and files findings on the agenda for the worker to
investigate, highest priority first:
- big 24h price moves on liquid markets
- held positions moving against their entry (thesis check candidates)
- held/watched markets resolving within 48h
- news bursts on held/watched markets (Google News, cheap)

Usage:
    python -m jobs.sentinel [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from typing import Optional

from backend import config
from backend.data import google_news, polymarket, supabase_client


def price_move_items(markets: list[dict]) -> list[dict]:
    """Liquid markets that moved hard in 24h (pure; unit-tested)."""
    items = []
    for m in markets:
        change = m.get("one_day_change")
        if change is None or abs(change) < config.SENTINEL_MOVE_PTS:
            continue
        if not (config.AUTO_MIN_MID <= m["mid"] <= config.AUTO_MAX_MID):
            continue
        items.append(
            {
                "market_id": m["slug"],
                "reason": f"price moved {change * 100:+.0f} pts in 24h",
                "priority": round(abs(change) * 100, 2),
            }
        )
    return items


def position_risk_items(positions: list[dict], mid_by_slug: dict[str, float]) -> list[dict]:
    """Open positions whose market moved against the entry (pure)."""
    items = []
    for p in positions:
        mid = mid_by_slug.get(p["market_id"])
        if mid is None:
            continue
        entry = float(p["entry_price"])
        current = mid if p["side"] == "BUY_YES" else 1 - mid
        adverse = entry - current
        if adverse >= config.SENTINEL_POSITION_MOVE:
            items.append(
                {
                    "market_id": p["market_id"],
                    "reason": f"held {p['side']} moved {adverse * 100:.0f} pts against entry — thesis check",
                    "priority": round(50 + adverse * 100, 2),  # protect the book first
                }
            )
    return items


def near_resolution_items(markets: list[dict], tracked: set[str], now: Optional[datetime] = None) -> list[dict]:
    """Held/watched markets resolving within the window (pure)."""
    now = now or datetime.now(timezone.utc)
    items = []
    for m in markets:
        if m["slug"] not in tracked or not m.get("end_date"):
            continue
        try:
            end = datetime.fromisoformat(m["end_date"].replace("Z", "+00:00"))
        except ValueError:
            continue
        hours_left = (end - now).total_seconds() / 3600
        if 0 < hours_left <= config.SENTINEL_RESOLUTION_HOURS:
            items.append(
                {
                    "market_id": m["slug"],
                    "reason": f"resolves in {hours_left:.0f}h — final look",
                    "priority": round(40 + (config.SENTINEL_RESOLUTION_HOURS - hours_left), 2),
                }
            )
    return items


async def news_burst_items(tracked_slugs: list[str], question_by_slug: dict[str, str]) -> list[dict]:
    """Held/watched markets with a burst of fresh headlines (few API calls)."""
    items = []
    for slug in tracked_slugs[:10]:  # stay polite
        question = question_by_slug.get(slug)
        if not question:
            continue
        headlines = await google_news.fetch_articles(question, max_records=config.SENTINEL_NEWS_BURST + 2, days=1)
        if len(headlines) >= config.SENTINEL_NEWS_BURST:
            items.append(
                {
                    "market_id": slug,
                    "reason": f"{len(headlines)} fresh headlines in 24h",
                    "priority": 30 + len(headlines),
                }
            )
    return items


async def main_async(dry_run: bool) -> None:
    markets = await polymarket.get_trending_markets(200)
    mid_by_slug = {m["slug"]: m["mid"] for m in markets}
    question_by_slug = {m["slug"]: m["question"] for m in markets}

    open_positions = [
        p for p in supabase_client.get_open_positions() if p.get("user_id") is None
    ]
    held = {p["market_id"] for p in open_positions}
    watched = set(supabase_client.distinct_watched_market_ids())
    tracked = held | watched

    items = (
        position_risk_items(open_positions, mid_by_slug)
        + near_resolution_items(markets, tracked)
        + price_move_items(markets)
        + await news_burst_items(sorted(tracked), question_by_slug)
    )
    # strongest signal per market wins
    best: dict[str, dict] = {}
    for item in items:
        current = best.get(item["market_id"])
        if current is None or item["priority"] > current["priority"]:
            best[item["market_id"]] = item
    findings = sorted(best.values(), key=lambda i: i["priority"], reverse=True)[:15]

    print(f"sentinel: {len(findings)} finding(s)")
    for f in findings:
        print(f"  [{f['priority']:>6}] {f['market_id'][:50]} — {f['reason']}")
    if dry_run:
        return
    written = supabase_client.add_agenda_items(findings)
    print(f"agenda: {written} new item(s) filed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
