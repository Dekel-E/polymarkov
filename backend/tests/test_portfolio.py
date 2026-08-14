import copy

import pytest

from backend import config
from backend.data import supabase_client
from backend.sim import paper_broker, portfolio, risk


def test_portfolio_fetches_all_pages_for_lifetime_stats():
    pages = [[{"id": str(i)} for i in range(2)], [{"id": "2"}]]

    class Query:
        def table(self, _name):
            return self

        def select(self, _fields):
            return self

        def order(self, _field, desc=False):
            return self

        def range(self, start, _end):
            self.start = start
            return self

        def execute(self):
            return type("Response", (), {"data": pages[self.start // 2]})()

    assert [row["id"] for row in portfolio._fetch_all_positions(Query(), page_size=2)] == ["0", "1", "2"]


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
async def test_live_refresh_marks_both_sides_and_recomputes_equity(monkeypatch):
    calls = []

    async def book(token_id: str):
        calls.append(token_id)
        return {"bids": [(0.59, 100)], "asks": [(0.61, 100)]}

    monkeypatch.setattr(portfolio.polymarket, "get_order_book", book)
    data = {
        "open": [
            {
                "market_id": "market",
                "side": "BUY_YES",
                "entry_price": 0.5,
                "size_usd": 100.0,
                "yes_token_id": "token",
                "current_price": 0.5,
                "unrealized_pnl": 0.0,
                "price_source": "cache",
            },
            {
                "market_id": "market",
                "side": "BUY_NO",
                "entry_price": 0.5,
                "size_usd": 50.0,
                "yes_token_id": "token",
                "current_price": 0.5,
                "unrealized_pnl": 0.0,
                "price_source": "cache",
            },
        ],
        "stats": {"balance_usd": 1_000.0, "open_fees_usd": 3.0},
    }

    await portfolio.refresh_open_prices(data)

    assert calls == ["token"]  # one CLOB request for both lots
    assert data["open"][0]["current_price"] == pytest.approx(0.6)
    assert data["open"][0]["unrealized_pnl"] == pytest.approx(20.0)
    assert data["open"][1]["current_price"] == pytest.approx(0.4)
    assert data["open"][1]["unrealized_pnl"] == pytest.approx(-10.0)
    assert all(row["price_source"] == "live" for row in data["open"])
    assert data["stats"]["unrealized_pnl_usd"] == pytest.approx(10.0)
    assert data["stats"]["equity_usd"] == pytest.approx(1_007.0)
    assert data["stats"]["live_price_positions"] == 2


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
