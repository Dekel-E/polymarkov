"""Portfolio views over the paper-trading positions table.

One book holds every position, distinguished by the `strategy` column. Open
rows first receive a safe cached mark; the HTTP portfolio route then upgrades
them from the live CLOB and recomputes unrealized PnL and equity.
"""

from __future__ import annotations

import asyncio

from backend.data import polymarket, supabase_client


def get_portfolio() -> dict:
    if not supabase_client.is_configured():
        return {"open": [], "resolved": [], "stats": _stats([], []), "equity_history": []}

    client = supabase_client.get_client()
    rows = _fetch_all_positions(client)

    open_rows = [r for r in rows if r.get("status") == "open"]
    resolved = [r for r in rows if r.get("status") == "resolved"]
    _enrich_open(client, open_rows)
    return {
        "open": open_rows,
        "resolved": resolved[:200],
        "stats": _stats(open_rows, resolved),
        "equity_history": supabase_client.get_equity_history(),
    }


def _fetch_all_positions(client, page_size: int = 1_000) -> list[dict]:
    """Fetch every position so lifetime P&L is not truncated to a UI page."""
    rows: list[dict] = []
    start = 0
    while True:
        page = (
            client.table("positions")
            .select("*")
            .order("opened_at", desc=True)
            .range(start, start + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < page_size:
            return rows
        start += page_size


def _enrich_open(client, open_rows: list[dict]) -> None:
    """Attach cached price metadata; the HTTP route refreshes it from CLOB."""
    slugs = sorted({r["market_id"] for r in open_rows})
    if not slugs:
        return
    try:
        markets = (
            client.table("markets")
            .select("slug,last_mid,category,yes_token_id")
            .in_("slug", slugs)
            .execute()
            .data
            or []
        )
    except Exception:
        markets = []
    by_slug = {m["slug"]: m for m in markets}

    for r in open_rows:
        m = by_slug.get(r["market_id"], {})
        r["category"] = m.get("category") or "other"
        r["yes_token_id"] = m.get("yes_token_id") or ""
        mid = float(m["last_mid"]) if m.get("last_mid") is not None else None
        if mid is None:
            r["current_price"] = None
            r["unrealized_pnl"] = None
            r["price_source"] = "unavailable"
            continue
        _apply_mid(r, mid, "cache")


def _apply_mid(row: dict, yes_mid: float, source: str) -> None:
    """Price either token side from one fresh YES midpoint."""
    current = yes_mid if row["side"] == "BUY_YES" else 1 - yes_mid
    entry = float(row["entry_price"])
    shares = float(row["size_usd"]) / entry if entry > 0 else 0.0
    row["current_price"] = round(current, 4)
    row["unrealized_pnl"] = round(shares * (current - entry), 2)
    row["price_source"] = source


async def refresh_open_prices(data: dict) -> dict:
    """Refresh every unique open market from the live CLOB, best effort.

    The database query supplies public token ids, so a normal refresh is one
    CLOB request per unique market. Missing ids fall back to one Gamma lookup.
    A venue failure preserves the cached price instead of breaking the whole
    portfolio response.
    """
    open_rows = data.get("open") or []
    if not open_rows:
        return data

    rows_by_market: dict[str, list[dict]] = {}
    for row in open_rows:
        rows_by_market.setdefault(str(row["market_id"]), []).append(row)

    async def live_mid(slug: str, rows: list[dict]) -> tuple[str, float | None]:
        token_id = next(
            (str(row.get("yes_token_id") or "") for row in rows if row.get("yes_token_id")),
            "",
        )
        fallback_mid = None
        if not token_id:
            try:
                market = await polymarket.get_market(slug)
                if market:
                    token_id = str(market.get("yes_token_id") or "")
                    fallback_mid = (
                        float(market["mid"]) if market.get("mid") is not None else None
                    )
            except Exception:
                return slug, None
        if not token_id:
            return slug, fallback_mid
        try:
            book = await polymarket.get_order_book(token_id)
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            if bids and asks:
                return slug, (float(bids[0][0]) + float(asks[0][0])) / 2
            if bids:
                return slug, float(bids[0][0])
            if asks:
                return slug, float(asks[0][0])
        except Exception:
            pass
        return slug, fallback_mid

    refreshed = await asyncio.gather(
        *(live_mid(slug, rows) for slug, rows in rows_by_market.items())
    )
    for slug, mid in refreshed:
        if mid is None or not 0 < mid < 1:
            continue
        for row in rows_by_market[slug]:
            _apply_mid(row, mid, "live")

    stats = data.get("stats") or {}
    unrealized = sum(float(row.get("unrealized_pnl") or 0) for row in open_rows)
    stats["unrealized_pnl_usd"] = round(unrealized, 2)
    stats["equity_usd"] = round(
        float(stats.get("balance_usd") or 0)
        + unrealized
        - float(stats.get("open_fees_usd") or 0),
        2,
    )
    stats["live_price_positions"] = sum(
        1 for row in open_rows if row.get("price_source") == "live"
    )
    return data


def _exposure(open_rows: list[dict], key: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in open_rows:
        k = r.get(key) or ("manual" if key == "strategy" else "other")
        out[k] = round(out.get(k, 0) + float(r.get("size_usd") or 0), 2)
    return dict(sorted(out.items(), key=lambda kv: kv[1], reverse=True))


def _stats(open_rows: list[dict], resolved: list[dict]) -> dict:
    bankroll = supabase_client.current_bankroll()
    realized = sum(float(r.get("pnl") or 0) for r in resolved)
    unrealized = sum(float(r.get("unrealized_pnl") or 0) for r in open_rows)
    open_exposure = sum(float(r.get("size_usd") or 0) for r in open_rows)
    open_fees = sum(float(r.get("fee_paid") or 0) for r in open_rows)
    balance = bankroll + realized
    wins = sum(1 for r in resolved if float(r.get("pnl") or 0) > 0)
    largest = max((float(r.get("size_usd") or 0) for r in open_rows), default=0.0)
    return {
        "bankroll_usd": round(bankroll, 2),
        "balance_usd": round(balance, 2),
        "available_usd": round(balance - open_exposure - open_fees, 2),
        "equity_usd": round(balance + unrealized - open_fees, 2),
        "open_positions": len(open_rows),
        "open_exposure_usd": round(open_exposure, 2),
        "open_fees_usd": round(open_fees, 2),
        "unrealized_pnl_usd": round(unrealized, 2),
        "resolved_positions": len(resolved),
        "realized_pnl_usd": round(realized, 2),
        "win_rate": round(wins / len(resolved), 3) if resolved else None,
        "largest_position_pct": round(largest / bankroll * 100, 2) if bankroll else 0,
        "exposure_by_strategy": _exposure(open_rows, "strategy"),
        "exposure_by_category": _exposure(open_rows, "category"),
    }
