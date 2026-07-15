"""The conversational layer: MarketChat + DeskChat.

MarketChat (POST /api/market/chat) — grounded Q&A on ONE market, at most 2
LLM calls per question:
1. plan (prompts/market_chat_planner.txt): does the question need fresh
   intelligence, and which search queries?
2. gather (deterministic, same fetchers the pipeline tools use): Google News
   + DuckDuckGo web search per query, socials (Polymarket comments, Bluesky,
   Reddit). Found articles are INDEXED into Supabase tagged with the market
   slug (embedded=False) — the NewsIndexer embeds them into Pinecone on its
   next pass, so chat discoveries feed future dossiers too.
3. answer (prompts/market_chat.txt): market state + dossier + gathered
   sources + chat history -> answer with citations.

DeskChat (POST /api/chat) — the global entry point. One router LLM call
classifies the question, then:
- market       -> resolve via Gamma search and delegate to MarketChat
- portfolio    -> deterministic fact-gathering from Supabase + one grounded
                 answer call
- meta         -> the registry-built self-description (zero further calls)
- out_of_scope -> friendly refusal + suggested Polymarket markets (zero LLM)
"""

from __future__ import annotations

import asyncio
import json
from typing import Optional

from backend import config
from backend.agent import intel_cache
from backend.agent.council import time_context
from backend.data import news, polymarket, social, supabase_client
from backend.llm.client import RunContext, load_prompt

MARKET_CHAT = "MarketChat"
DESK_CHAT = "DeskChat"


# ---------------------------------------------------------------------------
# MarketChat: context assembly
# ---------------------------------------------------------------------------


