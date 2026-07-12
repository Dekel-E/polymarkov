from backend import config
from backend.sim.market_maker import needs_requote, reward_score
from jobs.copy_trade import proportional_size, wallet_gate
from jobs.sentinel import new_listing_items, news_lag_item, whale_print_items
from jobs.watch_live import price_jump_item, spread_violation_item

MARKET = {"slug": "m", "category": "politics"}


# ---------------------------------------------------------------------------
# news-lag detector
# ---------------------------------------------------------------------------


def test_news_lag_outranks_plain_burst():
    lag = news_lag_item("m", 5, one_day_change=0.01)   # news broke, price flat
    plain = news_lag_item("m", 5, one_day_change=0.15)  # price already moved
    unknown = news_lag_item("m", 5, one_day_change=None)
    assert "lag" in lag["reason"] and lag["priority"] > plain["priority"]
    assert "lag" not in plain["reason"]
    assert "lag" not in unknown["reason"]  # no price data -> no lag claim


# ---------------------------------------------------------------------------
# new-listing scanner
# ---------------------------------------------------------------------------


def test_new_listing_scanner(monkeypatch):
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)

    def mk(slug, hours_old, mid=0.5, token="t", life_h=200.0):
        return {
            "slug": slug, "mid": mid, "yes_token_id": token,
            "created_at": (now - timedelta(hours=hours_old)).isoformat(),
            "end_date": (now + timedelta(hours=life_h)).isoformat(),
        }

    items = new_listing_items(
        [
            mk("fresh", 2),
            mk("old", 100),
            mk("extreme", 3, mid=0.99),
            mk("no-book", 1, token=""),
            mk("micro-updown", 0.1, life_h=0.25),  # 15-min market -> excluded
        ],
        now=now,
    )
    assert [i["market_id"] for i in items] == ["fresh"]
    assert "early look" in items[0]["reason"]


def test_new_listing_scanner_caps_flood():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
    flood = [
        {
            "slug": f"m{i}", "mid": 0.5, "yes_token_id": "t",
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "end_date": (now + timedelta(hours=100)).isoformat(),
        }
        for i in range(10)
    ]
    assert len(new_listing_items(flood, now=now)) == config.SENTINEL_NEW_LISTING_MAX


# ---------------------------------------------------------------------------
# whale-print trigger
# ---------------------------------------------------------------------------


def test_whale_print_trigger():
    trades = {
        "big-market": [
            {"side": "BUY", "notional_usd": 25_000, "price": 0.4, "outcome": "Yes", "timestamp": 2000},
            {"side": "SELL", "notional_usd": 500, "price": 0.4, "outcome": "No", "timestamp": 2000},
        ],
        "quiet-market": [
            {"side": "BUY", "notional_usd": 900, "price": 0.5, "outcome": "Yes", "timestamp": 2000},
        ],
        "stale-whale": [
            {"side": "BUY", "notional_usd": 50_000, "price": 0.5, "outcome": "Yes", "timestamp": 100},
        ],
    }
    items = whale_print_items(trades, since_ts=1000)
    assert [i["market_id"] for i in items] == ["big-market"]
    assert "$25,000" in items[0]["reason"]


# ---------------------------------------------------------------------------
# live watcher tick handlers
# ---------------------------------------------------------------------------


def test_price_jump_item_thresholds():
    assert price_jump_item(MARKET, baseline=0.50, price=0.51) is None
    item = price_jump_item(MARKET, baseline=0.50, price=0.56)
    assert item is not None and item["priority"] > 70


def test_spread_violation_item():
    # 0.48 + 0.47 = 0.95 -> free money after fees
    item = spread_violation_item(MARKET, yes_ask=0.48, no_ask=0.47)
    assert item is not None and item["priority"] > 90
    # consistent book -> nothing
    assert spread_violation_item(MARKET, yes_ask=0.52, no_ask=0.49) is None


# ---------------------------------------------------------------------------
# proportional copy sizing + gate
# ---------------------------------------------------------------------------


def test_proportional_size_mirrors_conviction():
    # 20% of the whale's book -> 20% of our bankroll, capped
    assert proportional_size(20_000, 100_000, 10_000) == config.COPY_MAX_USD  # 2000 capped at 100
    assert proportional_size(300, 100_000, 10_000) == 30.0  # 0.3% -> $30
    assert proportional_size(10, 100_000, 10_000) == config.COPY_MIN_USD  # floor
    assert proportional_size(500, 0, 10_000) == config.COPY_MIN_USD  # degenerate whale book


def test_wallet_gate():
    assert wallet_gate([{"pnl": 100}, {"pnl": -20}])
    assert not wallet_gate([{"pnl": -100}, {"pnl": 20}])
    assert not wallet_gate([])  # nothing to judge -> don't copy


# ---------------------------------------------------------------------------
# MM rewards + drift
# ---------------------------------------------------------------------------


def test_reward_score_quadratic_in_closeness():
    tight = reward_score(0.50, bid=0.49, ask=0.51, size_usd=25)  # 1c away
    wide = reward_score(0.50, bid=0.475, ask=0.525, size_usd=25)  # 2.5c away
    assert tight > wide * 4  # quadratic: 1c earns >4x what 2.5c earns
    assert reward_score(0.50, bid=0.46, ask=0.54, size_usd=25) == 0  # outside band


def test_needs_requote():
    assert needs_requote(0.52, 0.50)
    assert not needs_requote(0.505, 0.50)
    assert not needs_requote(0.52, None)