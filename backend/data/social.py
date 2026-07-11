"""Social signal clients — best-effort, feature-flagged per source (§2).

Primary source: Polymarket's own market comments (on-topic, free, no auth).
Secondary: Reddit search, only when REDDIT_CLIENT_ID/SECRET are configured.
Every function degrades to [] instead of raising.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from backend import config

GAMMA_BASE = "https://gamma-api.polymarket.com"
_HEADERS = {"User-Agent": "polymarkov/0.1 (course project)"}


def _parse_ts(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def mention_velocity(timestamps: list[datetime], now: Optional[datetime] = None) -> Optional[float]:
    """count(last 24h) / avg daily count(prior 6 days). None if no baseline."""
    if not timestamps:
        return None
    now = now or datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    recent = sum(1 for t in timestamps if t >= day_ago)
    prior = [t for t in timestamps if week_ago <= t < day_ago]
    prior_daily_avg = len(prior) / 6.0
    if prior_daily_avg == 0:
        return None  # guard div-by-zero: no baseline to compare against
    return round(recent / prior_daily_avg, 2)


# ---------------------------------------------------------------------------
# Polymarket comments (primary)
# ---------------------------------------------------------------------------


async def fetch_polymarket_comments(event_id: str, limit: int = config.MAX_SOCIAL_POSTS) -> list[dict]:
    """Recent comments on the market's event page. [] on any failure."""
    if not config.ENABLE_POLYMARKET_COMMENTS or not event_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            resp = await client.get(
                f"{GAMMA_BASE}/comments",
                params={
                    "parent_entity_type": "Event",
                    "parent_entity_id": event_id,
                    "limit": limit,
                    "order": "createdAt",
                    "ascending": "false",
                },
            )
            resp.raise_for_status()
            rows = resp.json() or []
    except (httpx.HTTPError, ValueError):
        return []

    posts = []
    for row in rows:
        body = (row.get("body") or "").strip()
        if not body:
            continue
        posts.append(
            {
                "text": body[:500],
                "source": "polymarket_comments",
                "url": "",
                "created_at": row.get("createdAt"),
            }
        )
    return posts[:limit]


# ---------------------------------------------------------------------------
# Reddit (optional, client-credentials OAuth)
# ---------------------------------------------------------------------------


async def _reddit_token(client: httpx.AsyncClient) -> Optional[str]:
    resp = await client.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET),
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json().get("access_token")


async def fetch_reddit_posts(query: str, limit: int = config.MAX_SOCIAL_POSTS) -> list[dict]:
    """Recent Reddit posts matching `query`. [] unless Reddit is enabled."""
    if not config.ENABLE_REDDIT:
        return []
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            token = await _reddit_token(client)
            if not token:
                return []
            resp = await client.get(
                "https://oauth.reddit.com/search",
                params={"q": query, "sort": "new", "t": "week", "limit": limit},
                headers={**_HEADERS, "Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            children = resp.json().get("data", {}).get("children", [])
    except (httpx.HTTPError, ValueError):
        return []

    posts = []
    for child in children:
        d = child.get("data", {})
        text = (d.get("title", "") + " " + (d.get("selftext") or "")).strip()
        if not text:
            continue
        created = d.get("created_utc")
        posts.append(
            {
                "text": text[:500],
                "source": "reddit",
                "url": f"https://www.reddit.com{d.get('permalink', '')}",
                "created_at": (
                    datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None
                ),
            }
        )
    return posts[:limit]


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


async def gather_social(event_id: str, query: str, limit: int = config.MAX_SOCIAL_POSTS) -> dict:
    """Collect posts from all enabled sources + compute mention velocity."""
    posts = await fetch_polymarket_comments(event_id, limit)
    if len(posts) < limit:
        posts += await fetch_reddit_posts(query, limit - len(posts))

    timestamps = [ts for p in posts if (ts := _parse_ts(p.get("created_at") or ""))]
    velocity = mention_velocity(timestamps)

    sources = sorted({p["source"] for p in posts})
    if not posts:
        note = "No social posts found — social signal unavailable for this market."
    else:
        note = f"{len(posts)} posts from {', '.join(sources)}."
        if velocity is None:
            note += " Not enough history to compute mention velocity."
    return {"posts": posts[:limit], "mention_velocity": velocity, "note": note}
