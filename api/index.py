"""Vercel serverless entrypoint. Thin: all real logic lives in backend/.

NOTE (course requirement): the root GUI and the four graded endpoints have
NO auth. Login is purely additive — it only tags manual paper trades with a
user id so the GUI can show a personal portfolio.
"""

import asyncio
import sys
from pathlib import Path
from typing import Literal, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend import config  # noqa: E402
from backend.agent.orchestrator import run_pipeline  # noqa: E402
from backend.agent.types import ExecuteIn, ExecuteOut, PricingResult  # noqa: E402
from backend.data import polymarket, supabase_client  # noqa: E402

app = FastAPI(title="Polymarkov", docs_url=None, redoc_url=None)


async def _user_id_from_request(request: Request) -> Optional[str]:
    """Resolve a Supabase Auth user from a Bearer token. None when absent/invalid."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not supabase_client.is_configured():
        return None
    token = auth[7:].strip()
    try:
        res = await asyncio.to_thread(supabase_client.get_client().auth.get_user, token)
        return res.user.id if res and res.user else None
    except Exception:
        return None


@app.get("/api/team_info")
def team_info() -> dict:
    return config.TEAM_INFO


@app.get("/api/agent_info")
def agent_info() -> dict:
    # Examples are frozen from real runs in Phase 8; prompts are read from
    # backend/prompts at runtime so docs never drift from behavior.
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
        "prompt_template": (
            "Market: <slug | url | free-text question>\n"
            "Focus: <news | socials | resolution | all>\n"
            "Trade: <yes | no>"
        ),
        "modules": config.CANONICAL_MODULES,
        "prompts": prompts,
        "examples": [],  # TODO(Phase 8): freeze 2 real recorded runs here
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


@app.get("/api/markets")
async def markets(limit: int = 20) -> dict:
    """Trending markets for the GUI market browser."""
    try:
        return {"markets": await polymarket.get_trending_markets(min(limit, 100)), "error": None}
    except Exception as exc:
        return {"markets": [], "error": str(exc)}


@app.get("/api/portfolio")
async def portfolio(request: Request, scope: str = "agent") -> dict:
    """Paper positions + stats. scope=agent (default) or scope=mine (needs login)."""
    try:
        from backend.sim.portfolio import get_portfolio

        user_id = await _user_id_from_request(request) if scope == "mine" else None
        if scope == "mine" and user_id is None:
            return {"portfolio": None, "error": "login required for scope=mine"}
        data = await asyncio.to_thread(get_portfolio, scope, user_id)
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
async def watchlist(request: Request) -> dict:
    """The logged-in user's watched markets, enriched from the cache."""
    try:
        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"items": [], "error": "login required"}
        from backend.agent import intel_cache

        slugs = await asyncio.to_thread(supabase_client.get_watchlist, user_id)
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
async def watch(body: WatchIn, request: Request) -> dict:
    try:
        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"error": "login required"}
        await asyncio.to_thread(supabase_client.add_watch, user_id, body.market_id)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


@app.delete("/api/watchlist")
async def unwatch(market_id: str, request: Request) -> dict:
    try:
        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"error": "login required"}
        await asyncio.to_thread(supabase_client.remove_watch, user_id, market_id)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


class FollowIn(BaseModel):
    wallet: str
    label: str = ""


class ImportWalletsIn(BaseModel):
    wallets: list  # ["0x..."] or [{wallet|address, label|name}]


@app.get("/api/wallets")
async def followed_wallets(request: Request) -> dict:
    """Wallets the logged-in user follows."""
    try:
        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"wallets": [], "error": "login required"}
        rows = await asyncio.to_thread(supabase_client.get_followed_wallets, user_id)
        return {"wallets": rows, "error": None}
    except Exception as exc:
        return {"wallets": [], "error": str(exc)}


@app.post("/api/wallets")
async def follow_wallet(body: FollowIn, request: Request) -> dict:
    try:
        from backend.data import smart_money

        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"error": "login required"}
        valid, _ = smart_money.validate_wallet_import([{"wallet": body.wallet, "label": body.label}])
        if not valid:
            return {"error": "not a valid wallet address (expected 0x + 40 hex chars)"}
        await asyncio.to_thread(supabase_client.follow_wallets, user_id, valid)
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


@app.delete("/api/wallets")
async def unfollow_wallet(wallet: str, request: Request) -> dict:
    try:
        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"error": "login required"}
        await asyncio.to_thread(supabase_client.unfollow_wallet, user_id, wallet.lower())
        return {"error": None}
    except Exception as exc:
        return {"error": str(exc)}


@app.post("/api/wallets/import")
async def import_wallets(body: ImportWalletsIn, request: Request) -> dict:
    """Bulk-follow wallets from a user-supplied JSON list."""
    try:
        from backend.data import smart_money

        user_id = await _user_id_from_request(request)
        if user_id is None:
            return {"imported": 0, "skipped": 0, "error": "login required"}
        valid, skipped = smart_money.validate_wallet_import(body.wallets)
        written = await asyncio.to_thread(supabase_client.follow_wallets, user_id, valid)
        return {"imported": written, "skipped": skipped, "error": None}
    except Exception as exc:
        return {"imported": 0, "skipped": 0, "error": str(exc)}


class RegisterIn(BaseModel):
    email: str
    password: str


@app.post("/api/auth/register")
async def register(body: RegisterIn) -> dict:
    """Create a user pre-confirmed (no confirmation email round-trip)."""
    try:
        if not supabase_client.is_configured():
            return {"error": "auth is not configured on the server"}
        if len(body.password) < 6:
            return {"error": "password must be at least 6 characters"}

        def _create():
            return supabase_client.get_client().auth.admin.create_user(
                {"email": body.email, "password": body.password, "email_confirm": True}
            )

        await asyncio.to_thread(_create)
        return {"error": None}
    except Exception as exc:
        msg = str(exc)
        if "already been registered" in msg or "already registered" in msg:
            return {"error": "this email is already registered — log in instead"}
        return {"error": msg}


class TradeIn(BaseModel):
    slug: str
    side: Literal["BUY_YES", "BUY_NO"]
    size_usd: float = 50.0


@app.post("/api/trade")
async def manual_trade(body: TradeIn, request: Request) -> dict:
    """GUI-directed paper trade: fill `size_usd` on the live book right now."""
    try:
        from backend.llm.client import RunContext
        from backend.sim import paper_broker

        size_usd = max(1.0, min(body.size_usd, 1000.0))  # sane paper limits
        user_id = await _user_id_from_request(request)
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
        fill = await paper_broker.execute_paper_trade(
            ctx, market, priced, size_usd=size_usd, user_id=user_id
        )
        if fill is None:
            return {"fill": None, "error": "the order book had no fillable liquidity"}
        return {"fill": fill.model_dump(), "error": None}
    except Exception as exc:
        return {"fill": None, "error": str(exc)}


class CloseIn(BaseModel):
    position_id: str


@app.post("/api/position/close")
async def close_position(body: CloseIn, request: Request) -> dict:
    """Close an open paper position at the current book."""
    try:
        from backend.sim import paper_broker

        user_id = await _user_id_from_request(request)
        return await paper_broker.close_position(body.position_id, user_id)
    except Exception as exc:
        return {"error": str(exc)}


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
async def execute(body: ExecuteIn) -> ExecuteOut:
    try:
        return await run_pipeline(body.prompt)
    except Exception as exc:  # never leak a 500 — envelope is always HTTP 200
        return ExecuteOut(status="error", error=str(exc), response=None, steps=[])
