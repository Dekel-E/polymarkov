"""backend/data/news.py — GDELT, Google News RSS, DuckDuckGo web search."""

import json
from pathlib import Path

import respx
from httpx import Response

from backend.data import news

FIXTURES = Path(__file__).parent / "fixtures"
GDELT_FIXTURE = json.loads((FIXTURES / "gdelt_articles.json").read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------------------
# GDELT
# ---------------------------------------------------------------------------


def test_parse_seendate():
    assert news.parse_seendate("20260709T143000Z") == "2026-07-09T14:30:00+00:00"
    assert news.parse_seendate("not-a-date") is None
    assert news.parse_seendate("") is None


def test_quote_query_is_english_only():
    assert news._quote_query("fed rate cut") == '"fed rate cut" sourcelang:english'
    assert news._quote_query("bitcoin") == "bitcoin sourcelang:english"
    assert news._quote_query('"already quoted"') == '"already quoted" sourcelang:english'


def test_extract_text_strips_markup():
    html = "<html><head><style>body{}</style><script>evil()</script></head><body><p>Hello <b>world</b></p></body></html>"
    assert news.extract_text(html) == "Hello world"


def test_extract_text_truncates():
    assert len(news.extract_text("<p>" + "x" * 5000 + "</p>", max_chars=100)) == 100


@respx.mock
async def test_gdelt_parses_and_drops_bad_rows():
    respx.get(news.GDELT_URL).mock(return_value=Response(200, json=GDELT_FIXTURE))
    articles = await news.gdelt_articles("fed rate cut")
    # 4 rows in fixture, 1 has no url and must be dropped
    assert len(articles) == 3
    assert articles[0]["domain"] == "reuters.com"
    assert articles[0]["published_at"] == "2026-07-09T14:30:00+00:00"


@respx.mock
async def test_gdelt_retries_once_then_succeeds():
    route = respx.get(news.GDELT_URL)
    route.side_effect = [Response(500), Response(200, json=GDELT_FIXTURE)]
    articles = await news.gdelt_articles("fed rate cut")
    assert len(articles) == 3
    assert route.call_count == 2


@respx.mock
async def test_gdelt_degrades_to_empty():
    respx.get(news.GDELT_URL).mock(return_value=Response(500))
    assert await news.gdelt_articles("fed rate cut") == []


@respx.mock
async def test_gdelt_rate_limit_fails_fast_no_retry():
    route = respx.get(news.GDELT_URL)
    route.mock(return_value=Response(429))
    assert await news.gdelt_articles("fed rate cut") == []
    assert route.call_count == 1  # a 429 is not retried


@respx.mock
async def test_gdelt_handles_garbage_body():
    respx.get(news.GDELT_URL).mock(return_value=Response(200, text="<html>error page</html>"))
    assert await news.gdelt_articles("fed rate cut") == []


# ---------------------------------------------------------------------------
# Google News RSS
# ---------------------------------------------------------------------------

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
    articles = news.parse_rss(RSS, max_records=10)
    assert len(articles) == 2
    assert articles[0]["title"] == "Strait of Hormuz traffic rebounds as tensions ease"
    assert articles[0]["domain"] == "reuters.com"
    assert articles[0]["published_at"].startswith("2026-07-10")
    assert articles[1]["domain"] == "bloomberg.com"


def test_parse_rss_respects_cap_and_garbage():
    assert len(news.parse_rss(RSS, max_records=1)) == 1
    assert news.parse_rss("not xml at all", 5) == []


@respx.mock
async def test_google_news_queries_with_recency():
    route = respx.get(news.RSS_URL).mock(return_value=Response(200, text=RSS))
    articles = await news.google_news_articles("strait of hormuz", max_records=5)
    assert len(articles) == 2
    assert "when%3A7d" in str(route.calls[0].request.url)  # recency operator, url-encoded


RSS_RELEVANCE_ORDERED = RSS.replace(
    "<pubDate>Fri, 10 Jul 2026 14:00:00 GMT</pubDate>",
    "<pubDate>Mon, 06 Jul 2026 14:00:00 GMT</pubDate>",
)


@respx.mock
async def test_google_news_resorts_newest_first():
    # Google puts a stale-but-relevant item first; we must not
    respx.get(news.RSS_URL).mock(return_value=Response(200, text=RSS_RELEVANCE_ORDERED))
    articles = await news.google_news_articles("q", max_records=5)
    assert articles[0]["published_at"].startswith("2026-07-09")  # the fresher one leads
    assert articles[1]["published_at"].startswith("2026-07-06")


@respx.mock
async def test_google_news_degrades():
    respx.get(news.RSS_URL).mock(return_value=Response(503))
    assert await news.google_news_articles("anything") == []


# ---------------------------------------------------------------------------
# Curated RSS feeds (generic RSS + Atom) + relevance filtering
# ---------------------------------------------------------------------------

FEED_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>BBC</title>
<item>
  <title>Fed holds interest rates steady amid inflation worries</title>
  <link>https://bbc.com/news/fed-holds</link>
  <description>The &lt;b&gt;Federal Reserve&lt;/b&gt; kept rates unchanged.</description>
  <pubDate>Fri, 10 Jul 2026 14:00:00 GMT</pubDate>
</item>
<item>
  <title>Local bakery wins award</title>
  <link>https://bbc.com/news/bakery</link>
  <description>A cake story.</description>
  <pubDate>Fri, 10 Jul 2026 09:00:00 GMT</pubDate>
</item>
</channel></rss>"""

FEED_ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
<entry>
  <title>Federal Reserve signals possible rate cut</title>
  <link rel="alternate" href="https://theverge.com/fed-cut"/>
  <summary>Fed officials discuss interest rate policy.</summary>
  <published>2026-07-11T08:00:00Z</published>
</entry>
</feed>"""


def test_parse_feed_handles_rss_and_atom():
    rss = news.parse_feed(FEED_RSS)
    assert [a["url"] for a in rss] == ["https://bbc.com/news/fed-holds", "https://bbc.com/news/bakery"]
    assert rss[0]["domain"] == "bbc.com"
    assert rss[0]["published_at"].startswith("2026-07-10")
    assert "Federal Reserve" in rss[0]["summary"]  # HTML stripped from description

    atom = news.parse_feed(FEED_ATOM)
    assert len(atom) == 1
    assert atom[0]["url"] == "https://theverge.com/fed-cut"  # href attribute, not element text
    assert atom[0]["published_at"].startswith("2026-07-11")  # ISO-8601 parsed


def test_parse_feed_garbage():
    assert news.parse_feed("<<not xml") == []


def test_query_terms_drops_stopwords_and_short():
    assert news.query_terms("Will the Fed cut rates in 2026?") == ["fed", "cut", "rates"]


def test_rss_feeds_for_dedups_general_and_category():
    feeds = news.rss_feeds_for("geopolitics", limit=10)
    assert len(feeds) == len(set(feeds))  # geopolitics reuses the general world feeds
    assert all(f.startswith("http") for f in feeds)


@respx.mock
async def test_rss_articles_filters_to_query_and_ranks(monkeypatch):
    respx.get("https://a.example/feed").mock(return_value=Response(200, text=FEED_RSS))
    respx.get("https://b.example/feed").mock(return_value=Response(200, text=FEED_ATOM))
    out = await news.rss_articles(
        "Fed interest rate decision", ["https://a.example/feed", "https://b.example/feed"]
    )
    urls = [a["url"] for a in out]
    # the off-topic bakery item is filtered out; the two Fed items survive
    assert "https://bbc.com/news/bakery" not in urls
    assert "https://bbc.com/news/fed-holds" in urls
    assert "https://theverge.com/fed-cut" in urls
    assert all("summary" not in a for a in out)  # summary dropped from output


@respx.mock
async def test_rss_articles_empty_query_returns_nothing():
    # no usable terms -> never dump unfiltered headlines
    assert await news.rss_articles("the a of", ["https://a.example/feed"]) == []


# ---------------------------------------------------------------------------
# Wikipedia (MediaWiki action API)
# ---------------------------------------------------------------------------

WIKI_BODY = {
    "query": {
        "pages": {
            "111": {"index": 2, "title": "Federal funds rate", "fullurl": "https://en.wikipedia.org/wiki/Federal_funds_rate",
                    "extract": "The federal funds rate is the interest rate..."},
            "222": {"index": 1, "title": "Federal Open Market Committee", "fullurl": "https://en.wikipedia.org/wiki/FOMC",
                    "extract": "The FOMC is a committee within the Federal Reserve..."},
            "333": {"index": 3, "title": "No extract page", "fullurl": "https://en.wikipedia.org/wiki/Empty", "extract": ""},
        }
    }
}


def test_parse_wiki_pages_orders_by_rank_and_drops_empty():
    rows = news.parse_wiki_pages(WIKI_BODY, max_records=5)
    assert [r["title"] for r in rows] == ["Federal Open Market Committee", "Federal funds rate"]
    assert rows[0]["domain"] == "en.wikipedia.org"
    assert rows[0]["fetched_text"].startswith("The FOMC")
    assert all("_idx" not in r for r in rows)  # internal ranking key stripped


@respx.mock
async def test_wikipedia_articles_fetches_and_parses():
    import json as _json

    respx.get(news.WIKI_API).mock(return_value=Response(200, text=_json.dumps(WIKI_BODY)))
    rows = await news.wikipedia_articles("federal reserve rate")
    assert rows[0]["title"] == "Federal Open Market Committee"
    assert rows[0]["published_at"] is None


@respx.mock
async def test_wikipedia_degrades_on_403():
    respx.get(news.WIKI_API).mock(return_value=Response(403, text="forbidden"))
    assert await news.wikipedia_articles("anything") == []


# ---------------------------------------------------------------------------
# DuckDuckGo web search
# ---------------------------------------------------------------------------

DDG_HTML = """
<div class="result">
  <a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Fhormuz-shipping&amp;rut=abc">
    Hormuz <b>shipping</b> latest
  </a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://www.ft.com/tanker-rates">Tanker rates surge</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a"
     href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.reuters.com%2Fhormuz-shipping">duplicate</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://duckduckgo.com/settings">not a result</a>
</div>
"""


def test_parse_web_results_unwraps_redirects_and_dedupes():
    results = news.parse_web_results(DDG_HTML, max_results=10)
    assert len(results) == 2
    assert results[0]["url"] == "https://www.reuters.com/hormuz-shipping"
    assert results[0]["title"] == "Hormuz shipping latest"  # tags stripped
    assert results[0]["domain"] == "reuters.com"
    assert results[1]["domain"] == "ft.com"


def test_parse_web_results_respects_cap_and_garbage():
    assert len(news.parse_web_results(DDG_HTML, max_results=1)) == 1
    assert news.parse_web_results("<html>no results here</html>", 5) == []


@respx.mock
async def test_web_search_degrades_on_error():
    respx.get(news.SEARCH_URL).mock(return_value=Response(503))
    assert await news.web_search("anything") == []


@respx.mock
async def test_web_search_returns_parsed():
    respx.get(news.SEARCH_URL).mock(return_value=Response(200, text=DDG_HTML))
    results = await news.web_search("strait of hormuz")
    assert len(results) == 2
