"""MarketChat + agent registry tests.

The chat flow is exercised with every external dependency stubbed: the LLM
(planner + answer), market state, dossier cache, news/web/social fetchers,
and the article indexer.
"""

from __future__ import annotations

import pytest

from backend import config
from backend.agent import chat, intel_cache
from backend.agent.registry import CANONICAL_MODULES, MODULES, PROMPT_FILES
from backend.agent.types import MarketState
from backend.data import news, polymarket, social, supabase_client
from backend.llm.client import RunContext


# ---------------------------------------------------------------------------
# Registry integrity
# ---------------------------------------------------------------------------


def test_registry_is_single_source_of_truth():
    names = [m["name"] for m in MODULES]
    assert names == CANONICAL_MODULES == config.CANONICAL_MODULES
    assert len(set(names)) == len(names), "module names must be unique"
    for m in MODULES:
        assert m["kind"] in ("llm", "tool", "job")
        assert m["description"] and m["implementation"]
        if m["kind"] == "llm":
            assert m["prompt_file"], f"LLM module {m['name']} needs a prompt file"


def test_every_prompt_file_exists():
    for stem in PROMPT_FILES:
        path = config.PROMPTS_DIR / f"{stem}.txt"
        assert path.exists(), f"missing prompt file: {path}"
        assert path.read_text(encoding="utf-8").strip()


def test_llm_prompt_files_match_registry():
    on_disk = {p.stem for p in config.PROMPTS_DIR.glob("*.txt")}
    assert set(PROMPT_FILES) <= on_disk


# ---------------------------------------------------------------------------
# Chat flow (fully stubbed)
# ---------------------------------------------------------------------------


def make_market(slug: str = "test-market") -> MarketState:
    return MarketState(
        question="Will X happen by 2027?",
        slug=slug,
        event_id="ev1",
        yes_token_id="tok",
        mid=0.42,
        best_bid=0.41,
        best_ask=0.43,
        spread=0.02,
        resolution_criteria="Resolves YES if X.",
    )


def _dossier_payload() -> dict:
    return {
        "response": "# dossier",
        "steps": [],
        "created_at": "2026-07-15T00:00:00+00:00",
        "ui": {
            "verdict": {"verdict": "PASS", "fair_probability": 0.45},
            "council": {"bull": {"thesis": "up"}},
            "news": [{"id": "c1", "headline": "X advances", "url": "https://n.ex/1", "source": "n.ex"}],
            "social": {"note": "quiet"},
            "market": make_market().model_dump(),
        },
    }


def _stub_llm(monkeypatch, responses: list[dict]) -> list[dict]:
    """RunContext.call_llm returns queued responses; records the calls."""
    calls: list[dict] = []

    async def fake_call(self, module, system_prompt, user_prompt):
        calls.append({"module": module, "system": system_prompt, "user": user_prompt})
        return responses[len(calls) - 1]

    monkeypatch.setattr(RunContext, "call_llm", fake_call)
    return calls


@pytest.fixture
def stub_world(monkeypatch):
    """Market resolves, dossier exists, all fetchers return canned data."""

    async def fake_state(slug):
        return make_market(slug)

    async def fake_gnews(query, max_records=10, days=7):
        return [{"url": "https://news.ex/a", "title": "Fresh A", "domain": "news.ex", "published_at": None}]

    async def fake_web(query, max_results=5):
        return [{"url": "https://web.ex/b", "title": "Fresh B", "domain": "web.ex", "published_at": None}]

    async def fake_rss(query, feeds, max_records=10):
        return [{"url": "https://bbc.ex/c", "title": "Fresh C", "domain": "bbc.ex", "published_at": None}]

    async def fake_wiki(query, max_records=3):
        return [{"url": "https://en.wikipedia.org/wiki/X", "title": "X", "domain": "en.wikipedia.org",
                 "published_at": None, "fetched_text": "Wikipedia intro about X."}]

    async def fake_social(event_id, query, limit=20):
        return {"posts": [{"text": "chatter", "source": "reddit", "url": "https://r.ex/p"}],
                "mention_velocity": 2.0, "note": "busy"}

    async def fake_text(url, max_chars=500):
        return "page text"

    monkeypatch.setattr(polymarket, "get_market_state", fake_state)
    monkeypatch.setattr(intel_cache, "get", lambda slug, max_age_s=None: _dossier_payload())
    monkeypatch.setattr(news, "google_news_articles", fake_gnews)
    monkeypatch.setattr(news, "web_search", fake_web)
    monkeypatch.setattr(news, "rss_articles", fake_rss)
    monkeypatch.setattr(news, "wikipedia_articles", fake_wiki)
    monkeypatch.setattr(social, "gather_social", fake_social)
    monkeypatch.setattr(news, "fetch_article_text", fake_text)
    monkeypatch.setattr(supabase_client, "get_social_posts_for", lambda slug, limit=20: [])
    indexed: list[list[dict]] = []
    monkeypatch.setattr(
        supabase_client, "upsert_articles", lambda articles: indexed.append(articles) or len(articles)
    )
    return indexed


@pytest.mark.asyncio
async def test_chat_gathers_indexes_and_cites(monkeypatch, stub_world):
    calls = _stub_llm(
        monkeypatch,
        [
            {"needs_fresh_intel": True, "news_queries": ["x latest"], "social_query": "x", "reason": "recent"},
            {"answer": "Latest: A happened.", "citations": [{"title": "Fresh A", "url": "https://news.ex/a"}]},
        ],
    )
    result = await chat.market_chat("test-market", "what's the latest news?", [])

    assert result["error"] is None
    assert result["answer"] == "Latest: A happened."
    assert result["citations"] == [{"title": "Fresh A", "url": "https://news.ex/a"}]
    assert result["gathered"]["searched"] is True
    assert result["gathered"]["articles"] == 4          # gnews + web + rss + wiki, deduped
    assert result["gathered"]["articles_indexed"] == 4  # indexed for the news pipeline
    assert result["gathered"]["social_posts"] == 1
    # gathered articles are tagged with the market slug for the indexer
    assert stub_world[0][0]["entities"] == ["test-market"]
    # both LLM calls belong to the canonical MarketChat module
    assert [c["module"] for c in calls] == ["MarketChat", "MarketChat"]
    # the answer call saw the fresh evidence and the dossier
    assert "news.ex/a" in calls[1]["user"] and "dossier" in calls[1]["user"]


@pytest.mark.asyncio
async def test_chat_skips_gathering_when_context_suffices(monkeypatch, stub_world):
    calls = _stub_llm(
        monkeypatch,
        [
            {"needs_fresh_intel": False, "news_queries": [], "social_query": None, "reason": "held data"},
            {"answer": "The spread is 2 points.", "citations": []},
        ],
    )
    result = await chat.market_chat("test-market", "what is the spread?", [])

    assert result["error"] is None
    assert result["gathered"]["searched"] is False
    assert result["gathered"]["articles"] == 0
    assert stub_world == []  # nothing indexed
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_chat_errors_without_market_or_dossier(monkeypatch):
    async def no_state(slug):
        return None

    monkeypatch.setattr(polymarket, "get_market_state", no_state)
    monkeypatch.setattr(intel_cache, "get", lambda slug, max_age_s=None: None)
    result = await chat.market_chat("ghost-market", "hi?", [])
    assert result["answer"] is None
    assert "no market found" in result["error"]


@pytest.mark.asyncio
async def test_chat_rejects_empty_question():
    result = await chat.market_chat("test-market", "   ", [])
    assert result["error"] == "empty question"
