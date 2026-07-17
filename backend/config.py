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
# The agent registry (backend/agent/registry/) is the single home for what
# the agent can do: tools.py declares every module/tool, prompts/ holds the
# system prompts (one .txt per LLM module).
REGISTRY_DIR = BACKEND_DIR / "agent" / "registry"
PROMPTS_DIR = REGISTRY_DIR / "prompts"
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

def _env(name: str, default: str = "") -> str:
    """Env read hardened for CI: strips whitespace/newlines (a pasted GitHub
    secret often carries a trailing newline, which makes an illegal HTTP
    header) and treats empty strings as unset."""
    return (os.environ.get(name) or "").strip() or default


LLMOD_API_KEY = _env("LLMOD_API_KEY")
LLMOD_BASE_URL = _env("LLMOD_BASE_URL")
# Course submission requires the LLMod models (defaults below). For local dev
# any OpenAI-compatible provider works — e.g. Gemini via
# LLMOD_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# LLM_MODEL=gemini-2.5-flash  EMBEDDING_MODEL=gemini-embedding-001
LLM_MODEL = _env("LLM_MODEL", "MB5R2CF-azure/gpt-5.4-mini")
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "MB5R2CF-azure/text-embedding-3-small")
EMBEDDING_DIM = int(_env("EMBEDDING_DIM", "1536"))

SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")

PINECONE_API_KEY = _env("PINECONE_API_KEY")
PINECONE_INDEX = _env("PINECONE_INDEX", "polymarkov")

