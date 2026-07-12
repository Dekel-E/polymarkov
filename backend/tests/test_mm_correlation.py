import pytest

from backend import config
from backend.sim.correlation import (
    excludes_opportunity,
    implies_opportunity,
    normalize_classification,
)
from backend.sim.market_maker import eligible_to_quote, make_quote, quote_fills


def mk(slug="m", mid=0.5, token="tok"):
    return {"slug": slug, "mid": mid, "yes_token_id": token}


# ---------------------------------------------------------------------------
# market maker: quoting rules
# ---------------------------------------------------------------------------


def test_eligible_to_quote_rules():
    assert eligible_to_quote(mk(), hours_to_end=500)
    assert not eligible_to_quote(mk(), hours_to_end=24)  # too close to resolution
    assert not eligible_to_quote(mk(mid=0.05), hours_to_end=500)  # extreme odds
    assert not eligible_to_quote(mk(token=""), hours_to_end=500)  # no book
    assert eligible_to_quote(mk(), hours_to_end=None)  # unknown end date -> allowed


def test_make_quote_symmetric_when_flat():
    bid, ask = make_quote(0.50, inventory_usd=0)
    assert bid == pytest.approx(0.50 - config.MM_HALF_SPREAD)
    assert ask == pytest.approx(0.50 + config.MM_HALF_SPREAD)


def test_make_quote_skews_against_inventory():
    flat_bid, flat_ask = make_quote(0.50, 0)
    long_bid, long_ask = make_quote(0.50, config.MM_MAX_INVENTORY_USD)  # fully long
    assert long_bid < flat_bid  # harder to accumulate more
    assert long_ask < flat_ask  # easier to unload


def test_make_quote_refuses_degenerate_prices():
    assert make_quote(0.015, 0) is None  # bid would cross zero
    assert make_quote(0.99, 0) is None


# ---------------------------------------------------------------------------
# market maker: traded-through fill simulation
# ---------------------------------------------------------------------------


def test_quote_fills_traded_through():
    assert quote_fills(0.48, 0.52, [0.50, 0.47, 0.51]) == ["bid"]
    assert quote_fills(0.48, 0.52, [0.50, 0.53]) == ["ask"]
    assert quote_fills(0.48, 0.52, [0.47, 0.53]) == ["bid", "ask"]  # both sides -> spread captured
    assert quote_fills(0.48, 0.52, [0.50, 0.49, 0.51]) == []
    assert quote_fills(0.48, 0.52, []) == []
    assert quote_fills(0.48, 0.52, [0.48]) == ["bid"]  # touch counts


# ---------------------------------------------------------------------------
# correlation: violation math
# ---------------------------------------------------------------------------

REL = {
    "relation": "implies",
    "a_slug": "candidate-a-wins",
    "b_slug": "party-x-wins",
    "a_question": "Will Candidate A win?",
    "b_question": "Will Party X win?",
}


def test_implies_violation_detected():
    # A priced 0.62, B priced 0.51: BUY_YES B @0.52 + BUY_NO A @0.40 = 0.92
    opp = implies_opportunity(REL, b_yes_asks=[(0.52, 100)], a_no_asks=[(0.40, 100)])
    assert opp is not None
    assert opp["type"] == "correlation"
    assert opp["cost_per_share"] == pytest.approx(0.92)
    assert opp["profit_per_share"] > 0
    assert {(l["slug"], l["side"]) for l in opp["legs"]} == {
        ("party-x-wins", "BUY_YES"),
        ("candidate-a-wins", "BUY_NO"),
    }


def test_implies_consistent_pricing_is_not_flagged():
    # consistent: basket cost ~1.03 -> no free lunch
    assert implies_opportunity(REL, b_yes_asks=[(0.55, 100)], a_no_asks=[(0.48, 100)]) is None


def test_excludes_violation_detected():
    rel = dict(REL, relation="excludes")
    opp = excludes_opportunity(rel, a_no_asks=[(0.45, 100)], b_no_asks=[(0.45, 100)])
    assert opp is not None
    assert opp["cost_per_share"] == pytest.approx(0.90)
    assert all(l["side"] == "BUY_NO" for l in opp["legs"])


def test_missing_book_is_no_opportunity():
    assert implies_opportunity(REL, [], [(0.4, 10)]) is None


# ---------------------------------------------------------------------------
# correlation: classification normalization
# ---------------------------------------------------------------------------


def make_pair_markets():
    a = {"slug": "a", "question": "A?", "yes_token_id": "ay", "no_token_id": "an", "event_id": "1"}
    b = {"slug": "b", "question": "B?", "yes_token_id": "by", "no_token_id": "bn", "event_id": "2"}
    return [(a, b)]


def test_normalize_classification_orients_and_filters():
    pairs = make_pair_markets()
    rows = normalize_classification(
        pairs,
        {
            "pairs": [
                {"i": 0, "relation": "b_implies_a", "confidence": 0.9, "rationale": "B ⊂ A"},
            ]
        },
    )
    assert len(rows) == 1
    assert rows[0]["relation"] == "implies"
    assert rows[0]["a_slug"] == "b"  # antecedent normalized to A
    assert rows[0]["b_slug"] == "a"


def test_normalize_classification_drops_weak_and_none():
    pairs = make_pair_markets()
    rows = normalize_classification(
        pairs,
        {
            "pairs": [
                {"i": 0, "relation": "none", "confidence": 0.99},
                {"i": 0, "relation": "excludes", "confidence": 0.3},  # below floor
                {"i": 5, "relation": "excludes", "confidence": 0.9},  # bad index
            ]
        },
    )
    assert rows == []