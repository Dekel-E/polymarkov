"""QueryPlanner — LLM call #1: user prompt -> structured research plan."""

from __future__ import annotations

from pydantic import ValidationError

from backend.agent.types import QueryPlan
from backend.llm.client import RunContext, load_prompt

MODULE = "QueryPlanner"


async def plan_query(ctx: RunContext, user_prompt: str) -> QueryPlan:
    raw = await ctx.call_llm(MODULE, load_prompt("query_planner"), user_prompt)
    try:
        return QueryPlan.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"QueryPlanner returned an unexpected schema: {exc}") from exc
