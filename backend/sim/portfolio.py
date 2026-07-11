"""Portfolio views over the paper-trading positions table."""

from __future__ import annotations

from backend.data import supabase_client


def get_portfolio() -> dict:
    """All positions + headline stats. Empty shell when Supabase is off."""
    if not supabase_client.is_configured():
        return {"open": [], "resolved": [], "stats": _stats([], [])}
    client = supabase_client.get_client()
    rows = (
        client.table("positions").select("*").order("opened_at", desc=True).limit(200).execute().data
        or []
    )
    open_rows = [r for r in rows if r.get("status") == "open"]
    resolved = [r for r in rows if r.get("status") == "resolved"]
    return {"open": open_rows, "resolved": resolved, "stats": _stats(open_rows, resolved)}


def _stats(open_rows: list[dict], resolved: list[dict]) -> dict:
    realized = sum(float(r.get("pnl") or 0) for r in resolved)
    wins = sum(1 for r in resolved if float(r.get("pnl") or 0) > 0)
    return {
        "open_positions": len(open_rows),
        "open_exposure_usd": round(sum(float(r.get("size_usd") or 0) for r in open_rows), 2),
        "resolved_positions": len(resolved),
        "realized_pnl_usd": round(realized, 2),
        "win_rate": round(wins / len(resolved), 3) if resolved else None,
    }
