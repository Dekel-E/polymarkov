"""Registry of every LLM module and tool the agent can run.

Each entry uses the exact `module` name that appears in steps[] traces and
the diagram. Prompts live in registry/prompts/, one .txt per LLM module
(`prompt_file` stem). GET /api/agent_info serves this registry verbatim.

Kept dependency-free (no backend imports) so config and the modules can
import it without cycles.
"""

MODULES: list[dict] = [
    {
        "name": "QueryPlanner",
        "kind": "llm",
        "prompt_file": "query_planner",
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Parses the raw user prompt: classifies intent (market research / "
            "meta question about the agent itself / out of scope), extracts "
            "the market query/URL, entities, requested intel focus, and "
            "whether a paper trade was requested. Meta questions are answered "
            "deterministically from this registry."
        ),
        "inputs": "raw user prompt (string)",
        "outputs": "QueryPlan JSON: {in_scope, intent, market_query, market_url, entities, intel_focus, wants_trade, reason}",
        "data_sources": [],
    },
    {
        "name": "MarketResolver",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Resolves the plan to ONE Polymarket market: direct slug/URL "
            "lookup, Gamma text search, then Pinecone vector match over the "
            "indexed markets namespace. Returns live state (mid, book, "
            "spread, depth, 7d history) or a candidate list to disambiguate."
        ),
        "inputs": "QueryPlan",
        "outputs": "MarketState | candidates[]",
        "data_sources": ["Polymarket Gamma", "Polymarket CLOB", "Pinecone (markets)"],
    },
    {
        "name": "SearchQueryGenerator",
        "kind": "llm",
        "prompt_file": "query_generator",
        "implementation": "backend/agent/pipeline.py",
        "description": "Generates optimal search queries for news, web, and Wikipedia based on the market.",
        "inputs": "Market question + resolution criteria + entities",
        "outputs": "{news_query, gnews_queries[], wiki_query, web_query}",
        "data_sources": [],
    },
    {
        "name": "EvidenceRetriever",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Gathers news evidence: indexed articles from Supabase/Pinecone, "
            "topped up live from GDELT, Google News, curated RSS feeds "
            "(reputable outlets, filtered to the market's terms) and "
            "Wikipedia, with a DuckDuckGo web-search fallback when coverage "
            "is thin. Deduplicates, clusters (max 8), reads the top pages for "
            "excerpts, indexes everything it fetched back into Supabase "
            "(tagged with the market) for future retrieval, and pulls "
            "resolved-market precedents."
        ),
        "inputs": "QueryPlan + MarketState",
        "outputs": "EvidenceCluster[] + Precedent[]",
        "data_sources": [
            "GDELT", "Google News", "Curated RSS feeds", "Wikipedia",
            "DuckDuckGo web search", "Supabase (articles)",
            "Pinecone (news, precedents)",
        ],
    },
    {
        "name": "SocialScanner",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Scrapes social chatter for the market: Polymarket comments, "
            "Bluesky posts and Reddit posts, plus a mention-velocity signal "
            "(24h vs prior 6-day average)."
        ),
        "inputs": "QueryPlan + MarketState",
        "outputs": "SocialPulse {posts[], mention_velocity, note}",
        "data_sources": ["Polymarket comments", "Bluesky", "Reddit"],
    },
    {
        "name": "SentimentScorer",
        "kind": "llm",
        "prompt_file": "sentiment_scorer",
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "ONE batched call scoring every evidence cluster and social post: "
            "sentiment -1..1 and stance yes/no/neutral relative to the "
            "market question."
        ),
        "inputs": "market question + clusters + posts",
        "outputs": "per-item {sentiment, stance}",
        "data_sources": [],
    },
    {
        "name": "BullAnalyst",
        "kind": "llm",
        "prompt_file": "council_bull",
        "implementation": "backend/agent/council.py",
        "description": "Council persona arguing the strongest YES case from the shared evidence context.",
        "inputs": "shared council context (market, clusters, social, precedents)",
        "outputs": "PersonaOpinion {thesis, evidence_weights[], estimated_probability, confidence, red_flags}",
        "data_sources": [],
    },
    {
        "name": "BearAnalyst",
        "kind": "llm",
        "prompt_file": "council_bear",
        "implementation": "backend/agent/council.py",
        "description": "Council persona arguing the strongest NO case from the shared evidence context.",
        "inputs": "shared council context",
        "outputs": "PersonaOpinion",
        "data_sources": [],
    },
    {
        "name": "QuantAnalyst",
        "kind": "llm",
        "prompt_file": "council_quant",
        "implementation": "backend/agent/council.py",
        "description": "Council persona weighing base rates, precedents and market microstructure.",
        "inputs": "shared council context",
        "outputs": "PersonaOpinion",
        "data_sources": [],
    },
    {
        "name": "ResolutionSkeptic",
        "kind": "llm",
        "prompt_file": "council_resolution_skeptic",
        "implementation": "backend/agent/council.py",
        "description": (
            "Council persona attacking the resolution criteria: ambiguity, "
            "edge cases, oracle risk. Its red flags set the resolution-risk "
            "haircut."
        ),
        "inputs": "shared council context",
        "outputs": "PersonaOpinion (red_flags drive resolution_risk)",
        "data_sources": [],
    },
    {
        "name": "PricingEngine",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/pricing.py",
        "description": (
            "Deterministically combines the market prior, council opinions, "
            "resolution-risk haircut, spread, fees, evidence quality and risk "
            "limits into fair value, net edge, verdict and fractional-Kelly "
            "size. No LLM performs or can override this arithmetic."
        ),
        "inputs": "MarketState + council opinions + resolution risk + evidence count",
        "outputs": "PricingResult {fair_raw, fair_adj, edge_net, verdict, size_pct_bankroll}",
        "data_sources": [],
    },
    {
        "name": "Judge",
        "kind": "llm",
        "prompt_file": "judge",
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Synthesizes the council into the final dossier verdict. All "
            "price/fee/edge/Kelly arithmetic is DETERMINISTIC CODE "
            "(backend/agent/pricing.py) — the Judge explains, it does not "
            "compute."
        ),
        "inputs": "council opinions + deterministic PricingResult",
        "outputs": "JudgeOutput {verdict, fair_probability, net_edge_pts, confidence, summary, key_risks}",
        "data_sources": [],
    },
    {
        "name": "PaperBroker",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/sim/paper_broker.py",
        "description": (
            "Simulates a taker fill on the LIVE order book: walks real CLOB "
            "levels for the Kelly-suggested size, computes VWAP, slippage "
            "and category fee, and records the position."
        ),
        "inputs": "MarketState + PricingResult (+ size override)",
        "outputs": "FillReport",
        "data_sources": ["Polymarket CLOB", "Supabase (positions)"],
    },
    {
        "name": "MarketChat",
        "kind": "llm",
        "prompt_file": "market_chat",
        "implementation": "backend/agent/chat.py",
        "description": (
            "Grounded Q&A on ONE market (POST /api/market/chat). First plans "
            "whether the question needs fresh intel (prompt file "
            "market_chat_planner); if so it searches Google News, curated RSS "
            "feeds, Wikipedia and the open web, scrapes socials (Polymarket "
            "comments, Bluesky, Reddit), and INDEXES the articles it finds "
            "into Supabase (the news indexer embeds them into Pinecone on its "
            "next pass). Then answers strictly from the dossier + gathered "
            "sources, citing them."
        ),
        "inputs": "market slug + question + chat history (+ cached dossier)",
        "outputs": "{answer, citations[], gathered {articles, social_posts}}",
        "data_sources": [
            "Google News", "Curated RSS feeds", "Wikipedia",
            "DuckDuckGo web search", "Polymarket comments", "Bluesky",
            "Reddit", "Supabase (articles, intel_cache)",
        ],
    },
    {
        "name": "DeskChat",
        "kind": "llm",
        "prompt_file": "desk_chat",
        "implementation": "backend/agent/chat.py",
        "description": (
            "Global conversational entry point (POST /api/chat). A router "
            "call (prompt file desk_chat_router) classifies the question: "
            "market questions are resolved to a Polymarket market and "
            "delegated to MarketChat; portfolio/status questions are answered "
            "from live Supabase facts (positions, PnL, strategies, runs, "
            "agenda, briefing); control instructions ('turn off copy "
            "trading', 'halt') are delegated to StrategyChat; questions "
            "about the agent itself get the registry-built self-description; "
            "everything else gets a friendly refusal with suggested "
            "Polymarket markets."
        ),
        "inputs": "question + chat history",
        "outputs": "{answer, citations[], market|null}",
        "data_sources": [
            "Polymarket Gamma", "Supabase (positions, runs, agenda, briefings)",
        ],
    },
    {
        "name": "StrategyChat",
        "kind": "llm",
        "prompt_file": "strategy_chat",
        "implementation": "backend/agent/chat.py",
        "description": (
            "Natural-language control channel of the Strategy Desk "
            "(POST /api/strategy/chat). Answers questions about the "
            "autonomous agent's configuration and performance, and turns "
            "explicit instructions ('turn off copy trading', 'set stop loss "
            "to 30%', 'halt everything') into a settings patch. The LLM only "
            "PROPOSES the patch — deterministic code whitelists the keys and "
            "clamps every number to configured bounds before persisting."
        ),
        "inputs": "question + chat history (+ current settings, bounds, portfolio stats)",
        "outputs": "{answer, applied (old->new diff)|null, settings|null}",
        "data_sources": ["Supabase (agent_settings, positions)"],
    },
    {
        "name": "CrossVenueScanner",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Finds the same event priced on Kalshi (keyless search with "
            "embedded live yes bid/ask) via conservative token matching and "
            "hands the council a second market-consensus prior. Divergence "
            "between venues is itself information; no match beats a wrong "
            "match."
        ),
        "inputs": "MarketState (question)",
        "outputs": "matched event + outcome prices | none",
        "data_sources": ["Kalshi"],
    },
    {
        "name": "MicrostructureScanner",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/microstructure.py",
        "description": (
            "Deterministic order-book + price-action indicators for the Quant: "
            "book imbalance and micro-price from the full ladder, banded depth, "
            "spread %, 24h/7d momentum, volatility, trend (SMA), and RSI. Code "
            "computes every number; the QuantAnalyst only interprets them."
        ),
        "inputs": "MarketState (order-book ladder + 7d price history)",
        "outputs": "microstructure/technical indicator dict",
        "data_sources": ["Polymarket CLOB"],
    },
    {
        "name": "SmartMoneyScanner",
        "kind": "tool",
        "prompt_file": None,
        "implementation": "backend/agent/pipeline.py",
        "description": (
            "Checks whether tracked (followed) wallets or top-leaderboard "
            "wallets are active in THIS market and which way they lean, by "
            "cross-referencing recent on-chain fills against the followed set "
            "and the profit leaderboard. Hands the council a smart-money prior "
            "plus any whale prints."
        ),
        "inputs": "MarketState (condition_id) + followed wallets + leaderboard",
        "outputs": "net flow + active tracked/top wallets + whale prints",
        "data_sources": ["Polymarket Data API", "Supabase"],
    },
    {
        "name": "MarketIndexer",
        "kind": "job",
        "prompt_file": None,
        "implementation": "jobs/index_markets.py",
        "description": "Background cron: indexes top Polymarket markets into Supabase + Pinecone every 2h.",
        "inputs": "cron schedule",
        "outputs": "markets table + vectors",
        "data_sources": ["Polymarket Gamma", "Supabase", "Pinecone"],
    },
    {
        "name": "NewsIndexer",
        "kind": "job",
        "prompt_file": None,
        "implementation": "jobs/index_news.py",
        "description": "Background cron: indexes GDELT news into Supabase + Pinecone and tags articles with market entities.",
        "inputs": "cron schedule",
        "outputs": "articles table + vectors",
        "data_sources": ["GDELT", "Supabase", "Pinecone"],
    },
    {
        "name": "RedditIndexer",
        "kind": "job",
        "prompt_file": None,
        "implementation": "jobs/index_social.py",
        "description": (
            "Background cron: scrapes Reddit for posts about tracked markets "
            "(trending + held + watchlisted), stores them in Supabase tagged "
            "with market slugs, and embeds them into the Pinecone `social` "
            "namespace. SocialScanner and MarketChat read this warm cache "
            "alongside their live scrapes."
        ),
        "inputs": "cron schedule",
        "outputs": "social_posts table + vectors",
        "data_sources": ["Reddit", "Supabase", "Pinecone"],
    },
]

# Exact module-name whitelist for steps[] traces and the diagram.
CANONICAL_MODULES: list[str] = [m["name"] for m in MODULES]

# Prompt file stems that must exist in registry/prompts/.
PROMPT_FILES: list[str] = sorted(
    {m["prompt_file"] for m in MODULES if m["prompt_file"]}
    | {"market_chat_planner", "desk_chat_router"}
)
