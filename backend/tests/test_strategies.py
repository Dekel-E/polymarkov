import pytest

from backend import config
from backend.data.supabase_client import _merge_settings
from backend.sim.arbitrage import (
    dutch_book_opportunity,
    execute_legs,
    opportunity_signature,
    spread_opportunity,
)
from backend.sim.risk import evaluate_position


def market(slug="m1", category="politics", question="Q?"):
    return {"slug": slug, "category": category, "question": question, "event_title": ""}


# ---------------------------------------------------------------------------
# spread arbitrage: YES ask + NO ask < $1
# ---------------------------------------------------------------------------


def test_spread_arb_detected_with_fees():
    # 0.48 + 0.47 = 0.95; politics fees ~ 0.04*(0.48*0.52 + 0.47*0.53) ≈ 0.0199
    opp = spread_opportunity([(0.48, 100)], [(0.47, 200)], "politics", market())
    assert opp is not None
    assert opp["type"] == "spread"
    assert opp["cost_per_share"] == pytest.approx(0.95)
    expected_fees = 0.04 * (0.48 * 0.52) + 0.04 * (0.47 * 0.53)
    assert opp["fees_per_share"] == pytest.approx(expected_fees, abs=1e-4)
    assert opp["profit_per_share"] == pytest.approx(1 - 0.95 - expected_fees, abs=1e-4)
    assert opp["max_shares"] == 100  # limited by the thinner side
    assert {l["side"] for l in opp["legs"]} == {"BUY_YES", "BUY_NO"}


def test_spread_arb_rejected_when_fees_eat_it():
    # 0.995 total cost -> under $1 but fees make it unprofitable
    assert spread_opportunity([(0.50, 100)], [(0.495, 100)], "crypto", market()) is None


def test_spread_arb_rejected_at_fair_pricing():
    assert spread_opportunity([(0.52, 100)], [(0.49, 100)], "politics", market()) is None


def test_spread_arb_empty_book():
    assert spread_opportunity([], [(0.4, 10)], "politics", market()) is None


def test_spread_arb_respects_size_cap():
    opp = spread_opportunity([(0.40, 100000)], [(0.40, 100000)], "geopolitics", market())
    assert opp is not None
    assert max(l["size_usd"] for l in opp["legs"]) <= config.ARB_MAX_SIZE_USD


# ---------------------------------------------------------------------------
# dutch book: sum of YES asks across mutually exclusive outcomes < $1
# ---------------------------------------------------------------------------


def event(n):
    return {"title": "Who wins?", "markets": [market(slug=f"o{i}") for i in range(n)]}


def test_dutch_book_detected():
    e = event(3)
    asks = [(e["markets"][0], [(0.30, 50)]), (e["markets"][1], [(0.30, 80)]), (e["markets"][2], [(0.30, 60)])]
    opp = dutch_book_opportunity(e, asks)
    assert opp is not None
    assert opp["type"] == "dutch_book"
    assert opp["cost_per_share"] == pytest.approx(0.90)
    assert opp["max_shares"] == 50
    assert len(opp["legs"]) == 3


def test_dutch_book_requires_every_outcome_buyable():
    e = event(3)
    asks = [(e["markets"][0], [(0.30, 50)]), (e["markets"][1], []), (e["markets"][2], [(0.30, 60)])]
    assert dutch_book_opportunity(e, asks) is None
    # missing an outcome entirely -> not covered -> not an arb
    assert dutch_book_opportunity(e, asks[:2]) is None


def test_dutch_book_rejected_when_sum_at_or_above_one():
    e = event(2)
    asks = [(e["markets"][0], [(0.55, 50)]), (e["markets"][1], [(0.50, 50)])]
    assert dutch_book_opportunity(e, asks) is None


def test_opportunity_signature_ignores_leg_order_but_not_basket_kind():
    legs = [
        {"slug": "m", "side": "BUY_YES"},
        {"slug": "m", "side": "BUY_NO"},
    ]
    assert opportunity_signature({"type": "spread", "legs": legs}) == opportunity_signature(
        {"type": "spread", "legs": list(reversed(legs))}
    )
    assert opportunity_signature({"type": "spread", "legs": legs}) != opportunity_signature(
        {"type": "correlation", "legs": legs}
    )


