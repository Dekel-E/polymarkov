import respx
from httpx import Response

from backend.data import gdelt, google_news

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>q - Google News</title>
<item>
  <title>Strait of Hormuz traffic rebounds as tensions ease - Reuters</title>
  <link>https://news.google.com/rss/articles/abc123</link>
  <pubDate>Fri, 10 Jul 2026 14:00:00 GMT</pubDate>
  <source url="https://www.reuters.com">Reuters</source>
</item>
<item>
  <title>Tanker insurance rates fall after strait reopening - Bloomberg</title>
  <link>https://news.google.com/rss/articles/def456</link>
  <pubDate>Thu, 09 Jul 2026 09:30:00 GMT</pubDate>
  <source url="https://www.bloomberg.com">Bloomberg</source>
</item>
<item><title>no link, dropped</title><link></link></item>
</channel></rss>"""


def test_parse_rss_normalizes():
    articles = google_news.parse_rss(RSS, max_records=10)
    assert len(articles) == 2
    assert articles[0]["title"] == "Strait of Hormuz traffic rebounds as tensions ease"
    assert articles[0]["domain"] == "reuters.com"
    assert articles[0]["published_at"].startswith("2026-07-10")
    assert articles[1]["domain"] == "bloomberg.com"


def test_parse_rss_respects_cap_and_garbage():
    assert len(google_news.parse_rss(RSS, max_records=1)) == 1
    assert google_news.parse_rss("not xml at all", 5) == []


@respx.mock
async def test_fetch_articles_queries_with_recency():
    route = respx.get(google_news.RSS_URL).mock(return_value=Response(200, text=RSS))
    articles = await google_news.fetch_articles("strait of hormuz", max_records=5)
    assert len(articles) == 2
    assert "when%3A7d" in str(route.calls[0].request.url)  # recency operator, url-encoded


RSS_RELEVANCE_ORDERED = RSS.replace(
    "<pubDate>Fri, 10 Jul 2026 14:00:00 GMT</pubDate>",
    "<pubDate>Mon, 06 Jul 2026 14:00:00 GMT</pubDate>",
)


@respx.mock
async def test_fetch_articles_resorts_newest_first():
    # Google puts a stale-but-relevant item first; we must not
    respx.get(google_news.RSS_URL).mock(return_value=Response(200, text=RSS_RELEVANCE_ORDERED))
    articles = await google_news.fetch_articles("q", max_records=5)
    assert articles[0]["published_at"].startswith("2026-07-09")  # the fresher one leads
    assert articles[1]["published_at"].startswith("2026-07-06")


@respx.mock
async def test_fetch_articles_degrades():
    respx.get(google_news.RSS_URL).mock(return_value=Response(503))
    assert await google_news.fetch_articles("anything") == []


def test_gdelt_query_is_english_only():
    assert gdelt._quote_query("strait of hormuz") == '"strait of hormuz" sourcelang:english'
    assert gdelt._quote_query("bitcoin") == "bitcoin sourcelang:english"
