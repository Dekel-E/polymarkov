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
        return {"markets": await polymarket.get_trending_markets(min(limit, 50)), "error": None}
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
