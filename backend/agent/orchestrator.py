"""Pipeline orchestrator (§3): exactly 7 LLM calls + tool steps per execute.

Order: QueryPlanner -> MarketResolver -> (EvidenceRetriever ∥ SocialScanner)
-> SentimentScorer -> Council×4 (concurrent) -> pricing.py -> Judge
[-> PaperBroker, Phase 7]. Any failure returns the error envelope with the
steps collected so far (always HTTP 200).
"""

from __future__ import annotations

import asyncio
import time

from backend.agent import pricing
from backend.agent.modules import (
    evidence_retriever,
    judge,
    market_resolver,
    query_planner,
    sentiment_scorer,
    social_scanner,
)
from backend.agent.modules.council import bear, bull, quant, resolution_skeptic
from backend.agent.modules.council.base import build_shared_context
from backend.agent.types import (
    EvidenceCluster,
    ExecuteOut,
    JudgeOutput,
    MarketState,
    PersonaOpinion,
    PricingResult,
    SocialPulse,
)
from backend.data import supabase_client
from backend.llm.client import RunContext
from backend.sim import paper_broker

DISCLAIMER = (
    "_Polymarkov is an educational tool doing paper trading only. "
    "Nothing here is financial advice._"
)

REFUSAL_DEFAULT = (
    "I can only help with Polymarket market intelligence: analyzing a market's "
    "news, social sentiment and resolution risk, estimating fair value, and "
    "paper trading. Please point me at a Polymarket market (URL, slug, or a "
    "description of the question)."
)


async def run_pipeline(user_prompt: str) -> ExecuteOut:
    ctx = RunContext()
    started = time.monotonic()
    try:
        result = await _run(ctx, user_prompt, started)
        return result
    except Exception as exc:  # noqa: BLE001 — envelope contract: never raise
        return ExecuteOut(
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            response=None,
            steps=ctx.steps,
        )


async def _run(ctx: RunContext, user_prompt: str, started: float) -> ExecuteOut:
    # 1. QueryPlanner (LLM #1)
    plan = await query_planner.plan_query(ctx, user_prompt)
    if not plan.in_scope:
        return ExecuteOut(
            status="ok", response=plan.reason or REFUSAL_DEFAULT, steps=ctx.steps
        )

    # 2. MarketResolver (tool)
    resolved = await market_resolver.resolve_market(ctx, plan)
    if resolved.market is None:
        lines = ["I found several matching markets — please pick one and re-run:", ""]
        lines += [
            f"{i + 1}. **{c['question']}** — mid {c['mid'] * 100:.0f}%, "
            f"24h volume ${c['volume24h']:,.0f} (`{c['slug']}`)"
            for i, c in enumerate(resolved.candidates)
        ]
        return ExecuteOut(status="ok", response="\n".join(lines), steps=ctx.steps)
    market = resolved.market

    # 3+4. EvidenceRetriever ∥ SocialScanner (tools, concurrent)
    evidence, pulse = await asyncio.gather(
        evidence_retriever.retrieve_evidence(ctx, plan, market),
        social_scanner.scan_social(ctx, plan, market),
    )

    # 5. SentimentScorer (LLM #2, one batched call)
    await sentiment_scorer.score_sentiment(ctx, market, evidence.clusters, pulse)

    # 6. Council (LLM #3-#6, concurrent, identical context)
    shared_context = build_shared_context(market, evidence.clusters, pulse, evidence.precedents)
    opinions = await asyncio.gather(
        bull.run(ctx, shared_context),
        bear.run(ctx, shared_context),
        quant.run(ctx, shared_context),
        resolution_skeptic.run(ctx, shared_context),
    )
    council = dict(zip((bull.NAME, bear.NAME, quant.NAME, resolution_skeptic.NAME), opinions))

    # 7. Deterministic pricing (code) + Judge (LLM #7)
    risk = pricing.parse_resolution_risk(council[resolution_skeptic.NAME].red_flags)
    priced = pricing.compute_pricing(market, council, risk, len(evidence.clusters))
    verdict = await judge.run_judge(ctx, market, council, priced)

    # 8. PaperBroker (tool) — only when the user asked to trade and verdict isn't PASS
    fill = None
    trade_note = None
    if plan.wants_trade:
        if priced.verdict == "PASS":
            trade_note = "No paper trade opened: the verdict is PASS."
        else:
            fill = await paper_broker.execute_paper_trade(ctx, market, priced)
            trade_note = None if fill else "No paper trade opened: the order book had no fillable liquidity."

    response = _dossier_markdown(market, verdict, priced, evidence.clusters, pulse, council, trade_note, fill)
    ui = _ui_payload(market, verdict, priced, evidence.clusters, pulse, council, fill)

    latency_ms = int((time.monotonic() - started) * 1000)
    await asyncio.to_thread(
        supabase_client.log_run,
        {
            "prompt": user_prompt[:2000],
            "verdict": priced.verdict,
            "fair_prob": priced.fair_adj,
            "mid_at_run": market.mid,
            "tokens_in": ctx.tokens_in,
            "tokens_out": ctx.tokens_out,
            "latency_ms": latency_ms,
        },
    )
    return ExecuteOut(status="ok", response=response, steps=ctx.steps, ui=ui)


