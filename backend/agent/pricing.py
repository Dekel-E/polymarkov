"""Deterministic pricing engine (plan §6) — code does ALL arithmetic.

LLM personas only assign interpretable weights; this module turns them into
fair probability, net edge, verdict, and position size. The Judge LLM
receives these numbers as immutable inputs. All constants live in config.
"""

from __future__ import annotations

import math
from typing import Optional

from backend import config
from backend.agent.types import EvidenceWeight, MarketState, PersonaOpinion, PricingResult


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def logit(p: float) -> float:
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def taker_fee(category: str, p_exec: float) -> float:
    """FEE_RATE[category] * p * (1-p) — peaks at 50c."""
    rate = config.FEE_RATE.get(category, config.FEE_RATE["other"])
    return rate * p_exec * (1 - p_exec)


def kelly_size_pct(fair: float, p_entry: float) -> float:
    """Quarter-Kelly position size in % of bankroll, capped at 5%.

    `fair` is the probability that the token being bought pays out;
    `p_entry` is that token's execution price.
    """
    if not 0 < p_entry < 1:
        return 0.0
    b = (1 - p_entry) / p_entry  # net odds
    f_star = (fair * b - (1 - fair)) / b
    return clamp(config.KELLY_FRACTION * f_star, 0.0, config.MAX_SIZE_PCT_BANKROLL) * 100


def parse_resolution_risk(red_flags: list[str]) -> str:
    """ResolutionSkeptic encodes resolution_risk in red_flags[0] (§5)."""
    if red_flags:
        first = red_flags[0].lower()
        for level in ("high", "medium", "low"):
            if level in first:
                return level
    return "medium"  # unknown -> neither trusting nor auto-PASS


# ---------------------------------------------------------------------------
# Evidence aggregation
# ---------------------------------------------------------------------------


def _effective_weight(w: EvidenceWeight) -> float:
    sign = 1.0 if w.direction == "yes" else -1.0
    raw = sign * w.strength * config.W_MAX
    return raw * w.reliability * (1 - w.already_priced_in)


def aggregate_evidence(
    council: dict[str, PersonaOpinion],
    cluster_of: Optional[dict[str, str]] = None,
) -> float:
    """Council evidence weights -> total log-odds update (capped).

    1. effective_i = sign * strength * W_MAX * reliability * (1 - priced_in)
    2. same evidence_id cited by multiple personas -> average, don't sum
    3. within one cluster, after the largest |effective|, discount 0.5^k
    4. clamp the sum to ±TOTAL_UPDATE_CAP
    """
    cluster_of = cluster_of or {}

    # Dedup across personas: evidence_id -> average effective weight
    by_id: dict[str, list[float]] = {}
    for opinion in council.values():
        for w in opinion.evidence_weights:
            by_id.setdefault(w.evidence_id, []).append(_effective_weight(w))
    deduped = {eid: sum(vals) / len(vals) for eid, vals in by_id.items()}

    # Correlation discount within clusters
    by_cluster: dict[str, list[float]] = {}
    for eid, eff in deduped.items():
        by_cluster.setdefault(cluster_of.get(eid, eid), []).append(eff)

    total = 0.0
    for effs in by_cluster.values():
        effs.sort(key=abs, reverse=True)
        for k, eff in enumerate(effs):
            total += eff * (config.CORRELATION_DISCOUNT**k)

    return clamp(total, -config.TOTAL_UPDATE_CAP, config.TOTAL_UPDATE_CAP)


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def compute_pricing(
    market: MarketState,
    council: dict[str, PersonaOpinion],
    resolution_risk: str,
    n_evidence_clusters: int,
    cluster_of: Optional[dict[str, str]] = None,
    slippage: float = 0.0,
) -> PricingResult:
    prior = clamp(market.mid, *config.PRIOR_CLAMP)
    l0 = logit(prior)

    total_update = aggregate_evidence(council, cluster_of)
    fair = sigmoid(l0 + total_update)

    # Resolution haircut: shrink toward the market prior
    h = config.RESOLUTION_HAIRCUT.get(resolution_risk, config.RESOLUTION_HAIRCUT["medium"])
    fair_adj = fair + (prior - fair) * min(1.0, h * config.HAIRCUT_MULTIPLIER)

    gross_edge = fair_adj - market.mid

    # Costs for the side we would actually trade
    half_spread = (market.spread / 2) if market.spread is not None else 0.0
    if gross_edge > 0:  # would buy YES at the ask
        p_exec = market.best_ask if market.best_ask is not None else market.mid
    else:  # would buy NO ≈ 1 - best_bid
        p_exec = (1 - market.best_bid) if market.best_bid is not None else (1 - market.mid)
    fee = taker_fee(market.category, p_exec)

    net_edge = abs(gross_edge) - half_spread - fee - slippage - config.SAFETY_MARGIN

    # PASS triggers (PASS is a first-class outcome)
    pass_reasons: list[str] = []
    if resolution_risk == "high":
        pass_reasons.append("resolution risk is high")
    if market.spread is None or market.best_bid is None or market.best_ask is None:
        pass_reasons.append("order book unavailable")
    elif market.spread > config.MAX_SPREAD:
        pass_reasons.append(f"spread {market.spread:.3f} wider than {config.MAX_SPREAD}")
    if n_evidence_clusters < config.MIN_EVIDENCE_CLUSTERS:
        pass_reasons.append(f"fewer than {config.MIN_EVIDENCE_CLUSTERS} evidence clusters")
    estimates = [o.estimated_probability for o in council.values()]
    if estimates and (max(estimates) - min(estimates)) > config.MAX_COUNCIL_DISAGREEMENT:
        pass_reasons.append(
            f"council estimates disagree by {max(estimates) - min(estimates):.2f} "
            f"(> {config.MAX_COUNCIL_DISAGREEMENT})"
        )
    if market.depth_at_ask_usd < config.MIN_DEPTH_USD:
        pass_reasons.append(
            f"depth ${market.depth_at_ask_usd:,.0f} below ${config.MIN_DEPTH_USD:,}"
        )
    if net_edge <= 0:
        pass_reasons.append("net edge non-positive after costs")

    verdict = "PASS"
    size_pct = 0.0
    if not pass_reasons:
        if gross_edge > 0:
            verdict = "BUY_YES"
            size_pct = kelly_size_pct(fair_adj, market.best_ask)  # type: ignore[arg-type]
        elif gross_edge < 0:
            verdict = "BUY_NO"
            size_pct = kelly_size_pct(1 - fair_adj, 1 - market.best_bid)  # type: ignore[operator]
        else:
            pass_reasons.append("no edge either way")

    return PricingResult(
        prior=round(prior, 6),
        fair=round(fair, 6),
        fair_adj=round(fair_adj, 6),
        gross_edge_pts=round(gross_edge, 6),
        half_spread=round(half_spread, 6),
        taker_fee=round(fee, 6),
        slippage=round(slippage, 6),
        net_edge_pts=round(net_edge, 6),
        verdict=verdict,
        pass_reasons=pass_reasons,
        suggested_size_pct_bankroll=round(size_pct, 4),
        resolution_risk=resolution_risk if resolution_risk in config.RESOLUTION_HAIRCUT else "medium",
    )
