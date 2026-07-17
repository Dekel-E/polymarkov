# Polymarkov — Architecture

One `/api/execute` run makes **exactly 7 LLM calls** (amber). Everything
else is deterministic code. Module names below are identical to the
`steps[]` trace and the PNG served at `/api/model_architecture`.

```mermaid
flowchart TB
    GUI["Web GUI<br/><small>POST /api/execute {prompt}</small>"]

    QP["QueryPlanner<br/><small>LLM #1 — scope, market query, entities</small>"]
    MR["MarketResolver<br/><small>tool — URL / text search / vector match</small>"]
    ER["EvidenceRetriever<br/><small>tool — GDELT/Google News/RSS/Wiki<br/>+ web fallback, dedup, cluster ≤8,<br/>read pages, index-on-demand</small>"]
    SS["SocialScanner<br/><small>tool — comments + mention velocity</small>"]
    CVS["CrossVenueScanner<br/><small>tool — same event priced on Kalshi</small>"]
    SC["SentimentScorer<br/><small>LLM #2 — ONE batched call</small>"]

    subgraph COUNCIL["Council — concurrent, identical context"]
        BULL["BullAnalyst<br/><small>LLM #3</small>"]
        BEAR["BearAnalyst<br/><small>LLM #4</small>"]
        QUANT["QuantAnalyst<br/><small>LLM #5</small>"]
        SKEP["ResolutionSkeptic<br/><small>LLM #6</small>"]
    end

    JUDGE["Judge<br/><small>LLM #7 — deterministic pricing engine<br/>computes verdict/edge/size in code</small>"]
    OUT["Response + Steps<br/><small>dossier + full trace</small>"]
    PB["PaperBroker<br/><small>tool — fills Kelly size on the live book<br/>(only when Trade: yes and verdict ≠ PASS)</small>"]

    CHAT["MarketChat<br/><small>LLM — grounded Q&A per market:<br/>plans → searches web/news + socials →<br/>indexes finds → answers with citations<br/>(POST /api/market/chat)</small>"]
    DESKCHAT["DeskChat<br/><small>LLM — global chat (POST /api/chat):<br/>routes → market / portfolio / meta /<br/>helpful refusal with market suggestions</small>"]
    STRATCHAT["StrategyChat<br/><small>LLM — Strategy Desk control<br/>(POST /api/strategy/chat):<br/>instructions → settings patch,<br/>whitelisted + clamped by code</small>"]

    GUI --> QP --> MR
    MR --> ER
    MR --> SS
    MR --> CVS
    ER --> SC
    SS --> SC
    CVS --> SC
    SC --> COUNCIL --> JUDGE
    JUDGE --> OUT
    JUDGE --> PB
    GUI --> CHAT
    GUI --> DESKCHAT
    GUI --> STRATCHAT
    DESKCHAT -->|market questions| CHAT
    DESKCHAT -->|control instructions| STRATCHAT
    OUT -.->|dossier context| CHAT
    STRATCHAT -.->|agent_settings| DB

    subgraph EXT["External services"]
        GAMMA["Polymarket Gamma + CLOB"]
        NEWS["GDELT · Google News · RSS · Wikipedia · Web"]
        SOCIAL["Polymarket Comments · Bluesky · Reddit"]
        LLMOD["LLMod.ai<br/><small>gpt-5.4-mini · text-embedding-3-small</small>"]
        KALSHI["Kalshi<br/><small>cross-venue odds (keyless search)</small>"]
    end

    MR -.-> GAMMA
    ER -.-> NEWS
    SS -.-> SOCIAL
    PB -.-> GAMMA
    COUNCIL -.-> LLMOD
    CHAT -.-> NEWS
    CHAT -.-> SOCIAL
    CVS -.-> KALSHI
    DESKCHAT -.->|portfolio facts| DB

    subgraph STORE["Storage"]
        DB["Supabase + Pinecone<br/><small>markets · articles · precedents · positions · runs<br/>namespaces: markets / news / precedents</small>"]
    end

    subgraph CRON["Background jobs (GitHub Actions)"]
        MI["MarketIndexer<br/><small>every 2h</small>"]
        NI["NewsIndexer<br/><small>every 2h</small>"]
    end

    MI --> DB
    NI --> DB
    DB -.->|warm cache reads| ER
    CHAT -->|indexes articles| DB
```

## The 7 LLM calls per execute

| # | Module | Job |
|---|---|---|
| 1 | `QueryPlanner` | prompt → structured research plan (or refusal) |
| 2 | `SentimentScorer` | ONE batched call scoring all news + posts |
| 3–6 | `BullAnalyst` `BearAnalyst` `QuantAnalyst` `ResolutionSkeptic` | concurrent council on one shared context |
| 7 | `Judge` | writes the dossier around numbers computed by code |

`MarketChat` sits outside the 7-call execute pipeline: each chat question
costs at most 2 LLM calls (a planner deciding whether fresh intel is needed,
then the grounded answer). Articles it gathers are indexed into Supabase and
embedded by the `NewsIndexer` on its next pass.

`StrategyChat` (ONE LLM call per turn) is the Strategy Desk's control
channel: "turn off copy trading", "set stop loss to 30%", "halt everything"
become a settings patch. The LLM only proposes — deterministic code
whitelists the keys, clamps every number to `config.RISK_BOUNDS` /
`config.BANKROLL_BOUNDS`, persists to `agent_settings`, and reports the real
old→new diff. Every autonomous job reads those settings before trading.

## Agent registry

Everything the agent can do is declared in one place —
[backend/agent/registry/](../backend/agent/registry/): `tools.py` holds the
formal spec of every module/tool (name, kind, inputs, outputs, data sources,
implementation path) and `prompts/` holds the system prompts, one `.txt` per
LLM module. `GET /api/agent_info` serves both verbatim.

## Guardrails

- **Code does all arithmetic** — the pricing engine ([backend/agent/pricing.py](../backend/agent/pricing.py))
  computes fair value, edge, verdict and Kelly size; the Judge cannot alter them.
- Evidence is treated as untrusted content; every claim must cite an evidence id.
- PASS is a first-class outcome; repeated requests are served from a 15-min dossier cache.

## Beyond the graded pipeline (autonomy layer)

Scheduled jobs reuse the same pipeline: `Sentinel` (perception) files agenda
items, `WorkAgenda` investigates and trades under risk rules, strategy jobs
(arbitrage / market making / copy trading / correlation graph) run under the
Strategy Desk toggles, and `DailyBriefing` reports it all each morning.
`jobs/watch_live.py` adds a real-time WebSocket sense when run persistently
(it always watches held + watchlisted markets, even outside the trending set).
The risk manager's circuit breaker judges realized losses PLUS open
unrealized drawdown, records a daily equity snapshot (`equity_snapshots`)
that drives the portfolio page's equity curve, and runs **strategy
self-tuning** on every pass: a strategy that lost ≥ `TUNE_DISABLE_LOSS_USD`
over ≥ `TUNE_MIN_TRADES` trades in 7 days disables itself (no LLM involved).

`jobs/autopilot.py` runs ALL of these cadences locally in one crash-proof
process — full autonomy without GitHub Actions. `RedditIndexer`
(`jobs/index_social.py`, every 2h) scrapes Reddit for posts about tracked
markets (keyless; OAuth when configured), stores them in `social_posts`
tagged per market, and embeds them into the Pinecone `social` namespace —
`SocialScanner` and `MarketChat` top up from this warm cache whenever live
scrapes run thin.
