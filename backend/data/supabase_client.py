"""Thin Supabase wrapper. Sync (supabase-py); the async pipeline calls these
via asyncio.to_thread. Every helper is a no-op returning a safe default when
Supabase is not configured, so the agent degrades instead of crashing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Optional

from backend import config


def is_configured() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY)


@lru_cache(maxsize=1)
def get_client():
    from supabase import create_client  # deferred: import is slow

    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# markets
# ---------------------------------------------------------------------------


def upsert_markets(markets: list[dict]) -> int:
    """Upsert normalized Gamma markets (see polymarket.normalize_market)."""
    if not is_configured() or not markets:
        return 0
    rows = [
        {
            "id": m["id"],
            "slug": m["slug"],
            "question": m["question"],
            "category": m["category"],
            "end_date": m["end_date"],
            "resolution_text": m["description"],
            "yes_token_id": m["yes_token_id"],
            "last_mid": m["mid"],
            "volume24h": m["volume24h"],
            "active": m["active"],
            "indexed_at": _now(),
        }
        for m in markets
        if m.get("id")
    ]
    get_client().table("markets").upsert(rows).execute()
    return len(rows)


def get_cached_markets(active_only: bool = True, limit: int = 300) -> list[dict]:
    if not is_configured():
        return []
    q = get_client().table("markets").select("*").order("volume24h", desc=True).limit(limit)
    if active_only:
        q = q.eq("active", True)
    return q.execute().data or []


def mark_markets_inactive(market_ids: list[str]) -> None:
    if not is_configured() or not market_ids:
        return
    get_client().table("markets").update({"active": False}).in_("id", market_ids).execute()


# ---------------------------------------------------------------------------
# articles
# ---------------------------------------------------------------------------


def upsert_articles(articles: list[dict]) -> int:
    """Upsert GDELT articles by unique url. Returns rows written."""
    if not is_configured() or not articles:
        return 0
    rows = [
        {
            "url": a["url"],
            "title": a.get("title", ""),
            "domain": a.get("domain", ""),
            "published_at": a.get("published_at"),
            "entities": a.get("entities") or [],
            "fetched_text": a.get("fetched_text"),
            "embedded": a.get("embedded", False),
        }
        for a in articles
        if a.get("url")
    ]
    get_client().table("articles").upsert(rows, on_conflict="url").execute()
    return len(rows)


def get_unembedded_articles(limit: int = 200) -> list[dict]:
    if not is_configured():
        return []
    return (
        get_client()
        .table("articles")
        .select("id,url,title,domain,published_at")
        .eq("embedded", False)
        .limit(limit)
        .execute()
        .data
        or []
    )


def mark_articles_embedded(article_ids: list[str]) -> None:
    if not is_configured() or not article_ids:
        return
    get_client().table("articles").update({"embedded": True}).in_("id", article_ids).execute()


def latest_article_date() -> Optional[str]:
    """Cache watermark for EvidenceRetriever live top-up."""
    if not is_configured():
        return None
    rows = (
        get_client()
        .table("articles")
        .select("published_at")
        .order("published_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["published_at"] if rows else None


# ---------------------------------------------------------------------------
# precedents
# ---------------------------------------------------------------------------


def upsert_precedents(precedents: list[dict]) -> int:
    if not is_configured() or not precedents:
        return 0
    get_client().table("precedents").upsert(precedents).execute()
    return len(precedents)


def count_precedents() -> int:
    if not is_configured():
        return 0
    resp = get_client().table("precedents").select("market_id", count="exact").limit(1).execute()
    return resp.count or 0


# ---------------------------------------------------------------------------
# positions & runs
# ---------------------------------------------------------------------------


def insert_position(position: dict) -> Optional[str]:
    if not is_configured():
        return None
    rows = get_client().table("positions").insert(position).execute().data
    return rows[0]["id"] if rows else None


def get_open_positions() -> list[dict]:
    if not is_configured():
        return []
    return get_client().table("positions").select("*").eq("status", "open").execute().data or []


def resolve_position(position_id: str, resolved_outcome: str, pnl: float) -> None:
    if not is_configured():
        return
    get_client().table("positions").update(
        {
            "status": "resolved",
            "resolved_outcome": resolved_outcome,
            "pnl": pnl,
            "resolved_at": _now(),
        }
    ).eq("id", position_id).execute()


def log_run(run: dict) -> None:
    if not is_configured():
        return
    try:
        get_client().table("runs").insert(run).execute()
    except Exception:
        pass  # budget telemetry must never break a run


def get_recent_runs(limit: int = 200) -> list[dict]:
    if not is_configured():
        return []
    return (
        get_client()
        .table("runs")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


# ---------------------------------------------------------------------------
# watchlist
# ---------------------------------------------------------------------------


def add_watch(user_id: str, market_id: str) -> None:
    if not is_configured():
        return
    get_client().table("watchlist").upsert(
        {"user_id": user_id, "market_id": market_id}, on_conflict="user_id,market_id"
    ).execute()


def remove_watch(user_id: str, market_id: str) -> None:
    if not is_configured():
        return
    get_client().table("watchlist").delete().eq("user_id", user_id).eq(
        "market_id", market_id
    ).execute()


def get_watchlist(user_id: str) -> list[str]:
    if not is_configured():
        return []
    rows = (
        get_client()
        .table("watchlist")
        .select("market_id")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    return [r["market_id"] for r in rows]


def distinct_watched_market_ids() -> list[str]:
    """All watched markets across users (for the refresh job)."""
    if not is_configured():
        return []
    rows = get_client().table("watchlist").select("market_id").execute().data or []
    return sorted({r["market_id"] for r in rows})
