import json
from pathlib import Path

import respx
from httpx import Response

from backend.data import gdelt

FIXTURES = Path(__file__).parent / "fixtures"
GDELT_FIXTURE = json.loads((FIXTURES / "gdelt_articles.json").read_text(encoding="utf-8-sig"))


def test_parse_seendate():
    assert gdelt.parse_seendate("20260709T143000Z") == "2026-07-09T14:30:00+00:00"
    assert gdelt.parse_seendate("not-a-date") is None
    assert gdelt.parse_seendate("") is None


def test_quote_query():
    assert gdelt._quote_query("fed rate cut") == '"fed rate cut"'
    assert gdelt._quote_query("bitcoin") == "bitcoin"
    assert gdelt._quote_query('"already quoted"') == '"already quoted"'


def test_extract_text_strips_markup():
    html = "<html><head><style>body{}</style><script>evil()</script></head><body><p>Hello <b>world</b></p></body></html>"
    assert gdelt.extract_text(html) == "Hello world"


def test_extract_text_truncates():
    assert len(gdelt.extract_text("<p>" + "x" * 5000 + "</p>", max_chars=100)) == 100


@respx.mock
async def test_fetch_articles_parses_and_drops_bad_rows():
    respx.get(gdelt.GDELT_URL).mock(return_value=Response(200, json=GDELT_FIXTURE))
    articles = await gdelt.fetch_articles("fed rate cut")
    # 4 rows in fixture, 1 has no url and must be dropped
    assert len(articles) == 3
    assert articles[0]["domain"] == "reuters.com"
    assert articles[0]["published_at"] == "2026-07-09T14:30:00+00:00"


@respx.mock
async def test_fetch_articles_retries_once_then_succeeds():
    route = respx.get(gdelt.GDELT_URL)
    route.side_effect = [Response(500), Response(200, json=GDELT_FIXTURE)]
    articles = await gdelt.fetch_articles("fed rate cut")
    assert len(articles) == 3
    assert route.call_count == 2


@respx.mock
async def test_fetch_articles_degrades_to_empty():
    respx.get(gdelt.GDELT_URL).mock(return_value=Response(500))
    assert await gdelt.fetch_articles("fed rate cut") == []


@respx.mock
async def test_fetch_articles_rate_limit_fails_fast_no_retry():
    route = respx.get(gdelt.GDELT_URL)
    route.mock(return_value=Response(429))
    assert await gdelt.fetch_articles("fed rate cut") == []
    assert route.call_count == 1  # a 429 is not retried


@respx.mock
async def test_fetch_articles_handles_garbage_body():
    respx.get(gdelt.GDELT_URL).mock(return_value=Response(200, text="<html>error page</html>"))
    assert await gdelt.fetch_articles("fed rate cut") == []
