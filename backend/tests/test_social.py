from datetime import datetime, timedelta, timezone

import respx
from httpx import Response

from backend.data import social

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


def _ts(hours_ago: float) -> datetime:
    return NOW - timedelta(hours=hours_ago)


def test_mention_velocity_basic():
    # 5 posts in last 24h, 12 posts across the prior 6 days (avg 2/day) -> 2.5
    timestamps = [_ts(h) for h in (1, 5, 10, 15, 23)] + [
        _ts(25 + i * 11) for i in range(12)  # hours 25..146, all in prior 6 days
    ]
    assert social.mention_velocity(timestamps, now=NOW) == 2.5


def test_mention_velocity_no_baseline_returns_none():
    # all posts are within the last 24h -> no prior-6-day baseline
    assert social.mention_velocity([_ts(2), _ts(3)], now=NOW) is None


def test_mention_velocity_empty():
    assert social.mention_velocity([], now=NOW) is None


async def test_reddit_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(social.config, "ENABLE_REDDIT", False)
    assert await social.fetch_reddit_posts("fed rate cut") == []


@respx.mock
async def test_polymarket_comments_parsed():
    respx.get("https://gamma-api.polymarket.com/comments").mock(
        return_value=Response(
            200,
            json=[
                {"body": "This is definitely happening", "createdAt": "2026-07-10T10:00:00Z"},
                {"body": "", "createdAt": "2026-07-10T09:00:00Z"},  # empty -> dropped
                {"body": "No way, priced wrong", "createdAt": "2026-07-09T08:00:00Z"},
            ],
        )
    )
    posts = await social.fetch_polymarket_comments("411239")
    assert len(posts) == 2
    assert posts[0]["source"] == "polymarket_comments"
    assert posts[0]["text"] == "This is definitely happening"


@respx.mock
async def test_polymarket_comments_degrade_on_error():
    respx.get("https://gamma-api.polymarket.com/comments").mock(return_value=Response(500))
    assert await social.fetch_polymarket_comments("411239") == []


async def test_gather_social_no_sources(monkeypatch):
    monkeypatch.setattr(social.config, "ENABLE_POLYMARKET_COMMENTS", False)
    monkeypatch.setattr(social.config, "ENABLE_BLUESKY", False)
    monkeypatch.setattr(social.config, "ENABLE_REDDIT", False)
    result = await social.gather_social("", "fed rate cut")
    assert result["posts"] == []
    assert result["mention_velocity"] is None
    assert "unavailable" in result["note"]
