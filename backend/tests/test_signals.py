"""MicrostructureScanner (order-book/price indicators) + SmartMoneyScanner flow."""

from __future__ import annotations

from backend.agent import microstructure
from backend.agent.types import MarketState
from backend.data import smart_money


def _market(**kw) -> MarketState:
    base = dict(question="Q?", slug="m", yes_token_id="t", mid=0.50)
    base.update(kw)
    return MarketState(**base)


# --------------------------------------------------------------------------- #
# Microstructure
# --------------------------------------------------------------------------- #

def test_book_imbalance_and_micro_price():
    # heavy bid side within the band -> positive imbalance; micro-price > mid
    m = _market(
        mid=0.50,
        bids=[(0.49, 20000.0), (0.48, 10000.0)],  # ~$14.7k notional
        asks=[(0.51, 2000.0), (0.52, 1000.0)],    # ~$1.5k notional
    )
    ind = microstructure.book_indicators(m)
    assert ind["imbalance"] is not None and ind["imbalance"] > 0.5  # bid-heavy
    assert ind["micro_price"] is not None
    assert ind["bid_depth_5c_usd"] > ind["ask_depth_5c_usd"]


def test_book_empty_degrades():
    ind = microstructure.book_indicators(_market(bids=[], asks=[]))
    assert ind["imbalance"] is None and ind["micro_price"] is None


def test_price_technicals_trend_and_momentum():
    # steadily rising series over ~2 days
    hist = [(1_000_000 + i * 3600, 0.40 + i * 0.01) for i in range(12)]
    m = _market(price_history_7d=hist)
    tech = microstructure.price_technicals(m)
    assert tech["trend"] == "up"
    assert tech["momentum_7d_pts"] is not None and tech["momentum_7d_pts"] > 0
    assert tech["rsi"] is None or 0 <= tech["rsi"] <= 100


def test_compute_and_summarize_run_on_thin_data():
    ind = microstructure.compute(_market())
    assert "imbalance" in ind and "trend" in ind
    assert isinstance(microstructure.summarize(ind), str)


# --------------------------------------------------------------------------- #
# Smart money
# --------------------------------------------------------------------------- #

def test_yes_lean_direction():
    assert smart_money._yes_lean("BUY", "Yes", 100) == 100      # buy yes -> +yes
    assert smart_money._yes_lean("SELL", "Yes", 100) == -100    # sell yes -> -yes
    assert smart_money._yes_lean("BUY", "No", 100) == -100      # buy no -> -yes
    assert smart_money._yes_lean("SELL", "No", 100) == 100      # sell no -> +yes
    assert smart_money._yes_lean("BUY", "Cut 25bps", 100) == 0  # multi-outcome -> neutral


def test_aggregate_market_flow_matches_followed_and_top_and_whales():
    trades = [
        {"wallet": "0xAAA", "side": "BUY", "outcome": "Yes", "notional_usd": 15000.0, "timestamp": 5},
        {"wallet": "0xBBB", "side": "BUY", "outcome": "No", "notional_usd": 3000.0, "timestamp": 4},
        {"wallet": "0xCCC", "side": "SELL", "outcome": "Yes", "notional_usd": 500.0, "timestamp": 3},
    ]
    followed = [{"wallet": "0xaaa", "label": "SharpWhale"}]
    top = [{"wallet": "0xBBB", "name": "TopTrader", "rank": 2}]

    flow = smart_money.aggregate_market_flow(trades, followed, top, whale_usd=10_000.0)

    assert len(flow["followed_active"]) == 1
    assert flow["followed_active"][0]["label"] == "SharpWhale"
    assert flow["followed_active"][0]["side"] == "YES"
    assert len(flow["top_active"]) == 1
    assert flow["top_active"][0]["side"] == "NO"  # bought No
    assert len(flow["whale_prints"]) == 1  # only the $15k print
    assert "followed" in flow["note"]


def test_aggregate_empty_when_no_matches():
    flow = smart_money.aggregate_market_flow(
        [{"wallet": "0xZZZ", "side": "BUY", "outcome": "Yes", "notional_usd": 100.0, "timestamp": 1}],
        followed=[], top=[],
    )
    assert flow["followed_active"] == [] and flow["top_active"] == []
    assert "No tracked" in flow["note"]
