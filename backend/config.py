"""Environment variables and tunable constants."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
REGISTRY_DIR = BACKEND_DIR / "agent" / "registry"
PROMPTS_DIR = REGISTRY_DIR / "prompts"
ASSETS_DIR = BACKEND_DIR / "assets"
ARCHITECTURE_PNG = ASSETS_DIR / "architecture.png"


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
    """Read an env var, stripping whitespace; empty strings count as unset."""
    return (os.environ.get(name) or "").strip() or default


LLMOD_API_KEY = _env("LLMOD_API_KEY")
LLMOD_BASE_URL = _env("LLMOD_BASE_URL")
# Any OpenAI-compatible provider works for local dev (e.g. Gemini via
# LLMOD_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/).
LLM_MODEL = _env("LLM_MODEL", "MB5R2CF-azure/gpt-5.4-mini")
EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "MB5R2CF-azure/text-embedding-3-small")
EMBEDDING_DIM = int(_env("EMBEDDING_DIM", "1536"))

SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _env("SUPABASE_SERVICE_KEY")

PINECONE_API_KEY = _env("PINECONE_API_KEY")
PINECONE_INDEX = _env("PINECONE_INDEX", "polymarkov")

REDDIT_CLIENT_ID = _env("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = _env("REDDIT_CLIENT_SECRET")

# Social sources are best-effort and feature-flagged.
ENABLE_POLYMARKET_COMMENTS = True
# Reddit works keyless via public JSON search; OAuth kicks in when the
# CLIENT_ID/SECRET are set.
ENABLE_REDDIT = True
ENABLE_BLUESKY = True
ENABLE_X = False

# Single-user install, no auth. watchlist and followed_wallets need a non-null
# uuid, so rows carry this fixed id; it has no per-user meaning.
DESK_USER_ID = "00000000-0000-0000-0000-000000000000"

TEAM_INFO = {
    "group_batch_order_number": "batch1_order1",
    "team_name": "Polymarkov Team",
    "students": [
        {"name": "Dekel Elimelech", "email": "korikata8@protonmail.com"},
        {"name": "Rom Katav", "email": "TODO_rom_katav@example.com"},
        {"name": "Omer Perchuk", "email": "TODO_omer_perchuk@example.com"},
    ],
}

HTTP_TIMEOUT_S = 10.0
# Bounded so one stuck gateway request can't eat the whole serverless budget.
# TIMEOUT x (1 + retries) stays under EXECUTE_DEADLINE_S.
LLM_TIMEOUT_S = 75.0
LLM_MAX_RETRIES = 1
EXECUTE_DEADLINE_S = 270.0
GDELT_MAX_RECORDS = 25
GDELT_TIMESPAN = "7d"
CITATION_TEXT_MAX_CHARS = 1500

DEDUP_COSINE_THRESHOLD = 0.92
CLUSTER_COSINE_THRESHOLD = 0.80
# Floors below which a semantic match is noise, not evidence. These embeddings
# run hot (unrelated texts often score 0.5+), so the floors are strict.
NEWS_MIN_MATCH_SCORE = 0.62
PRECEDENT_MIN_MATCH_SCORE = 0.55
# Live articles are gated against the market question by cosine before they can
# become evidence. On-topic titles score ~0.60+, unrelated ~0.38-0.46.
LIVE_EVIDENCE_MIN_SCORE = 0.55
MAX_EVIDENCE_CLUSTERS = 8
MAX_PRECEDENTS = 5
MAX_SOCIAL_POSTS = 20

# Pricing engine
PRIOR_CLAMP = (0.02, 0.98)
W_MAX = 0.6
TOTAL_UPDATE_CAP = 1.0
CORRELATION_DISCOUNT = 0.5       # within-cluster decay factor 0.5^k

RESOLUTION_HAIRCUT = {"low": 0.02, "medium": 0.07, "high": 0.15}
HAIRCUT_MULTIPLIER = 6           # fair_adj = fair + (prior - fair) * min(1, h * 6)

# Taker-fee rates by category. Re-check against Polymarket docs at deploy time.
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

SAFETY_MARGIN = 0.02
MIN_DEPTH_USD = 2000             # minimum depth at ask to trade
MAX_SPREAD = 0.08                # PASS if spread wider than this
MIN_EVIDENCE_CLUSTERS = 2        # PASS if fewer clusters than this
MAX_COUNCIL_DISAGREEMENT = 0.25  # PASS if persona estimates differ more

KELLY_FRACTION = 0.25            # quarter Kelly
MAX_SIZE_PCT_BANKROLL = 0.05     # hard cap: 5% of bankroll
PAPER_BANKROLL_USD = 10_000

# Serve a recent dossier for the same market instead of re-running 8 LLM calls.
# Trades always bypass the cache.
INTEL_CACHE_TTL_S = 900

# Automation caps protect the LLM quota.
AUTO_RUNS_PER_JOB = 3
AUTO_MIN_MID = 0.05              # skip near-settled markets
AUTO_MAX_MID = 0.95
WATCHLIST_RUNS_PER_JOB = 5

# Strategy Desk defaults. The GUI edits these in Supabase (agent_settings);
# jobs read the merged result at run time. This dict is the schema + fallback.
DEFAULT_AGENT_SETTINGS = {
    "strategies": {
        "ai_signal": True,
        "arbitrage": True,
        "copy_trading": False,
        "market_making": False,
        "correlation": True,
    },
    "risk": {
        "stop_loss_pct": 50,
        "take_profit_pct": 100,
        "max_position_usd": 500,
        "max_open_positions": 10,
        "daily_loss_halt_usd": 300,
    },
    "halt": {"active": False, "reason": "", "at": ""},
    "funds": {"bankroll_usd": PAPER_BANKROLL_USD},
}
COPY_TRADES_PER_JOB = 5

# Bounds for GUI/chat-editable settings, shared by PUT /api/settings and
# StrategyChat so a typo can never write an insane value.
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
AGENDA_RUNS_PER_JOB = 3
NEWS_LAG_MAX_MOVE = 0.03          # news burst + price move under this = lag window
SENTINEL_NEW_LISTING_HOURS = 24   # markets younger than this get an early look
SENTINEL_NEW_LISTING_MIN_LIFE_H = 24  # but must live at least this long
SENTINEL_NEW_LISTING_MAX = 3
WHALE_PRINT_USD = 10_000          # single fill this big on a tracked market -> agenda
SMART_MONEY_TRADES = 60           # recent fills SmartMoneyScanner pulls per market
SMART_MONEY_TOP_N = 40            # leaderboard depth checked for smart-money activity
WHALE_LOOKBACK_MIN = 90
LIVE_MOVE_PTS = 0.03              # live watcher: instant price jump threshold
LIVE_REFRESH_MIN = 15             # live watcher: re-pick watched assets this often
MAX_ANALYSES_PER_DAY = 40         # hard LLM budget: pipeline runs per UTC day
TUNE_DISABLE_LOSS_USD = 50        # 7d realized loss that disables a strategy
TUNE_MIN_TRADES = 5
EXCERPT_CLUSTERS = 4              # top news clusters whose pages the agent reads
EXCERPT_MAX_CHARS = 500

# Cross-venue (Kalshi): a second market-consensus prior. Matching is
# conservative; no match beats a wrong match.
KALSHI_MATCH_MIN = 0.5           # min fraction of question tokens matched
KALSHI_MAX_MARKETS = 4

# News intake + web fallback
GNEWS_MAX_RECORDS = 15
WEB_SEARCH_ENABLED = True
WEB_SEARCH_MIN_ARTICLES = 4       # below this article count, search the web
WEB_SEARCH_RESULTS = 6

# Curated RSS feeds + Wikipedia, keyless, work where GDELT's IP block bites.
RSS_ENABLED = True
WIKI_ENABLED = True
RSS_MAX_FEEDS = 5
RSS_MAX_RECORDS = 10
RSS_MATCH_MIN_TOKENS = 1         # an item must mention >= this many query terms
WIKI_MAX_RECORDS = 3

# Verified-live feeds (2026-07-17). A dead feed contributes [] and the list can
# be pruned freely.
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

# Market making (paper): quote both sides, settle fills against what the market
# actually traded through. Inventory risk is the binding constraint.
MM_HALF_SPREAD = 0.02            # quote at mid +/- this
MM_QUOTE_SIZE_USD = 25           # per side, per market
MM_MARKETS = 2
MM_MAX_INVENTORY_USD = 100       # per-market cap on net inventory
MM_MIN_HOURS_TO_RESOLUTION = 72  # never quote near expiry (total-loss zone)
MM_MIN_MID = 0.15
MM_MAX_MID = 0.85
MM_INVENTORY_SKEW = 0.015        # shift quotes against a full inventory
MM_REQUOTE_DRIFT = 0.01          # requote when mid drifts this far
MM_REWARD_MAX_SPREAD = 0.03      # liquidity-rewards qualifying distance
COPY_MIN_USD = 5                 # proportional copy sizing bounds
COPY_MAX_USD = 100

# Correlation graph
RELATION_SIMILARITY_MIN = 0.72   # embedding cosine gate for candidate pairs
RELATION_MAX_PAIRS = 40          # pairs classified per LLM call
RELATION_MIN_CONFIDENCE = 0.7

# Arbitrage scanner (pure book math)
ARB_MIN_EDGE = 0.01              # min guaranteed profit per share after fees ($)
ARB_MAX_SIZE_USD = 100           # paper cap per leg
ARB_SCAN_MARKETS = 25
ARB_SCAN_EVENTS = 12

# Module names come from the registry (single source of truth).
from backend.agent.registry.tools import CANONICAL_MODULES  # noqa: E402

# MarketChat
CHAT_MAX_QUESTION_CHARS = 600
CHAT_MAX_HISTORY_TURNS = 8        # prior turns carried into the answer call
CHAT_MAX_HISTORY_CHARS = 500      # per carried turn
CHAT_NEWS_RESULTS = 6
CHAT_WEB_RESULTS = 5
CHAT_SOCIAL_POSTS = 12
CHAT_DOSSIER_MAX_AGE_S = 24 * 3600  # a stale dossier is still usable context
CHAT_DEFAULT_TRADE_USD = 50.0     # paper size when a chat trade omits an amount
CHAT_MAX_TRADE_USD = 1000.0       # clamp on chat-directed paper trades
