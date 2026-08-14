"""StrategyChat: natural-language Strategy Desk control + patch sanitizing."""

from __future__ import annotations

import copy

import pytest

from backend import config
from backend.agent import chat
from backend.data import supabase_client
from backend.tests.test_market_chat import _stub_llm  # noqa: F401  (helper)


# ---------------------------------------------------------------------------
# sanitize_settings_patch (pure)
# ---------------------------------------------------------------------------


def test_sanitize_clamps_and_whitelists():
    patch = supabase_client.sanitize_settings_patch(
        {
            "strategies": {"copy_trading": 1, "made_up": True},
            "risk": {"stop_loss_pct": 99999, "nonsense": 5, "take_profit_pct": "abc"},
            "funds": {"bankroll_usd": 5},
            "extra_section": {"x": 1},
        }
    )
    assert patch["strategies"] == {"copy_trading": True}
    assert patch["risk"] == {"stop_loss_pct": config.RISK_BOUNDS["stop_loss_pct"][1]}
    assert patch["funds"] == {"bankroll_usd": config.BANKROLL_BOUNDS[0]}
    assert "extra_section" not in patch


def test_sanitize_halt_activation_is_opt_in():
    raw = {"halt": {"active": True, "reason": "user said stop"}}
    assert supabase_client.sanitize_settings_patch(raw) == {}  # GUI path: resume only
    armed = supabase_client.sanitize_settings_patch(raw, allow_halt_activation=True)
    assert armed["halt"]["active"] is True
    assert armed["halt"]["reason"] == "user said stop"
    resumed = supabase_client.sanitize_settings_patch({"halt": {"active": False}})
    assert resumed["halt"] == {"active": False, "reason": "", "at": ""}


def test_sanitize_empty_and_garbage():
    assert supabase_client.sanitize_settings_patch({}) == {}
    assert supabase_client.sanitize_settings_patch(
        {"strategies": "on", "risk": 5, "halt": {"active": "yes"}}
    ) == {}


def test_sanitize_rejects_non_finite_numbers_and_string_booleans():
    patch = supabase_client.sanitize_settings_patch(
        {
            "strategies": {"copy_trading": "false"},
            "risk": {"stop_loss_pct": float("nan")},
            "funds": {"bankroll_usd": float("inf")},
        }
    )
    assert patch == {}


# ---------------------------------------------------------------------------
# _settings_diff (pure)
# ---------------------------------------------------------------------------


def test_settings_diff_reports_only_changes():
    before = copy.deepcopy(config.DEFAULT_AGENT_SETTINGS)
    after = copy.deepcopy(before)
    after["strategies"]["copy_trading"] = True
    after["risk"]["stop_loss_pct"] = 30
    diff = chat._settings_diff(before, after)
    assert diff == {
        "strategies.copy_trading": {"from": False, "to": True},
        "risk.stop_loss_pct": {"from": 50, "to": 30},
    }
    assert chat._settings_diff(before, before) == {}


# ---------------------------------------------------------------------------
# strategy_chat (LLM + storage stubbed)
# ---------------------------------------------------------------------------


@pytest.fixture
def desk_state(monkeypatch):
    """In-memory agent settings + quiet portfolio/risk reads."""
    state = {"settings": copy.deepcopy(config.DEFAULT_AGENT_SETTINGS)}

    def fake_get():
        return copy.deepcopy(state["settings"])

    def fake_update(patch):
        merged = copy.deepcopy(state["settings"])
        for section, values in patch.items():
            merged.setdefault(section, {}).update(values)
        state["settings"] = merged
        return copy.deepcopy(merged)

    monkeypatch.setattr(supabase_client, "get_agent_settings", fake_get)
    monkeypatch.setattr(supabase_client, "update_agent_settings", fake_update)
    monkeypatch.setattr(
        "backend.sim.portfolio.get_portfolio",
        lambda: {"open": [], "resolved": [], "stats": {"bankroll_usd": 10_000}},
    )
    monkeypatch.setattr("backend.sim.risk.realized_pnl_today", lambda: 0.0)
    return state


@pytest.mark.asyncio
async def test_instruction_applies_patch(monkeypatch, desk_state):
    calls = _stub_llm(
        monkeypatch,
        [{"reply": "Turning copy trading off.", "patch": {"strategies": {"copy_trading": False}}}],
    )
    desk_state["settings"]["strategies"]["copy_trading"] = True

    result = await chat.strategy_chat("turn off copy trading", [])
    assert result["error"] is None
    assert result["applied"] == {"strategies.copy_trading": {"from": True, "to": False}}
    assert result["settings"]["strategies"]["copy_trading"] is False
    assert desk_state["settings"]["strategies"]["copy_trading"] is False
    assert "**Applied:**" in result["answer"]
    # context reached the model: settings + bounds + the question
    assert "copy_trading" in calls[0]["user"]
    assert "stop_loss_pct" in calls[0]["user"]


@pytest.mark.asyncio
async def test_question_changes_nothing(monkeypatch, desk_state):
    _stub_llm(monkeypatch, [{"reply": "Stop loss is 50%.", "patch": None}])
    before = copy.deepcopy(desk_state["settings"])

    result = await chat.strategy_chat("what is my stop loss?", [])
    assert result["applied"] is None
    assert result["settings"] is None
    assert desk_state["settings"] == before
    assert result["answer"] == "Stop loss is 50%."


@pytest.mark.asyncio
async def test_out_of_bounds_patch_is_clamped(monkeypatch, desk_state):
    _stub_llm(
        monkeypatch,
        [{"reply": "Setting max position.", "patch": {"risk": {"max_position_usd": 999_999}}}],
    )
    result = await chat.strategy_chat("set max position to a million", [])
    hi = config.RISK_BOUNDS["max_position_usd"][1]
    assert result["applied"] == {"risk.max_position_usd": {"from": 500, "to": hi}}
    assert desk_state["settings"]["risk"]["max_position_usd"] == hi


@pytest.mark.asyncio
async def test_halt_instruction_arms_breaker(monkeypatch, desk_state):
    _stub_llm(monkeypatch, [{"reply": "Halting all trading.", "patch": {"halt": {"active": True}}}])
    result = await chat.strategy_chat("halt everything now", [])
    assert result["applied"]["halt.active"] == {"from": False, "to": True}
    assert desk_state["settings"]["halt"]["active"] is True


@pytest.mark.asyncio
async def test_invalid_patch_keys_do_not_apply(monkeypatch, desk_state):
    _stub_llm(
        monkeypatch,
        [{"reply": "Doing something odd.", "patch": {"secret": {"admin": True}}}],
    )
    before = copy.deepcopy(desk_state["settings"])
    result = await chat.strategy_chat("do something odd", [])
    assert result["applied"] is None
    assert desk_state["settings"] == before
    assert "no change applied" in result["answer"]


@pytest.mark.asyncio
async def test_empty_question_rejected(desk_state):
    result = await chat.strategy_chat("   ", [])
    assert result["error"] == "empty question"


@pytest.mark.asyncio
async def test_llm_failure_degrades(monkeypatch, desk_state):
    async def boom(self, module, system_prompt, user_prompt):
        raise RuntimeError("gateway down")

    from backend.llm.client import RunContext

    monkeypatch.setattr(RunContext, "call_llm", boom)
    result = await chat.strategy_chat("turn off arbitrage", [])
    assert result["answer"] is None
    assert "chat call failed" in result["error"]


def test_registry_lists_strategy_chat():
    assert "StrategyChat" in config.CANONICAL_MODULES
    assert (config.PROMPTS_DIR / "strategy_chat.txt").exists()
