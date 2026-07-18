"""Polymarket Data API client: wallet leaderboard + per-wallet positions.

Public, no auth (https://data-api.polymarket.com). Endpoint shapes drift, so
parsing is defensive and everything degrades to [] on failure.
"""

from __future__ import annotations

import re
import time
from typing import Any, Optional

import httpx

from backend import config

DATA_API = "https://data-api.polymarket.com"
_HEADERS = {"User-Agent": "polymarkov/0.1"}

WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
MAX_IMPORT = 100


def validate_wallet_import(items: Any) -> tuple[list[dict], int]:
    """Normalize a user-supplied wallet list (JSON import) -> (valid [{wallet, label}], skipped count)."""
    if not isinstance(items, list):
        return [], 0
    valid: list[dict] = []
    seen: set[str] = set()
    skipped = 0
    for item in items[:MAX_IMPORT]:
        if isinstance(item, str):
            wallet, label = item.strip(), ""
        elif isinstance(item, dict):
            wallet = str(item.get("wallet") or item.get("address") or "").strip()
            label = str(item.get("label") or item.get("name") or "").strip()[:60]
        else:
            skipped += 1
            continue
        wallet = wallet.lower()
        if not WALLET_RE.match(wallet) or wallet in seen:
            skipped += 1
            continue
        seen.add(wallet)
        valid.append({"wallet": wallet, "label": label})
    skipped += max(0, len(items) - MAX_IMPORT)
    return valid, skipped

