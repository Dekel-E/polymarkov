# Polymarkov

**An autonomous pre-trade intelligence desk for Polymarket prediction markets.**

Point it at any market — a URL, a slug, or a plain-English question — and it compiles a **dossier**: recent news, social sentiment, resolution-risk analysis, and a four-persona AI council. It then issues a **BUY_YES / BUY_NO / PASS** verdict with a fractional-Kelly position size, and can paper-trade that verdict against the live CLOB order book.

> Educational course project. **Paper trading only. Not financial advice.**

The headline design rule: **code does all the arithmetic; the LLM never computes a number.** The council argues in interpretable *weights*; a deterministic pricing engine ([backend/agent/pricing.py](backend/agent/pricing.py)) computes fair value, edge, verdict, and size. Every run is reproducible and auditable.

---

## The flow at a glance

```
prompt
  │
  ▼
QueryPlanner ── scope? which market? paper-trade?      (LLM #1)
  │
  ▼
MarketResolver ── URL / text search / vector match      (tool)
  │
  ▼
SearchQueryGenerator ── targeted news/web search queries  (LLM #2)
  │
  ├─▶ EvidenceRetriever ─┐  news: GDELT · Google News · RSS · Wikipedia · web
  ├─▶ SocialScanner ─────┤  social: Polymarket comments · Bluesky · Reddit   (concurrent tools)
  └─▶ CrossVenueScanner ─┘  same event priced on Kalshi
  │
  ▼
SentimentScorer ── ONE batched call over all evidence   (LLM #3)
  │
  ▼
Council (concurrent, one shared context)                (LLM #4–7)
  Bull · Bear · Quant · ResolutionSkeptic → interpretable weights
  │
  ▼
Deterministic pricing engine ── fair value, edge, verdict, Kelly size   (pure code)
  │
  ▼
Judge ── writes the narrative around the computed numbers   (LLM #8)
  │
  ├─▶ response + full steps[] trace  ──▶  GUI
  └─▶ PaperBroker ── fills the Kelly size on the live book   (only when Trade: yes and verdict ≠ PASS)
```

**Exactly 8 LLM calls per `/api/execute`** (fewer on short-circuits: cache hit = 0, out-of-scope = 1, empty evidence skips sentiment). A 15-minute dossier cache serves repeats with zero LLM calls. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full walkthrough.

---

## Required endpoints (course contract)

| Endpoint | Returns |
|---|---|
| `GET /api/team_info` | Team metadata `{group_batch_order_number, team_name, students[]}` |
| `GET /api/agent_info` | Description, purpose, prompt template, recorded examples with steps |
| `GET /api/model_architecture` | Architecture diagram (PNG) |
| `POST /api/execute` | Run the agent: `{"prompt": "..."}` → exactly `{status, error, response, steps}` |

## Extra endpoints (GUI + conversational + autonomy)

| Endpoint | Purpose |
|---|---|
| `POST /api/chat` | **DeskChat** — the single omni-chat (used on every page). Routes a message to market Q&A, a **paper trade**, a **watchlist** change, the portfolio, desk control, the agent's self-description, or a helpful refusal. Pass an optional `slug` so "buy $50 yes" / "watch this" scope to the market in view |
| `POST /api/market/chat` | **MarketChat** — grounded Q&A on one market (≤2 LLM calls); searches + indexes fresh intel, answers with citations |
| `POST /api/strategy/chat` | **StrategyChat** — plain-language control of the desk; instructions become a whitelisted, clamped settings patch |
| `GET /api/markets`, `/api/market`, `/api/search` | Live Polymarket data for the GUI |
| `GET /api/portfolio`, `/api/settings`, `/api/agenda`, `/api/activity` | Desk state for the terminal pages |

## Steps schema

Every entry in `steps[]` is `{ module, prompt: { system_prompt, user_prompt }, response }`. Module names are identical across the `steps[]` trace, the architecture PNG, and the registry ([backend/agent/registry/tools.py](backend/agent/registry/tools.py)) — the single source of truth. `/api/agent_info` serves that registry verbatim.

## Grader quickstart

Verify the four required endpoints in one go. Set `BASE` to the deployed URL (or `http://localhost:3000` in dev, with both servers up):

```bash
BASE=https://your-app.vercel.app          # or http://localhost:3000

curl -s $BASE/api/team_info | jq                       # {group_batch_order_number, team_name, students[]}
curl -s $BASE/api/agent_info | jq 'keys'               # description, purpose, prompt_template, prompt_examples, ...
curl -s $BASE/api/model_architecture -o architecture.png && file architecture.png   # PNG image data

curl -s -X POST $BASE/api/execute \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "Market: fed-decision-in-september\nFocus: all\nTrade: no"}' | jq '{status, error, response, steps: (.steps | length)}'
# → {status:"ok", error:null, response:"<dossier>", steps:7}
```

