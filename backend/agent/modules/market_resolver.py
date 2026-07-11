"""MarketResolver — deterministic tool: plan -> exactly one MarketState.

Resolution ladder: pasted URL/slug -> Gamma text search (clear winner by
volume) -> Pinecone vector match over indexed markets -> otherwise return
top candidates and ask the user to pick.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Optional

from backend.agent.types import MarketState
from backend.data import pinecone_client, polymarket
from backend.llm import embeddings
from backend.llm.client import RunContext

MODULE = "MarketResolver"
CLEAR_WINNER_VOLUME_RATIO = 3.0
VECTOR_MATCH_MIN_SCORE = 0.45


@dataclass
class ResolveResult:
    market: Optional[MarketState] = None
    candidates: list[dict] = field(default_factory=list)


def _candidate(m: dict) -> dict:
    return {
        "slug": m["slug"],
        "question": m["question"],
        "mid": m["mid"],
        "volume24h": m["volume24h"],
    }


async def _vector_match(query: str) -> Optional[str]:
    """Best market slug from the Pinecone `markets` namespace, if confident."""
    if not (pinecone_client.is_configured() and embeddings.is_configured()):
        return None
    try:
        vector = await asyncio.to_thread(embeddings.embed_one, query)
        matches = await asyncio.to_thread(pinecone_client.query, "markets", vector, 3)
    except Exception:
        return None
    if matches and matches[0]["score"] >= VECTOR_MATCH_MIN_SCORE:
        return matches[0]["metadata"].get("slug") or matches[0]["id"]
    return None


async def resolve_market(ctx: RunContext, plan) -> ResolveResult:
    query = plan.market_query or " ".join(plan.entities) or ""
    result = ResolveResult()
    how = ""

    # 1) explicit URL/slug
    ref = polymarket.parse_market_ref(plan.market_url or "")
    if ref:
        result.market = await polymarket.get_market_state(ref)
        how = f"url ref {ref!r}"

    # 2) Gamma text search with a clear winner
    if result.market is None and query:
        found = await polymarket.search_markets(query, limit=5)
        found = [m for m in found if m["yes_token_id"]]
        if len(found) == 1 or (
            len(found) > 1
            and found[0]["volume24h"] >= CLEAR_WINNER_VOLUME_RATIO * max(found[1]["volume24h"], 1e-9)
        ):
            result.market = await polymarket.get_market_state(found[0]["slug"])
            how = f"text search {query!r} (clear winner)"
        elif found:
            # 3) vector match against indexed markets
            slug = await _vector_match(query)
            if slug:
                result.market = await polymarket.get_market_state(slug)
                how = f"vector match {query!r} -> {slug!r}"
            if result.market is None:
                result.candidates = [_candidate(m) for m in found[:3]]
                how = f"ambiguous text search {query!r}"

    if result.market is None and not result.candidates:
        raise RuntimeError(
            f"No Polymarket market found for {query or plan.market_url!r}. "
            "Try pasting the market URL or being more specific."
        )

    ctx.add_tool_step(
        MODULE,
        f"market_url={plan.market_url!r} market_query={query!r} -> resolved via {how}",
        (
            {
                "slug": result.market.slug,
                "question": result.market.question,
                "mid": result.market.mid,
                "spread": result.market.spread,
                "depth_at_ask_usd": result.market.depth_at_ask_usd,
            }
            if result.market
            else {"candidates": result.candidates}
        ),
    )
    return result
