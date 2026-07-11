"""Central configuration: environment variables + tunable constants.

All pricing/verdict constants from the plan (§6) live here so pricing.py
stays pure math and tests can override values in one place.
"""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
PROMPTS_DIR = BACKEND_DIR / "prompts"
ASSETS_DIR = BACKEND_DIR / "assets"
ARCHITECTURE_PNG = ASSETS_DIR / "architecture.png"

# ---------------------------------------------------------------------------
# Environment (.env is loaded by uvicorn/vercel; fall back to os.environ)
# ---------------------------------------------------------------------------


def _load_dotenv() -> None:
    """Minimal .env loader so local dev works without extra deps."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

LLMOD_API_KEY = os.environ.get("LLMOD_API_KEY", "")
LLMOD_BASE_URL = os.environ.get("LLMOD_BASE_URL", "")
# Course submission requires the LLMod models (defaults below). For local dev
# any OpenAI-compatible provider works — e.g. Gemini via
# LLMOD_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# LLM_MODEL=gemini-2.5-flash  EMBEDDING_MODEL=gemini-embedding-001
LLM_MODEL = os.environ.get("LLM_MODEL", "MB5R2CF-azure/gpt-5.4-mini")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "MB5R2CF-azure/text-embedding-3-small")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

PINECONE_API_KEY = os.environ.get("PINECONE_API_KEY", "")
PINECONE_INDEX = os.environ.get("PINECONE_INDEX", "polymarkov")

REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")

# Social sources are best-effort and feature-flagged (§2).
ENABLE_POLYMARKET_COMMENTS = True
ENABLE_REDDIT = bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET)
ENABLE_BLUESKY = False
ENABLE_X = False

# ---------------------------------------------------------------------------
# Team info (course requirement) — TODO: fill in real values before submission
# ---------------------------------------------------------------------------
TEAM_INFO = {
    "group_batch_order_number": "TODO_GROUP_BATCH_ORDER_NUMBER",
    "team_name": "TODO_TEAM_NAME",
    "students": [
        {"name": "TODO_STUDENT_NAME", "email": "korikata8@protonmail.com"},
    ],
}

# ---------------------------------------------------------------------------
# HTTP behavior
# ---------------------------------------------------------------------------
HTTP_TIMEOUT_S = 10.0
GDELT_MAX_RECORDS = 25
GDELT_TIMESPAN = "7d"
CITATION_TEXT_MAX_CHARS = 1500

# ---------------------------------------------------------------------------
# Evidence handling (§3)
# ---------------------------------------------------------------------------
DEDUP_COSINE_THRESHOLD = 0.92   # near-duplicates: keep highest-authority domain
CLUSTER_COSINE_THRESHOLD = 0.80  # same-day + cosine>0.80 -> one cluster
MAX_EVIDENCE_CLUSTERS = 8
MAX_PRECEDENTS = 5
MAX_SOCIAL_POSTS = 20

# ---------------------------------------------------------------------------
# Pricing engine constants (§6) — implement pricing.py against these exactly
# ---------------------------------------------------------------------------
PRIOR_CLAMP = (0.02, 0.98)
W_MAX = 0.6                      # max weight-of-evidence per item, log-odds units
TOTAL_UPDATE_CAP = 1.0           # cap on summed log-odds update
CORRELATION_DISCOUNT = 0.5       # within-cluster decay factor 0.5^k

RESOLUTION_HAIRCUT = {"low": 0.02, "medium": 0.07, "high": 0.15}
HAIRCUT_MULTIPLIER = 6           # fair_adj = fair + (prior - fair) * min(1, h * 6)

# Taker-fee rates by category. Config default — re-check against Polymarket
# docs at deploy time (see README).
FEE_RATE = {
    "sports": 0.03,
    "politics": 0.04,
    "finance": 0.04,
    "tech": 0.04,
    "economics": 0.05,
    "culture": 0.05,
    "weather": 0.05,
    "other": 0.05,
    "crypto": 0.07,
    "geopolitics": 0.0,
}

SAFETY_MARGIN = 0.02             # subtracted from net edge, probability points
MIN_DEPTH_USD = 2000             # minimum depth at ask to trade
MAX_SPREAD = 0.08                # PASS if spread wider than this
MIN_EVIDENCE_CLUSTERS = 2        # PASS if fewer clusters than this
MAX_COUNCIL_DISAGREEMENT = 0.25  # PASS if persona estimates differ more

KELLY_FRACTION = 0.25            # quarter Kelly
MAX_SIZE_PCT_BANKROLL = 0.05     # hard cap: 5% of bankroll
PAPER_BANKROLL_USD = 10_000      # simulated bankroll for PaperBroker sizing

# ---------------------------------------------------------------------------
# Intel cache: serve a recent dossier for the same market instead of
# re-running 7 LLM calls. Trades always bypass the cache.
# ---------------------------------------------------------------------------
INTEL_CACHE_TTL_S = 900  # 15 minutes

# ---------------------------------------------------------------------------
# Automation (jobs/auto_trade.py + jobs/refresh_watchlist.py, run on a
# GitHub Actions schedule). Caps protect the LLM quota.
# ---------------------------------------------------------------------------
AUTO_RUNS_PER_JOB = 3            # markets analyzed per auto-trade run
AUTO_MAX_OPEN_POSITIONS = 10     # agent stops opening new trades at this count
AUTO_MIN_MID = 0.05              # skip near-settled markets
AUTO_MAX_MID = 0.95
WATCHLIST_RUNS_PER_JOB = 5       # watched markets re-analyzed per refresh run

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
CANONICAL_MODULES = [
    "QueryPlanner",
    "MarketResolver",
    "EvidenceRetriever",
    "SocialScanner",
    "SentimentScorer",
    "BullAnalyst",
    "BearAnalyst",
    "QuantAnalyst",
    "ResolutionSkeptic",
    "Judge",
    "PaperBroker",
    # background jobs (diagram only, never called from /api/execute)
    "MarketIndexer",
    "NewsIndexer",
]