# ---------------------------------------------------------------------------
# Output assembly
# ---------------------------------------------------------------------------


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def _dossier_markdown(
    market: MarketState,
    verdict: JudgeOutput,
    priced: PricingResult,
    clusters: list[EvidenceCluster],
    pulse: SocialPulse,
    council: dict[str, PersonaOpinion],
    trade_note: str | None,
    fill=None,
) -> str:
    v = verdict.verdict.replace("_", " ")
    lines = [
        f"# {market.question}",
        "",
        f"**Market snapshot** — mid {_pct(market.mid)} | bid {_pct(market.best_bid)} | "
        f"ask {_pct(market.best_ask)} | spread {_pct(market.spread)} | "
        f"ask depth ${market.depth_at_ask_usd:,.0f} | 24h volume ${market.volume24h:,.0f}",
        "",
        f"## Verdict: {v}",
        f"Fair probability **{_pct(verdict.fair_probability)}** vs market {_pct(market.mid)} | "
        f"net edge **{verdict.net_edge_pts * 100:.1f} pts** | "
        f"suggested size **{verdict.suggested_size_pct_bankroll:.1f}% of bankroll** | "
        f"confidence **{verdict.confidence}** | resolution risk **{priced.resolution_risk}**",
        "",
        verdict.summary,
    ]
    if priced.pass_reasons:
        lines += ["", "**Why PASS:** " + "; ".join(priced.pass_reasons)]

    lines += ["", "## News & sentiment"]
    if clusters:
        for c in clusters:
            sent = f"{c.sentiment:+.2f} ({c.stance})" if c.sentiment is not None else "unscored"
            lines.append(f"- **{c.id}** [{c.headline}]({c.url}) — {c.source}, {c.date or 'undated'}, sentiment {sent}")
    else:
        lines.append("- No news evidence was available for this run.")

    lines += ["", "## Social pulse", f"- {pulse.note}"]
    if pulse.mention_velocity is not None:
        lines.append(f"- Mention velocity (24h vs prior 6-day avg): {pulse.mention_velocity}×")

    lines += ["", "## Council"]
    for name, o in council.items():
        lines.append(
            f"- **{name}** — P(YES) {o.estimated_probability:.2f} ({o.confidence}): {o.thesis}"
        )

    if verdict.key_risks:
        lines += ["", "## Key risks"]
        lines += [f"- {r}" for r in verdict.key_risks]

    if fill:
        lines += [
            "",
            "## Paper-trade fill",
            f"- **{fill.side.replace('_', ' ')}** ${fill.size_usd:,.2f} at VWAP {_pct(fill.vwap)}"
            f" | slippage {fill.slippage_bps:.1f} bps vs mid | fee ${fill.fee_paid:,.2f}"
            f" | {fill.levels_consumed} book level(s)",
            f"- Position id: `{fill.position_id}`",
        ]
    if trade_note:
        lines += ["", f"_{trade_note}_"]

    lines += ["", "---", DISCLAIMER]
    return "\n".join(lines)


def _ui_payload(
    market: MarketState,
    verdict: JudgeOutput,
    priced: PricingResult,
    clusters: list[EvidenceCluster],
    pulse: SocialPulse,
    council: dict[str, PersonaOpinion],
    fill=None,
) -> dict:
    persona_key = {"BullAnalyst": "bull", "BearAnalyst": "bear", "QuantAnalyst": "quant", "ResolutionSkeptic": "skeptic"}
    return {
        "verdict": {
            "verdict": verdict.verdict,
            "fair_probability": verdict.fair_probability,
            "net_edge_pts": verdict.net_edge_pts,
            "confidence": verdict.confidence,
            "suggested_size_pct_bankroll": verdict.suggested_size_pct_bankroll,
            "summary": verdict.summary,
            "key_risks": verdict.key_risks,
        },
        "market": market.model_dump(),
        "news": [c.model_dump() for c in clusters],
        "social": pulse.model_dump(),
        "council": {
            persona_key[name]: {
                "thesis": o.thesis,
                "estimated_probability": o.estimated_probability,
                "confidence": o.confidence,
                "red_flags": o.red_flags,
            }
            for name, o in council.items()
        },
        "fill": fill.model_dump() if fill else None,
    }
