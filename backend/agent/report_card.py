"""Agent report card: run history + calibration once markets resolve.

Brier score = mean((forecast - outcome)^2), lower is better. We score the
agent's fair probability against each resolved market's outcome and compare
with the market price at run time — the honest question is not "is the
agent accurate" but "does it beat the market it trades against".
"""

from __future__ import annotations

from typing import Optional

from backend.data import supabase_client


def brier(forecast: float, outcome: int) -> float:
    return (forecast - outcome) ** 2


def score_runs(runs: list[dict], outcome_by_slug: dict[str, int]) -> Optional[dict]:
    """Aggregate Brier scores for runs whose market has resolved."""
    agent_scores: list[float] = []
    market_scores: list[float] = []
    for r in runs:
        slug = r.get("market_id")
        fair = r.get("fair_prob")
        mid = r.get("mid_at_run")
        if slug not in outcome_by_slug or fair is None or mid is None:
            continue
        outcome = outcome_by_slug[slug]
        agent_scores.append(brier(float(fair), outcome))
        market_scores.append(brier(float(mid), outcome))
    if not agent_scores:
        return None
    return {
        "scored_runs": len(agent_scores),
        "agent_brier": round(sum(agent_scores) / len(agent_scores), 4),
        "market_brier": round(sum(market_scores) / len(market_scores), 4),
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
