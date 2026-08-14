"""Thin Supabase wrapper. Sync (supabase-py); the async pipeline calls these
via asyncio.to_thread. Every helper is a no-op returning a safe default when
Supabase is not configured, so the agent degrades instead of crashing.
"""

from __future__ import annotations

import math
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


def today_utc() -> str:
    """Date-only UTC stamp. The halt breaker's `at` field must use this format; risk.py string-compares it."""
    return datetime.now(timezone.utc).date().isoformat()


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


def upsert_social_posts(posts: list[dict]) -> int:
    """Upsert scraped social posts by unique url. Returns rows written."""
    if not is_configured() or not posts:
        return 0
    rows = [
        {
            "url": p["url"],
            "text": (p.get("text") or "")[:500],
            "source": p.get("source") or "reddit",
            "subreddit": p.get("subreddit") or "",
            "score": int(p.get("score") or 0),
            "posted_at": p.get("created_at"),
            "entities": p.get("entities") or [],
        }
        for p in posts
        if p.get("url") and p.get("text")
    ]
    if not rows:
        return 0
    get_client().table("social_posts").upsert(rows, on_conflict="url").execute()
    return len(rows)


def get_social_posts_for(slug: str, limit: int = 20) -> list[dict]:
    """Recent indexed posts tagged with this market (newest first)."""
    if not is_configured():
        return []
    try:
        return (
            get_client()
            .table("social_posts")
            .select("url,text,source,subreddit,score,posted_at")
            .contains("entities", [slug])
            .order("posted_at", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception:
        return []


def get_unembedded_social_posts(limit: int = 200) -> list[dict]:
    if not is_configured():
        return []
    return (
        get_client()
        .table("social_posts")
        .select("id,url,text,source,subreddit,posted_at")
        .eq("embedded", False)
        .limit(limit)
        .execute()
        .data
        or []
    )


def mark_social_posts_embedded(post_ids: list[str]) -> None:
    if not is_configured() or not post_ids:
        return
    get_client().table("social_posts").update({"embedded": True}).in_("id", post_ids).execute()


def upsert_precedents(precedents: list[dict]) -> int:
    if not is_configured() or not precedents:
        return 0
    get_client().table("precedents").upsert(precedents).execute()
    return len(precedents)


def insert_position(position: dict) -> Optional[str]:
    if not is_configured():
        return None
    rows = get_client().table("positions").insert(position).execute().data
    return rows[0]["id"] if rows else None


def insert_positions(positions: list[dict]) -> list[Optional[str]]:
    """Insert a paper basket in one PostgREST request.

    PostgreSQL treats the multi-row insert atomically, which prevents an
    arbitrage simulation from leaving one leg recorded without its hedge.
    """
    if not positions:
        return []
    if not is_configured():
        return [None] * len(positions)
    rows = get_client().table("positions").insert(positions).execute().data or []
    return [str(row["id"]) for row in rows]


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
        pass  # telemetry must never break a run


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


# watchlist rows carry the fixed DESK_USER_ID; the schema needs a non-null uuid.


def add_watch(market_id: str) -> None:
    if not is_configured():
        return
    get_client().table("watchlist").upsert(
        {"user_id": config.DESK_USER_ID, "market_id": market_id},
        on_conflict="user_id,market_id",
    ).execute()


def remove_watch(market_id: str) -> None:
    if not is_configured():
        return
    get_client().table("watchlist").delete().eq("market_id", market_id).execute()


def get_watchlist() -> list[str]:
    if not is_configured():
        return []
    rows = (
        get_client()
        .table("watchlist")
        .select("market_id")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    seen: set[str] = set()
    out: list[str] = []
    for r in rows:  # newest first; dedupe
        if r["market_id"] not in seen:
            seen.add(r["market_id"])
            out.append(r["market_id"])
    return out


def add_agenda_items(items: list[dict]) -> int:
    """Insert pending items [{market_id, reason, priority}]; dupes are skipped by a partial unique index."""
    if not is_configured() or not items:
        return 0
    written = 0
    for item in items:
        try:
            get_client().table("agenda").insert(
                {
                    "market_id": item["market_id"],
                    "reason": item["reason"][:300],
                    "priority": item.get("priority", 0),
                }
            ).execute()
            written += 1
        except Exception:
            continue  # duplicate pending item
    return written


def get_pending_agenda(limit: int = 10) -> list[dict]:
    if not is_configured():
        return []
    return (
        get_client()
        .table("agenda")
        .select("*")
        .eq("status", "pending")
        .order("priority", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )


def resolve_agenda_item(item_id: str, status: str, outcome: str) -> None:
    if not is_configured():
        return
    get_client().table("agenda").update(
        {"status": status, "outcome": outcome[:300], "handled_at": _now()}
    ).eq("id", item_id).execute()


def analyses_today() -> int:
    """Pipeline runs so far this UTC day — the daily LLM budget counter."""
    if not is_configured():
        return 0
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
    resp = (
        get_client()
        .table("runs")
        .select("id", count="exact")
        .gte("created_at", today)
        .limit(1)
        .execute()
    )
    return resp.count or 0


def save_briefing(content: str, facts: dict) -> None:
    if not is_configured():
        return
    get_client().table("briefings").insert({"content": content, "facts": facts}).execute()


def latest_briefing() -> Optional[dict]:
    if not is_configured():
        return None
    rows = (
        get_client()
        .table("briefings")
        .select("content,created_at")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    return rows[0] if rows else None


def strategy_pnl_7d() -> dict[str, dict]:
    """strategy -> {pnl, trades} over positions resolved in the last 7 days."""
    if not is_configured():
        return {}
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    rows = (
        get_client()
        .table("positions")
        .select("strategy,pnl")
        .eq("status", "resolved")
        .gte("resolved_at", cutoff)
        .execute()
        .data
        or []
    )
    out: dict[str, dict] = {}
    for r in rows:
        s = r.get("strategy") or "manual"
        entry = out.setdefault(s, {"pnl": 0.0, "trades": 0})
        entry["pnl"] += float(r.get("pnl") or 0)
        entry["trades"] += 1
    for entry in out.values():
        entry["pnl"] = round(entry["pnl"], 2)
    return out


def _merge_settings(defaults: dict, stored: dict) -> dict:
    """Two-level merge so new default keys appear without wiping stored ones."""
    merged = {}
    for section, section_defaults in defaults.items():
        stored_section = stored.get(section)
        if isinstance(section_defaults, dict) and isinstance(stored_section, dict):
            merged[section] = {**section_defaults, **stored_section}
        elif stored_section is not None:
            merged[section] = stored_section
        else:
            merged[section] = section_defaults
    return merged


def get_agent_settings() -> dict:
    from backend import config

    if not is_configured():
        return config.DEFAULT_AGENT_SETTINGS
    try:
        rows = (
            get_client().table("agent_settings").select("value").eq("key", "main").execute().data
        )
        stored = rows[0]["value"] if rows else {}
    except Exception:
        stored = {}
    return _merge_settings(config.DEFAULT_AGENT_SETTINGS, stored)


def current_bankroll() -> float:
    """Paper bankroll — adjustable from the terminal, config as fallback."""
    from backend import config

    try:
        return float(get_agent_settings()["funds"]["bankroll_usd"])
    except (KeyError, TypeError, ValueError):
        return float(config.PAPER_BANKROLL_USD)


def update_agent_settings(patch: dict) -> dict:
    """Apply a partial update ({strategies?, risk?, halt?}) and persist."""
    current = get_agent_settings()
    merged = _merge_settings(current, patch)
    if is_configured():
        get_client().table("agent_settings").upsert(
            {"key": "main", "value": merged, "updated_at": _now()}
        ).execute()
    return merged


def save_equity_snapshot(stats: dict) -> None:
    """Upsert today's equity snapshot (keyed on UTC day — last write wins)."""
    if not is_configured():
        return
    get_client().table("equity_snapshots").upsert(
        {
            "day": today_utc(),
            "equity_usd": float(stats.get("equity_usd") or 0),
            "balance_usd": float(stats.get("balance_usd") or 0),
            "open_exposure_usd": float(stats.get("open_exposure_usd") or 0),
            "unrealized_pnl_usd": float(stats.get("unrealized_pnl_usd") or 0),
            "realized_pnl_usd": float(stats.get("realized_pnl_usd") or 0),
            "open_positions": int(stats.get("open_positions") or 0),
            "created_at": _now(),
        }
    ).execute()


def get_equity_history(limit: int = 90) -> list[dict]:
    """Daily snapshots, oldest first (for the equity curve)."""
    if not is_configured():
        return []
    try:
        rows = (
            get_client()
            .table("equity_snapshots")
            .select("day,equity_usd,balance_usd,realized_pnl_usd,unrealized_pnl_usd")
            .order("day", desc=True)
            .limit(limit)
            .execute()
            .data
            or []
        )
    except Exception:
        return []
    return list(reversed(rows))


def sanitize_settings_patch(raw: dict, allow_halt_activation: bool = False) -> dict:
    """Whitelist and clamp an untrusted settings patch. The circuit breaker only arms when the caller opts in."""
    from backend import config

    patch: dict = {}
    strategies = raw.get("strategies")
    if isinstance(strategies, dict):
        cleaned = {}
        for key, value in strategies.items():
            if key not in config.DEFAULT_AGENT_SETTINGS["strategies"]:
                continue
            if isinstance(value, bool):
                cleaned[key] = value
            elif isinstance(value, (int, float)) and value in (0, 1):
                cleaned[key] = bool(value)
        if cleaned:
            patch["strategies"] = cleaned
    risk = raw.get("risk")
    if isinstance(risk, dict):
        cleaned = {}
        for key, (lo, hi) in config.RISK_BOUNDS.items():
            if key in risk:
                try:
                    value = float(risk[key])
                    if math.isfinite(value):
                        cleaned[key] = max(lo, min(hi, value))
                except (TypeError, ValueError):
                    continue
        if cleaned:
            patch["risk"] = cleaned
    halt = raw.get("halt")
    if isinstance(halt, dict) and isinstance(halt.get("active"), bool):
        if halt["active"] is False:
            patch["halt"] = {"active": False, "reason": "", "at": ""}
        elif allow_halt_activation:
            patch["halt"] = {
                "active": True,
                "reason": str(halt.get("reason") or "halted on user instruction")[:200],
                "at": today_utc(),
            }
    funds = raw.get("funds")
    if isinstance(funds, dict) and "bankroll_usd" in funds:
        lo, hi = config.BANKROLL_BOUNDS
        try:
            value = float(funds["bankroll_usd"])
            if math.isfinite(value):
                patch["funds"] = {"bankroll_usd": max(lo, min(hi, value))}
        except (TypeError, ValueError):
            pass
    return patch


def already_mirrored(wallet: str, market_id: str, outcome: str) -> bool:
    if not is_configured():
        return False
    rows = (
        get_client()
        .table("mirrored_trades")
        .select("id")
        .eq("wallet", wallet)
        .eq("market_id", market_id)
        .eq("outcome", outcome)
        .limit(1)
        .execute()
        .data
    )
    return bool(rows)


def record_mirrored(wallet: str, market_id: str, outcome: str, position_id: str | None) -> None:
    if not is_configured():
        return
    get_client().table("mirrored_trades").upsert(
        {"wallet": wallet, "market_id": market_id, "outcome": outcome, "position_id": position_id},
        on_conflict="wallet,market_id,outcome",
    ).execute()


def distinct_followed_wallets() -> list[str]:
    if not is_configured():
        return []
    rows = get_client().table("followed_wallets").select("wallet").execute().data or []
    return sorted({r["wallet"] for r in rows})


# followed wallets: single-user, same DESK_USER_ID rule as the watchlist.


def follow_wallets(wallets: list[dict]) -> int:
    """Upsert [{wallet, label}]. Returns rows written."""
    if not is_configured() or not wallets:
        return 0
    rows = [
        {"user_id": config.DESK_USER_ID, "wallet": w["wallet"], "label": w.get("label", "")}
        for w in wallets
    ]
    get_client().table("followed_wallets").upsert(rows, on_conflict="user_id,wallet").execute()
    return len(rows)


def unfollow_wallet(wallet: str) -> None:
    if not is_configured():
        return
    get_client().table("followed_wallets").delete().eq("wallet", wallet).execute()


def get_followed_wallets() -> list[dict]:
    if not is_configured():
        return []
    rows = (
        get_client()
        .table("followed_wallets")
        .select("wallet,label")
        .order("created_at", desc=True)
        .execute()
        .data
        or []
    )
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        if r["wallet"] not in seen:
            seen.add(r["wallet"])
            out.append(r)
    return out


def distinct_watched_market_ids() -> list[str]:
    """All watched markets across users (for the refresh job)."""
    if not is_configured():
        return []
    rows = get_client().table("watchlist").select("market_id").execute().data or []
    return sorted({r["market_id"] for r in rows})
