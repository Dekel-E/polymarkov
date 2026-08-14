"""Portfolio views over the paper-trading positions table.

One book holds every position, distinguished by the `strategy` column. Open
rows are enriched with the cached market mid for current price and unrealized
PnL without hitting Gamma.
"""

from __future__ import annotations

from backend.data import supabase_client


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
    """Attach current_price, unrealized_pnl and category from the markets cache."""
    slugs = sorted({r["market_id"] for r in open_rows})
    if not slugs:
        return
    try:
        markets = (
            client.table("markets").select("slug,last_mid,category").in_("slug", slugs).execute().data
            or []
        )
    except Exception:
        markets = []
    by_slug = {m["slug"]: m for m in markets}

    for r in open_rows:
        m = by_slug.get(r["market_id"], {})
        r["category"] = m.get("category") or "other"
        mid = float(m["last_mid"]) if m.get("last_mid") is not None else None
        if mid is None:
            r["current_price"] = None
            r["unrealized_pnl"] = None
            continue
        current = mid if r["side"] == "BUY_YES" else 1 - mid
        entry = float(r["entry_price"])
        shares = float(r["size_usd"]) / entry if entry > 0 else 0.0
        r["current_price"] = round(current, 4)
        r["unrealized_pnl"] = round(shares * (current - entry), 2)


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
