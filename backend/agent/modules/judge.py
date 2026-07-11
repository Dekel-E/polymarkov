"""Judge — pricing.py computes the decision (code), then LLM call #7 writes
the dossier narrative. The LLM may NOT change the numbers: whatever it
returns, the deterministic values are copied over its output.
"""

from __future__ import annotations

import json

from backend.agent.types import JudgeOutput, MarketState, PersonaOpinion, PricingResult
from backend.llm.client import RunContext, load_prompt

MODULE = "Judge"

_DIGEST_KEYS = {"BullAnalyst": "bull", "BearAnalyst": "bear", "QuantAnalyst": "quant", "ResolutionSkeptic": "skeptic"}


def _council_block(council: dict[str, PersonaOpinion]) -> str:
    parts = []
    for name, o in council.items():
        parts.append(
            f"--- {name} ---\n"
            f"P(YES): {o.estimated_probability:.2f} (confidence {o.confidence})\n"
            f"Thesis: {o.thesis}\n"
            f"Red flags: {'; '.join(o.red_flags) or 'none'}"
        )
    return "\n".join(parts)


def _numbers_block(pricing: PricingResult) -> str:
    data = {
        "verdict": pricing.verdict,
        "fair_probability": pricing.fair_adj,
        "net_edge_pts": pricing.net_edge_pts,
        "suggested_size_pct_bankroll": pricing.suggested_size_pct_bankroll,
        "market_mid": pricing.prior,
        "gross_edge_pts": pricing.gross_edge_pts,
        "half_spread": pricing.half_spread,
        "taker_fee": pricing.taker_fee,
        "resolution_risk": pricing.resolution_risk,
        "pass_reasons": pricing.pass_reasons,
    }
    return json.dumps(data, indent=1)


async def run_judge(
    ctx: RunContext,
    market: MarketState,
    council: dict[str, PersonaOpinion],
    pricing: PricingResult,
) -> JudgeOutput:
    user_prompt = (
        f"Market: {market.question}\n"
        f"Current mid: {market.mid:.3f} | Ends: {market.end_date or 'n/a'}\n\n"
        f"== COUNCIL OPINIONS ==\n{_council_block(council)}\n\n"
        f"== COMPUTED DECISION (FINAL — copy these values exactly) ==\n"
        f"{_numbers_block(pricing)}"
    )
    raw = await ctx.call_llm(MODULE, load_prompt("judge"), user_prompt)
    raw = raw if isinstance(raw, dict) else {}

    digest_raw = raw.get("council_digest") or {}
    digest = {
        key: str(digest_raw.get(key) or f"{name}: P(YES) {council[name].estimated_probability:.2f}")
        for name, key in _DIGEST_KEYS.items()
        if name in council
    }
    confidence = raw.get("confidence")
    if confidence not in ("low", "medium", "high"):
        confidence = "low"

    # Deterministic values ALWAYS win — the LLM's numbers are discarded.
    return JudgeOutput(
        verdict=pricing.verdict,
        fair_probability=pricing.fair_adj,
        net_edge_pts=pricing.net_edge_pts,
        confidence=confidence,
        suggested_size_pct_bankroll=pricing.suggested_size_pct_bankroll,
        summary=str(raw.get("summary") or "No narrative produced."),
        key_risks=[str(r) for r in (raw.get("key_risks") or [])][:5],
        council_digest=digest,
    )
