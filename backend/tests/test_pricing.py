import pytest

from backend import config
from backend.agent import pricing
from backend.agent.types import EvidenceWeight, MarketState, PersonaOpinion


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def make_market(**overrides) -> MarketState:
    defaults = dict(
        question="Will the Fed cut rates in September?",
        slug="fed-cut-september",
        end_date="2026-09-30T00:00:00Z",
        resolution_criteria="Resolves YES if the FOMC lowers the target rate.",
        category="politics",
        yes_token_id="tok",
        mid=0.50,
        best_bid=0.49,
        best_ask=0.51,
        spread=0.02,
        depth_at_ask_usd=10_000.0,
        volume24h=1_000_000.0,
        price_history_7d=[],
    )
    defaults.update(overrides)
    return MarketState(**defaults)


def weight(eid="c1", direction="yes", strength=0.5, reliability=1.0, priced_in=0.0):
    return EvidenceWeight(
        evidence_id=eid,
        direction=direction,
        strength=strength,
        reliability=reliability,
        already_priced_in=priced_in,
        citation="https://example.com",
    )


def opinion(prob=0.55, weights=None, confidence="medium", red_flags=None):
    return PersonaOpinion(
        thesis="test thesis",
        evidence_weights=weights or [],
        estimated_probability=prob,
        confidence=confidence,
        red_flags=red_flags or [],
    )


def agreeing_council(weights_by_persona=None, prob=0.55):
    weights_by_persona = weights_by_persona or {}
    return {
        name: opinion(prob=prob, weights=weights_by_persona.get(name, []))
        for name in ("BullAnalyst", "BearAnalyst", "QuantAnalyst", "ResolutionSkeptic")
    }


