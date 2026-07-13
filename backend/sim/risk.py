"""Risk manager: stop-loss / take-profit / daily circuit breaker.

Rules come from the GUI-editable agent settings; enforcement runs on the
automation schedule. Protection keeps running even when strategies are
halted — the breaker stops NEW trades, never risk checks.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.data import supabase_client
from backend.sim import paper_broker, portfolio


def evaluate_position(position: dict, current_price: Optional[float], risk: dict) -> Optional[str]:
    """'stop_loss' | 'take_profit' | None for one open position (pure).

    Per-position price levels (sl_price / tp_price, set from the terminal)
    take precedence; the global % rules are the fallback."""
    if current_price is None or current_price <= 0:
        return None
    entry = float(position["entry_price"])
    size_usd = float(position["size_usd"])
    if entry <= 0 or size_usd <= 0:
        return None

    sl_price = position.get("sl_price")
    tp_price = position.get("tp_price")
    if sl_price is not None and current_price <= float(sl_price):
        return "stop_loss"
    if tp_price is not None and current_price >= float(tp_price):
        return "take_profit"
    if sl_price is not None or tp_price is not None:
        return None  # explicit levels replace the % rules entirely

    shares = size_usd / entry
    pnl_pct = (shares * (current_price - entry)) / size_usd * 100
    if pnl_pct <= -float(risk["stop_loss_pct"]):
        return "stop_loss"
    if pnl_pct >= float(risk["take_profit_pct"]):
        return "take_profit"
    return None


def realized_pnl_today() -> float:
    if not supabase_client.is_configured():
        return 0.0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00+00:00")
    rows = (
        supabase_client.get_client()
        .table("positions")
        .select("pnl")
        .eq("status", "resolved")
        .gte("resolved_at", today)
        .execute()
        .data
        or []
    )
    return round(sum(float(r.get("pnl") or 0) for r in rows), 2)


async def run_risk_checks() -> dict:
    """One pass: close breached positions, arm/refresh the circuit breaker."""
    settings = supabase_client.get_agent_settings()
    risk = settings["risk"]
    report = {"closed": [], "halted": False, "realized_today": 0.0}

    # 1. stop-loss / take-profit on every open position (any book)
    data = portfolio.get_portfolio(scope="agent")
    for position in data["open"]:
        reason = evaluate_position(position, position.get("current_price"), risk)
        if reason is None:
            continue
        result = await paper_broker.close_position(str(position["id"]), allow_agent=True)
        report["closed"].append(
            {"market_id": position["market_id"], "reason": reason,
             "pnl": result.get("pnl"), "error": result.get("error")}
        )

    # 2. daily circuit breaker on realized PnL
    realized = realized_pnl_today()
    report["realized_today"] = realized
    halt_active = settings["halt"].get("active", False)
    today = datetime.now(timezone.utc).date().isoformat()
    if realized <= -float(risk["daily_loss_halt_usd"]) and not halt_active:
        supabase_client.update_agent_settings(
            {"halt": {"active": True, "reason": f"daily loss {realized} breached limit", "at": today}}
        )
        report["halted"] = True
    elif halt_active and settings["halt"].get("at") and settings["halt"]["at"] < today:
        # a new day resets an automatic halt (manual resume also available in GUI)
        supabase_client.update_agent_settings({"halt": {"active": False, "reason": "", "at": ""}})

    return report


def strategies_allowed() -> tuple[dict, bool]:
    """(strategy flags, trading_allowed) — jobs call this before trading."""
    settings = supabase_client.get_agent_settings()
    return settings["strategies"], not settings["halt"].get("active", False)