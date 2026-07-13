# Polymarkov — Architecture

One `/api/execute` run makes **exactly 7 LLM calls** (amber). Everything
else is deterministic code. Module names below are identical to the
`steps[]` trace and the PNG served at `/api/model_architecture`.

```mermaid
flowchart TB
    GUI["Web GUI<br/><small>POST /api/execute {prompt}</small>"]

    QP["QueryPlanner<br/><small>LLM #1 — scope, market query, entities</small>"]
    MR["MarketResolver<br/><small>tool — URL / text search / vector match</small>"]
    ER["EvidenceRetriever<br/><small>tool — news search + web fallback,<br/>dedup, cluster ≤8, read pages</small>"]
    SS["SocialScanner<br/><small>tool — comments + mention velocity</small>"]
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

    GUI --> QP --> MR
    MR --> ER
    MR --> SS
    ER --> SC
    SS --> SC
    SC --> COUNCIL --> JUDGE
    JUDGE --> OUT
    JUDGE --> PB

    subgraph EXT["External services"]
        GAMMA["Polymarket Gamma + CLOB"]
        NEWS["GDELT · Google News · Web"]
        SOCIAL["Polymarket Comments · Reddit"]
        LLMOD["LLMod.ai<br/><small>gpt-5.4-mini · text-embedding-3-small</small>"]
    end

    MR -.-> GAMMA
    ER -.-> NEWS
    SS -.-> SOCIAL
    PB -.-> GAMMA
    COUNCIL -.-> LLMOD

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
```

## The 7 LLM calls per execute

| # | Module | Job |
|---|---|---|
| 1 | `QueryPlanner` | prompt → structured research plan (or refusal) |
| 2 | `SentimentScorer` | ONE batched call scoring all news + posts |
| 3–6 | `BullAnalyst` `BearAnalyst` `QuantAnalyst` `ResolutionSkeptic` | concurrent council on one shared context |
| 7 | `Judge` | writes the dossier around numbers computed by code |

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
`jobs/watch_live.py` adds a real-time WebSocket sense when run persistently.
