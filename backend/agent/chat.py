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
- control      -> delegate to StrategyChat (instructions become a settings
                 patch, whitelisted + clamped by code)
- meta         -> the registry-built self-description (zero further calls)
- out_of_scope -> friendly refusal + suggested Polymarket markets (zero LLM)

StrategyChat (POST /api/strategy/chat) — the Strategy Desk control channel,
also reachable through DeskChat's control route. ONE LLM call per turn.
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
STRATEGY_CHAT = "StrategyChat"


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


async def _gather(
    slug: str, plan: dict, event_id: str, category: str = "other"
) -> tuple[list[dict], list[dict], int]:
    """Run the planned searches. Returns (articles, social_posts, indexed_count)."""
    news_queries = [q for q in (plan.get("news_queries") or []) if isinstance(q, str) and q.strip()][:2]
    social_query = plan.get("social_query")

    tasks: list = []
    for q in news_queries:
        tasks.append(news.google_news_articles(q, max_records=config.CHAT_NEWS_RESULTS))
        if config.WEB_SEARCH_ENABLED:
            tasks.append(news.web_search(q, max_results=config.CHAT_WEB_RESULTS))
    # curated RSS + Wikipedia on the first query (keyless, work where GDELT
    # is IP-blocked); both get indexed with the news below
    if news_queries:
        if config.RSS_ENABLED:
            tasks.append(news.rss_articles(news_queries[0], news.rss_feeds_for(category)))
        if config.WIKI_ENABLED:
            tasks.append(news.wikipedia_articles(news_queries[0]))
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

    # top up socials from the RedditIndexer's warm cache for this market
    if len(posts) < config.CHAT_SOCIAL_POSTS:
        seen_posts = {p.get("url") for p in posts if p.get("url")}
        for row in await asyncio.to_thread(
            supabase_client.get_social_posts_for, slug, config.CHAT_SOCIAL_POSTS
        ):
            if row["url"] in seen_posts:
                continue
            posts.append({"text": row["text"], "source": row["source"], "url": row["url"]})
            if len(posts) >= config.CHAT_SOCIAL_POSTS:
                break

    # read the top pages so answers cite substance, not headlines (Wikipedia
    # already carries its intro text, so it is used verbatim, not re-crawled)
    async def _excerpt(article: dict) -> str:
        if article.get("fetched_text"):
            return article["fetched_text"][: config.EXCERPT_MAX_CHARS]
        return await news.fetch_article_text(article["url"], max_chars=config.EXCERPT_MAX_CHARS)

    if articles:
        texts = await asyncio.gather(*(_excerpt(a) for a in articles[:3]))
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
        articles, posts, indexed = await _gather(
            slug, plan, market_ctx.get("event_id", ""), market_ctx.get("category", "other")
        )

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
# StrategyChat: natural-language control of the Strategy Desk
# ---------------------------------------------------------------------------


def _settings_diff(before: dict, after: dict) -> dict:
    """Flat old->new map of what actually changed (ground truth for the UI).
    The halt section reports only `active` — reason/at are bookkeeping that
    would inflate one user action into three 'changes'."""
    diff: dict = {}
    for section in ("strategies", "risk", "halt", "funds"):
        b, a = before.get(section) or {}, after.get(section) or {}
        keys = ("active",) if section == "halt" else a.keys()
        for key in keys:
            if a.get(key) != b.get(key):
                diff[f"{section}.{key}"] = {"from": b.get(key), "to": a.get(key)}
    return diff


async def strategy_chat(question: str, history: list[dict]) -> dict:
    """One Strategy Desk chat turn: answer, and apply any instructed settings
    change (whitelisted + clamped by code — the LLM proposes, code disposes).
    ONE LLM call per turn. Never raises for expected cases."""
    ctx = RunContext()
    question = question.strip()[: config.CHAT_MAX_QUESTION_CHARS]
    if not question:
        return {"answer": None, "applied": None, "settings": None, "error": "empty question"}

    from backend.sim.portfolio import get_portfolio
    from backend.sim.risk import realized_pnl_today

    before, portfolio, realized = await asyncio.gather(
        asyncio.to_thread(supabase_client.get_agent_settings),
        asyncio.to_thread(get_portfolio),
        asyncio.to_thread(realized_pnl_today),
    )
    stats = portfolio["stats"]
    payload = json.dumps(
        {
            "settings": before,
            "bounds": {"risk": config.RISK_BOUNDS, "bankroll_usd": config.BANKROLL_BOUNDS},
            "realized_today_usd": realized,
            "portfolio_stats": {
                k: stats.get(k)
                for k in (
                    "bankroll_usd", "equity_usd", "available_usd", "open_positions",
                    "open_exposure_usd", "unrealized_pnl_usd", "realized_pnl_usd",
                    "win_rate", "exposure_by_strategy",
                )
            },
            "chat_history": _clip_history(history),
            "question": question,
        },
        ensure_ascii=False,
        default=str,
    )
    try:
        raw = await ctx.call_llm(STRATEGY_CHAT, load_prompt("strategy_chat"), payload)
    except Exception as exc:  # noqa: BLE001
        return {"answer": None, "applied": None, "settings": None,
                "error": f"chat call failed: {type(exc).__name__}"}
    raw = raw if isinstance(raw, dict) else {}
    answer = str(raw.get("reply") or "").strip() or "(no reply)"

    applied = None
    settings = None
    patch = raw.get("patch")
    if isinstance(patch, dict) and patch:
        clean = supabase_client.sanitize_settings_patch(patch, allow_halt_activation=True)
        if clean:
            try:
                after = await asyncio.to_thread(supabase_client.update_agent_settings, clean)
            except Exception:  # noqa: BLE001 — keep the "never raises" contract
                return {
                    "answer": answer + "\n\n_(the settings write failed — nothing was changed; try again)_",
                    "applied": None, "settings": None, "error": None,
                }
            diff = _settings_diff(before, after)
            if diff:
                applied = diff
                settings = after
                lines = [
                    f"- `{key}`: {change['from']} → {change['to']}"
                    for key, change in diff.items()
                ]
                answer += "\n\n**Applied:**\n" + "\n".join(lines)
            else:
                answer += "\n\n_(no change — the settings already had these values)_"
        else:
            answer += "\n\n_(no change applied — the requested update was outside what I'm allowed to touch)_"

    return {"answer": answer, "applied": applied, "settings": settings, "error": None}


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

    if route == "control":
        # strategy-desk instruction: delegate to StrategyChat (its own LLM
        # call proposes the patch; code whitelists, clamps and applies it)
        result = await strategy_chat(question, history)
        return {**result, "citations": [], "market": None}

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
