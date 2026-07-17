"""Autopilot — run the WHOLE autonomous desk locally in one process.

GitHub Actions runs these jobs on cron once the repo is pushed with
secrets; until then (or on a VPS/your PC instead), this daemon replicates
every cadence. Each job runs as a subprocess (`python -m jobs.X`) so one
crash or hang never takes the desk down, in a fixed order per tick:
protection first, then perception, then trading.

Cadences (defaults):
  30 min  manage_risk           stop-loss / take-profit / breaker / self-tuning
  60 min  sentinel              perception -> agenda items (no LLM)
  60 min  work_agenda           investigate agenda by priority (LLM, budgeted)
  60 min  market_maker          settle resting quotes, requote
   2 h    index_markets         markets -> Supabase + Pinecone
   2 h    index_news            GDELT news -> Supabase + Pinecone
   2 h    index_social          Reddit posts -> Supabase + Pinecone
   4 h    auto_trade            trending scan -> full pipeline -> paper trades
   4 h    refresh_watchlist     re-analyze stale watched markets
   4 h    scan_arbitrage        books scan -> execute risk-free baskets
   4 h    copy_trade            mirror followed profitable wallets
  24 h    resolve_positions     settle resolved markets -> precedents
  24 h    build_relations       correlation graph refresh (1 LLM call)
  24 h    daily_briefing        morning report + tuning report (1 LLM call)

Every job is skipped gracefully by its own guards when its strategy toggle
is off, the circuit breaker is tripped, or its services aren't configured.

Usage:
    python -m jobs.autopilot [--once] [--dry-run]

  --once     run every job a single time, in order, then exit
  --dry-run  pass --dry-run to every job (no writes, no trades)

Tip: run `python -m jobs.watch_live` alongside for the real-time sense.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from datetime import datetime, timezone

JOB_TIMEOUT_S = 15 * 60  # no single job may hold the loop hostage
TICK_S = 60

# (module, interval_seconds) — order = execution order within a tick:
# protection -> indexing -> perception -> decisions -> trading -> accounting
SCHEDULE: list[tuple[str, int]] = [
    ("jobs.manage_risk", 30 * 60),
    ("jobs.index_markets", 2 * 3600),
    ("jobs.index_news", 2 * 3600),
    ("jobs.index_social", 2 * 3600),
    ("jobs.sentinel", 3600),
    ("jobs.work_agenda", 3600),
    ("jobs.market_maker", 3600),
    ("jobs.auto_trade", 4 * 3600),
    ("jobs.refresh_watchlist", 4 * 3600),
    ("jobs.scan_arbitrage", 4 * 3600),
    ("jobs.copy_trade", 4 * 3600),
    ("jobs.resolve_positions", 24 * 3600),
    ("jobs.build_relations", 24 * 3600),
    ("jobs.daily_briefing", 24 * 3600),
]


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


# jobs with no --dry-run flag (they always write) — skipped in dry-run mode
NO_DRY_RUN = {"jobs.manage_risk"}


async def run_job(module: str, dry_run: bool) -> None:
    """One job as a subprocess: prefixed output, hard timeout, crash-proof."""
    name = module.rsplit(".", 1)[-1]
    if dry_run and module in NO_DRY_RUN:
        print(f"[{_stamp()}] {name}: skipped (always writes; no dry-run mode)")
        return
    args = [sys.executable, "-m", module] + (["--dry-run"] if dry_run else [])
    print(f"[{_stamp()}] ── {name} ──")
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=JOB_TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            print(f"[{_stamp()}] {name}: KILLED after {JOB_TIMEOUT_S // 60} min")
            return
        for line in (out or b"").decode("utf-8", errors="replace").splitlines():
            if line.strip():
                print(f"  {line}")
        if proc.returncode != 0:
            print(f"[{_stamp()}] {name}: exited {proc.returncode} (continuing)")
    except Exception as exc:  # noqa: BLE001 — the daemon must survive anything
        print(f"[{_stamp()}] {name}: failed to launch ({exc})")


async def run_loop(once: bool, dry_run: bool) -> None:
    last_run: dict[str, float] = {}  # module -> monotonic ts; empty = all due
    print(f"autopilot up — {len(SCHEDULE)} jobs on schedule, Ctrl+C to stop")
    while True:
        for module, interval in SCHEDULE:
            if time.monotonic() - last_run.get(module, float("-inf")) >= interval:
                await run_job(module, dry_run)
                last_run[module] = time.monotonic()
        if once:
            print("single pass complete")
            return
        await asyncio.sleep(TICK_S)


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="one full pass, then exit")
    parser.add_argument("--dry-run", action="store_true", help="pass --dry-run to every job")
    args = parser.parse_args()
    try:
        asyncio.run(run_loop(args.once, args.dry_run))
    except KeyboardInterrupt:
        print("\nautopilot stopped")


if __name__ == "__main__":
    main()
