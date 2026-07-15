# Polymarkov

An AI agent that produces a **pre-trade intelligence dossier** for a Polymarket market — news (GDELT), social sentiment, resolution-risk analysis, and a multi-persona AI council — then issues a **BUY_YES / BUY_NO / PASS** verdict with a fractional-Kelly position size, and can paper-trade it against the live CLOB order book.

> Educational course project. Paper trading only. **Not financial advice.**

## Architecture

`QueryPlanner → MarketResolver → EvidenceRetriever + SocialScanner → SentimentScorer → Council (BullAnalyst, BearAnalyst, QuantAnalyst, ResolutionSkeptic) → Judge → PaperBroker`, with background jobs `MarketIndexer` / `NewsIndexer` keeping Supabase + Pinecone warm. Exactly **7 LLM calls per execute**; all price/fee/edge/Kelly arithmetic is deterministic code ([backend/agent/pricing.py](backend/agent/pricing.py)).

`MarketChat` adds grounded per-market Q&A outside the execute pipeline (≤2 LLM calls per question): it plans whether the question needs fresh intel, searches the web/news and scrapes socials when it does, indexes what it finds, and answers with citations. `DeskChat` (`POST /api/chat`, on the home page) is the global conversational entry point: it routes any question to the right market, to the desk's own portfolio/state, or to the agent's self-description — and out-of-scope asks get related Polymarket markets suggested instead of a dead-end refusal. `CrossVenueScanner` gives the council same-event odds from Kalshi as a second market-consensus prior. `/api/execute` accepts an optional `history` for follow-up prompts.

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

## Local development

```bash
# 1. Env
cp .env.example .env       # then fill in the values

# 2. Backend (Python 3.12) — one-time setup
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt

# 3. Run BOTH servers (two terminals — the GUI 500s without the backend)
npm run dev:api            # terminal 1: FastAPI on :8000 (uses .venv, no activation needed)
npm run dev                # terminal 2: Next.js on :3000, /api/* proxied to :8000
```

Open http://localhost:3000.

## Storage setup (one-time, Phase 3)

1. **Supabase**: create a project at https://supabase.com/dashboard → Project Settings → Data API: copy the URL into `SUPABASE_URL` and the `service_role` key into `SUPABASE_SERVICE_KEY` in `.env`. Then open the SQL Editor and run each file in [supabase/migrations/](supabase/migrations/) in order (0001 → 0005).
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

- [indexers.yml](.github/workflows/indexers.yml) — every 2h: index top markets + GDELT news into Supabase/Pinecone; daily: settle paper positions and harvest resolved markets into precedents.
- [automation.yml](.github/workflows/automation.yml) — every 4h: **AutoTrade** (the agent scans trending markets, analyzes up to `AUTO_RUNS_PER_JOB`, and paper-trades when the deterministic engine finds real net edge, capped at `AUTO_MAX_OPEN_POSITIONS` open positions) and **RefreshWatchlist** (re-analyzes user-watched markets whose dossier cache expired).

All jobs support `--dry-run` locally, e.g. `.venv\Scripts\python -m jobs.auto_trade --dry-run`.

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
