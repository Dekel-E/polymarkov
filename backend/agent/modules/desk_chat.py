"""DeskChat — the global conversational entry point (POST /api/chat).

One router LLM call classifies the question, then:
- market     -> resolve the market (Gamma search) and delegate to MarketChat
               (which plans, gathers/indexes fresh intel, and answers cited)
- portfolio  -> deterministic fact-gathering from Supabase (positions, PnL,
               strategies, runs, agenda, briefing) + one grounded answer call
- meta       -> the registry-built self-description (zero further LLM calls)
- out_of_scope -> friendly refusal + suggested Polymarket markets (zero LLM)
"""

from __future__ import annotations

import asyncio
import json

from backend import config
from backend.agent.modules import market_chat
from backend.agent.modules.council.base import time_context
from backend.data import polymarket, supabase_client
from backend.llm.client import RunContext, load_prompt

MODULE = "DeskChat"


def _portfolio_facts() -> dict:
    """Everything the desk knows about itself, trimmed for one prompt."""
    from backend.sim.portfolio import get_portfolio

    p = get_portfolio()
    open_rows = [
        {k: r.get(k) for k in ("market_id", "side", "strategy", "size_usd",
                               "entry_price", "current_price", "unrealized_pnl", "opened_at")}
        for r in p["open"][:15]
    ]
    resolved = [
        {k: r.get(k) for k in ("market_id", "side", "strategy", "size_usd",
                               "pnl", "resolved_outcome", "resolved_at")}
        for r in p["resolved"][:15]
    ]
    runs = [
        {k: r.get(k) for k in ("market_id", "verdict", "fair_prob", "mid_at_run", "created_at")}
        for r in supabase_client.get_recent_runs(10)
    ]
    briefing = supabase_client.latest_briefing()
    return {
        "stats": p["stats"],
        "open_positions": open_rows,
        "recent_resolved": resolved,
        "settings": supabase_client.get_agent_settings(),
        "recent_analyses": runs,
        "pending_agenda": supabase_client.get_pending_agenda(8),
        "latest_briefing": (briefing or {}).get("content", "")[:1200] or None,
    }


async def chat(question: str, history: list[dict]) -> dict:
    """Answer one global chat question. Never raises for expected cases."""
    ctx = RunContext()
    question = question.strip()[: config.CHAT_MAX_QUESTION_CHARS]
    if not question:
        return {"answer": None, "citations": [], "market": None, "error": "empty question"}

    recent = [
        {"role": "user" if str(t.get("role")) == "user" else "assistant",
         "content": str(t.get("content", ""))[: config.CHAT_MAX_HISTORY_CHARS]}
        for t in history
        if t.get("content")
    ][-config.CHAT_MAX_HISTORY_TURNS :]

    route_raw = await ctx.call_llm(
        MODULE,
        load_prompt("desk_chat_router"),
        json.dumps({"question": question, "chat_history": recent}, ensure_ascii=False),
    )
    route_raw = route_raw if isinstance(route_raw, dict) else {}
    route = route_raw.get("route")

    if route == "meta":
        from backend.agent.orchestrator import self_description

        return {"answer": self_description(), "citations": [], "market": None, "error": None}

    if route == "market":
        query = str(route_raw.get("market_query") or question)
        try:
            hits = await polymarket.search_markets(query, limit=1)
        except Exception:
            hits = []
        if not hits:
            return {
                "answer": (
                    f"I couldn't find an active Polymarket market for *{query}* — "
                    "try naming the market more specifically or paste its URL."
                ),
                "citations": [], "market": None, "error": None,
            }
        slug = hits[0]["slug"]
        result = await market_chat.chat(slug, question, history)
        result["market"] = {"slug": slug, "question": hits[0].get("question", slug)}
        return result

    if route == "portfolio":
        facts = await asyncio.to_thread(_portfolio_facts)
        answer_raw = await ctx.call_llm(
            MODULE,
            load_prompt("desk_chat"),
            json.dumps(
                {"time": time_context(None), "facts": facts,
                 "chat_history": recent, "question": question},
                ensure_ascii=False, default=str,
            ),
        )
        answer = str(answer_raw.get("answer", "")) if isinstance(answer_raw, dict) else str(answer_raw)
        return {"answer": answer, "citations": [], "market": None, "error": None}

    # out_of_scope (or an unrecognized route): friendly refusal + suggestions
    from backend.agent.orchestrator import REFUSAL_DEFAULT, suggest_markets

    keywords = [k for k in (route_raw.get("topic_keywords") or []) if isinstance(k, str)]
    reason = str(route_raw.get("reason") or REFUSAL_DEFAULT)
    return {
        "answer": reason + await suggest_markets(keywords),
        "citations": [], "market": None, "error": None,
    }
