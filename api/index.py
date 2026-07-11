"""Vercel serverless entrypoint. Thin: all real logic lives in backend/."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402

from backend import config  # noqa: E402
from backend.agent.types import ExecuteIn, ExecuteOut  # noqa: E402

app = FastAPI(title="Polymarkov", docs_url=None, redoc_url=None)


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


@app.post("/api/execute")
async def execute(body: ExecuteIn) -> ExecuteOut:
    # Phase 1 stub — replaced by backend.agent.orchestrator.run_pipeline in Phase 5.
    try:
        return ExecuteOut(
            status="ok",
            error=None,
            response=(
                "Polymarkov skeleton is live, but the analysis pipeline is not "
                f"implemented yet. You asked: {body.prompt!r}"
            ),
            steps=[],
        )
    except Exception as exc:  # never leak a 500 — envelope is always HTTP 200
        return ExecuteOut(status="error", error=str(exc), response=None, steps=[])
