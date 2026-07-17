"""RedditIndexer: parsing, dedup/entity tagging, warm-cache retrieval,
and LLM-free strategy self-tuning."""

from __future__ import annotations

import pytest

from backend.data import social, supabase_client
from jobs import index_social

# ---------------------------------------------------------------------------
# Reddit listing parsing (pure)
# ---------------------------------------------------------------------------

_CHILDREN = [
    {"data": {"title": "Fed will cut in September", "selftext": "sources say...",
              "permalink": "/r/economics/1", "created_utc": 1_750_000_000,
              "score": 42, "subreddit": "economics"}},
    {"data": {"title": "", "selftext": ""}},  # empty -> dropped
    {"data": {"title": "Another take", "selftext": "", "permalink": "/r/politics/2",
              "score": 3, "subreddit": "politics"}},
]


def test_parse_reddit_children_normalizes_and_drops_empty():
    posts = social.parse_reddit_children(_CHILDREN, limit=10)
    assert len(posts) == 2
    assert posts[0]["text"].startswith("Fed will cut")
    assert posts[0]["url"] == "https://www.reddit.com/r/economics/1"
    assert posts[0]["score"] == 42
    assert posts[0]["subreddit"] == "economics"
    assert posts[0]["created_at"] is not None
    assert posts[1]["created_at"] is None  # missing created_utc tolerated


def test_parse_reddit_children_respects_limit():
    assert len(social.parse_reddit_children(_CHILDREN, limit=1)) == 1


# ---------------------------------------------------------------------------
# collect_posts: dedup by url, merge entity tags across markets
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collect_posts_dedups_and_merges_entities(monkeypatch):
    shared = {"text": "Big Fed news", "url": "https://www.reddit.com/r/e/1",
              "source": "reddit", "created_at": None, "score": 5, "subreddit": "e"}

    async def fake_fetch(query, limit=15):
        return [dict(shared)]

    monkeypatch.setattr(social, "fetch_reddit_posts", fake_fetch)
    markets = [
        {"slug": "fed-cut-september", "question": "Fed cut in September?", "event_title": ""},
        {"slug": "fed-cut-december", "question": "Fed cut in December?", "event_title": ""},
    ]
    monkeypatch.setattr(index_social, "REDDIT_DELAY_S", 0)
    posts = await index_social.collect_posts(markets)
    assert len(posts) == 1  # same url from both searches -> one row
    assert posts[0]["entities"] == ["fed-cut-december", "fed-cut-september"]


def test_embed_pending_skips_when_unconfigured(monkeypatch):
    # without Pinecone/embeddings the embed pass is a graceful no-op —
    # stubbed, so the test never touches a live .env configuration
    monkeypatch.setattr(index_social.pinecone_client, "is_configured", lambda: False)
    assert index_social.embed_pending_posts() == 0


# ---------------------------------------------------------------------------
# SocialScanner tops up from the indexed cache
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scan_social_tops_up_from_indexed_cache(monkeypatch):
    from backend.agent import pipeline
    from backend.agent.types import QueryPlan
    from backend.llm.client import RunContext
    from backend.tests.test_market_chat import make_market

    async def thin_gather(event_id, query, limit=20):
        return {
            "posts": [{"text": "live post", "source": "reddit",
                       "url": "https://www.reddit.com/r/x/live", "created_at": None}],
            "mention_velocity": None,
            "note": "1 posts from reddit.",
        }

    monkeypatch.setattr(pipeline.social, "gather_social", thin_gather)
    monkeypatch.setattr(
        pipeline.supabase_client, "get_social_posts_for",
        lambda slug, limit=20: [
            {"text": "indexed post", "source": "reddit",
             "url": "https://www.reddit.com/r/x/indexed", "posted_at": None},
            {"text": "live post", "source": "reddit",  # same url as live -> deduped
             "url": "https://www.reddit.com/r/x/live", "posted_at": None},
        ],
    )
    plan = QueryPlan(in_scope=True, market_query="fed cut")
    pulse = await pipeline.scan_social(RunContext(), plan, make_market())
    texts = [p.text for p in pulse.posts]
    assert "live post" in texts and "indexed post" in texts
    assert len(pulse.posts) == 2  # dedup by url worked
    assert "indexed posts from the Reddit cache" in pulse.note


# ---------------------------------------------------------------------------
# strategy self-tuning runs without an LLM and persists
# ---------------------------------------------------------------------------


def test_run_strategy_tuning_disables_and_persists(monkeypatch):
    import copy

    from backend import config
    from backend.sim import risk

    state = {"settings": copy.deepcopy(config.DEFAULT_AGENT_SETTINGS), "written": None}
    state["settings"]["strategies"]["copy_trading"] = True

    monkeypatch.setattr(supabase_client, "get_agent_settings", lambda: copy.deepcopy(state["settings"]))
    monkeypatch.setattr(
        supabase_client, "strategy_pnl_7d",
        lambda: {"copy_trading": {"pnl": -80.0, "trades": 9},
                 "ai_signal": {"pnl": 12.0, "trades": 4}},
    )

    def fake_update(patch):
        state["written"] = patch
        return patch

    monkeypatch.setattr(supabase_client, "update_agent_settings", fake_update)
    actions = risk.run_strategy_tuning()
    assert actions == ["disabled copy_trading: -80.00 over 9 trades in 7d"]
    assert state["written"]["strategies"]["copy_trading"] is False
    assert state["written"]["strategies"]["ai_signal"] is True  # profitable one untouched


def test_run_strategy_tuning_no_action_no_write(monkeypatch):
    from backend.sim import risk

    monkeypatch.setattr(supabase_client, "strategy_pnl_7d", lambda: {})
    called = []
    monkeypatch.setattr(supabase_client, "update_agent_settings", lambda p: called.append(p))
    assert risk.run_strategy_tuning() == []
    assert not called
