import pytest

from backend import config
from backend.agent.report_card import brier, score_runs
from backend.data.smart_money import parse_leaderboard, parse_positions
from jobs.auto_trade import select_candidates


def mk(slug, mid=0.5, spread=0.02, token="tok", volume=1000.0):
    return {"slug": slug, "mid": mid, "spread": spread, "yes_token_id": token, "volume24h": volume}


# ---------------------------------------------------------------------------
# auto_trade candidate selection
# ---------------------------------------------------------------------------


def test_select_skips_open_cached_and_extreme():
    markets = [
        mk("already-open"),
        mk("already-cached"),
        mk("too-settled", mid=0.01),
        mk("too-certain", mid=0.99),
        mk("wide-spread", spread=0.2),
        mk("no-token", token=""),
        mk("good-one"),
        mk("good-two"),
    ]
    picked = select_candidates(markets, {"already-open"}, {"already-cached"}, limit=5)
    assert [m["slug"] for m in picked] == ["good-one", "good-two"]


def test_select_respects_limit_and_order():
    markets = [mk(f"m{i}") for i in range(10)]
    picked = select_candidates(markets, set(), set(), limit=3)
    assert [m["slug"] for m in picked] == ["m0", "m1", "m2"]  # volume order preserved


def test_select_allows_missing_spread():
    picked = select_candidates([mk("no-spread", spread=None)], set(), set(), 3)
    assert len(picked) == 1


# ---------------------------------------------------------------------------
# report card scoring
# ---------------------------------------------------------------------------


def test_brier():
    assert brier(1.0, 1) == 0.0
    assert brier(0.0, 1) == 1.0
    assert brier(0.7, 1) == pytest.approx(0.09)


def test_score_runs_compares_agent_vs_market():
    runs = [
        {"market_id": "a", "fair_prob": 0.8, "mid_at_run": 0.6},  # resolved YES
        {"market_id": "b", "fair_prob": 0.1, "mid_at_run": 0.3},  # resolved NO
        {"market_id": "unresolved", "fair_prob": 0.5, "mid_at_run": 0.5},
        {"market_id": "a", "fair_prob": None, "mid_at_run": 0.6},  # missing -> skipped
    ]
    result = score_runs(runs, {"a": 1, "b": 0})
    assert result["scored_runs"] == 2
    # agent: (0.2^2 + 0.1^2)/2 = 0.025 ; market: (0.4^2 + 0.3^2)/2 = 0.125
    assert result["agent_brier"] == pytest.approx(0.025)
    assert result["market_brier"] == pytest.approx(0.125)


def test_score_runs_none_when_nothing_resolved():
    assert score_runs([{"market_id": "x", "fair_prob": 0.5, "mid_at_run": 0.5}], {}) is None


# ---------------------------------------------------------------------------
# smart money parsing (defensive across API shape variants)
# ---------------------------------------------------------------------------


def test_parse_leaderboard_variants():
    rows = parse_leaderboard(
        [
            {"proxyWallet": "0xabc", "name": "whale", "pnl": "1234.5", "volume": 99},
            {"wallet": "0xdef", "amount": 55.5, "rank": 7},
            {"userName": "nobody-no-wallet"},  # dropped
        ]
    )
    assert len(rows) == 2
    assert rows[0] == {
        "rank": 1, "wallet": "0xabc", "name": "whale", "pnl": 1234.5,
        "volume": 99.0, "image": "", "verified": False,
    }
    assert rows[1]["rank"] == 7
    assert rows[1]["pnl"] == 55.5


def test_parse_positions_sorted_and_capped():
    rows = parse_positions(
        [
            {"title": "Small", "slug": "s", "currentValue": 10, "cashPnl": -1},
            {"title": "Big", "slug": "b", "currentValue": 500, "cashPnl": 20, "outcome": "Yes"},
        ],
        limit=1,
    )
    assert len(rows) == 1
    assert rows[0]["market"] == "Big"
    assert rows[0]["size_usd"] == 500.0
