import copy

import pytest

from backend import config
from backend.data import supabase_client
from backend.sim import paper_broker, portfolio, risk


def test_portfolio_stats_include_open_entry_fees(monkeypatch):
    monkeypatch.setattr(supabase_client, "current_bankroll", lambda: 1_000.0)
    stats = portfolio._stats(
        [
            {
                "size_usd": 100.0,
                "fee_paid": 2.5,
                "unrealized_pnl": 10.0,
                "strategy": "manual",
                "category": "politics",
            }
        ],
        [],
    )
    assert stats["open_fees_usd"] == 2.5
    assert stats["available_usd"] == 897.5
    assert stats["equity_usd"] == 1_007.5


@pytest.mark.asyncio
async def test_risk_refreshes_portfolio_after_closing_before_halt(monkeypatch):
    settings = copy.deepcopy(config.DEFAULT_AGENT_SETTINGS)
    settings["risk"]["daily_loss_halt_usd"] = 100
    initial = {
        "open": [
            {
                "id": "p1",
                "market_id": "market",
                "entry_price": 0.5,
                "size_usd": 100.0,
                "current_price": 0.1,
            }
        ],
        "stats": {"unrealized_pnl_usd": -80.0},
    }
    refreshed = {"open": [], "stats": {"unrealized_pnl_usd": 0.0}}
    portfolio_reads = iter([initial, refreshed])
    updates: list[dict] = []

    monkeypatch.setattr(supabase_client, "get_agent_settings", lambda: settings)
    monkeypatch.setattr(portfolio, "get_portfolio", lambda: next(portfolio_reads))
    monkeypatch.setattr(risk, "realized_pnl_today", lambda: -80.0)
    monkeypatch.setattr(supabase_client, "update_agent_settings", updates.append)
    monkeypatch.setattr(supabase_client, "save_equity_snapshot", lambda stats: None)

    async def fake_close(position_id: str):
        return {"error": None, "pnl": -80.0}

    monkeypatch.setattr(paper_broker, "close_position", fake_close)
    report = await risk.run_risk_checks()

    assert report["closed"][0]["pnl"] == -80.0
    assert report["halted"] is False
    assert updates == []
