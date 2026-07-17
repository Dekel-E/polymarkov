"""Pipeline orchestrator: wires the stages together per execute.

Any failure returns the error envelope with the steps collected so far
(always HTTP 200).
"""

from __future__ import annotations

import asyncio
import time

from backend import config
from backend.agent import council, intel_cache, pipeline, pricing
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


def self_description() -> str:
    """Answer 'who are you / what can you do' from the registry. Same specs
    as /api/agent_info, so it can't drift from the code. Zero LLM calls."""
    from backend.agent.registry import MODULES

    llm = [m for m in MODULES if m["kind"] == "llm"]
    tools = [m for m in MODULES if m["kind"] == "tool"]
    sources = sorted({s for m in MODULES for s in m["data_sources"]})
    lines = [
        "# Polymarkov — what I am and what I can do",
        "",
        "I'm an educational pre-trade intelligence agent for **Polymarket** "
        "prediction markets. Give me a market (URL, slug, or a description) and "
        "I build a research dossier: recent news, social chatter, a four-analyst "
        "AI council debate, a deterministic fair-value estimate, and a "
        "**BUY YES / BUY NO / PASS** verdict with a suggested paper-trade size.",
        "",
        "## What I CAN do",
        "- Analyze any active Polymarket market: `Market: <slug or question>`",
        "- Gather and index evidence — news search, open-web search, and social "
        "chatter — and score its sentiment and stance",
        "- Estimate a fair probability and net edge after spread and fees "
        "(computed by code, not by the model)",
        "- Paper-trade a verdict against the live order book (`Trade: yes`)",
        "- Answer follow-up questions about an analyzed market in the chat on "
        "its page, fetching fresh sources when needed",
        "",
        "## What I CANNOT do",
        "- Trade real money, hold funds, or give financial advice — every fill "
        "here is simulated",
        "- Analyze non-Polymarket assets (stocks, live crypto prices) or answer "
        "questions unrelated to prediction markets",
        "- Guarantee outcomes: my verdicts are calibrated estimates from cited "
        "evidence, and PASS is a first-class answer",
        "",
        f"## How I work ({len(llm)} LLM modules, {len(tools)} deterministic tools)",
    ]
    for m in llm + tools:
        lines.append(f"- **{m['name']}** ({m['kind']}): {m['description']}")
    lines += [
        "",
        "**Data sources:** " + ", ".join(sources),
        "",
        "Full specs, prompt templates and worked examples: `GET /api/agent_info`.",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


async def run_pipeline(user_prompt: str, history: list[dict] | None = None) -> ExecuteOut:
    ctx = RunContext()
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(
            _run(ctx, user_prompt, started, history or []),
            timeout=config.EXECUTE_DEADLINE_S,
        )
        return result
    except asyncio.TimeoutError:
        return ExecuteOut(
            status="error",
            error=(
                f"Analysis exceeded the {config.EXECUTE_DEADLINE_S:.0f}s time "
                "budget and was stopped. Please try again."
            ),
            response=None,
            steps=ctx.steps,
        )
    except Exception as exc:  # noqa: BLE001
        return ExecuteOut(
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            response=None,
            steps=ctx.steps,
        )


def _planner_input(user_prompt: str, history: list[dict]) -> str:
    """Prepend recent turns so follow-ups resolve against the prior market."""
    if not history:
        return user_prompt
    lines = ["== PREVIOUS CONVERSATION (context for resolving follow-ups) =="]
    for turn in history[-6:]:
        role = "user" if str(turn.get("role")) == "user" else "assistant"
        content = str(turn.get("content", "")).strip()
        if content:
            lines.append(f"{role}: {content[:300]}")
    lines += ["", "== CURRENT REQUEST ==", user_prompt]
    return "\n".join(lines)


async def suggest_markets(entities: list[str], fallback_query: str = "") -> str:
    """Turn an out-of-scope topic into Polymarket markets the agent can
    analyze. Deterministic Gamma search, zero LLM calls."""
    from backend.data import polymarket

    query = " ".join(entities[:3]).strip() or fallback_query.strip()
    if not query:
        return ""
    try:
        hits = await polymarket.search_markets(query, limit=3)
    except Exception:
        return ""
    if not hits:
        return ""
    lines = ["", "", "Related Polymarket markets I CAN analyze — re-run with one of these:"]
    for h in hits:
        mid = h.get("mid")
        mid_txt = f" — mid {float(mid) * 100:.0f}%" if mid is not None else ""
        lines.append(f"- **{h.get('question', h.get('slug', ''))}**{mid_txt} (`Market: {h.get('slug', '')}`)")
    return "\n".join(lines)


def _serve_cached(payload: dict) -> ExecuteOut:
    created_at = payload.get("created_at", "")
    age_min = max(0, int(intel_cache._age_s(created_at) // 60))
    note = (
        f"_(Cached dossier compiled {age_min} min ago — a fresh analysis runs "
        f"automatically once the cache expires after "
        f"{config.INTEL_CACHE_TTL_S // 60} min.)_\n\n"
    )
    ui = dict(payload.get("ui") or {})
    ui["cached_at"] = created_at
    return ExecuteOut(
        status="ok",
        response=note + (payload.get("response") or ""),
        steps=payload.get("steps") or [],
        ui=ui,
    )


async def _run(ctx: RunContext, user_prompt: str, started: float, history: list[dict]) -> ExecuteOut:
    # Cache fast path: templated GUI prompts name the market outright, so a
    # fresh dossier can be served without any LLM calls.
    fast_slug = intel_cache.slug_from_prompt(user_prompt)
    if fast_slug:
        cached = await asyncio.to_thread(intel_cache.get, fast_slug)
        if cached:
            return _serve_cached(cached)

    plan = await pipeline.plan_query(ctx, _planner_input(user_prompt, history))
    if plan.intent == "meta":
        return ExecuteOut(status="ok", response=self_description(), steps=ctx.steps)
    if not plan.in_scope:
        refusal = (plan.reason or REFUSAL_DEFAULT) + await suggest_markets(
            plan.entities, plan.market_query or ""
        )
        return ExecuteOut(status="ok", response=refusal, steps=ctx.steps)

    resolved = await pipeline.resolve_market(ctx, plan)
    if resolved.market is None:
        lines = ["I found several matching markets — please pick one and re-run:", ""]
        lines += [
            f"{i + 1}. **{c['question']}** — mid {c['mid'] * 100:.0f}%, "
            f"24h volume ${c['volume24h']:,.0f} (`{c['slug']}`)"
            for i, c in enumerate(resolved.candidates)
        ]
        return ExecuteOut(status="ok", response="\n".join(lines), steps=ctx.steps)
    market = resolved.market

    # Cache check post-resolve for free-text prompts. Trades bypass the cache.
    if not plan.wants_trade:
        cached = await asyncio.to_thread(intel_cache.get, market.slug)
        if cached:
            return _serve_cached(cached)

    # Evidence, social and cross-venue tools run concurrently.
    evidence, pulse, venue = await asyncio.gather(
        pipeline.retrieve_evidence(ctx, plan, market),
        pipeline.scan_social(ctx, plan, market),
        pipeline.scan_cross_venue(ctx, market),
    )

    await pipeline.score_sentiment(ctx, market, evidence.clusters, pulse)

    shared_context = council.build_shared_context(
        market, evidence.clusters, pulse, evidence.precedents, cross_venue=venue
    )
    opinions = await council.run_council(ctx, shared_context)

    risk = pricing.parse_resolution_risk(opinions["ResolutionSkeptic"].red_flags)
    priced = pricing.compute_pricing(market, opinions, risk, len(evidence.clusters))
    verdict = await pipeline.run_judge(ctx, market, opinions, priced)

    # Paper trade only when requested and the verdict isn't PASS.
    fill = None
    trade_note = None
    if plan.wants_trade:
        if priced.verdict == "PASS":
            trade_note = "No paper trade opened: the verdict is PASS."
        else:
            fill = await paper_broker.execute_paper_trade(ctx, market, priced, strategy="ai_signal")
            trade_note = None if fill else "No paper trade opened: the order book had no fillable liquidity."

    response = _dossier_markdown(market, verdict, priced, evidence.clusters, pulse, opinions, trade_note, fill)
    ui = _ui_payload(market, verdict, priced, evidence.clusters, pulse, opinions, fill)

    # cache the analysis for repeat requests; the fill is not replayed
    await asyncio.to_thread(
        intel_cache.put,
        market.slug,
        response,
        [s.model_dump() for s in ctx.steps],
        {**ui, "fill": None},
    )

    latency_ms = int((time.monotonic() - started) * 1000)
    await asyncio.to_thread(
        supabase_client.log_run,
        {
            "prompt": user_prompt[:2000],
            "market_id": market.slug,
            "verdict": priced.verdict,
            "fair_prob": priced.fair_adj,
            "mid_at_run": market.mid,
            "tokens_in": ctx.tokens_in,
            "tokens_out": ctx.tokens_out,
            "latency_ms": latency_ms,
        },
    )
    return ExecuteOut(status="ok", response=response, steps=ctx.steps, ui=ui)


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
