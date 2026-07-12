"""Daily briefing — the agent accounts for itself (ONE LLM call/day).

Gathers hard numbers (book, PnL by strategy, yesterday's activity, agenda),
applies mechanical self-tuning (a strategy with a bad enough 7-day record
disables itself), then writes a short morning report. The report shows on
the Strategy Desk.

Usage:
    python -m jobs.daily_briefing [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json

from backend import config
from backend.data import supabase_client
from backend.llm import client as llm_client
from backend.sim.portfolio import get_portfolio
from backend.sim.risk import realized_pnl_today

BRIEFING_SYSTEM_PROMPT = (
    "You are the desk agent of Polymarkov, an educational paper-trading "
    "research system, writing your own concise morning briefing from the JSON "
    "facts provided. At most 220 words of markdown. Structure: one-line book "
    "status; what happened since yesterday (trades, settles, notable "
    "verdicts); what is on today's agenda; any self-tuning actions taken and "
    "why. Use ONLY the numbers given — never invent one. Plain, dry, honest; "
    'no hype, no advice. Return ONLY JSON: {"briefing": "<markdown report>"}'
)


def tune_strategies(pnl_7d: dict[str, dict], strategies: dict) -> list[str]:
    """Disable autonomous strategies with a clearly bad 7-day record (pure).
    Returns human-readable actions. Manual trades are never touched."""
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


def _mm_rewards_7d() -> float:
    """Simulated liquidity-rewards points earned by resting quotes (7d)."""
    if not supabase_client.is_configured():
        return 0.0
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    try:
        rows = (
            supabase_client.get_client()
            .table("mm_quotes")
            .select("reward_score")
            .gte("placed_at", cutoff)
            .execute()
            .data
            or []
        )
        return round(sum(float(r.get("reward_score") or 0) for r in rows), 2)
    except Exception:
        return 0.0


async def main_async(dry_run: bool) -> None:
    if not llm_client.is_configured():
        print("LLM is not configured — aborting")
        return

    settings = supabase_client.get_agent_settings()
    pnl_7d = supabase_client.strategy_pnl_7d()

    strategies = dict(settings["strategies"])
    actions = tune_strategies(pnl_7d, strategies)
    if actions and not dry_run:
        supabase_client.update_agent_settings({"strategies": strategies})

    portfolio = get_portfolio(scope="agent")
    facts = {
        "stats": portfolio["stats"],
        "realized_today_usd": realized_pnl_today(),
        "pnl_by_strategy_7d": pnl_7d,
        "open_positions": [
            {"market": p["market_id"], "side": p["side"], "size_usd": p["size_usd"],
             "unrealized": p.get("unrealized_pnl")}
            for p in portfolio["open"][:10]
        ],
        "pending_agenda": [
            {"market": a["market_id"], "reason": a["reason"], "priority": a["priority"]}
            for a in supabase_client.get_pending_agenda(limit=8)
        ],
        "strategies_enabled": strategies,
        "mm_reward_points_7d": _mm_rewards_7d(),
        "circuit_breaker": settings["halt"],
        "self_tuning_actions": actions,
        "analyses_used_today": supabase_client.analyses_today(),
        "analyses_budget": config.MAX_ANALYSES_PER_DAY,
    }

    if dry_run:
        print(json.dumps(facts, indent=1, default=str))
        return

    ctx = llm_client.RunContext()
    content = await ctx.call_llm("DeskBriefing", BRIEFING_SYSTEM_PROMPT, json.dumps(facts, default=str))
    # the model returns JSON-mode output; accept either a plain string or {"briefing": ...}
    if isinstance(content, dict):
        content = content.get("briefing") or content.get("report") or json.dumps(content)
    supabase_client.save_briefing(str(content), facts)
    print("briefing saved:\n")
    print(str(content)[:800])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print facts, no LLM call")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