def run(market=None, council=None, risk="low", clusters=4, **kwargs):
    return pricing.compute_pricing(
        market or make_market(),
        council if council is not None else agreeing_council(),
        resolution_risk=risk,
        n_evidence_clusters=clusters,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# logit / sigmoid
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("p", [0.02, 0.1, 0.25, 0.5, 0.75, 0.9, 0.98])
def test_logit_sigmoid_roundtrip(p):
    assert pricing.sigmoid(pricing.logit(p)) == pytest.approx(p, abs=1e-12)


def test_prior_is_clamped():
    result = run(market=make_market(mid=0.001))
    assert result.prior == config.PRIOR_CLAMP[0]


# ---------------------------------------------------------------------------
# Evidence aggregation
# ---------------------------------------------------------------------------


def test_already_priced_in_one_has_zero_effect():
    council = agreeing_council(
        {"BullAnalyst": [weight(strength=1.0, priced_in=1.0)]}
    )
    result = run(council=council)
    assert result.fair == pytest.approx(result.prior)
    assert result.gross_edge_pts == pytest.approx(0.0)
    assert result.verdict == "PASS"


def test_effective_weight_formula():
    # sign * strength * W_MAX * reliability * (1 - priced_in)
    council = {"BullAnalyst": opinion(weights=[weight(strength=0.5, reliability=0.8, priced_in=0.25)])}
    total = pricing.aggregate_evidence(council)
    assert total == pytest.approx(0.5 * config.W_MAX * 0.8 * 0.75)


def test_dedup_same_id_averages_not_sums():
    council = {
        "BullAnalyst": opinion(weights=[weight(eid="c1", strength=0.6)]),
        "QuantAnalyst": opinion(weights=[weight(eid="c1", strength=0.2)]),
    }
    total = pricing.aggregate_evidence(council)
    expected = (0.6 * config.W_MAX + 0.2 * config.W_MAX) / 2
    assert total == pytest.approx(expected)


def test_correlation_discount_within_cluster():
    council = {
        "BullAnalyst": opinion(
            weights=[weight(eid="a", strength=0.6), weight(eid="b", strength=0.4)]
        )
    }
    # same cluster: largest kept, next discounted by 0.5
    total = pricing.aggregate_evidence(council, cluster_of={"a": "c1", "b": "c1"})
    assert total == pytest.approx(0.6 * config.W_MAX + 0.4 * config.W_MAX * 0.5)
    # independent clusters (default): full sum
    total_indep = pricing.aggregate_evidence(council)
    assert total_indep == pytest.approx(0.6 * config.W_MAX + 0.4 * config.W_MAX)


def test_correlation_discount_third_item_quarter_weight():
    council = {
        "BullAnalyst": opinion(
            weights=[
                weight(eid="a", strength=1.0),
                weight(eid="b", strength=0.8),
                weight(eid="c", strength=0.6),
            ]
        )
    }
    total = pricing.aggregate_evidence(council, cluster_of={"a": "x", "b": "x", "c": "x"})
    w = config.W_MAX
    assert total == pytest.approx(1.0 * w + 0.8 * w * 0.5 + 0.6 * w * 0.25)


def test_total_update_cap_binds():
    council = {
        "BullAnalyst": opinion(
            weights=[weight(eid=f"c{i}", strength=1.0) for i in range(6)]  # 6 * 0.6 = 3.6
        )
    }
    assert pricing.aggregate_evidence(council) == config.TOTAL_UPDATE_CAP
    negative = {
        "BearAnalyst": opinion(
            weights=[weight(eid=f"c{i}", direction="no", strength=1.0) for i in range(6)]
        )
    }
    assert pricing.aggregate_evidence(negative) == -config.TOTAL_UPDATE_CAP


# ---------------------------------------------------------------------------
# Resolution haircut
# ---------------------------------------------------------------------------


def test_haircut_pulls_toward_prior():
    council = agreeing_council({"BullAnalyst": [weight(strength=1.0)]})
    low = run(council=council, risk="low")
    med = run(council=council, risk="medium")
    assert low.fair > low.prior  # evidence moved us up
    # medium haircut ends closer to the prior than low haircut
    assert abs(med.fair_adj - med.prior) < abs(low.fair_adj - low.prior)
    # exact formula: fair_adj = fair + (prior - fair) * min(1, h*6)
    h = config.RESOLUTION_HAIRCUT["medium"]
    expected = med.fair + (med.prior - med.fair) * min(1, h * config.HAIRCUT_MULTIPLIER)
    assert med.fair_adj == pytest.approx(expected, abs=2e-6)  # fields are rounded to 6dp


def test_high_risk_haircut_shrinks_90_percent():
    council = agreeing_council({"BullAnalyst": [weight(strength=1.0)]})
    result = run(council=council, risk="high")
    shrink = min(1, config.RESOLUTION_HAIRCUT["high"] * config.HAIRCUT_MULTIPLIER)
    assert shrink == pytest.approx(0.9)
    assert result.fair_adj == pytest.approx(result.fair + (result.prior - result.fair) * shrink)


# ---------------------------------------------------------------------------
# Fees
# ---------------------------------------------------------------------------


def test_taker_fee_peaks_at_half():
    fee_mid = pricing.taker_fee("politics", 0.5)
    assert fee_mid == pytest.approx(config.FEE_RATE["politics"] * 0.25)
    assert fee_mid > pricing.taker_fee("politics", 0.3)
    assert fee_mid > pricing.taker_fee("politics", 0.9)
    assert pricing.taker_fee("politics", 0.3) == pytest.approx(pricing.taker_fee("politics", 0.7))


def test_taker_fee_unknown_category_uses_other():
    assert pricing.taker_fee("nonsense", 0.5) == pytest.approx(config.FEE_RATE["other"] * 0.25)


def test_geopolitics_fee_is_zero():
    assert pricing.taker_fee("geopolitics", 0.5) == 0.0


# ---------------------------------------------------------------------------
# Verdicts — BUY paths and every PASS trigger
# ---------------------------------------------------------------------------


def strong_yes_council():
    return agreeing_council(
        {"BullAnalyst": [weight(strength=1.0)], "QuantAnalyst": [weight(eid="c2", strength=0.8)]},
        prob=0.62,
    )


def strong_no_council():
    return agreeing_council(
        {
            "BearAnalyst": [weight(direction="no", strength=1.0)],
            "QuantAnalyst": [weight(eid="c2", direction="no", strength=0.8)],
        },
        prob=0.38,
    )


def test_buy_yes_happy_path():
    result = run(council=strong_yes_council())
    assert result.verdict == "BUY_YES"
    assert result.gross_edge_pts > 0
    assert result.net_edge_pts > 0
    assert result.pass_reasons == []
    assert 0 < result.suggested_size_pct_bankroll <= config.MAX_SIZE_PCT_BANKROLL * 100


def test_pass_on_thin_depth():
    result = run(market=make_market(depth_at_ask_usd=500.0), council=strong_yes_council())
    assert result.verdict == "PASS"
    assert any("depth" in r for r in result.pass_reasons)


def test_buy_no_checks_no_side_depth():
    market = make_market(depth_at_ask_usd=50_000.0, depth_at_no_ask_usd=100.0)
    result = run(market=market, council=strong_no_council())
    assert result.verdict == "PASS"
    assert any("NO ask depth" in reason for reason in result.pass_reasons)


def test_buy_no_ignores_thin_yes_side_when_no_side_is_liquid():
    market = make_market(depth_at_ask_usd=100.0, depth_at_no_ask_usd=50_000.0)
    result = run(market=market, council=strong_no_council())
    assert not any("depth" in reason for reason in result.pass_reasons)


def test_pass_on_wide_spread():
    result = run(
        market=make_market(spread=0.12, best_bid=0.44, best_ask=0.56),
        council=strong_yes_council(),
    )
    assert result.verdict == "PASS"
    assert any("spread" in r for r in result.pass_reasons)


def test_pass_on_high_resolution_risk():
    result = run(council=strong_yes_council(), risk="high")
    assert result.verdict == "PASS"
    assert any("resolution risk" in r for r in result.pass_reasons)


def test_pass_on_council_disagreement():
    council = strong_yes_council()
    council["BearAnalyst"] = opinion(prob=0.30)
    council["BullAnalyst"].estimated_probability = 0.70
    result = run(council=council)
    assert result.verdict == "PASS"
    assert any("disagree" in r for r in result.pass_reasons)


def test_pass_on_too_few_evidence_clusters():
    result = run(council=strong_yes_council(), clusters=1)
    assert result.verdict == "PASS"
    assert any("clusters" in r for r in result.pass_reasons)


def test_pass_on_missing_order_book():
    result = run(
        market=make_market(best_bid=None, best_ask=None, spread=None, depth_at_ask_usd=0.0),
        council=strong_yes_council(),
    )
    assert result.verdict == "PASS"
    assert any("order book" in r for r in result.pass_reasons)


def test_pass_when_costs_eat_the_edge():
    # tiny evidence -> tiny gross edge; safety margin alone kills it
    council = agreeing_council({"BullAnalyst": [weight(strength=0.1, reliability=0.5)]})
    result = run(council=council)
    assert result.verdict == "PASS"
    assert any("net edge" in r for r in result.pass_reasons)


def test_slippage_reduces_net_edge():
    base = run(council=strong_yes_council())
    slipped = run(council=strong_yes_council(), slippage=0.03)
    assert slipped.net_edge_pts == pytest.approx(base.net_edge_pts - 0.03)


# ---------------------------------------------------------------------------
# Kelly sizing
# ---------------------------------------------------------------------------


def test_kelly_never_exceeds_cap():
    # absurdly favorable: fair 0.95, entry at 0.51
    assert pricing.kelly_size_pct(0.95, 0.51) == config.MAX_SIZE_PCT_BANKROLL * 100


def test_kelly_never_negative():
    assert pricing.kelly_size_pct(0.40, 0.51) == 0.0


def test_kelly_quarter_fraction_exact():
    fair, p_entry = 0.60, 0.50
    b = (1 - p_entry) / p_entry
    f_star = (fair * b - (1 - fair)) / b
    expected = min(config.KELLY_FRACTION * f_star, config.MAX_SIZE_PCT_BANKROLL) * 100
    assert pricing.kelly_size_pct(fair, p_entry) == pytest.approx(expected)


def test_kelly_invalid_entry_price():
    assert pricing.kelly_size_pct(0.6, 0.0) == 0.0
    assert pricing.kelly_size_pct(0.6, 1.0) == 0.0


# ---------------------------------------------------------------------------
# NO-side symmetry
# ---------------------------------------------------------------------------


def test_no_side_symmetry():
    yes_result = run(council=strong_yes_council())
    no_result = run(council=strong_no_council())

    assert yes_result.verdict == "BUY_YES"
    assert no_result.verdict == "BUY_NO"
    # mirrored market (mid 0.5): fair flips around 0.5, edges mirror, sizes match
    assert no_result.fair_adj == pytest.approx(1 - yes_result.fair_adj, abs=1e-9)
    assert no_result.gross_edge_pts == pytest.approx(-yes_result.gross_edge_pts, abs=1e-9)
    assert no_result.net_edge_pts == pytest.approx(yes_result.net_edge_pts, abs=1e-9)
    assert no_result.suggested_size_pct_bankroll == pytest.approx(
        yes_result.suggested_size_pct_bankroll, abs=1e-6
    )


# ---------------------------------------------------------------------------
# parse_resolution_risk
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flags,expected",
    [
        (["resolution_risk: high — oracle ambiguity"], "high"),
        (["Resolution risk is LOW"], "low"),
        (["medium resolution risk, some edge cases"], "medium"),
        (["no risk keyword here"], "medium"),
        ([], "medium"),
    ],
)
def test_parse_resolution_risk(flags, expected):
    assert pricing.parse_resolution_risk(flags) == expected
