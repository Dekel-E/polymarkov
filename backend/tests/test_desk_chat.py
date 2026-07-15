"""DeskChat routing + Kalshi cross-venue + helpful refusals + follow-ups."""

from __future__ import annotations

import pytest

from backend import config
from backend.agent import chat, orchestrator
from backend.agent.council import build_shared_context
from backend.data import kalshi, polymarket
from backend.llm.client import RunContext
from backend.tests.test_market_chat import make_market
from backend.tests.test_market_chat import _stub_llm  # noqa: F401  (helper)


# ---------------------------------------------------------------------------
# Kalshi matching (pure)
# ---------------------------------------------------------------------------

_KALSHI_BODY = {
    "current_page": [
        {
            "type": "contract",
            "series_ticker": "KXFEDDECISION",
            "series_title": "Fed meeting",
            "event_ticker": "KXFEDDECISION-26SEP",
            "event_title": "Fed decision in September?",
            "event_subtitle": "On Sep 16, 2026",
            "markets": [
                {"yes_subtitle": "Fed maintains rate", "yes_bid": 66, "yes_ask": 67, "last_price": 67},
                {"yes_subtitle": "Cut 25bps", "yes_bid": 4, "yes_ask": 5, "last_price": 4},
                {"yes_subtitle": "unpriced", "yes_bid": None, "yes_ask": None, "last_price": None},
            ],
        },
        {"type": "series", "series_title": "irrelevant"},
    ]
}


def test_kalshi_parse_matches_and_converts_cents():
    result = kalshi.parse_search(_KALSHI_BODY, "Will the Fed cut rates in September?")
    assert result is not None
    assert result["event_title"] == "Fed decision in September?"
    assert result["markets"][0] == {
        "outcome": "Fed maintains rate", "yes_bid": 0.66, "yes_ask": 0.67, "last_price": 0.67,
    }
    # unpriced outcomes are dropped
    assert all(m["outcome"] != "unpriced" for m in result["markets"])
    assert result["url"] == "https://kalshi.com/markets/kxfeddecision"


def test_kalshi_rejects_weak_matches():
    assert kalshi.parse_search(_KALSHI_BODY, "Will aliens land in Ohio tomorrow?") is None
    assert kalshi.match_score("", "anything") == 0.0


def test_cross_venue_block_reaches_council_context():
    venue = kalshi.parse_search(_KALSHI_BODY, "Fed decision in September?")
    text = build_shared_context(make_market(), [], __import__(
        "backend.agent.types", fromlist=["SocialPulse"]).SocialPulse(), [], cross_venue=venue)
    assert "CROSS-VENUE (Kalshi)" in text
    assert "Fed maintains rate: yes 66.0%/67.0%" in text


# ---------------------------------------------------------------------------
# helpful refusals
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_suggest_markets_formats_hits(monkeypatch):
    async def fake_search(query, limit=10):
        return [{"slug": "fed-cut-september", "question": "Fed cut in September?", "mid": 0.31}]

    monkeypatch.setattr(polymarket, "search_markets", fake_search)
    text = await orchestrator.suggest_markets(["fed", "rates"])
    assert "Fed cut in September?" in text
    assert "`Market: fed-cut-september`" in text
    assert "mid 31%" in text


@pytest.mark.asyncio
async def test_suggest_markets_empty_when_no_topic():
    assert await orchestrator.suggest_markets([], "") == ""


# ---------------------------------------------------------------------------
# follow-up history reaches the planner
# ---------------------------------------------------------------------------


def test_planner_input_includes_recent_turns():
    text = orchestrator._planner_input(
        "what about the resolution risk?",
        [{"role": "user", "content": "analyze the fed market"},
         {"role": "assistant", "content": "verdict PASS on fed-decision-in-september"}],
    )
    assert "PREVIOUS CONVERSATION" in text
    assert "fed-decision-in-september" in text
    assert text.endswith("what about the resolution risk?")
    # no history -> prompt passes through untouched
    assert orchestrator._planner_input("hi", []) == "hi"


# ---------------------------------------------------------------------------
# DeskChat routing (LLM + externals stubbed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_desk_chat_routes_meta(monkeypatch):
    _stub_llm(monkeypatch, [{"route": "meta"}])
    result = await chat.desk_chat("what can you do?", [])
    assert "What I CAN do" in result["answer"]
    assert result["error"] is None


@pytest.mark.asyncio
async def test_desk_chat_routes_market_to_market_chat(monkeypatch):
    _stub_llm(monkeypatch, [{"route": "market", "market_query": "fed cut"}])

    async def fake_search(query, limit=10):
        return [{"slug": "fed-cut", "question": "Fed cut?"}]

    async def fake_market_chat(slug, question, history):
        return {"answer": f"about {slug}", "citations": [], "error": None}

    monkeypatch.setattr(polymarket, "search_markets", fake_search)
    monkeypatch.setattr(chat, "market_chat", fake_market_chat)
    result = await chat.desk_chat("latest on the fed?", [])
    assert result["answer"] == "about fed-cut"
    assert result["market"] == {"slug": "fed-cut", "question": "Fed cut?"}


@pytest.mark.asyncio
async def test_desk_chat_routes_portfolio_with_facts(monkeypatch):
    calls = _stub_llm(
        monkeypatch,
        [{"route": "portfolio"}, {"answer": "You are up $12.50 on paper."}],
    )
    monkeypatch.setattr(
        chat, "_portfolio_facts",
        lambda: {"stats": {"realized_pnl_usd": 12.5}, "open_positions": []},
    )
    result = await chat.desk_chat("how is the portfolio doing?", [])
    assert result["answer"] == "You are up $12.50 on paper."
    assert "realized_pnl_usd" in calls[1]["user"]  # facts reached the answer call


@pytest.mark.asyncio
async def test_desk_chat_out_of_scope_suggests_markets(monkeypatch):
    _stub_llm(monkeypatch, [{
        "route": "out_of_scope", "reason": "I can't advise on stocks.",
        "topic_keywords": ["tesla"],
    }])

    async def fake_search(query, limit=10):
        assert query == "tesla"
        return [{"slug": "tesla-q3-delivery", "question": "Tesla Q3 deliveries above X?", "mid": 0.5}]

    monkeypatch.setattr(polymarket, "search_markets", fake_search)
    result = await chat.desk_chat("should I buy tesla stock?", [])
    assert "I can't advise on stocks." in result["answer"]
    assert "tesla-q3-delivery" in result["answer"]


@pytest.mark.asyncio
async def test_desk_chat_rejects_empty_question():
    result = await chat.desk_chat("  ", [])
    assert result["error"] == "empty question"


def test_config_lists_new_modules():
    assert "DeskChat" in config.CANONICAL_MODULES
    assert "CrossVenueScanner" in config.CANONICAL_MODULES
