"""Re-analyze watched markets whose cached dossier has expired (never trades).

Usage:
    python -m jobs.refresh_watchlist [--limit N] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend import config
from backend.agent import intel_cache
from backend.agent.orchestrator import run_pipeline
from backend.data import supabase_client
from backend.llm import client as llm_client


async def main_async(limit: int, dry_run: bool) -> None:
    if not dry_run:
        from jobs._preflight import require

        require("LLMOD_API_KEY", "LLMOD_BASE_URL", "SUPABASE_URL", "SUPABASE_SERVICE_KEY")
    if not llm_client.is_configured():
        print("LLM is not configured — aborting")
        return

    watched = supabase_client.distinct_watched_market_ids()
    stale = [slug for slug in watched if intel_cache.get(slug) is None][:limit]
    print(f"watched: {len(watched)} | stale: {len(stale)} -> {stale}")

    if dry_run:
        print("dry run — no pipelines executed")
        return

    for slug in stale:
        result = await run_pipeline(f"Market: {slug}\nFocus: all\nTrade: no")
        verdict = (result.ui or {}).get("verdict", {}).get("verdict") if result.ui else None
        print(f"  {slug}: status={result.status} verdict={verdict}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=config.WATCHLIST_RUNS_PER_JOB)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.limit, args.dry_run))


if __name__ == "__main__":
    main()
