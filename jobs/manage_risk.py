"""Risk manager job — stop-loss, take-profit, daily circuit breaker.

Runs FIRST in the automation schedule so breached positions are closed and
the breaker is armed before any strategy opens new trades. Rules live in
agent_settings (edited from the Strategy Desk GUI).

Usage:
    python -m jobs.manage_risk
"""

from __future__ import annotations

import asyncio

from backend.sim.risk import run_risk_checks


def main() -> None:
    report = asyncio.run(run_risk_checks())
    print(f"realized PnL today: {report['realized_today']}")
    for closed in report["closed"]:
        print(f"  closed {closed['market_id']} ({closed['reason']}): pnl={closed['pnl']} err={closed['error']}")
    if report["halted"]:
        print("CIRCUIT BREAKER TRIPPED — all strategies halted for the rest of the day")
    if not report["closed"] and not report["halted"]:
        print("no action needed")


if __name__ == "__main__":
    main()
