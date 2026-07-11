import pytest

from jobs.resolve_positions import market_outcome, position_pnl


def pos(side="BUY_YES", entry=0.50, size=100.0, fee=1.0) -> dict:
    return {"id": "p1", "side": side, "entry_price": entry, "size_usd": size, "fee_paid": fee}


# ---------------------------------------------------------------------------
# position_pnl on fixtures (Phase 7 acceptance)
# ---------------------------------------------------------------------------


def test_buy_yes_wins():
    # $100 at 0.50 -> 200 shares -> $200 payout; minus stake and $1 fee = +$99
    assert position_pnl(pos(), "YES") == pytest.approx(99.0)


def test_buy_yes_loses():
    assert position_pnl(pos(), "NO") == pytest.approx(-101.0)


def test_buy_no_wins():
    # entry is the NO token price
    assert position_pnl(pos(side="BUY_NO", entry=0.40, size=80.0, fee=0.5), "NO") == pytest.approx(
        80.0 / 0.40 - 80.0 - 0.5
    )


def test_buy_no_loses():
    assert position_pnl(pos(side="BUY_NO", entry=0.40, size=80.0, fee=0.5), "YES") == pytest.approx(-80.5)


def test_zero_entry_price_is_safe():
    assert position_pnl(pos(entry=0.0), "YES") == pytest.approx(-101.0)


# ---------------------------------------------------------------------------
# market_outcome
# ---------------------------------------------------------------------------


def test_market_outcome_yes_no_and_unresolved():
    closed = {"active": False, "outcome_prices": [1.0, 0.0]}
    assert market_outcome(closed) == "YES"
    assert market_outcome({"active": False, "outcome_prices": [0.005, 0.995]}) == "NO"
    assert market_outcome({"active": True, "outcome_prices": [1.0, 0.0]}) is None  # still active
    assert market_outcome({"active": False, "outcome_prices": [0.6, 0.4]}) is None  # not settled
    assert market_outcome({"active": False, "outcome_prices": []}) is None
