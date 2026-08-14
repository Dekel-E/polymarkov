"""Agent report card: run history and calibration once markets resolve.

Brier score = mean((forecast - outcome)^2), lower is better. Scores the
agent's fair probability against each resolved outcome and compares it with
the market price at run time.
"""

from __future__ import annotations

import math
from typing import Optional

from backend.data import supabase_client


def brier(forecast: float, outcome: int) -> float:
    return (forecast - outcome) ** 2


def _probability(value) -> Optional[float]:
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        return None
    return probability


def _score_pairs(pairs: list[tuple[float, float, int]]) -> dict:
    """Metrics over (agent forecast, market forecast, binary outcome)."""
    agent_scores = [brier(agent, outcome) for agent, _market, outcome in pairs]
    market_scores = [brier(market, outcome) for _agent, market, outcome in pairs]
    agent_brier = sum(agent_scores) / len(agent_scores)
    market_brier = sum(market_scores) / len(market_scores)

    epsilon = 1e-6

    def log_loss(probability: float, outcome: int) -> float:
        p = min(max(probability, epsilon), 1 - epsilon)
        return -(outcome * math.log(p) + (1 - outcome) * math.log(1 - p))

    bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]
    buckets = []
    weighted_gap = 0.0
    for lower, upper in bins:
        bucket = [
            (agent, outcome)
            for agent, _market, outcome in pairs
            if lower <= agent < upper or (upper == 1.0 and agent == 1.0)
        ]
        if not bucket:
            continue
        mean_forecast = sum(agent for agent, _outcome in bucket) / len(bucket)
        outcome_rate = sum(outcome for _agent, outcome in bucket) / len(bucket)
        gap = abs(mean_forecast - outcome_rate)
        weighted_gap += len(bucket) * gap
        buckets.append(
            {
                "range": f"{int(lower * 100)}-{int(upper * 100)}%",
                "count": len(bucket),
                "mean_forecast": round(mean_forecast, 4),
                "outcome_rate": round(outcome_rate, 4),
                "absolute_gap": round(gap, 4),
            }
        )

    skill = None if market_brier == 0 else 1 - (agent_brier / market_brier)
    return {
        "agent_brier": round(agent_brier, 4),
        "market_brier": round(market_brier, 4),
        "brier_skill_vs_market": round(skill, 4) if skill is not None else None,
        "agent_log_loss": round(
            sum(log_loss(agent, outcome) for agent, _market, outcome in pairs) / len(pairs), 4
        ),
        "market_log_loss": round(
            sum(log_loss(market, outcome) for _agent, market, outcome in pairs) / len(pairs), 4
        ),
        "expected_calibration_error": round(weighted_gap / len(pairs), 4),
        "buckets": buckets,
    }


def score_runs(runs: list[dict], outcome_by_slug: dict[str, int]) -> Optional[dict]:
    """Score resolved forecasts, including an independence-aware market view."""
    pairs: list[tuple[float, float, int]] = []
    latest_by_market: dict[str, tuple[str, float, float, int]] = {}
    forecast_runs = 0
    forecast_markets: set[str] = set()
    for r in runs:
        slug = r.get("market_id")
        fair = _probability(r.get("fair_prob"))
        mid = _probability(r.get("mid_at_run"))
        if not slug or fair is None or mid is None:
            continue
        forecast_runs += 1
        forecast_markets.add(str(slug))
        if slug not in outcome_by_slug:
            continue
        outcome = outcome_by_slug[slug]
        if outcome not in (0, 1):
            continue
        pairs.append((fair, mid, outcome))
        # Recent runs arrive newest-first. ISO timestamps also compare in time
        # order, so this remains correct for direct score_runs callers.
        created_at = str(r.get("created_at") or "")
        previous = latest_by_market.get(str(slug))
        if previous is None or created_at > previous[0]:
            latest_by_market[str(slug)] = (created_at, fair, mid, outcome)

    if not pairs:
        return None
    market_pairs = [(fair, mid, outcome) for _at, fair, mid, outcome in latest_by_market.values()]
    resolved_markets = len(market_pairs)
    if resolved_markets < 20:
        sample_status = "early"
        sample_warning = "Fewer than 20 resolved markets; calibration estimates are unstable."
    elif resolved_markets < 100:
        sample_status = "developing"
        sample_warning = "Fewer than 100 resolved markets; interpret small differences cautiously."
    else:
        sample_status = "established"
        sample_warning = None

    return {
        "scored_runs": len(pairs),
        "resolved_markets": resolved_markets,
        "forecast_runs": forecast_runs,
        "forecast_markets": len(forecast_markets),
        "resolution_coverage_pct": round(len(pairs) / forecast_runs * 100, 1),
        "sample_status": sample_status,
        "sample_warning": sample_warning,
        **_score_pairs(pairs),
        # Repeated forecasts of one event are correlated. This view gives each
        # resolved market one vote and should be preferred as the sample grows.
        "latest_per_market": {"markets": resolved_markets, **_score_pairs(market_pairs)},
    }


def _resolved_outcomes(slugs: list[str]) -> dict[str, int]:
    """slug -> 1/0 for markets that have resolved, via markets + precedents."""
    if not supabase_client.is_configured() or not slugs:
        return {}
    client = supabase_client.get_client()
    try:
        markets = (
            client.table("markets").select("id,slug").in_("slug", slugs).execute().data or []
        )
        id_to_slug = {m["id"]: m["slug"] for m in markets}
        if not id_to_slug:
            return {}
        precedents = (
            client.table("precedents")
            .select("market_id,outcome")
            .in_("market_id", list(id_to_slug))
            .execute()
            .data
            or []
        )
        return {
            id_to_slug[p["market_id"]]: 1 if p["outcome"] == "YES" else 0 for p in precedents
        }
    except Exception:
        return {}


def get_report_card() -> dict:
    runs = supabase_client.get_recent_runs(limit=200)
    verdicts: dict[str, int] = {}
    latencies = []
    tokens_out = 0
    for r in runs:
        if r.get("verdict"):
            verdicts[r["verdict"]] = verdicts.get(r["verdict"], 0) + 1
        if r.get("latency_ms"):
            latencies.append(int(r["latency_ms"]))
        tokens_out += int(r.get("tokens_out") or 0)

    slugs = sorted({r["market_id"] for r in runs if r.get("market_id")})
    calibration = score_runs(runs, _resolved_outcomes(slugs))

    return {
        "total_runs": len(runs),
        "verdicts": verdicts,
        "avg_latency_s": round(sum(latencies) / len(latencies) / 1000, 1) if latencies else None,
        "total_tokens_out": tokens_out,
        "calibration": calibration,  # None until analyzed markets resolve
        "recent": [
            {
                "market_id": r.get("market_id"),
                "verdict": r.get("verdict"),
                "fair_prob": r.get("fair_prob"),
                "mid_at_run": r.get("mid_at_run"),
                "latency_ms": r.get("latency_ms"),
                "created_at": r.get("created_at"),
            }
            for r in runs[:15]
        ],
    }
