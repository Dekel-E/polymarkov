"""Vercel serverless entrypoint. Thin: all real logic lives in backend/.

NOTE (course requirement): NO auth anywhere — no login, no signup, no
guards. GUI-directed actions (manual trades, watchlist, followed wallets)
belong to one shared anonymous desk (config.DESK_USER_ID); user_id NULL
remains the agent's own book.
"""

import asyncio
import sys
from pathlib import Path
from typing import Literal, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend import config  # noqa: E402
from backend.agent.orchestrator import run_pipeline  # noqa: E402
from backend.agent.types import ExecuteIn, ExecuteOut, PricingResult  # noqa: E402
from backend.data import polymarket, supabase_client  # noqa: E402

app = FastAPI(title="Polymarkov", docs_url=None, redoc_url=None)


@app.get("/api/team_info")
def team_info() -> dict:
    return config.TEAM_INFO


_EXAMPLES_FILE = config.ASSETS_DIR / "agent_examples.json"
_examples_cache: Optional[list] = None


def _load_examples() -> list:
    """Frozen real runs recorded by scripts/record_examples.py."""
    global _examples_cache
    if _examples_cache is None:
        try:
            import json

            _examples_cache = json.loads(_EXAMPLES_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _examples_cache = []
    return _examples_cache


@app.get("/api/agent_info")
def agent_info() -> dict:
    # Everything the agent can do lives in backend/agent/registry/ — tools.py
    # (formal module/tool specs) + prompts/*.txt (system prompts). Both are
    # read at runtime so these docs can never drift from behavior;
    # prompt_examples are frozen real runs (course schema).
    from backend.agent.registry import MODULES

    prompt_files = sorted(config.PROMPTS_DIR.glob("*.txt"))
    prompts = {p.stem: p.read_text(encoding="utf-8") for p in prompt_files}
    return {
        "name": "Polymarkov",
        "description": (
            "Polymarkov produces a pre-trade intelligence dossier for a Polymarket "
            "market: it resolves the market, gathers recent news (GDELT) and social "
            "chatter, scores sentiment, runs a four-persona AI council (BullAnalyst, "
            "BearAnalyst, QuantAnalyst, ResolutionSkeptic), computes a deterministic "
            "fair probability and net edge, and issues a BUY_YES / BUY_NO / PASS "
            "verdict with a fractional-Kelly position size. It can paper-trade the "
            "verdict against the live order book. It CANNOT trade real money, give "
            "guaranteed financial advice, or answer questions unrelated to "
            "prediction markets."
        ),
        "purpose": (
            "Pre-trade research assistant and paper-trading simulator for "
            "Polymarket prediction markets. Educational tool, not financial advice."
        ),
        "prompt_template": {
            "template": (
                "Market: <slug | url | free-text question>\n"
                "Focus: <news | socials | resolution | all>\n"
                "Trade: <yes | no>"
            ),
            "example": (
                "Market: fed-decision-in-september\nFocus: all\nTrade: no"
            ),
        },
        "prompt_examples": _load_examples(),
        "modules": config.CANONICAL_MODULES,
        "tools": MODULES,
        "prompts": prompts,
    }


@app.get("/api/model_architecture")
def model_architecture():
    if not config.ARCHITECTURE_PNG.exists():
        return JSONResponse(
            status_code=500,
            content={"error": "architecture.png not generated yet — run scripts/gen_architecture_png.py"},
        )
    return FileResponse(config.ARCHITECTURE_PNG, media_type="image/png")


# --- GUI support endpoints (not part of the graded four) ---------------------


_markets_cache: dict = {"ts": 0.0, "limit": 0, "markets": []}


@app.get("/api/markets")
async def markets(limit: int = 20) -> dict:
    """Trending markets for the GUI market browser (30s server cache)."""
    try:
        import time as _time

        limit = min(limit, 300)
        if _time.time() - _markets_cache["ts"] < 30 and _markets_cache["limit"] >= limit:
            return {"markets": _markets_cache["markets"][:limit], "error": None}
        rows = await polymarket.get_trending_markets(limit)
        _markets_cache.update(ts=_time.time(), limit=limit, markets=rows)
        return {"markets": rows, "error": None}
    except Exception as exc:
        return {"markets": [], "error": str(exc)}


@app.get("/api/portfolio")
async def portfolio() -> dict:
    """Paper positions + stats — one book (filter by strategy in the GUI)."""
    try:
        from backend.sim.portfolio import get_portfolio

        data = await asyncio.to_thread(get_portfolio)
        return {"portfolio": data, "error": None}
    except Exception as exc:
        return {"portfolio": None, "error": str(exc)}


@app.get("/api/search")
async def search(q: str, limit: int = 12) -> dict:
    """Text search over active Polymarket markets (Gamma public search)."""
    try:
        if not q.strip():
            return {"markets": [], "error": None}
        results = await polymarket.search_markets(q.strip(), limit=min(limit, 20))
        return {"markets": results, "error": None}
    except Exception as exc:
        return {"markets": [], "error": str(exc)}


@app.get("/api/league")
async def league(window: str = "30d") -> dict:
    """Smart Money League: top wallets by profit (Polymarket Data API)."""
    try:
        from backend.data import smart_money

        if window not in ("1d", "7d", "30d", "all"):
            window = "30d"
        rows = await smart_money.fetch_leaderboard(window=window, limit=20)
        return {"leaders": rows, "error": None}
    except Exception as exc:
        return {"leaders": [], "error": str(exc)}


@app.get("/api/league/wallet")
async def league_wallet(address: str) -> dict:
    """One wallet's current open positions."""
    try:
        from backend.data import smart_money

        return {"positions": await smart_money.fetch_wallet_positions(address), "error": None}
    except Exception as exc:
        return {"positions": [], "error": str(exc)}


@app.get("/api/agenda")
async def agenda() -> dict:
    """The agent's pending to-do list (filed by the sentinel)."""
    try:
        items = await asyncio.to_thread(supabase_client.get_pending_agenda, 12)
        return {"items": items, "error": None}
    except Exception as exc:
        return {"items": [], "error": str(exc)}


@app.get("/api/briefing")
async def briefing() -> dict:
    """The agent's latest morning briefing."""
    try:
        row = await asyncio.to_thread(supabase_client.latest_briefing)
        return {"briefing": row, "error": None}
    except Exception as exc:
        return {"briefing": None, "error": str(exc)}


@app.get("/api/activity")
async def activity(limit: int = 25) -> dict:
    """Chronological feed of what the agent did: analyses, trades, settles."""
    try:
        if not supabase_client.is_configured():
            return {"events": [], "error": None}

        def _collect() -> list[dict]:
            client = supabase_client.get_client()
            events: list[dict] = []
            for r in (
                client.table("runs").select("market_id,verdict,latency_ms,created_at")
                .order("created_at", desc=True).limit(15).execute().data or []
            ):
                events.append(
                    {"type": "analysis", "at": r["created_at"], "market_id": r.get("market_id"),
                     "verdict": r.get("verdict"), "latency_ms": r.get("latency_ms")}
                )
            for p in (
                client.table("positions").select("market_id,side,size_usd,strategy,opened_at")
                .order("opened_at", desc=True).limit(15).execute().data or []
            ):
                events.append(
                    {"type": "trade", "at": p["opened_at"], "market_id": p["market_id"],
                     "side": p["side"], "size_usd": p["size_usd"], "strategy": p.get("strategy")}
                )
            for p in (
                client.table("positions").select("market_id,resolved_outcome,pnl,resolved_at")
                .eq("status", "resolved").not_.is_("resolved_at", "null")
                .order("resolved_at", desc=True).limit(10).execute().data or []
            ):
                events.append(
                    {"type": "settle", "at": p["resolved_at"], "market_id": p["market_id"],
                     "outcome": p.get("resolved_outcome"), "pnl": p.get("pnl")}
                )
            events.sort(key=lambda e: e["at"] or "", reverse=True)
            return events[: min(limit, 50)]

        return {"events": await asyncio.to_thread(_collect), "error": None}
    except Exception as exc:
        return {"events": [], "error": str(exc)}


@app.get("/api/agent/stats")
async def agent_stats() -> dict:
    """Run history + calibration for the agent report card."""
    try:
        from backend.agent.report_card import get_report_card

        return {"stats": await asyncio.to_thread(get_report_card), "error": None}
    except Exception as exc:
        return {"stats": None, "error": str(exc)}


class WatchIn(BaseModel):
    market_id: str


@app.get("/api/watchlist")
async def watchlist() -> dict:
    """The desk's watched markets, enriched from the cache."""
    try:
        from backend.agent import intel_cache

        slugs = await asyncio.to_thread(supabase_client.get_watchlist)
        rows = []
        if slugs and supabase_client.is_configured():
            cached_markets = await asyncio.to_thread(
                lambda: supabase_client.get_client()
                .table("markets")
                .select("slug,question,last_mid,category")
                .in_("slug", slugs)
                .execute()
                .data
                or []
            )
            by_slug = {m["slug"]: m for m in cached_markets}
            for slug in slugs:
                m = by_slug.get(slug, {})
                dossier = intel_cache.get(slug)
                verdict = ((dossier or {}).get("ui") or {}).get("verdict") or {}
                rows.append(
                    {
                        "market_id": slug,
                        "question": m.get("question") or slug,
                        "last_mid": m.get("last_mid"),
                        "category": m.get("category") or "other",
                        "verdict": verdict.get("verdict"),
                        "fair_probability": verdict.get("fair_probability"),
                        "analyzed_at": (dossier or {}).get("created_at"),
                    }
                )
        return {"items": rows, "error": None}
    except Exception as exc:
        return {"items": [], "error": str(exc)}


@app.post("/api/watchlist")
async def watch(body: WatchIn) -> dict:
    try:
        await asyncio.to_thread(supabase_client.add_watch, body.market_id)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


@app.delete("/api/watchlist")
async def unwatch(market_id: str) -> dict:
    try:
        await asyncio.to_thread(supabase_client.remove_watch, market_id)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


class SettingsIn(BaseModel):
    strategies: Optional[dict] = None
    risk: Optional[dict] = None
    halt: Optional[dict] = None
    funds: Optional[dict] = None


_RISK_BOUNDS = {
    "stop_loss_pct": (5, 95),
    "take_profit_pct": (10, 500),
    "max_position_usd": (10, 2000),
    "max_open_positions": (1, 50),
    "daily_loss_halt_usd": (10, 5000),
}


@app.get("/api/settings")
async def get_settings() -> dict:
    """Strategy Desk state: strategy toggles, risk rules, breaker status."""
    try:
        settings = await asyncio.to_thread(supabase_client.get_agent_settings)
        from backend.sim.risk import realized_pnl_today

        realized = await asyncio.to_thread(realized_pnl_today)
        return {"settings": settings, "realized_today": realized, "error": None}
    except Exception as exc:
        return {"settings": None, "realized_today": 0, "error": str(exc)}


@app.put("/api/settings")
async def put_settings(body: SettingsIn) -> dict:
    """Partial update from the Strategy Desk (numbers clamped to sane bounds)."""
    try:
        patch: dict = {}
        if body.strategies is not None:
            patch["strategies"] = {
                k: bool(v)
                for k, v in body.strategies.items()
                if k in config.DEFAULT_AGENT_SETTINGS["strategies"]
            }
        if body.risk is not None:
            cleaned = {}
            for key, (lo, hi) in _RISK_BOUNDS.items():
                if key in body.risk:
                    try:
                        cleaned[key] = max(lo, min(hi, float(body.risk[key])))
                    except (TypeError, ValueError):
                        continue
            patch["risk"] = cleaned
        if body.halt is not None and body.halt.get("active") is False:
            patch["halt"] = {"active": False, "reason": "", "at": ""}  # manual resume
        if body.funds is not None and "bankroll_usd" in body.funds:
            try:
                patch["funds"] = {
                    "bankroll_usd": max(100.0, min(1_000_000.0, float(body.funds["bankroll_usd"])))
                }
            except (TypeError, ValueError):
                pass
        settings = await asyncio.to_thread(supabase_client.update_agent_settings, patch)
        return {"settings": settings, "error": None}
    except Exception as exc:
        return {"settings": None, "error": str(exc)}


@app.get("/api/market/news")
async def market_news(slug: str, limit: int = 10) -> dict:
    """Latest news relevant to ONE market: live Google News search on the
    market question, merged with indexer-tagged articles. Semantic matches
    only count above the relevance floor."""
    try:
        from backend.data import news

        limit = min(limit, 15)
        question = ""
        articles: list[dict] = []

        if supabase_client.is_configured():
            def _tagged() -> tuple[str, list[dict]]:
                client = supabase_client.get_client()
                rows = (
                    client.table("markets").select("question").eq("slug", slug).limit(1).execute().data
                )
                tagged = (
                    client.table("articles")
                    .select("title,url,domain,published_at")
                    .contains("entities", [slug])
                    .order("published_at", desc=True)
                    .limit(limit)
                    .execute()
                    .data
                    or []
                )
                return (rows[0]["question"] if rows else "", tagged)

            question, articles = await asyncio.to_thread(_tagged)

        # live, query-relevant headlines (works even when nothing is indexed)
        if question:
            seen = {a["url"] for a in articles}
            for a in await news.google_news_articles(question, max_records=limit):
                if a["url"] not in seen:
                    articles.append(a)
                    seen.add(a["url"])

        articles.sort(key=lambda a: a.get("published_at") or "", reverse=True)
        return {"articles": articles[:limit], "error": None}
    except Exception as exc:
        return {"articles": [], "error": str(exc)}


_arb_cache: dict = {"ts": 0.0, "opportunities": []}


@app.get("/api/arbitrage")
async def arbitrage_scan(fresh: bool = False) -> dict:
    """Scan books for pricing violations (cached 3 min; ?fresh=true rescans)."""
    try:
        import time as _time

        from backend.sim import arbitrage

        if not fresh and _time.time() - _arb_cache["ts"] < 180:
            return {"opportunities": _arb_cache["opportunities"], "cached": True, "error": None}
        opportunities = await arbitrage.scan(n_markets=20, n_events=10)
        _arb_cache.update(ts=_time.time(), opportunities=opportunities)
        return {"opportunities": opportunities, "cached": False, "error": None}
    except Exception as exc:
        return {"opportunities": [], "cached": False, "error": str(exc)}


class ArbExecuteIn(BaseModel):
    opportunity: dict


@app.post("/api/arbitrage/execute")
async def arbitrage_execute(body: ArbExecuteIn) -> dict:
    """Paper-fill all legs of a scanned opportunity (desk book)."""
    try:
        from backend.sim import arbitrage

        legs = body.opportunity.get("legs") or []
        if not legs or len(legs) > 16:
            return {"reports": [], "error": "opportunity has no executable legs"}
        for leg in legs:
            leg["size_usd"] = max(1.0, min(float(leg.get("size_usd", 0)), config.ARB_MAX_SIZE_USD))
        reports = await arbitrage.execute_legs(body.opportunity)
        return {"reports": reports, "error": None}
    except Exception as exc:
        return {"reports": [], "error": str(exc)}


class FollowIn(BaseModel):
    wallet: str
    label: str = ""


class ImportWalletsIn(BaseModel):
    wallets: list  # ["0x..."] or [{wallet|address, label|name}]


@app.get("/api/wallets")
async def followed_wallets() -> dict:
    """Wallets the desk follows."""
    try:
        rows = await asyncio.to_thread(supabase_client.get_followed_wallets)
        return {"wallets": rows, "error": None}
    except Exception as exc:
        return {"wallets": [], "error": str(exc)}


@app.post("/api/wallets")
async def follow_wallet(body: FollowIn) -> dict:
    try:
        from backend.data import smart_money

        valid, _ = smart_money.validate_wallet_import([{"wallet": body.wallet, "label": body.label}])
        if not valid:
            return {"error": "not a valid wallet address (expected 0x + 40 hex chars)"}
        await asyncio.to_thread(supabase_client.follow_wallets, valid)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


@app.delete("/api/wallets")
async def unfollow_wallet(wallet: str) -> dict:
    try:
        await asyncio.to_thread(supabase_client.unfollow_wallet, wallet.lower())
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/wallets/import")
async def import_wallets(body: ImportWalletsIn) -> dict:
    """Bulk-follow wallets from a user-supplied JSON list."""
    try:
        from backend.data import smart_money

        valid, skipped = smart_money.validate_wallet_import(body.wallets)
        written = await asyncio.to_thread(supabase_client.follow_wallets, valid)
        return {"imported": written, "skipped": skipped, "error": None}
    except Exception as exc:
        return {"imported": 0, "skipped": 0, "error": str(exc)}


class TradeIn(BaseModel):
    slug: str
    side: Literal["BUY_YES", "BUY_NO"]
    size_usd: float = 50.0


@app.post("/api/trade")
async def manual_trade(body: TradeIn) -> dict:
    """GUI-directed paper trade: fill `size_usd` on the live book right now."""
    try:
        from backend.llm.client import RunContext
        from backend.sim import paper_broker

        size_usd = max(1.0, min(body.size_usd, 1000.0))  # sane paper limits
        market = await polymarket.get_market_state(body.slug)
        if market is None:
            return {"fill": None, "error": f"no market found for {body.slug!r}"}

        priced = PricingResult(
            prior=market.mid, fair=market.mid, fair_adj=market.mid,
            gross_edge_pts=0.0, half_spread=(market.spread or 0) / 2, taker_fee=0.0,
            net_edge_pts=0.0, verdict=body.side, suggested_size_pct_bankroll=0.0,
            resolution_risk="medium",
        )
        ctx = RunContext()
        fill = await paper_broker.execute_paper_trade(ctx, market, priced, size_usd=size_usd)
        if fill is None:
            return {"fill": None, "error": "the order book had no fillable liquidity"}
        return {"fill": fill.model_dump(), "error": None}
    except Exception as exc:
        return {"fill": None, "error": str(exc)}


class CloseIn(BaseModel):
    position_id: str
    fraction: float = 1.0  # 0.25 = close a quarter


@app.post("/api/position/close")
async def close_position(body: CloseIn) -> dict:
    """Close all or part of any open paper position at the current book."""
    try:
        from backend.sim import paper_broker

        fraction = max(0.01, min(1.0, body.fraction))
        return await paper_broker.close_position(body.position_id, fraction=fraction)
    except Exception as exc:
        return {"error": str(exc)}


class LimitsIn(BaseModel):
    position_id: str
    sl_price: Optional[float] = None  # None clears the level
    tp_price: Optional[float] = None


@app.put("/api/position/limits")
async def set_position_limits(body: LimitsIn) -> dict:
    """Set/clear per-position stop-loss / take-profit price levels. The risk
    manager enforces them on its next pass."""
    try:
        for level in (body.sl_price, body.tp_price):
            if level is not None and not (0 < level < 1):
                return {"error": "price levels must be between 0 and 1"}

        def _update():
            client = supabase_client.get_client()
            rows = client.table("positions").select("status").eq("id", body.position_id).limit(1).execute().data
            if not rows:
                return "position not found"
            if rows[0].get("status") != "open":
                return "position is already resolved"
            client.table("positions").update(
                {"sl_price": body.sl_price, "tp_price": body.tp_price}
            ).eq("id", body.position_id).execute()
            return None

        error = await asyncio.to_thread(_update)
        return {"error": error}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/quotes")
async def working_quotes() -> dict:
    """Resting market-maker quotes (the terminal's working-orders panel)."""
    try:
        if not supabase_client.is_configured():
            return {"quotes": [], "error": None}
        rows = await asyncio.to_thread(
            lambda: supabase_client.get_client()
            .table("mm_quotes")
            .select("id,market_id,bid,ask,size_usd,mid_at_placement,placed_at")
            .eq("status", "pending")
            .order("placed_at", desc=True)
            .execute()
            .data
            or []
        )
        return {"quotes": rows, "error": None}
    except Exception as exc:
        return {"quotes": [], "error": str(exc)}


class CancelQuoteIn(BaseModel):
    quote_id: str


@app.post("/api/quotes/cancel")
async def cancel_quote(body: CancelQuoteIn) -> dict:
    """Pull a resting MM quote (it can no longer fill)."""
    try:
        def _cancel():
            supabase_client.get_client().table("mm_quotes").update(
                {"status": "settled", "fills": "cancelled"}
            ).eq("id", body.quote_id).eq("status", "pending").execute()

        await asyncio.to_thread(_cancel)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


class DeskChatIn(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/chat")
async def desk_chat_endpoint(body: DeskChatIn) -> dict:
    """Global chat (DeskChat module): routes a question to the right market
    (via MarketChat), to the desk's own portfolio/state, to the agent's
    self-description, or to a helpful refusal with market suggestions."""
    try:
        from backend.agent import chat

        return await chat.desk_chat(body.question, body.history[:24])
    except Exception as exc:
        return {"answer": None, "citations": [], "market": None, "error": str(exc)}


class MarketChatIn(BaseModel):
    slug: str
    question: str
    history: list[dict] = []


@app.post("/api/market/chat")
async def market_chat_endpoint(body: MarketChatIn) -> dict:
    """Grounded Q&A on one market (MarketChat module): plans whether the
    question needs fresh intel, searches web/news and scrapes socials if so,
    indexes what it finds, and answers with citations."""
    try:
        from backend.agent import chat

        return await chat.market_chat(body.slug, body.question, body.history[:24])
    except Exception as exc:
        return {"answer": None, "citations": [], "error": str(exc)}


@app.get("/api/market")
async def market_detail(slug: str) -> dict:
    """Live detail (order book, spread, depth, 7d history) for one market."""
    try:
        state = await polymarket.get_market_state(slug)
        if state is None:
            return {"market": None, "error": f"No market found for {slug!r}"}
        return {"market": state.model_dump(), "error": None}
    except Exception as exc:
        return {"market": None, "error": str(exc)}


@app.post("/api/execute")
async def execute(body: ExecuteIn, ui: bool = False) -> JSONResponse:
    """Course envelope: exactly {status, error, response, steps} at the top
    level (the spec says "must match exactly these top-level fields"). The
    GUI opts into the extra structured dossier payload with ?ui=1."""
    try:
        out = await run_pipeline(body.prompt, history=body.history[:12])
    except Exception as exc:  # never leak a 500 — envelope is always HTTP 200
        out = ExecuteOut(status="error", error=str(exc), response=None, steps=[])
    data = out.model_dump(mode="json")
    if not ui:
        data.pop("ui", None)
    return JSONResponse(data)
