"""SentimentScorer — LLM call #2: ONE batched call scoring all news + posts."""

from __future__ import annotations

import json

from backend.agent.types import EvidenceCluster, MarketState, SocialPulse
from backend.llm.client import RunContext, load_prompt

MODULE = "SentimentScorer"

_STANCES = ("yes", "no", "neutral")


async def score_sentiment(
    ctx: RunContext,
    market: MarketState,
    clusters: list[EvidenceCluster],
    pulse: SocialPulse,
) -> None:
    """Mutates clusters/posts in place with sentiment + stance."""
    items = [
        {"id": c.id, "text": f"{c.headline} — {c.source}, {c.date or 'undated'}"}
        for c in clusters
    ] + [{"id": p.id, "text": p.text[:280]} for p in pulse.posts]
    if not items:
        return  # nothing to score; skipping the call saves budget

    user_prompt = (
        f"Market question: {market.question}\n"
        f"Resolution criteria (excerpt): {market.resolution_criteria[:500]}\n\n"
        f"Items to score:\n{json.dumps(items, ensure_ascii=False, indent=1)}"
    )
    raw = await ctx.call_llm(MODULE, load_prompt("sentiment_scorer"), user_prompt)

    scored: dict[str, tuple[float, str]] = {}
    for row in raw.get("items", []) if isinstance(raw, dict) else []:
        try:
            sentiment = max(-1.0, min(1.0, float(row["sentiment"])))
            stance = row.get("stance", "neutral")
            scored[str(row["id"])] = (
                sentiment,
                stance if stance in _STANCES else "neutral",
            )
        except (KeyError, TypeError, ValueError):
            continue

    for c in clusters:
        if c.id in scored:
            c.sentiment, c.stance = scored[c.id]
    for p in pulse.posts:
        if p.id in scored:
            p.sentiment, p.stance = scored[p.id]
