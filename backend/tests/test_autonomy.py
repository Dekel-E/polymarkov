from datetime import datetime, timedelta, timezone

from backend import config
from jobs.daily_briefing import tune_strategies
from jobs.sentinel import near_resolution_items, position_risk_items, price_move_items
from jobs.work_agenda import thesis_broken

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)


def mk(slug, mid=0.5, change=0.0, end_hours=1000):
    return {
        "slug": slug,
        "mid": mid,
        "one_day_change": change,
        "end_date": (NOW + timedelta(hours=end_hours)).isoformat(),
        "question": f"{slug}?",
    }


# ---------------------------------------------------------------------------
# sentinel triggers
# ---------------------------------------------------------------------------


def test_price_move_trigger():
    items = price_move_items(
        [mk("mover", change=0.12), mk("quiet", change=0.02), mk("settled", mid=0.99, change=0.2), mk("no-data", change=None)]
    )
    assert [i["market_id"] for i in items] == ["mover"]
    assert "moved +12 pts" in items[0]["reason"]


def test_position_risk_trigger():
    positions = [
        {"market_id": "hurting", "side": "BUY_YES", "entry_price": 0.50},
        {"market_id": "fine", "side": "BUY_YES", "entry_price": 0.50},
        {"market_id": "no-price", "side": "BUY_NO", "entry_price": 0.40},
    ]
    items = position_risk_items(positions, {"hurting": 0.35, "fine": 0.48})
    assert [i["market_id"] for i in items] == ["hurting"]
    assert items[0]["priority"] > 50  # book protection outranks curiosity


def test_position_risk_no_side_semantics():
    # BUY_NO at 0.40: NO now worth 1-0.75 = 0.25 -> 15 pts adverse -> trigger
    items = position_risk_items(
        [{"market_id": "m", "side": "BUY_NO", "entry_price": 0.40}], {"m": 0.75}
    )
    assert len(items) == 1


def test_near_resolution_only_tracked():
    markets = [mk("soon-held", end_hours=24), mk("soon-ignored", end_hours=24), mk("far-held", end_hours=500)]
    items = near_resolution_items(markets, tracked={"soon-held", "far-held"}, now=NOW)
    assert [i["market_id"] for i in items] == ["soon-held"]


# ---------------------------------------------------------------------------
# thesis-based exits
# ---------------------------------------------------------------------------


def test_thesis_broken_yes_side():
    pos = {"side": "BUY_YES", "entry_price": 0.30}
    assert thesis_broken(pos, new_fair=0.25)  # fair fell to/below entry
    assert thesis_broken(pos, new_fair=0.30)
    assert not thesis_broken(pos, new_fair=0.40)


def test_thesis_broken_no_side():
    pos = {"side": "BUY_NO", "entry_price": 0.40}  # NO token bought at 0.40
    assert thesis_broken(pos, new_fair=0.65)  # NO fair value 0.35 <= 0.40
    assert not thesis_broken(pos, new_fair=0.50)  # NO worth 0.50 > 0.40


# ---------------------------------------------------------------------------
# self-tuning
# ---------------------------------------------------------------------------


def test_tune_disables_losing_strategy():
    strategies = {"ai_signal": True, "arbitrage": True, "copy_trading": True}
    actions = tune_strategies(
        {
            "ai_signal": {"pnl": -80.0, "trades": 6},
            "arbitrage": {"pnl": -80.0, "trades": 2},  # too few trades -> untouched
            "copy_trading": {"pnl": 20.0, "trades": 10},
            "manual": {"pnl": -500.0, "trades": 20},  # never touched
        },
        strategies,
    )
    assert strategies["ai_signal"] is False
    assert strategies["arbitrage"] is True
    assert strategies["copy_trading"] is True
    assert len(actions) == 1 and "ai_signal" in actions[0]


def test_tune_skips_already_disabled():
    strategies = {"ai_signal": False, "arbitrage": True, "copy_trading": False}
    actions = tune_strategies({"ai_signal": {"pnl": -999, "trades": 99}}, strategies)
    assert actions == []


# ---------------------------------------------------------------------------
# agent_info course schema
# ---------------------------------------------------------------------------


def test_agent_info_matches_course_schema():
    from api.index import agent_info

    info = agent_info()
    assert isinstance(info["prompt_template"], dict)
    assert "template" in info["prompt_template"]
    assert isinstance(info["prompt_examples"], list)
    for example in info["prompt_examples"]:
        assert set(example) >= {"prompt", "full_response", "steps"}
    assert info["description"] and info["purpose"]