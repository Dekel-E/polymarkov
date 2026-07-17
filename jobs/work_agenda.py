"""Investigate the highest-priority agenda items with the intel pipeline. If a
market is held, recheck the thesis and close when fair value no longer supports
the entry; otherwise trade only on real edge. Budget and strategy guards apply.

Usage:
    python -m jobs.work_agenda [--items N] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from backend import config
from backend.agent.orchestrator import run_pipeline
from backend.data import supabase_client
from backend.llm import client as llm_client
from backend.sim import paper_broker
from backend.sim.risk import strategies_allowed


def thesis_broken(position: dict, new_fair: float) -> bool:
    """True when the fresh fair value no longer supports the position."""
    entry = float(position["entry_price"])
    if position["side"] == "BUY_YES":
        return new_fair <= entry
    return (1 - new_fair) <= entry  # BUY_NO holds the NO token at `entry`


async def handle_item(item: dict, held_by_slug: dict[str, dict], may_trade: bool) -> str:
    slug = item["market_id"]
    position = held_by_slug.get(slug)
    trade_flag = "yes" if (may_trade and position is None) else "no"

    result = await run_pipeline(f"Market: {slug}\nFocus: all\nTrade: {trade_flag}")
    if result.status != "ok" or not result.ui or not result.ui.get("verdict"):
        return f"analysis failed: {result.error or 'no verdict'}"

    verdict = result.ui["verdict"]
    outcome = f"verdict {verdict['verdict']} fair {verdict['fair_probability']:.2f}"
    if result.ui.get("fill"):
        outcome += f" — traded ${result.ui['fill']['size_usd']:.0f}"

    if position is not None and thesis_broken(position, float(verdict["fair_probability"])):
        closed = await paper_broker.close_position(str(position["id"]))
        if closed.get("error"):
            outcome += f" — thesis broken but close failed: {closed['error']}"
        else:
            outcome += f" — thesis broken, closed at pnl {closed['pnl']:+.2f}"
    return outcome


async def main_async(max_items: int, dry_run: bool) -> None:
    if not dry_run:
        from jobs._preflight import require

        require("LLMOD_API_KEY", "LLMOD_BASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    if not llm_client.is_configured():
        print("LLM is not configured — aborting")
        return

    used = supabase_client.analyses_today()
    if used >= config.MAX_ANALYSES_PER_DAY:
        print(f"daily analysis budget spent ({used}/{config.MAX_ANALYSES_PER_DAY}) — resting until tomorrow")
        return
    max_items = min(max_items, config.MAX_ANALYSES_PER_DAY - used)

    strategies, allowed = strategies_allowed()
    may_trade = allowed and strategies.get("ai_signal", False)
    if not may_trade:
        print("trading gated (strategy off or breaker active) — investigating without trading")

    items = supabase_client.get_pending_agenda(limit=max_items)
    if not items:
        print("agenda is clear")
        return
    print(f"working {len(items)} agenda item(s), budget {used}/{config.MAX_ANALYSES_PER_DAY} used")

    held_by_slug = {p["market_id"]: p for p in supabase_client.get_open_positions()}

    for item in items:
        print(f"  [{item['priority']}] {item['market_id'][:50]} — {item['reason']}")
        if dry_run:
            continue
        try:
            outcome = await handle_item(item, held_by_slug, may_trade)
            supabase_client.resolve_agenda_item(str(item["id"]), "done", outcome)
            print(f"    -> {outcome}")
        except Exception as exc:  # one bad item must not kill the loop
            supabase_client.resolve_agenda_item(str(item["id"]), "skipped", str(exc)[:200])
            print(f"    -> skipped: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=int, default=config.AGENDA_RUNS_PER_JOB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.items, args.dry_run))


if __name__ == "__main__":
    main()
