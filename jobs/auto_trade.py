"""Autonomous trading loop — the agent manages its own paper book.

Every scheduled run: pick the most tradeable unanalyzed markets, run the
full intel pipeline with trading enabled, and let the deterministic pricing
engine decide (all PASS gates apply; a trade only opens on real net edge).
Caps protect the LLM quota and the book: AUTO_RUNS_PER_JOB and
AUTO_MIN_MID/AUTO_MAX_MID in config, max_open_positions from the
GUI-editable agent settings.

Usage:
    python -m jobs.auto_trade [--runs N] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend import config
from backend.agent import intel_cache
from backend.agent.orchestrator import run_pipeline
from backend.data import polymarket, supabase_client
from backend.llm import client as llm_client


def select_candidates(
    markets: list[dict],
    open_slugs: set[str],
    cached_slugs: set[str],
    limit: int,
) -> list[dict]:
    """Tradeable, unanalyzed markets, best first (pure; unit-tested)."""
    picked = []
    for m in markets:  # already sorted by 24h volume desc
        if m["slug"] in open_slugs or m["slug"] in cached_slugs:
            continue
        if not m.get("yes_token_id"):
            continue
        if not (config.AUTO_MIN_MID <= m["mid"] <= config.AUTO_MAX_MID):
            continue
        if m.get("spread") is not None and m["spread"] > config.MAX_SPREAD:
            continue
        picked.append(m)
        if len(picked) >= limit:
            break
    return picked


async def main_async(runs: int, dry_run: bool) -> None:
    if not dry_run:
        from jobs._preflight import require

        require("LLMOD_API_KEY", "LLMOD_BASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    if not llm_client.is_configured():
        print("LLM is not configured — aborting")
        return

    from backend.sim.risk import strategies_allowed

    strategies, allowed = strategies_allowed()
    if not strategies.get("ai_signal"):
        print("ai_signal strategy is disabled in agent settings — skipping")
        return
    settings = supabase_client.get_agent_settings()
    max_open = int(settings["risk"]["max_open_positions"])

    open_positions = supabase_client.get_open_positions()
    agent_open = {p["market_id"] for p in open_positions}
    at_cap = len(agent_open) >= max_open or not allowed
    if not allowed:
        print("circuit breaker active — analyzing without trading")
    trade_flag = "no" if at_cap else "yes"
    if at_cap and allowed:
        print(f"open positions at cap ({len(agent_open)}/{max_open}) — analyzing without trading")

    markets = await polymarket.get_trending_markets(50)
    cached = {m["slug"] for m in markets if intel_cache.get(m["slug"])}
    candidates = select_candidates(markets, agent_open, cached, runs)
    print(f"candidates: {[m['slug'] for m in candidates]}")

    if dry_run:
        print("dry run — no pipelines executed")
        return

    for m in candidates:
        prompt = f"Market: {m['slug']}\nFocus: all\nTrade: {trade_flag}"
        result = await run_pipeline(prompt)
        verdict = (result.ui or {}).get("verdict", {}).get("verdict") if result.ui else None
        fill = (result.ui or {}).get("fill") if result.ui else None
        print(
            f"  {m['slug']}: status={result.status} verdict={verdict} "
            f"traded={'yes' if fill else 'no'}"
            + (f" error={result.error}" if result.error else "")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=config.AUTO_RUNS_PER_JOB)
    parser.add_argument("--dry-run", action="store_true", help="pick candidates, run nothing")
    args = parser.parse_args()
    asyncio.run(main_async(args.runs, args.dry_run))


if __name__ == "__main__":
    main()
