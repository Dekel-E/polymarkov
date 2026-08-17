"""Conversational layer: MarketChat, DeskChat, StrategyChat."""

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


def _dossier_context(payload: Optional[dict]) -> Optional[dict]:
    """Slim dossier context for the answer call."""
    if not payload:
        return None
    ui = payload.get("ui") or {}
    age_min = max(0, int(intel_cache._age_s(payload.get("created_at", "")) // 60))
    news_items = [
        {k: c.get(k) for k in ("id", "headline", "source", "date", "url", "sentiment", "stance", "excerpt")}
        for c in (ui.get("news") or [])
    ]
    social = ui.get("social") or {}
    return {
        "age_minutes": age_min,
        "verdict": ui.get("verdict"),
        "council": ui.get("council"),
        "news_clusters": news_items,
        "social_note": social.get("note"),
        "social_pulse": {
            k: social.get(k) for k in ("score", "volume", "bullish", "bearish", "neutral")
            if social.get(k) is not None
        } or None,
        "paper_fill": ui.get("fill"),
        # The rendered dossier carries the blocks the ui payload has no slot for
        # — precedents, cross-venue, microstructure, smart money. Without it the
        # chat can only see the verdict and council, and answers "the analysis
        # doesn't cover that" for sections that in fact ran.
        "analysis_markdown": (payload.get("response") or "")[: config.CHAT_DOSSIER_MD_CHARS] or None,
    }


def _price_history_summary(history) -> Optional[dict]:
    """First/last/min/max of the 7d (ts, price) series. The full series is far
    too noisy to carry into a prompt, but dropping it entirely makes the chat
    blind to "why did this move?" — the shape is what the question is about."""
    points: list[float] = []
    for row in history or []:
        if isinstance(row, (list, tuple)) and len(row) == 2:
            price = row[1]
        elif isinstance(row, (int, float)):  # bare price series
            price = row
        else:
            continue
        if isinstance(price, (int, float)):
            points.append(float(price))
    if not points:
        return None
    return {
        "points": len(points),
        "start": round(points[0], 4),
        "latest": round(points[-1], 4),
        "min": round(min(points), 4),
        "max": round(max(points), 4),
        "change_pts": round((points[-1] - points[0]) * 100, 2),
    }


def _market_context(market) -> dict:
    m = market.model_dump()
    m["price_history_7d_summary"] = _price_history_summary(m.pop("price_history_7d", None))
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
    # keyless RSS + Wikipedia fallback, indexed with the news below
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

    # read the top pages so answers cite substance, not headlines
    async def _excerpt(article: dict) -> str:
        if article.get("fetched_text"):
            return article["fetched_text"][: config.EXCERPT_MAX_CHARS]
        return await news.fetch_article_text(article["url"], max_chars=config.EXCERPT_MAX_CHARS)

    if articles:
        texts = await asyncio.gather(*(_excerpt(a) for a in articles[:3]))
        for article, text in zip(articles[:3], texts):
            article["excerpt"] = text

    # index what was found, tagged with this market
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


async def market_chat(
    slug: str,
    question: str,
    history: list[dict],
    resolved_question: Optional[str] = None,
) -> dict:
    """Answer one chat question about `slug`. Never raises for expected cases.

    `resolved_question` is the router's pronoun-resolved reading of the message
    ("the other candidate" -> "Newsom 2028 nomination"); it steers the search
    planner while the user's literal words still drive the answer.
    """
    ctx = RunContext()
    question = question.strip()[: config.CHAT_MAX_QUESTION_CHARS]
    if not question:
        return {"answer": None, "citations": [], "error": "empty question"}
    recent = _clip_history(history)

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

    # 1. plan: does this question need fresh intel?
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
            # A follow-up ("and last week?", "what about the other one?") is
            # unplannable in isolation — the planner needs the same history the
            # answer call gets, or it writes searches for the wrong subject.
            "chat_history": recent,
            "resolved_question": resolved_question,
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

    # 3. answer, grounded in everything held and gathered
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
            "chat_history": recent,
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


def _portfolio_facts() -> dict:
    """Everything the desk knows about itself, trimmed for one prompt."""
    from backend.sim.portfolio import get_portfolio

    p = get_portfolio()
    open_rows = [
        # `id` is what makes a position closeable from chat — without it the
        # model can name a position it has no way to act on.
        {k: r.get(k) for k in ("id", "market_id", "side", "strategy", "size_usd",
                               "entry_price", "current_price", "unrealized_pnl",
                               "sl_price", "tp_price", "opened_at")}
        for r in p["open"][:20]
    ]
    resolved = [
        {k: r.get(k) for k in ("market_id", "side", "strategy", "size_usd",
                               "pnl", "resolved_outcome", "resolved_at")}
        for r in p["resolved"][:20]
    ]
    runs = [
        {k: r.get(k) for k in ("market_id", "verdict", "fair_prob", "mid_at_run", "created_at")}
        for r in supabase_client.get_recent_runs(10)
    ]
    briefing = supabase_client.latest_briefing()

    # equity curve: the endpoints and extremes answer "how are we doing over
    # time?" without pouring 90 daily rows into the prompt
    curve = p.get("equity_history") or []
    equity = None
    if curve:
        values = [float(r.get("equity_usd") or 0) for r in curve]
        equity = {
            "points": len(curve),
            "first": {"at": curve[0].get("captured_at"), "equity_usd": values[0]},
            "latest": {"at": curve[-1].get("captured_at"), "equity_usd": values[-1]},
            "min_usd": round(min(values), 2),
            "max_usd": round(max(values), 2),
            "change_usd": round(values[-1] - values[0], 2),
        }

    try:
        from backend.agent.report_card import get_report_card

        card = get_report_card()
        report_card = {
            k: card.get(k) for k in ("total_runs", "verdicts", "avg_latency_s", "calibration")
        }
    except Exception:  # noqa: BLE001 — self-knowledge is best-effort like every source
        report_card = None

    try:
        watchlist = supabase_client.get_watchlist()[:20]
    except Exception:  # noqa: BLE001
        watchlist = []

    return {
        "stats": p["stats"],
        "open_positions": open_rows,
        "recent_resolved": resolved,
        "equity_curve": equity,
        "report_card": report_card,
        "settings": supabase_client.get_agent_settings(),
        "recent_analyses": runs,
        "pending_agenda": supabase_client.get_pending_agenda(8),
        "watchlist": watchlist,
        "latest_briefing": (briefing or {}).get("content", "")[:1200] or None,
    }


def _settings_diff(before: dict, after: dict) -> dict:
    """Flat old->new map of what actually changed.

    The halt section reports only `active`; reason/at are bookkeeping that
    would inflate one user action into three changes.
    """
    diff: dict = {}
    for section in ("strategies", "risk", "halt", "funds"):
        b, a = before.get(section) or {}, after.get(section) or {}
        keys = ("active",) if section == "halt" else a.keys()
        for key in keys:
            if a.get(key) != b.get(key):
                diff[f"{section}.{key}"] = {"from": b.get(key), "to": a.get(key)}
    return diff


async def strategy_chat(question: str, history: list[dict]) -> dict:
    """One Strategy Desk chat turn. Applies any instructed settings change,
    whitelisted and clamped by code. Never raises for expected cases."""
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
            except Exception:  # noqa: BLE001
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


async def _resolve_slug(query: str, slug: Optional[str]) -> Optional[str]:
    """The current market (slug context) wins; else search for the named one."""
    if slug:
        return slug
    if not query.strip():
        return None
    try:
        hits = await polymarket.search_markets(query, limit=1)
    except Exception:
        hits = []
    return hits[0]["slug"] if hits else None


async def _halt_reason() -> Optional[str]:
    settings = await asyncio.to_thread(supabase_client.get_agent_settings)
    halt = settings.get("halt") or {}
    if halt.get("active"):
        return str(halt.get("reason") or "no reason recorded")
    return None


async def _pending_action(action_type: str, payload: dict, summary: str, market: dict) -> dict:
    try:
        row = await asyncio.to_thread(
            supabase_client.create_chat_action, action_type, payload
        )
    except Exception:
        return {
            "answer": (
                "I couldn't create a durable confirmation. No action was taken. "
                "Install migration 0018 and try again."
            ),
            "citations": [], "market": market, "error": None,
        }
    return {
        "answer": f"Ready for confirmation: **{summary}**. Nothing has been changed yet.",
        "citations": [],
        "market": market,
        "pending_action": {
            "token": str(row["token"]),
            "action_type": action_type,
            "summary": summary,
            "expires_at": row.get("expires_at"),
        },
        "error": None,
    }


async def _desk_trade(route_raw: dict, slug: Optional[str]) -> dict:
    """Resolve an exact paper trade and persist it for explicit confirmation."""
    query = str(route_raw.get("market_query") or "")
    target = await _resolve_slug(query, slug)
    if not target:
        return {"answer": f"I couldn't find a market to trade for *{query or 'that'}* — "
                "name it more specifically or open its page and try again.",
                "citations": [], "market": None, "error": None}
    side = route_raw.get("side")
    if side not in ("BUY_YES", "BUY_NO"):
        return {"answer": "Tell me which side — **BUY YES** or **BUY NO** — and I'll place the paper trade.",
                "citations": [], "market": None, "error": None}

    reason = await _halt_reason()
    if reason:
        return {"answer": f"Trading is halted ({reason}) — no paper trade was placed. "
                          "Say **resume trading** to lift the circuit breaker first.",
                "citations": [], "market": None, "error": None}

    try:
        size_usd = float(route_raw.get("size_usd") or config.CHAT_DEFAULT_TRADE_USD)
    except (TypeError, ValueError):
        size_usd = config.CHAT_DEFAULT_TRADE_USD
    size_usd = max(1.0, min(size_usd, config.CHAT_MAX_TRADE_USD))

    market = await polymarket.get_market_state(target)
    if market is None:
        return {"answer": f"No live market found for `{target}`.", "citations": [], "market": None, "error": None}

    market_ref = {"slug": target, "question": market.question}
    summary = f"{side.replace('_', ' ')} ${size_usd:.2f} on {market.question}"
    return await _pending_action(
        "trade",
        {"slug": target, "side": side, "size_usd": size_usd, "question": market.question},
        summary,
        market_ref,
    )


async def _execute_trade_action(payload: dict) -> dict:
    """Execute one already-claimed trade action against a fresh live book."""
    reason = await _halt_reason()
    if reason:
        return {
            "answer": f"Trading is halted ({reason}) — no paper trade was placed.",
            "citations": [], "market": None, "error": None,
        }

    target = str(payload.get("slug") or "")
    side = payload.get("side")
    size_usd = float(payload.get("size_usd") or 0)
    if not target or side not in ("BUY_YES", "BUY_NO") or size_usd <= 0:
        return {"answer": "That confirmation payload is invalid. No trade was placed.",
                "citations": [], "market": None, "error": None}
    market = await polymarket.get_market_state(target)
    if market is None:
        return {"answer": f"No live market found for `{target}`.", "citations": [], "market": None, "error": None}

    from backend.agent.types import PricingResult
    from backend.sim import paper_broker

    priced = PricingResult(
        prior=market.mid, fair=market.mid, fair_adj=market.mid,
        gross_edge_pts=0.0, half_spread=(market.spread or 0) / 2, taker_fee=0.0,
        net_edge_pts=0.0, verdict=side, suggested_size_pct_bankroll=0.0,
        resolution_risk="medium",
    )
    ctx = RunContext()
    fill = await paper_broker.execute_paper_trade(ctx, market, priced, size_usd=size_usd, strategy="manual")
    market_ref = {"slug": target, "question": market.question}
    if fill is None:
        return {"answer": "The order book had no fillable liquidity, so no paper trade was opened.",
                "citations": [], "market": market_ref, "error": None}
    f = fill.model_dump()
    answer = (
        f"✅ Paper trade filled: **{side.replace('_', ' ')}** ${f['size_usd']:.2f} on "
        f"*{market.question}* at {f['vwap'] * 100:.1f}% "
        f"(slippage {f['slippage_bps']:.0f} bps · fee ${f['fee_paid']:.2f}). "
        "Paper trading only — not financial advice."
    )
    return {"answer": answer, "citations": [], "market": market_ref, "fill": f, "error": None}


async def _desk_analyze(route_raw: dict, slug: Optional[str]) -> dict:
    """Run the real analysis pipeline and hand back the dossier.

    Before this route existed, "run a full analysis on X" classified as `market`
    and came back as a news summary with no verdict, no fair value and no sign
    that the council had never actually run.
    """
    query = str(route_raw.get("market_query") or "")
    target = await _resolve_slug(query, slug)
    if not target:
        return {"answer": f"I couldn't find a market to analyze for *{query or 'that'}* — "
                "name it more specifically or paste its Polymarket URL.",
                "citations": [], "market": None, "error": None}

    from backend.agent.orchestrator import run_pipeline

    # `Market: <slug>` is the templated form intel_cache.slug_from_prompt reads,
    # so a fresh dossier is served from cache with zero LLM calls.
    out = await run_pipeline(f"Market: {target}\nTrade: no")
    if out.status != "ok" or not out.response:
        return {"answer": f"The analysis failed: {out.error or 'unknown error'}",
                "citations": [], "market": {"slug": target, "question": target}, "error": None}

    ui = out.ui or {}
    market_ref = {"slug": target, "question": (ui.get("market") or {}).get("question", target)}
    return {
        "answer": out.response,
        "citations": [
            {"title": str(c.get("headline", ""))[:200], "url": str(c.get("url", ""))}
            for c in (ui.get("news") or [])[:8]
            if isinstance(c, dict) and c.get("url")
        ],
        "market": market_ref,
        "analyzed": {"slug": target, "verdict": (ui.get("verdict") or {}).get("verdict")},
        "error": None,
    }


async def _desk_close(route_raw: dict, slug: Optional[str]) -> dict:
    """Resolve an exact open position and persist a close confirmation."""
    from backend.sim.portfolio import get_portfolio

    portfolio = await asyncio.to_thread(get_portfolio)
    open_rows = portfolio.get("open") or []
    if not open_rows:
        return {"answer": "There are no open paper positions to close.",
                "citations": [], "market": None, "error": None}

    query = str(route_raw.get("market_query") or "")
    target = slug or None
    if not target and query:
        target = await _resolve_slug(query, None)
    matches = [r for r in open_rows if r.get("market_id") == target] if target else []
    if not matches:
        names = ", ".join(sorted({str(r.get("market_id")) for r in open_rows})[:8])
        return {"answer": f"I couldn't match *{query or target or 'that'}* to an open position. "
                          f"Currently open: {names}.",
                "citations": [], "market": None, "error": None}

    try:
        fraction = float(route_raw.get("fraction") or 1.0)
    except (TypeError, ValueError):
        fraction = 1.0
    fraction = max(0.01, min(1.0, fraction))

    # Several rows can share a market (different strategies); close the largest
    # rather than guessing, and say so.
    position = max(matches, key=lambda r: float(r.get("size_usd") or 0))
    market_ref = {"slug": str(position["market_id"]), "question": str(position["market_id"])}
    portion = "all" if fraction >= 0.999 else f"{fraction * 100:.0f}%"
    summary = (
        f"close {portion} of {position.get('side', '')} ${float(position.get('size_usd') or 0):.2f} "
        f"on {position['market_id']}"
    )
    return await _pending_action(
        "close",
        {
            "position_id": str(position["id"]),
            "fraction": fraction,
            "market_id": str(position["market_id"]),
            "side": str(position.get("side") or ""),
            "matching_positions": len(matches),
        },
        summary,
        market_ref,
    )


async def _execute_close_action(payload: dict) -> dict:
    from backend.sim import paper_broker

    position_id = str(payload.get("position_id") or "")
    fraction = max(0.01, min(1.0, float(payload.get("fraction") or 1.0)))
    market_id = str(payload.get("market_id") or "")
    side = str(payload.get("side") or "")
    market_ref = {"slug": market_id, "question": market_id}
    if not position_id or not market_id:
        return {"answer": "That confirmation payload is invalid. No position was closed.",
                "citations": [], "market": None, "error": None}
    report = await paper_broker.close_position(position_id, fraction=fraction)
    if report.get("error"):
        return {"answer": f"Couldn't close that position: {report['error']}.",
                "citations": [], "market": market_ref, "error": None}

    pnl = float(report.get("pnl") or 0)
    portion = "in full" if fraction >= 0.999 else f"{fraction * 100:.0f}% of it"
    count = int(payload.get("matching_positions") or 0)
    extra = f" ({count} positions share this market — I closed the largest.)" if count > 1 else ""
    return {
        "answer": (
            f"✅ Closed {portion}: **{side}** on *{market_id}* "
            f"at {float(report.get('exit_price') or 0) * 100:.1f}% — "
            f"realized PnL **{'+' if pnl >= 0 else '-'}${abs(pnl):,.2f}**.{extra} "
            "Paper trading only — not financial advice."
        ),
        "citations": [], "market": market_ref,
        "closed": {"position_id": position_id, "fraction": fraction, "pnl": pnl},
        "error": None,
    }


async def decide_chat_action(token: str, decision: str) -> dict:
    """Confirm/cancel once; retries receive the original stored result."""
    try:
        action = await asyncio.to_thread(supabase_client.claim_chat_action, token)
    except Exception:
        return {"answer": "Confirmation storage is unavailable. No action was taken.",
                "citations": [], "market": None, "error": None}

    status = action.get("status")
    if not action.get("claimed"):
        stored = action.get("result")
        if status == "completed" and isinstance(stored, dict):
            return {**stored, "idempotent_replay": True}
        if status == "processing":
            return {"answer": "This action is already being processed. It will not run twice.",
                    "citations": [], "market": None, "error": None, "idempotent_replay": True}
        if status == "cancelled":
            reason = stored.get("reason") if isinstance(stored, dict) else None
            answer = "This confirmation expired. No action was taken." if reason == "expired" else "This action was already cancelled."
            return {"answer": answer, "citations": [], "market": None, "error": None,
                    "idempotent_replay": True}
        if status == "failed" and isinstance(stored, dict):
            return {**stored, "idempotent_replay": True}
        return {"answer": "That confirmation was not found. No action was taken.",
                "citations": [], "market": None, "error": None}

    if decision == "cancel":
        result = {"answer": "Cancelled. No action was taken.", "citations": [], "market": None, "error": None}
        await asyncio.to_thread(supabase_client.finish_chat_action, token, "cancelled", result)
        return result

    payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
    try:
        if action.get("action_type") == "trade":
            result = await _execute_trade_action(payload)
        elif action.get("action_type") == "close":
            result = await _execute_close_action(payload)
        else:
            result = {"answer": "Unknown action type. No action was taken.",
                      "citations": [], "market": None, "error": None}
        await asyncio.to_thread(supabase_client.finish_chat_action, token, "completed", result)
        return result
    except Exception as exc:
        result = {"answer": f"The action failed before completion: {exc}",
                  "citations": [], "market": None, "error": None}
        try:
            await asyncio.to_thread(supabase_client.finish_chat_action, token, "failed", result)
        except Exception:
            pass
        return result


async def _desk_watchlist(route_raw: dict, slug: Optional[str]) -> dict:
    """Add/remove a market from the desk's watchlist immediately."""
    query = str(route_raw.get("market_query") or "")
    target = await _resolve_slug(query, slug)
    if not target:
        return {"answer": f"I couldn't find a market to watch for *{query or 'that'}*.",
                "citations": [], "market": None, "error": None}
    action = "remove" if route_raw.get("watch_action") == "remove" else "add"
    if action == "remove":
        await asyncio.to_thread(supabase_client.remove_watch, target)
        answer = f"Removed **{target}** from the watchlist."
    else:
        await asyncio.to_thread(supabase_client.add_watch, target)
        answer = (f"Added **{target}** to the watchlist — the desk will re-analyze it "
                  "as its dossier cache expires.")
    return {"answer": answer, "citations": [], "market": {"slug": target, "question": target},
            "watchlisted": {"slug": target, "action": action}, "error": None}


async def desk_chat(question: str, history: list[dict], slug: Optional[str] = None) -> dict:
    """Answer one global chat question. `slug` is the market the user is viewing
    (if any) so "buy $50 yes" / "watch this" / "what's the latest?" scope to it.
    Never raises for expected cases."""
    ctx = RunContext()
    question = question.strip()[: config.CHAT_MAX_QUESTION_CHARS]
    if not question:
        return {"answer": None, "citations": [], "market": None, "error": "empty question"}

    recent = _clip_history(history)

    router_input: dict = {"question": question, "chat_history": recent}
    if slug:
        router_input["CURRENT_MARKET"] = slug
    route_raw = await ctx.call_llm(
        DESK_CHAT,
        load_prompt("desk_chat_router"),
        json.dumps(router_input, ensure_ascii=False),
    )
    route_raw = route_raw if isinstance(route_raw, dict) else {}
    route = route_raw.get("route")

    if route == "meta":
        from backend.agent.orchestrator import self_description

        return {"answer": self_description(), "citations": [], "market": None, "error": None}

    if route == "trade":
        return await _desk_trade(route_raw, slug)

    if route == "analyze":
        return await _desk_analyze(route_raw, slug)

    if route == "close":
        return await _desk_close(route_raw, slug)

    if route == "watchlist":
        return await _desk_watchlist(route_raw, slug)

    if route == "market":
        # On a market page, answer about the market in view without re-searching;
        # otherwise search and keep the matched market's question.
        query = str(route_raw.get("market_query") or question)
        if slug:
            target = slug
            # Resolve the real title rather than showing the raw slug back.
            live = await polymarket.get_market_state(slug)
            market_question = live.question if live is not None else slug
        else:
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
            target = hits[0]["slug"]
            market_question = hits[0].get("question", target)
        # `recent`, not raw history: the router saw 8 clipped turns and the
        # sub-module must reason over the same window. `query` is the router's
        # pronoun-resolved reading, which is what makes follow-ups searchable.
        result = await market_chat(target, question, recent, resolved_question=query)
        result["market"] = {"slug": target, "question": market_question}
        return result

    if route == "control":
        result = await strategy_chat(question, recent)
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

    # out_of_scope or unrecognized route: refusal plus suggestions
    from backend.agent.orchestrator import REFUSAL_DEFAULT, suggest_markets

    keywords = [k for k in (route_raw.get("topic_keywords") or []) if isinstance(k, str)]
    reason = str(route_raw.get("reason") or REFUSAL_DEFAULT)
    return {
        "answer": reason + await suggest_markets(keywords),
        "citations": [], "market": None, "error": None,
    }