The GUI at `$BASE/` exercises the same `/api/execute` — enter a prompt, click **Run Agent**, and expand the **Run log** to inspect every step.

---

## Stack

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind, served at `/`. No auth — the GUI is available immediately.
- **Backend:** Python 3.12 + FastAPI as a single Vercel serverless function ([api/index.py](api/index.py)).
- **LLM:** LLMod.ai (OpenAI-compatible) — `MB5R2CF-azure/gpt-5.4-mini` (text), `text-embedding-3-small` (embeddings).
- **Storage (Phase-3 optional):** Supabase (rows) + Pinecone (vectors; namespaces `markets` / `news` / `precedents` / `social`). The agent runs *degraded but functional* without them.

## Local development

```bash
# 1. Env
cp .env.example .env          # then fill in the values

# 2. Backend (Python 3.12) — one-time setup
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
npm install

# 3. Run BOTH servers (the GUI 500s without the backend)
npm run up                    # FastAPI :8000 + Next.js :3000, each in its own window
npm run down                  # take everything down (also clears stale :8000 listeners)

# ...or manually, in two terminals:
npm run dev:api               # FastAPI on :8000 (uses .venv directly, no activation)
npm run dev                   # Next.js on :3000, /api/* proxied to :8000
```

Open http://localhost:3000.

## Tests & checks

```bash
.venv\Scripts\python -m pytest backend/tests -q      # full suite (237 tests)
npx tsc --noEmit                                      # frontend type-check
npm run lint                                          # frontend lint
.venv\Scripts\python -m scripts.gen_architecture_png  # regenerate the PNG after any module rename
```

## Storage setup (one-time, Phase 3)

1. **Supabase** — create a project → Project Settings → Data API: copy the URL into `SUPABASE_URL` and the `service_role` key into `SUPABASE_SERVICE_KEY`. In the SQL Editor, run every file in [supabase/migrations/](supabase/migrations/) **in order (0001 → 0016)**.
2. **Pinecone** — create an API key → `PINECONE_API_KEY`. The index (`PINECONE_INDEX`, default `polymarkov`, serverless, dim 1536, cosine) is created automatically on first use.
3. **Backfill & first index run** (needs `LLMOD_*` set for embeddings):
   ```bash
   .venv\Scripts\python -m jobs.index_markets
   .venv\Scripts\python -m jobs.index_news
   .venv\Scripts\python -m scripts.seed_precedents    # ≥200 resolved markets
   ```
   Every job supports `--dry-run` to preview without writing.
4. **GitHub Actions** — add the env values as repo secrets so the scheduled workflows can run.

## Autonomy layer (optional, reuses the same pipeline)

- **Local autopilot (no GitHub needed):** `.venv\Scripts\python -m jobs.autopilot` runs the entire desk in one crash-proof process — risk manager every 30 min, indexers every 2h, sentinel/agenda/market-maker hourly, trading strategies every 4h, settlement + briefing daily. `--once` = single pass, `--dry-run` = no writes.
- **Scheduled (GitHub Actions):** `indexers.yml` (index markets/news/Reddit, settle positions, harvest precedents) and `automation.yml` (AutoTrade + RefreshWatchlist).
- **Real-time:** `python -m jobs.watch_live` — a persistent WebSocket watcher (needs a persistent host, not Actions) that reacts to book updates in seconds.

Every strategy gates on `agent_settings` (toggles + risk rules + halt) read at run time, respects the `MAX_ANALYSES_PER_DAY` LLM budget, and self-tunes (a strategy that lost ≥ `TUNE_DISABLE_LOSS_USD` over ≥ `TUNE_MIN_TRADES` trades in 7 days disables itself — no LLM involved).

## Deployment (Vercel)

Deployed as a single serverless function. `vercel.json` sets `maxDuration: 300`; `/api/execute` wraps the pipeline in a 270s `asyncio.wait_for` so it always returns the graded envelope before Vercel's 300s kill. Keep the Vercel account active until grading.

## Notes & gotchas

- Background indexers run via GitHub Actions or the local autopilot — **never inside Vercel functions**.
- `backend/assets/agent_examples.json` (served as `prompt_examples`) is a **frozen recording**; re-record with `scripts/record_examples.py` if the pipeline changes.
- `backend/config.py` `TEAM_INFO` must hold your real team name, student names/emails, and batch/order number before submission.
- Wikipedia's API 403s generic User-Agents — it needs a contact-info UA (handled in `news.py`).

---

Vercel URL: {url}
GitHub Repo URL: {url}
