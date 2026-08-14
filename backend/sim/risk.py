"""Risk manager: stop-loss, take-profit, daily circuit breaker.

Rules come from the agent settings; enforcement runs on the automation
schedule. The breaker stops new trades but never the risk checks themselves.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from backend.data import supabase_client
from backend.sim import paper_broker, portfolio


def evaluate_position(position: dict, current_price: Optional[float], risk: dict) -> Optional[str]:
    """'stop_loss' | 'take_profit' | None for one open position.

    Per-position sl_price / tp_price take precedence; the global % rules are
    the fallback."""
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


def daily_drawdown(realized_today: float, unrealized_total: float) -> float:
    """Realized losses today plus any open drawdown. Unrealized gains don't
    offset realized losses; they can evaporate before anyone books them."""
    return realized_today + min(0.0, unrealized_total)


async def run_risk_checks() -> dict:
    """One pass: close breached positions, arm/refresh the circuit breaker,
    and record today's equity snapshot (the portfolio equity curve)."""
    settings = supabase_client.get_agent_settings()
    risk = settings["risk"]
    report = {"closed": [], "halted": False, "realized_today": 0.0}

    # 1. stop-loss / take-profit on every open position (any book)
    data = portfolio.get_portfolio()
    closed_any = False
    for position in data["open"]:
        reason = evaluate_position(position, position.get("current_price"), risk)
        if reason is None:
            continue
        result = await paper_broker.close_position(str(position["id"]))
        closed_any = closed_any or result.get("error") is None
        report["closed"].append(
            {"market_id": position["market_id"], "reason": reason,
             "pnl": result.get("pnl"), "error": result.get("error")}
        )

    # 2. daily circuit breaker: realized loss today + open (unrealized) drawdown
    # Refresh after closes so a realized loss is not also counted as open drawdown.
    if closed_any:
        data = portfolio.get_portfolio()
    realized = realized_pnl_today()
    report["realized_today"] = realized
    unrealized = float(data["stats"].get("unrealized_pnl_usd") or 0)
    drawdown = daily_drawdown(realized, unrealized)
    halt_active = settings["halt"].get("active", False)
    today = supabase_client.today_utc()
    if drawdown <= -float(risk["daily_loss_halt_usd"]) and not halt_active:
        supabase_client.update_agent_settings(
            {"halt": {
                "active": True,
                "reason": (
                    f"daily loss {realized:+.2f} realized "
                    f"{min(0.0, unrealized):+.2f} unrealized breached limit"
                ),
                "at": today,
            }}
        )
        report["halted"] = True
    elif halt_active and settings["halt"].get("at") and settings["halt"]["at"] < today:
        # a new day resets an automatic halt (manual resume also available in GUI)
        supabase_client.update_agent_settings({"halt": {"active": False, "reason": "", "at": ""}})

    # 3. equity snapshot (one row per UTC day, last write wins) — best-effort
    try:
        supabase_client.save_equity_snapshot(data["stats"])
    except Exception:  # noqa: BLE001 the curve must never block risk checks
        pass

    return report


def strategies_allowed() -> tuple[dict, bool]:
    """(strategy flags, trading_allowed) — jobs call this before trading."""
    settings = supabase_client.get_agent_settings()
    return settings["strategies"], not settings["halt"].get("active", False)


def tune_strategies(pnl_7d: dict[str, dict], strategies: dict) -> list[str]:
    """Disable autonomous strategies with a bad 7-day record. Mutates
    `strategies` in place and returns the actions taken. Needs both
    TUNE_MIN_TRADES of evidence and a TUNE_DISABLE_LOSS_USD loss; manual
    trades are never touched."""
    from backend import config

    actions = []
    for strategy, record in pnl_7d.items():
        if strategy in ("manual",) or strategy not in strategies:
            continue
        if not strategies.get(strategy):
            continue
        if record["trades"] >= config.TUNE_MIN_TRADES and record["pnl"] <= -config.TUNE_DISABLE_LOSS_USD:
            strategies[strategy] = False
            actions.append(
                f"disabled {strategy}: {record['pnl']:+.2f} over {record['trades']} trades in 7d"
            )
    return actions


def run_strategy_tuning() -> list[str]:
    """One tuning pass: read the 7-day per-strategy record, disable losers,
    persist. Runs on every risk-manager pass, no LLM involved."""
    settings = supabase_client.get_agent_settings()
    strategies = dict(settings["strategies"])
    actions = tune_strategies(supabase_client.strategy_pnl_7d(), strategies)
    if actions:
        supabase_client.update_agent_settings({"strategies": strategies})
    return actions