def _dossier_context(payload: Optional[dict]) -> Optional[dict]:
    """Slim dossier context for the answer call (drop history/steps bloat)."""
    if not payload:
        return None
    ui = payload.get("ui") or {}
    age_min = max(0, int(intel_cache._age_s(payload.get("created_at", "")) // 60))
    news_items = [
        {k: c.get(k) for k in ("id", "headline", "source", "date", "url", "sentiment", "stance", "excerpt")}
        for c in (ui.get("news") or [])
    ]
    return {
        "age_minutes": age_min,
        "verdict": ui.get("verdict"),
        "council": ui.get("council"),
        "news_clusters": news_items,
        "social_note": (ui.get("social") or {}).get("note"),
    }


def _market_context(market) -> dict:
    m = market.model_dump()
    m.pop("price_history_7d", None)  # hundreds of points — noise for Q&A
    m.pop("yes_token_id", None)
    return m


def _clip_history(history: list[dict]) -> list[dict]:
    turns = [
        {
            "role": "user" if str(t.get("role")) == "user" else "assistant",
            "content": str(t.get("content", ""))[: config.CHAT_MAX_HISTORY_CHARS],
        }
        for t in history
        if t.get("content")
    ]
    return turns[-config.CHAT_MAX_HISTORY_TURNS :]


# ---------------------------------------------------------------------------
# MarketChat: gathering (deterministic tools)
# ---------------------------------------------------------------------------


async def _gather(slug: str, plan: dict, event_id: str) -> tuple[list[dict], list[dict], int]:
    """Run the planned searches. Returns (articles, social_posts, indexed_count)."""
    news_queries = [q for q in (plan.get("news_queries") or []) if isinstance(q, str) and q.strip()][:2]
    social_query = plan.get("social_query")

    tasks: list = []
    for q in news_queries:
        tasks.append(news.google_news_articles(q, max_records=config.CHAT_NEWS_RESULTS))
        if config.WEB_SEARCH_ENABLED:
            tasks.append(news.web_search(q, max_results=config.CHAT_WEB_RESULTS))
    social_task = (
        social.gather_social(event_id, str(social_query), limit=config.CHAT_SOCIAL_POSTS)
        if social_query
        else None
    )
    if social_task is not None:
        tasks.append(social_task)

    results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []

    posts: list[dict] = []
    by_url: dict[str, dict] = {}
    for res in results:
        if isinstance(res, Exception):
            continue
        if isinstance(res, dict):  # social payload
            posts = res.get("posts") or []
            continue
        for a in res or []:
            by_url.setdefault(a["url"], a)
    articles = list(by_url.values())

    # read the top pages so answers cite substance, not headlines
    if articles:
        texts = await asyncio.gather(
            *(
                news.fetch_article_text(a["url"], max_chars=config.EXCERPT_MAX_CHARS)
                for a in articles[:3]
            )
        )
        for article, text in zip(articles[:3], texts):
            article["excerpt"] = text

    # index what was found: tagged with this market, embedded on the news
    # indexer's next pass
    indexed = 0
    if articles:
        try:
            indexed = await asyncio.to_thread(
                supabase_client.upsert_articles,
                [{**a, "entities": [slug]} for a in articles],
            )
        except Exception:
            indexed = 0
    return articles, posts, indexed


# ---------------------------------------------------------------------------
# MarketChat: entry point
# ---------------------------------------------------------------------------


async def market_chat(slug: str, question: str, history: list[dict]) -> dict:
    """Answer one chat question about `slug`. Never raises for expected cases."""
    ctx = RunContext()
    question = question.strip()[: config.CHAT_MAX_QUESTION_CHARS]
    if not question:
        return {"answer": None, "citations": [], "error": "empty question"}

    market = await polymarket.get_market_state(slug)
    dossier_payload = await asyncio.to_thread(
        intel_cache.get, slug, config.CHAT_DOSSIER_MAX_AGE_S
    )
    if market is None and not dossier_payload:
        return {
            "answer": None,
            "citations": [],
            "error": f"no market found for {slug!r} and no dossier on file",
        }

    market_ctx = _market_context(market) if market else (dossier_payload.get("ui") or {}).get("market") or {}
    dossier_ctx = _dossier_context(dossier_payload)

    # 1. plan — does this question need fresh intel?
    if dossier_ctx:
        held = (
            f"dossier: {dossier_ctx['age_minutes']} min old, "
            f"{len(dossier_ctx['news_clusters'])} news clusters"
        )
    else:
        held = "dossier: none"
    plan_input = json.dumps(
        {
            "market_question": market_ctx.get("question", slug),
            "resolution_criteria": (market_ctx.get("resolution_criteria") or "")[:400],
            "time": time_context(market_ctx.get("end_date")),
            "user_question": question,
            "held_context": held,
        },
        ensure_ascii=False,
    )
    plan = await ctx.call_llm(MARKET_CHAT, load_prompt("market_chat_planner"), plan_input)
    if not isinstance(plan, dict):
        plan = {"needs_fresh_intel": False, "news_queries": [], "social_query": None}

    # 2. gather + index
    articles: list[dict] = []
    posts: list[dict] = []
    indexed = 0
    if plan.get("needs_fresh_intel"):
        articles, posts, indexed = await _gather(slug, plan, market_ctx.get("event_id", ""))

    # 3. answer, grounded in everything held + gathered
    answer_input = json.dumps(
        {
            "time": time_context(market_ctx.get("end_date")),
            "market": market_ctx,
            "dossier": dossier_ctx,
            "fresh_articles": [
                {k: a.get(k) for k in ("title", "url", "domain", "published_at", "excerpt")}
                for a in articles
            ],
            "social_posts": [
                {"text": str(p.get("text", ""))[:280], "source": p.get("source"), "url": p.get("url")}
                for p in posts
            ],
            "chat_history": _clip_history(history),
            "question": question,
        },
        ensure_ascii=False,
    )
    result = await ctx.call_llm(MARKET_CHAT, load_prompt("market_chat"), answer_input)
    answer = str(result.get("answer", "")) if isinstance(result, dict) else str(result)
    citations = result.get("citations") if isinstance(result, dict) else []
    if not isinstance(citations, list):
        citations = []

    return {
        "answer": answer,
        "citations": [
            {"title": str(c.get("title", ""))[:200], "url": str(c.get("url", ""))}
            for c in citations
            if isinstance(c, dict) and c.get("url")
        ],
        "gathered": {
            "searched": bool(plan.get("needs_fresh_intel")),
            "queries": (plan.get("news_queries") or [])[:2],
            "articles": len(articles),
            "articles_indexed": indexed,
            "social_posts": len(posts),
        },
        "dossier_age_min": dossier_ctx["age_minutes"] if dossier_ctx else None,
        "error": None,
    }


# ---------------------------------------------------------------------------
# DeskChat: portfolio facts (deterministic)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# DeskChat: entry point
# ---------------------------------------------------------------------------


async def desk_chat(question: str, history: list[dict]) -> dict:
    """Answer one global chat question. Never raises for expected cases."""
    ctx = RunContext()
    question = question.strip()[: config.CHAT_MAX_QUESTION_CHARS]
    if not question:
        return {"answer": None, "citations": [], "market": None, "error": "empty question"}

    recent = _clip_history(history)

    route_raw = await ctx.call_llm(
        DESK_CHAT,
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
        result = await market_chat(slug, question, history)
        result["market"] = {"slug": slug, "question": hits[0].get("question", slug)}
        return result

    if route == "portfolio":
        facts = await asyncio.to_thread(_portfolio_facts)
        answer_raw = await ctx.call_llm(
            DESK_CHAT,
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
