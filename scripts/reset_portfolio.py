"""Safely preview or reset all paper-portfolio state in Supabase.

Preview (the default):
    python -m scripts.reset_portfolio

Apply the reset:
    python -m scripts.reset_portfolio --confirm RESET

This intentionally preserves watchlists, followed wallets, cached research,
agent runs, strategy toggles, and risk settings.
"""

from __future__ import annotations

import argparse

from backend import config
from backend.data import supabase_client


TABLE_KEYS = {
    "mirrored_trades": "id",
    "mm_quotes": "id",
    "equity_snapshots": "day",
    "positions": "id",
}


def _missing_table(exc: Exception) -> bool:
    return "PGRST205" in str(exc) or "Could not find the table" in str(exc)


def row_counts(client) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for table, key in TABLE_KEYS.items():
        try:
            response = client.table(table).select(key, count="exact").limit(1).execute()
            counts[table] = int(response.count or 0)
        except Exception as exc:
            if not _missing_table(exc):
                raise
            # Older project schemas may predate optional quote/equity tables.
            # There is nothing in a missing table to clear, so report it rather
            # than making the safe preview unusable.
            counts[table] = None
    return counts


def reset(client, available_tables: set[str]) -> None:
    # PostgREST requires a filter on DELETE. These predicates match every valid
    # row while avoiding a dangerously unfiltered request.
    zero_uuid = "00000000-0000-0000-0000-000000000000"
    if "mirrored_trades" in available_tables:
        client.table("mirrored_trades").delete().neq("id", zero_uuid).execute()
    if "mm_quotes" in available_tables:
        client.table("mm_quotes").delete().neq("id", zero_uuid).execute()
    if "equity_snapshots" in available_tables:
        client.table("equity_snapshots").delete().gte("day", "0001-01-01").execute()
    if "positions" in available_tables:
        client.table("positions").delete().neq("id", zero_uuid).execute()
    supabase_client.update_agent_settings(
        {
            "funds": {"bankroll_usd": config.PAPER_BANKROLL_USD},
            "halt": {"active": False, "reason": "", "at": ""},
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm",
        help="Pass the exact word RESET to permanently clear paper-portfolio state.",
    )
    args = parser.parse_args()

    if not supabase_client.is_configured():
        raise SystemExit("Supabase is not configured; no persistent portfolio exists to reset.")

    client = supabase_client.get_client()
    before = row_counts(client)
    print("Paper-portfolio rows:")
    for table, count in before.items():
        display = "table not installed" if count is None else str(count)
        print(f"  {table}: {display}")
    print(f"  bankroll after reset: ${config.PAPER_BANKROLL_USD:,.2f}")

    if args.confirm != "RESET":
        print("Dry run only. Re-run with --confirm RESET to apply the reset.")
        return

    available = {table for table, count in before.items() if count is not None}
    reset(client, available)
    after = row_counts(client)
    remaining = {table: count for table, count in after.items() if count}
    if remaining:
        raise SystemExit(f"Reset was incomplete; remaining rows: {remaining}")
    print("Portfolio reset complete. Watchlists, research, and strategy settings were preserved.")


if __name__ == "__main__":
    main()
