import json
from pathlib import Path

import pytest
import respx
from httpx import Response

from backend.data import polymarket

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8-sig"))


# ---------------------------------------------------------------------------
# normalize_market — Gamma stringified-array parsing (recorded fixture)
# ---------------------------------------------------------------------------


def test_normalize_market_parses_stringified_arrays():
    raw = load_fixture("gamma_markets.json")[0]
    m = polymarket.normalize_market(raw)

    assert isinstance(m["outcomes"], list) and m["outcomes"], "outcomes must parse to a list"
    assert all(isinstance(p, float) for p in m["outcome_prices"])
    assert m["yes_token_id"] and isinstance(m["yes_token_id"], str)
    assert 0.0 <= m["mid"] <= 1.0
    assert isinstance(m["volume24h"], float)
    assert m["category"]  # empty Gamma category falls back to event or "other"
    assert m["slug"]


def test_normalize_market_handles_garbage():
    m = polymarket.normalize_market(
        {"outcomes": "not json", "outcomePrices": None, "clobTokenIds": "[]"}
    )
    assert m["outcomes"] == []
    assert m["outcome_prices"] == []
    assert m["yes_token_id"] == ""
    assert m["mid"] == 0.5  # neutral default when nothing is known
    assert m["category"] == "other"


# ---------------------------------------------------------------------------
# parse_market_ref — URL/slug extraction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://polymarket.com/event/fed-decision/fed-cut-september-2026", "fed-cut-september-2026"),
        ("https://polymarket.com/event/fed-decision-in-september", "fed-decision-in-september"),
        ("check https://polymarket.com/market/some-market-slug?tid=1 please", "some-market-slug"),
        ("Market: exact-market-slug\nFocus: all\nTrade: no", "exact-market-slug"),
        ("exact-market-slug", "exact-market-slug"),
        ("no url here", None),
    ],
)
def test_parse_market_ref(text, expected):
    assert polymarket.parse_market_ref(text) == expected


def test_query_relevance_prefers_requested_event_child():
    query = "fed interest rates september 2026 meeting no change"
    no_change = "Will there be no change in Fed interest rates after the September 2026 meeting?"
    cut = "Will the Fed decrease interest rates by 25 bps after the September 2026 meeting?"
    assert polymarket._query_relevance(query, no_change) > polymarket._query_relevance(query, cut)


# ---------------------------------------------------------------------------
# walk_book — hand-computed VWAP / slippage on a synthetic book
# ---------------------------------------------------------------------------


def test_walk_book_two_levels_hand_computed():
    asks = [(0.50, 100.0), (0.55, 200.0)]  # notionals: $50, $110
    fill = polymarket.walk_book(asks, size_usd=80.0)

    # $50 buys 100 shares at 0.50; remaining $30 buys 30/0.55 shares at 0.55
    expected_shares = 100.0 + 30.0 / 0.55
    expected_vwap = 80.0 / expected_shares

    assert fill["filled_usd"] == 80.0
    assert fill["shares"] == pytest.approx(expected_shares, abs=1e-4)
    assert fill["vwap"] == pytest.approx(expected_vwap, abs=1e-6)
    assert fill["levels_consumed"] == 2
    assert fill["slippage_pts"] == pytest.approx(expected_vwap - 0.50, abs=1e-6)
    assert not fill["exhausted"]


def test_walk_book_single_level_no_slippage():
    fill = polymarket.walk_book([(0.40, 1000.0)], size_usd=100.0)
    assert fill["vwap"] == pytest.approx(0.40)
    assert fill["slippage_pts"] == 0.0
    assert fill["slippage_bps"] == 0.0


def test_walk_book_exhausts_thin_book():
    fill = polymarket.walk_book([(0.50, 10.0)], size_usd=100.0)  # only $5 resting
    assert fill["exhausted"]
    assert fill["filled_usd"] == pytest.approx(5.0)


def test_walk_book_empty_and_zero():
    assert polymarket.walk_book([], 100.0)["shares"] == 0.0
    assert polymarket.walk_book([(0.5, 10.0)], 0.0)["levels_consumed"] == 0


def test_walk_book_ignores_invalid_levels_and_non_finite_size():
    fill = polymarket.walk_book(
        [(0.0, 10.0), (float("nan"), 10.0), (0.5, -2.0), (0.6, 10.0)],
        3.0,
    )
    assert fill["vwap"] == pytest.approx(0.6)
    assert fill["levels_consumed"] == 1
    assert polymarket.walk_book([(0.5, 10.0)], float("nan"))["vwap"] is None


def test_depth_usd():
    assert polymarket.depth_usd([(0.50, 100.0), (0.60, 50.0)]) == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# get_order_book — sorts levels best-first regardless of API order (fixture)
# ---------------------------------------------------------------------------


@respx.mock
async def test_get_order_book_sorts_levels():
    raw = load_fixture("clob_book.json")
    respx.get("https://clob.polymarket.com/book").mock(return_value=Response(200, json=raw))

    book = await polymarket.get_order_book("tok123")

    ask_prices = [p for p, _ in book["asks"]]
    bid_prices = [p for p, _ in book["bids"]]
    assert ask_prices == sorted(ask_prices), "asks must be ascending (best first)"
    assert bid_prices == sorted(bid_prices, reverse=True), "bids must be descending (best first)"
    if ask_prices and bid_prices:
        assert bid_prices[0] < ask_prices[0], "book must not be crossed"


@respx.mock
async def test_get_price_history_parses_points():
    raw = load_fixture("price_history.json")
    respx.get("https://clob.polymarket.com/prices-history").mock(
        return_value=Response(200, json=raw)
    )
    history = await polymarket.get_price_history("tok123")
    assert len(history) == len(raw["history"])
    assert all(isinstance(t, float) and isinstance(p, float) for t, p in history)
