"""SocialScanner — deterministic tool: recent posts + mention velocity."""

from __future__ import annotations

from backend import config
from backend.agent.types import MarketState, QueryPlan, SocialPost, SocialPulse
from backend.data import social
from backend.llm.client import RunContext

MODULE = "SocialScanner"


async def scan_social(ctx: RunContext, plan: QueryPlan, market: MarketState) -> SocialPulse:
    query = plan.market_query or market.question
    data = await social.gather_social(market.event_id, query, limit=config.MAX_SOCIAL_POSTS)

    posts = [
        SocialPost(
            id=f"s{i + 1}",
            text=p["text"],
            source=p["source"],
            url=p.get("url", ""),
            created_at=p.get("created_at"),
        )
        for i, p in enumerate(data["posts"])
    ]
    pulse = SocialPulse(posts=posts, mention_velocity=data["mention_velocity"], note=data["note"])

    ctx.add_tool_step(
        MODULE,
        f"event_id={market.event_id!r} query={query!r}",
        {
            "posts": len(posts),
            "sources": sorted({p.source for p in posts}),
            "mention_velocity": pulse.mention_velocity,
            "note": pulse.note,
        },
    )
    return pulse
