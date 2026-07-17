# Polymarkov

An AI agent that produces a **pre-trade intelligence dossier** for a Polymarket market — news (GDELT), social sentiment, resolution-risk analysis, and a multi-persona AI council — then issues a **BUY_YES / BUY_NO / PASS** verdict with a fractional-Kelly position size, and can paper-trade it against the live CLOB order book.

> Educational course project. Paper trading only. **Not financial advice.**

## Architecture

`QueryPlanner → MarketResolver → EvidenceRetriever + SocialScanner → SentimentScorer → Council (BullAnalyst, BearAnalyst, QuantAnalyst, ResolutionSkeptic) → Judge → PaperBroker`, with background jobs `MarketIndexer` / `NewsIndexer` keeping Supabase + Pinecone warm. Exactly **7 LLM calls per execute**; all price/fee/edge/Kelly arithmetic is deterministic code ([backend/agent/pricing.py](backend/agent/pricing.py)).

`EvidenceRetriever` gathers news from GDELT, Google News, **curated RSS feeds** (reputable outlets, filtered to the market's terms) and **Wikipedia** (all keyless — they work where GDELT's IP block bites), with a web-search fallback; everything it fetches is **indexed on demand** back into Supabase tagged with the market, so future runs (and the vector index) can retrieve it.

`MarketChat` adds grounded per-market Q&A outside the execute pipeline (≤2 LLM calls per question): it plans whether the question needs fresh intel, searches the web/news and scrapes socials when it does, indexes what it finds, and answers with citations. `DeskChat` (`POST /api/chat`, on the home page) is the global conversational entry point: it routes any question to the right market, to the desk's own portfolio/state, or to the agent's self-description — and out-of-scope asks get related Polymarket markets suggested instead of a dead-end refusal. `StrategyChat` (`POST /api/strategy/chat`, on the Strategy Desk) is the control channel: plain-language instructions ("turn off copy trading", "set stop loss to 30%", "halt everything") become a settings patch that code whitelists and clamps before persisting — the autonomous jobs obey it on their next run. DeskChat routes control instructions there too, so the whole desk is steerable from the home-page chat. `CrossVenueScanner` gives the council same-event odds from Kalshi as a second market-consensus prior. `/api/execute` accepts an optional `history` for follow-up prompts.

**Agent registry:** everything the agent can do — formal tool/module specs and every system prompt — lives in [backend/agent/registry/](backend/agent/registry/) (`tools.py` + `prompts/*.txt`), served verbatim by `/api/agent_info`.

## Stack

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind, served at `/`
- **Backend:** Python 3.12 + FastAPI as a Vercel serverless function ([api/index.py](api/index.py))
- **LLM:** LLMod.ai (OpenAI-compatible) — `MB5R2CF-azure/gpt-5.4-mini`, embeddings `text-embedding-3-small`
- **Storage:** Supabase (rows) + Pinecone (vectors, namespaces `markets` / `news` / `precedents`)

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/team_info` | Team metadata |
| `GET /api/agent_info` | Agent description, prompt template, recorded examples |
| `GET /api/model_architecture` | Architecture diagram (PNG) |
| `POST /api/execute` | Run the agent: `{"prompt": "..."}` → `{status, error, response, steps}` |
| `POST /api/market/chat` | Grounded Q&A on one market: `{"slug", "question", "history"}` → answer + citations (searches & indexes fresh intel when needed) |
| `POST /api/chat` | Global desk chat: routes any question to a market / the portfolio / the agent's self-description |
| `POST /api/strategy/chat` | Strategy Desk control chat: instructions become whitelisted, clamped settings changes |

## Local development

```bash
# 1. Env
cp .env.example .env       # then fill in the values

# 2. Backend (Python 3.12) — one-time setup
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt

# 3. Run BOTH servers with one command (kills stale listeners first,
#    then opens each server in its own window)
npm run up                 # = .\scripts\dev.ps1
npm run down               # = .\scripts\dev.ps1 -Stop   (take everything down)

# ...or manually in two terminals (the GUI 500s without the backend):
npm run dev:api            # terminal 1: FastAPI on :8000 (uses .venv, no activation needed)
npm run dev                # terminal 2: Next.js on :3000, /api/* proxied to :8000
```

Open http://localhost:3000.

## Storage setup (one-time, Phase 3)

1. **Supabase**: create a project at https://supabase.com/dashboard → Project Settings → Data API: copy the URL into `SUPABASE_URL` and the `service_role` key into `SUPABASE_SERVICE_KEY` in `.env`. Then open the SQL Editor and run each file in [supabase/migrations/](supabase/migrations/) in order (0001 → 0015).
2. **Pinecone**: create an API key at https://app.pinecone.io → put it in `PINECONE_API_KEY`. The index (`PINECONE_INDEX`, default `polymarkov`, serverless, dim 1536, cosine) is created automatically on first use.
3. **Backfill & first index run** (needs `LLMOD_*` set too, for embeddings):
   ```bash
   .venv\Scripts\python -m jobs.index_markets
   .venv\Scripts\python -m jobs.index_news
   .venv\Scripts\python -m scripts.seed_precedents   # ≥200 resolved markets
   ```
   Every job supports `--dry-run` to preview without writing.
4. **GitHub Actions**: add all six env values as repo secrets so [.github/workflows/indexers.yml](.github/workflows/indexers.yml) can run on schedule.

## Automation (GitHub Actions)

Once the repo is on GitHub with secrets set, two workflows run on schedule:

- [indexers.yml](.github/workflows/indexers.yml) — every 2h: index top markets, GDELT news, and Reddit posts (RedditIndexer — keyless scrape tagged per market, embedded into Pinecone `social`) into Supabase/Pinecone; daily: settle paper positions and harvest resolved markets into precedents.
- [automation.yml](.github/workflows/automation.yml) — every 4h: **AutoTrade** (the agent scans trending markets, analyzes up to `AUTO_RUNS_PER_JOB`, and paper-trades when the deterministic engine finds real net edge, capped at the Strategy Desk's `max_open_positions`) and **RefreshWatchlist** (re-analyzes user-watched markets whose dossier cache expired).

All jobs support `--dry-run` locally, e.g. `.venv\Scripts\python -m jobs.auto_trade --dry-run`.

**Local autopilot (no GitHub needed):** `.venv\Scripts\python -m jobs.autopilot`
runs the entire autonomous desk in one process — risk manager every 30 min,
indexers every 2h, sentinel/agenda/market-maker hourly, trading strategies
every 4h, settlement + briefing daily. Each job runs isolated (a crash or
hang never stops the desk) and every strategy toggle / circuit breaker /
self-tuning rule still applies. `--once` does a single full pass;
`--dry-run` makes no writes. Self-tuning (a strategy that lost ≥$50 over ≥5
trades in 7 days disables itself) runs on every risk-manager pass — no LLM
required.

**Real-time mode:** `python -m jobs.watch_live` is a persistent WebSocket watcher
(needs your PC or a VPS — not GitHub Actions). It sees live book updates on
tracked + trending markets and reacts in seconds: price jumps and YES+NO
spread violations go straight onto the agent's agenda, and drifting mids
trigger immediate market-maker requotes.

## Notes

- The taker-fee table in [backend/config.py](backend/config.py) is a config default — re-check against Polymarket fee docs at deploy time.
- Background indexers run via GitHub Actions ([.github/workflows/indexers.yml](.github/workflows/indexers.yml)), never inside Vercel functions.

---

Vercel URL: {url}
GitHub Repo URL: {url}
