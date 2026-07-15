"""Agent UX behaviors: date awareness, self-explanation (meta intent), and
the Bluesky social source parser."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.agent import orchestrator
from backend.agent.modules import query_planner
from backend.agent.modules.council.base import time_context
from backend.agent.registry import MODULES
from backend.agent.types import QueryPlan
from backend.data.social import parse_bluesky_posts


# ---------------------------------------------------------------------------
# time context (the model does not know the current date)
# ---------------------------------------------------------------------------


def test_time_context_computes_days_to_resolution():
    now = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    line = time_context("2026-07-20T12:00:00Z", now=now)
    assert "Today: 2026-07-15" in line
    assert "Days to resolution: 5.0" in line


def test_time_context_handles_missing_or_bad_end_date():
    now = datetime(2026, 7, 15, tzinfo=timezone.utc)
    assert time_context(None, now=now) == "Today: 2026-07-15"
    assert time_context("not-a-date", now=now) == "Today: 2026-07-15"
    # past end dates clamp to 0, never negative
    assert "Days to resolution: 0.0" in time_context("2026-01-01T00:00:00Z", now=now)


# ---------------------------------------------------------------------------
# meta intent: the agent explains itself from the registry
# ---------------------------------------------------------------------------


def test_self_description_covers_role_and_limits():
    text = orchestrator.self_description()
    assert "What I CAN do" in text
    assert "What I CANNOT do" in text
    assert "paper" in text.lower() and "financial advice" in text.lower()
    # module names come from the registry, so they can never drift
    for m in MODULES:
        if m["kind"] in ("llm", "tool"):
            assert m["name"] in text


@pytest.mark.asyncio
async def test_meta_question_answers_without_running_the_pipeline(monkeypatch):
    async def fake_plan(ctx, user_prompt):
        return QueryPlan(in_scope=False, intent="meta")

    monkeypatch.setattr(query_planner, "plan_query", fake_plan)
    result = await orchestrator.run_pipeline("what can you do?")
    assert result.status == "ok"
    assert "What I CAN do" in (result.response or "")
    assert result.steps == []  # only the (mocked) planner ran — no other calls


def test_query_plan_intent_defaults_to_market():
    plan = QueryPlan(in_scope=True)  # old-style planner output without intent
    assert plan.intent == "market"


# ---------------------------------------------------------------------------
# Bluesky parsing (pure)
# ---------------------------------------------------------------------------


def test_parse_bluesky_posts():
    body = {
        "posts": [
            {
                "uri": "at://did:plc:abc/app.bsky.feed.post/3xyz",
                "author": {"handle": "trader.bsky.social"},
                "record": {"text": "Fed cutting in September", "createdAt": "2026-07-01T00:00:00Z"},
            },
            {"uri": "at://x/app.bsky.feed.post/1", "author": {}, "record": {"text": ""}},  # empty -> dropped
        ]
    }
    posts = parse_bluesky_posts(body, limit=5)
    assert len(posts) == 1
    assert posts[0]["source"] == "bluesky"
    assert posts[0]["text"] == "Fed cutting in September"
    assert posts[0]["url"] == "https://bsky.app/profile/trader.bsky.social/post/3xyz"
    assert posts[0]["created_at"] == "2026-07-01T00:00:00Z"


def test_parse_bluesky_posts_respects_limit_and_empty_body():
    body = {"posts": [{"uri": f"at://x/app.bsky.feed.post/{i}", "author": {"handle": "h"},
                       "record": {"text": f"post {i}"}} for i in range(10)]}
    assert len(parse_bluesky_posts(body, limit=4)) == 4
    assert parse_bluesky_posts({}, limit=4) == []
