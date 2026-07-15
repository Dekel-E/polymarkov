"""CrossVenueScanner — deterministic tool: same-event odds from Kalshi.

A second venue pricing the same event is a market-consensus prior no news
source can provide; divergence between venues is itself information. The
match is conservative token overlap — when unsure, it reports nothing.
"""

from __future__ import annotations

from typing import Optional

from backend.agent.types import MarketState
from backend.data import kalshi
from backend.llm.client import RunContext

MODULE = "CrossVenueScanner"


async def scan(ctx: RunContext, market: MarketState) -> Optional[dict]:
    result = await kalshi.find_matching_event(market.question)
    ctx.add_tool_step(
        MODULE,
        f"question={market.question!r}",
        result
        if result
        else {"found": False, "note": "no confident Kalshi match for this event"},
    )
    return result