REDDIT_CLIENT_ID = _env("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = _env("REDDIT_CLIENT_SECRET")

# Social sources are best-effort and feature-flagged (§2).
ENABLE_POLYMARKET_COMMENTS = True
# Reddit works keyless via the public JSON search; OAuth (higher limits)
# kicks in automatically when REDDIT_CLIENT_ID/SECRET are set.
ENABLE_REDDIT = True
ENABLE_BLUESKY = True   # public AppView search — keyless
ENABLE_X = False        # paid API — off

# Single-user install (course requirement: no auth). The watchlist and
# followed_wallets tables require a non-null uuid, so rows carry this fixed
# id; it has no per-user meaning. Positions are one book, no ownership.
DESK_USER_ID = "00000000-0000-0000-0000-000000000000"

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
# LLM calls: bounded so one stuck gateway request can never eat the whole
# serverless budget (Vercel kills at 300s — a kill returns a 504, not the
# course envelope). Per-request timeout x (1 + max_retries) stays well under
# the overall EXECUTE_DEADLINE_S, after which the pipeline returns the error
# envelope with whatever steps it collected.
LLM_TIMEOUT_S = 75.0
LLM_MAX_RETRIES = 1
EXECUTE_DEADLINE_S = 270.0
GDELT_MAX_RECORDS = 25
GDELT_TIMESPAN = "7d"
CITATION_TEXT_MAX_CHARS = 1500

# ---------------------------------------------------------------------------
# Evidence handling (§3)
# ---------------------------------------------------------------------------
DEDUP_COSINE_THRESHOLD = 0.92   # near-duplicates: keep highest-authority domain
CLUSTER_COSINE_THRESHOLD = 0.80  # same-day + cosine>0.80 -> one cluster
# Semantic matches BELOW these scores are noise, not evidence — without the
# floor, an off-topic market pulls in whatever happens to be nearest.
# NOTE: gemini/llmod embeddings run "hot" — unrelated texts often score
# 0.5+ — so these floors are deliberately strict.
NEWS_MIN_MATCH_SCORE = 0.62
PRECEDENT_MIN_MATCH_SCORE = 0.55
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
AUTO_MIN_MID = 0.05              # skip near-settled markets
AUTO_MAX_MID = 0.95
WATCHLIST_RUNS_PER_JOB = 5       # watched markets re-analyzed per refresh run

# Strategy Desk defaults — the GUI edits these in Supabase (agent_settings);
# jobs read the merged result at run time. This dict is the schema + fallback.
DEFAULT_AGENT_SETTINGS = {
    "strategies": {
        "ai_signal": True,       # the intel pipeline auto-trade loop
        "arbitrage": True,       # spread + dutch-book scanner
        "copy_trading": False,   # mirror followed wallets (opt-in)
        "market_making": False,  # quote both sides, capture the spread (opt-in)
        "correlation": True,     # logical-consistency violations across markets
    },
    "risk": {
        "stop_loss_pct": 50,         # close when a position loses this % of its stake
        "take_profit_pct": 100,      # close when a position gains this %
        "max_position_usd": 500,     # hard cap per position
        "max_open_positions": 10,
        "daily_loss_halt_usd": 300,  # circuit breaker: halt all strategies for the day
    },
    "halt": {"active": False, "reason": "", "at": ""},
    # paper funds are adjustable from the terminal (deposits/withdrawals)
    "funds": {"bankroll_usd": PAPER_BANKROLL_USD},
}
COPY_TRADES_PER_JOB = 5

# Bounds for GUI/chat-editable settings — shared by PUT /api/settings and
# StrategyChat so a typo (or the LLM) can never write an insane value.
RISK_BOUNDS = {
    "stop_loss_pct": (5, 95),
    "take_profit_pct": (10, 500),
    "max_position_usd": (10, 2000),
    "max_open_positions": (1, 50),
    "daily_loss_halt_usd": (10, 5000),
}
BANKROLL_BOUNDS = (100.0, 1_000_000.0)

# Autonomy: sentinel triggers + agenda worker + daily self-accounting
SENTINEL_MOVE_PTS = 0.08          # 24h price move that makes a market interesting
SENTINEL_POSITION_MOVE = 0.10     # adverse move on a held position -> re-analyze
SENTINEL_RESOLUTION_HOURS = 48    # held/watched market resolving soon -> re-analyze
SENTINEL_NEWS_BURST = 3           # fresh headlines in 24h on a held/watched market
AGENDA_RUNS_PER_JOB = 3           # agenda items analyzed per worker run
NEWS_LAG_MAX_MOVE = 0.03          # news burst + price move under this = lag window
SENTINEL_NEW_LISTING_HOURS = 24   # markets younger than this get an early look
SENTINEL_NEW_LISTING_MIN_LIFE_H = 24  # ...but must LIVE at least this long
SENTINEL_NEW_LISTING_MAX = 3      # early looks per scan (don't flood the agenda)
WHALE_PRINT_USD = 10_000          # single fill this big on a tracked market -> agenda
WHALE_LOOKBACK_MIN = 90           # how far back the whale-print check looks
LIVE_MOVE_PTS = 0.03              # live watcher: instant price jump threshold
LIVE_REFRESH_MIN = 15             # live watcher: re-pick watched assets this often
MAX_ANALYSES_PER_DAY = 40         # hard LLM budget: pipeline runs per UTC day
TUNE_DISABLE_LOSS_USD = 50        # self-tuning: 7d realized loss that disables a strategy
TUNE_MIN_TRADES = 5               # ...but only with enough evidence
EXCERPT_CLUSTERS = 4              # top news clusters whose pages the agent reads
EXCERPT_MAX_CHARS = 500           # excerpt length carried into the council context

# Cross-venue (Kalshi): a second market-consensus prior for the council.
# Matching is conservative — no match beats a wrong match.
KALSHI_MATCH_MIN = 0.5           # min fraction of question tokens matched
KALSHI_MAX_MARKETS = 4           # outcomes carried into the council context

# News intake + web fallback
GNEWS_MAX_RECORDS = 15            # Google News results per query (2 queries/run)
WEB_SEARCH_ENABLED = True         # DuckDuckGo fallback when news runs thin
WEB_SEARCH_MIN_ARTICLES = 4       # below this article count, search the web
WEB_SEARCH_RESULTS = 6

# Curated RSS feeds + Wikipedia — keyless, work where GDELT's IP block bites.
# Fetched on demand during intel gathering, filtered to the market's terms,
# and indexed into Supabase (embedded by the NewsIndexer on its next pass).
RSS_ENABLED = True
WIKI_ENABLED = True
RSS_MAX_FEEDS = 5                # general + category feeds fetched per gather
RSS_MAX_RECORDS = 10             # relevant items kept per gather
RSS_MATCH_MIN_TOKENS = 1         # an item must mention >= this many query terms
WIKI_MAX_RECORDS = 3             # Wikipedia pages pulled per gather

# Reputable, verified-live feeds (2026-07-17). A dead feed contributes [] —
# the fetch degrades per-source, so the list can be pruned freely.
RSS_FEEDS_GENERAL = [
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://www.theguardian.com/world/rss",
    "https://feeds.npr.org/1001/rss.xml",
]
RSS_FEEDS_BY_CATEGORY = {
    "finance": [
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://finance.yahoo.com/news/rssindex",
    ],
    "economics": [
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://www.theguardian.com/business/rss",
    ],
    "crypto": [
        "https://www.coindesk.com/arc/outboundfeeds/rss/",
        "https://cointelegraph.com/rss",
    ],
    "tech": [
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://www.theverge.com/rss/index.xml",
    ],
    "politics": [
        "https://feeds.npr.org/1014/rss.xml",
        "https://www.theguardian.com/us-news/us-politics/rss",
    ],
    "geopolitics": [
        "https://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.theguardian.com/world/rss",
    ],
    "sports": [
        "https://www.espn.com/espn/rss/news",
    ],
}

# Market making (paper): quote both sides, settle fills against what the
# market actually traded through. Inventory risk is the binding constraint.
MM_HALF_SPREAD = 0.02            # quote at mid +/- this
MM_QUOTE_SIZE_USD = 25           # per side, per market
MM_MARKETS = 2                   # markets quoted simultaneously
MM_MAX_INVENTORY_USD = 100       # per-market cap on net inventory
MM_MIN_HOURS_TO_RESOLUTION = 72  # never quote near expiry (total-loss zone)
MM_MIN_MID = 0.15                # avoid the extreme-odds inventory traps
MM_MAX_MID = 0.85
MM_INVENTORY_SKEW = 0.015        # shift quotes against a full inventory
MM_REQUOTE_DRIFT = 0.01          # live watcher requotes when mid drifts this far
MM_REWARD_MAX_SPREAD = 0.03      # Polymarket liquidity rewards: qualifying distance
COPY_MIN_USD = 5                 # proportional copy sizing bounds
COPY_MAX_USD = 100

# Correlation graph
RELATION_SIMILARITY_MIN = 0.72   # embedding cosine gate for candidate pairs
RELATION_MAX_PAIRS = 40          # pairs classified per (single) LLM call
RELATION_MIN_CONFIDENCE = 0.7    # keep only confident relations

# Arbitrage scanner (no LLM involved — pure book math)
ARB_MIN_EDGE = 0.01              # min guaranteed profit per share AFTER fees ($)
ARB_MAX_SIZE_USD = 100           # paper cap per leg
ARB_SCAN_MARKETS = 25            # binary markets checked per scan
ARB_SCAN_EVENTS = 12             # mutually-exclusive events checked per scan

# ---------------------------------------------------------------------------
# Pipeline — module names come from the registry (single source of truth)
# ---------------------------------------------------------------------------
from backend.agent.registry.tools import CANONICAL_MODULES  # noqa: E402

# ---------------------------------------------------------------------------
# MarketChat (grounded per-market Q&A with on-demand intel gathering)
# ---------------------------------------------------------------------------
CHAT_MAX_QUESTION_CHARS = 600
CHAT_MAX_HISTORY_TURNS = 8        # prior turns carried into the answer call
CHAT_MAX_HISTORY_CHARS = 500      # per carried turn
CHAT_NEWS_RESULTS = 6             # Google News articles fetched per query
CHAT_WEB_RESULTS = 5              # DuckDuckGo results per query
CHAT_SOCIAL_POSTS = 12            # social posts carried into the answer
CHAT_DOSSIER_MAX_AGE_S = 24 * 3600  # a stale dossier is still usable context