@pytest.mark.asyncio
async def test_execute_legs_records_complete_basket_atomically(monkeypatch):
    from backend.data import polymarket, supabase_client

    async def fake_market(_slug):
        return {
            "yes_token_id": "yes", "no_token_id": "no", "category": "geopolitics",
            "mid": 0.5,
        }

    async def fake_book(token):
        return {"asks": [(0.4, 20.0)] if token == "yes" else [(0.45, 20.0)], "bids": []}

    written = []
    monkeypatch.setattr(polymarket, "get_market", fake_market)
    monkeypatch.setattr(polymarket, "get_order_book", fake_book)
    monkeypatch.setattr(
        supabase_client,
        "insert_positions",
        lambda rows: written.extend(rows) or ["p1", "p2"],
    )
    reports = await execute_legs(
        {
            "type": "spread", "max_shares": 10,
            "legs": [
                {"slug": "m", "side": "BUY_YES", "price": 0.4},
                {"slug": "m", "side": "BUY_NO", "price": 0.45},
            ],
        }
    )
    assert all(report["filled"] for report in reports)
    assert len(written) == 2
    assert {row["side"] for row in written} == {"BUY_YES", "BUY_NO"}


@pytest.mark.asyncio
async def test_execute_legs_writes_nothing_when_one_leg_is_too_thin(monkeypatch):
    from backend.data import polymarket, supabase_client

    async def fake_market(_slug):
        return {
            "yes_token_id": "yes", "no_token_id": "no", "category": "geopolitics",
            "mid": 0.5,
        }

    async def fake_book(token):
        size = 20.0 if token == "yes" else 2.0
        return {"asks": [(0.4, size)], "bids": []}

    writes = []
    monkeypatch.setattr(polymarket, "get_market", fake_market)
    monkeypatch.setattr(polymarket, "get_order_book", fake_book)
    monkeypatch.setattr(supabase_client, "insert_positions", lambda rows: writes.append(rows))
    reports = await execute_legs(
        {
            "type": "spread", "max_shares": 10,
            "legs": [
                {"slug": "m", "side": "BUY_YES", "price": 0.4},
                {"slug": "m", "side": "BUY_NO", "price": 0.4},
            ],
        }
    )
    assert not any(report["filled"] for report in reports)
    assert writes == []
    assert "no longer fillable" in reports[0]["error"]


# ---------------------------------------------------------------------------
# risk rules
# ---------------------------------------------------------------------------

RISK = {"stop_loss_pct": 50, "take_profit_pct": 100}


def pos(entry=0.50, size=100.0):
    return {"entry_price": entry, "size_usd": size}


def test_stop_loss_triggers():
    # entry 0.50, now 0.24 -> -52% of stake
    assert evaluate_position(pos(), 0.24, RISK) == "stop_loss"


def test_take_profit_triggers():
    # entry 0.30, now 0.65 -> +116%
    assert evaluate_position(pos(entry=0.30), 0.65, RISK) == "take_profit"


def test_hold_inside_bands():
    assert evaluate_position(pos(), 0.60, RISK) is None
    assert evaluate_position(pos(), 0.30, RISK) is None  # -40%, above the stop


def test_no_price_no_action():
    assert evaluate_position(pos(), None, RISK) is None
    assert evaluate_position(pos(entry=0.0), 0.5, RISK) is None


# ---------------------------------------------------------------------------
# settings merge
# ---------------------------------------------------------------------------


def test_merge_settings_two_levels():
    merged = _merge_settings(
        config.DEFAULT_AGENT_SETTINGS,
        {"strategies": {"copy_trading": True}, "risk": {"stop_loss_pct": 25}},
    )
    assert merged["strategies"]["copy_trading"] is True
    assert merged["strategies"]["ai_signal"] is True  # default preserved
    assert merged["risk"]["stop_loss_pct"] == 25
    assert merged["risk"]["max_open_positions"] == 10  # default preserved
    assert merged["halt"]["active"] is False


def test_merge_settings_empty_store_returns_defaults():
    assert _merge_settings(config.DEFAULT_AGENT_SETTINGS, {}) == config.DEFAULT_AGENT_SETTINGS
