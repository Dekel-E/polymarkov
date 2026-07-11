"""Arbitrage scanner job — detect pricing violations and paper-trade them.

No LLM calls; pure order-book math. Scheduled with the other automation.

Usage:
    python -m jobs.scan_arbitrage [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio

from backend.sim import arbitrage


async def main_async(dry_run: bool) -> None:
    from backend.sim.risk import strategies_allowed

    strategies, allowed = strategies_allowed()
    if not strategies.get("arbitrage"):
        print("arbitrage strategy is disabled in agent settings — skipping")
        return
    if not allowed:
        dry_run = True
        print("circuit breaker active — scan only, no execution")

    opportunities = await arbitrage.scan()
    print(f"scan complete: {len(opportunities)} opportunit{'y' if len(opportunities) == 1 else 'ies'}")
    for opp in opportunities:
        print(
            f"  [{opp['type']}] {opp['question'][:70]} | cost {opp['cost_per_share']} "
            f"-> profit {opp['profit_per_share']}/share ({opp['roi_pct']}%) "
            f"| up to ${opp['guaranteed_profit_usd']}"
        )
    if dry_run or not opportunities:
        return
    for opp in opportunities:
        reports = await arbitrage.execute_legs(opp)
        filled = sum(1 for r in reports if r["filled"])
        print(f"  executed {opp['type']}: {filled}/{len(reports)} legs filled")
        for r in reports:
            if not r["filled"]:
                print(f"    WARNING unfilled leg: {r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="detect only, trade nothing")
    args = parser.parse_args()
    asyncio.run(main_async(args.dry_run))


if __name__ == "__main__":
    main()
