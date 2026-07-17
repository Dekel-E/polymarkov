"""Risk manager job — stop-loss, take-profit, daily circuit breaker, and
strategy self-tuning (a strategy with a clearly bad 7-day record disables
itself — no LLM involved).

Runs FIRST in the automation schedule so breached positions are closed, the
breaker is armed, and losing strategies are cut before anything opens new
trades. Rules live in agent_settings (edited from the Strategy Desk GUI).

Usage:
    python -m jobs.manage_risk
"""

from __future__ import annotations

import asyncio

from backend.sim.risk import run_risk_checks, run_strategy_tuning


async def main_async() -> None:
    report = await run_risk_checks()
    print(f"realized PnL today: {report['realized_today']}")
    for closed in report["closed"]:
        print(f"  closed {closed['market_id']} ({closed['reason']}): pnl={closed['pnl']} err={closed['error']}")
    if report["halted"]:
        print("CIRCUIT BREAKER TRIPPED — all strategies halted for the rest of the day")

    actions = await asyncio.to_thread(run_strategy_tuning)
    for action in actions:
        print(f"self-tuning: {action}")
    if not report["closed"] and not report["halted"] and not actions:
        print("no action needed")


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
