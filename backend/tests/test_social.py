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


def test_relevant_subreddits_scopes_by_category():
    subs = social.relevant_subreddits("crypto")
    assert "CryptoCurrency" in subs and "PredictionMarkets" in subs
    assert len(subs) <= 6
    # unknown category still yields the general prediction-market subs
    assert social.relevant_subreddits("nonsense") == ["PredictionMarkets", "Polymarket"]


def test_parse_reddit_rss_normalizes_and_drops_empty():
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<entry><title>Fed likely to cut in September</title>"
        '<link href="https://www.reddit.com/r/Economics/comments/a/x/"/>'
        "<updated>2026-07-15T10:00:00+00:00</updated>"
        '<category term="Economics"/></entry>'
        '<entry><title></title><link href="https://x/y"/></entry>'  # empty title -> dropped
        "</feed>"
    )
    posts = social.parse_reddit_rss(xml, limit=10)
    assert len(posts) == 1
    assert posts[0]["source"] == "reddit"
    assert posts[0]["subreddit"] == "Economics"
    assert posts[0]["text"] == "Fed likely to cut in September"


def test_parse_reddit_rss_bad_xml_returns_empty():
    assert social.parse_reddit_rss("", limit=10) == []
    assert social.parse_reddit_rss("<not xml", limit=10) == []


def test_parse_reddit_search_extracts_subreddit_and_filters():
    results = [
        {"url": "https://www.reddit.com/r/Economics/comments/a/fed_cut/", "title": "Fed set to cut", "domain": "reddit.com"},
        {"url": "https://www.cnbc.com/x", "title": "not reddit", "domain": "cnbc.com"},  # dropped
        {"url": "https://www.reddit.com/user/someone", "title": "no subreddit", "domain": "reddit.com"},  # no /r/ -> dropped
    ]
    posts = social.parse_reddit_search(results, limit=10)
    assert len(posts) == 1
    assert posts[0]["source"] == "reddit"
    assert posts[0]["subreddit"] == "Economics"
    assert posts[0]["text"] == "Fed set to cut"


def test_subreddit_from_url():
    assert social._subreddit_from_url("https://www.reddit.com/r/CryptoCurrency/comments/x/") == "CryptoCurrency"
    assert social._subreddit_from_url("https://www.reddit.com/") == ""


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
