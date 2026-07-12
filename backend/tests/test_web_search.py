import respx
from httpx import Response

from backend.data import web_search

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


def test_parse_results_unwraps_redirects_and_dedupes():
    results = web_search.parse_results(DDG_HTML, max_results=10)
    assert len(results) == 2
    assert results[0]["url"] == "https://www.reuters.com/hormuz-shipping"
    assert results[0]["title"] == "Hormuz shipping latest"  # tags stripped
    assert results[0]["domain"] == "reuters.com"
    assert results[1]["domain"] == "ft.com"


def test_parse_results_respects_cap_and_garbage():
    assert len(web_search.parse_results(DDG_HTML, max_results=1)) == 1
    assert web_search.parse_results("<html>no results here</html>", 5) == []


@respx.mock
async def test_search_degrades_on_error():
    respx.get(web_search.SEARCH_URL).mock(return_value=Response(503))
    assert await web_search.search("anything") == []


@respx.mock
async def test_search_returns_parsed():
    respx.get(web_search.SEARCH_URL).mock(return_value=Response(200, text=DDG_HTML))
    results = await web_search.search("strait of hormuz")
    assert len(results) == 2