LEAGUE_CACHE_TTL_S = 600
_league_cache: dict[str, tuple[float, list[dict]]] = {}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_leaderboard(rows: list[dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        wallet = r.get("proxyWallet") or r.get("wallet") or r.get("address") or ""
        if not wallet:
            continue
        out.append(
            {
                "rank": int(r.get("rank") or i + 1),
                "wallet": wallet,
                "name": r.get("name") or r.get("userName") or r.get("pseudonym") or "",
                "pnl": _to_float(r.get("pnl") if r.get("pnl") is not None else r.get("amount")),
                "volume": _to_float(r.get("volume") or r.get("vol")),
                "image": r.get("profileImage") or r.get("profileImageOptimized") or "",
                "verified": bool(r.get("verifiedBadge") or r.get("verified")),
            }
        )
    return out


# /v1/leaderboard takes timePeriod=DAY|WEEK|MONTH|ALL and silently ignores unknown params.
_TIME_PERIOD = {"1d": "DAY", "7d": "WEEK", "30d": "MONTH", "all": "ALL"}


async def fetch_leaderboard(window: str = "30d", limit: int = 20) -> list[dict]:
    """Top wallets by profit for a time window. Cached 10 min. [] on failure."""
    cache_key = f"{window}:{limit}"
    hit = _league_cache.get(cache_key)
    if hit and time.time() - hit[0] < LEAGUE_CACHE_TTL_S:
        return hit[1]

    params = {
        "timePeriod": _TIME_PERIOD.get(window, "MONTH"),
        "orderBy": "PNL",
        "limit": min(limit, 50),
    }
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            resp = await client.get(f"{DATA_API}/v1/leaderboard", params=params)
            resp.raise_for_status()
            body = resp.json()
            rows = body if isinstance(body, list) else body.get("leaderboard") or body.get("data") or []
            parsed = parse_leaderboard(rows)
            if parsed:
                _league_cache[cache_key] = (time.time(), parsed)
                return parsed
    except (httpx.HTTPError, ValueError):
        pass
    return []


def parse_positions(rows: list[dict], limit: int = 8) -> list[dict]:
    out = []
    for r in rows:
        market_obj = r.get("market") if isinstance(r.get("market"), dict) else {}
        title = r.get("title") or market_obj.get("question") or ""
        out.append(
            {
                "market": title or r.get("slug") or "",
                "event_slug": r.get("eventSlug") or "",
                "slug": r.get("slug") or r.get("eventSlug") or "",
                "outcome": r.get("outcome") or "",
                "size_usd": round(_to_float(r.get("currentValue") or r.get("initialValue") or r.get("size")), 2),
                "pnl": round(_to_float(r.get("cashPnl") if r.get("cashPnl") is not None else r.get("percentPnl")), 2),
                "avg_price": _to_float(r.get("avgPrice")),
                "current_price": _to_float(r.get("curPrice")),
            }
        )
    out.sort(key=lambda p: abs(p["size_usd"]), reverse=True)
    return out[:limit]


async def fetch_market_trades(condition_id: str, limit: int = 50) -> list[dict]:
    """Recent fills on one market (on-chain flow). [] on failure.
    Rows: {side, size, price, notional_usd, timestamp, wallet, outcome}."""
    if not condition_id:
        return []
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            resp = await client.get(
                f"{DATA_API}/trades", params={"market": condition_id, "limit": min(limit, 100)}
            )
            resp.raise_for_status()
            body = resp.json()
            rows = body if isinstance(body, list) else body.get("data") or []
    except (httpx.HTTPError, ValueError):
        return []
    trades = []
    for r in rows:
        size = _to_float(r.get("size"))
        price = _to_float(r.get("price"))
        trades.append(
            {
                "side": r.get("side", ""),
                "size": size,
                "price": price,
                "notional_usd": round(size * price, 2),
                "timestamp": int(_to_float(r.get("timestamp"))),
                "wallet": r.get("proxyWallet", ""),
                "outcome": r.get("outcome", ""),
            }
        )
    return trades


def _yes_lean(side: str, outcome: str, notional: float) -> float:
    """Signed notional toward YES: buying YES or selling NO is bullish-YES."""
    o = (outcome or "").strip().lower()
    is_yes = o.startswith("y") or o in ("1", "true")
    is_no = o.startswith("n") or o in ("0", "false")
    if not (is_yes or is_no):  # multi-outcome market: no clean YES/NO direction
        return 0.0
    buy = (side or "").strip().upper() == "BUY"
    return notional if (buy and is_yes) or (not buy and is_no) else -notional


def aggregate_market_flow(
    trades: list[dict], followed: list[dict], top: list[dict], whale_usd: float = 10_000.0
) -> dict:
    """Cross-reference recent market trades against followed + top wallets (pure).

    Returns net directional flow, which tracked/top wallets are active and which
    way they lean, and any whale prints."""
    followed_ix = {(w.get("wallet") or "").lower(): w for w in followed}
    top_ix = {(t.get("wallet") or "").lower(): t for t in top}

    per_wallet: dict[str, dict] = {}
    net_yes = 0.0
    whales: list[dict] = []
    for t in trades:
        w = (t.get("wallet") or "").lower()
        notional = float(t.get("notional_usd") or 0.0)
        lean = _yes_lean(t.get("side", ""), t.get("outcome", ""), notional)
        net_yes += lean
        pw = per_wallet.setdefault(w, {"yes_lean": 0.0, "notional": 0.0, "trades": 0})
        pw["yes_lean"] += lean
        pw["notional"] += notional
        pw["trades"] += 1
        if notional >= whale_usd and w:
            whales.append({
                "wallet": w, "side": t.get("side", ""), "outcome": t.get("outcome", ""),
                "notional_usd": round(notional, 2), "timestamp": t.get("timestamp"),
            })

    def _active(index: dict, name_key: str) -> list[dict]:
        rows = []
        for w, meta in index.items():
            pw = per_wallet.get(w)
            if not pw:
                continue
            rows.append({
                "wallet": w,
                "label": meta.get("label") or meta.get(name_key) or "",
                "rank": meta.get("rank"),
                "yes_lean_usd": round(pw["yes_lean"], 2),
                "notional_usd": round(pw["notional"], 2),
                "side": "YES" if pw["yes_lean"] >= 0 else "NO",
            })
        rows.sort(key=lambda r: abs(r["yes_lean_usd"]), reverse=True)
        return rows

    followed_active = _active(followed_ix, "name")
    top_active = _active(top_ix, "name")
    whales.sort(key=lambda x: x["notional_usd"], reverse=True)

    if not followed_active and not top_active and not whales:
        note = "No tracked/top-wallet activity detected in recent trades."
    else:
        direction = "YES" if net_yes >= 0 else "NO"
        note = (
            f"{len(followed_active)} followed + {len(top_active)} top-wallet(s) active; "
            f"net flow {direction} ${abs(net_yes):,.0f}"
            + (f"; {len(whales)} whale print(s)" if whales else "")
        )
    return {
        "net_yes_usd": round(net_yes, 2),
        "followed_active": followed_active,
        "top_active": top_active,
        "whale_prints": whales[:5],
        "trades_scanned": len(trades),
        "note": note,
    }


async def fetch_wallet_positions(wallet: str, limit: int = 8) -> list[dict]:
    """A wallet's current open positions, largest first. [] on failure."""
    try:
        async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT_S, headers=_HEADERS) as client:
            resp = await client.get(
                f"{DATA_API}/positions",
                params={"user": wallet, "sizeThreshold": 1, "limit": 50},
            )
            resp.raise_for_status()
            body = resp.json()
            rows = body if isinstance(body, list) else body.get("data") or []
            return parse_positions(rows, limit)
    except (httpx.HTTPError, ValueError):
        return []
