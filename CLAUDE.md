# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Polymarkov is an educational course-project AI agent: it produces a pre-trade intelligence **dossier** for a Polymarket prediction market (news, social sentiment, resolution-risk, a four-persona AI council), issues a **BUY_YES / BUY_NO / PASS** verdict with a fractional-Kelly size, and paper-trades it against the live CLOB order book. Paper trading only, not financial advice. The course spec lives in `Project (1).pdf`.

## Commands

```bash
# Setup (Python 3.12)
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
npm install

# Dev — needs BOTH servers (the GUI 500s without the backend)
npm run up      # starts FastAPI :8000 + Next.js :3000, each in its own window (scripts/dev.ps1)
npm run down    # kills everything on :8000/:3000
# ...or manually: `npm run dev:api` (backend) + `npm run dev` (frontend) in two terminals

# Tests (pytest, asyncio_mode=auto so async tests need no marker)
.venv\Scripts\python -m pytest backend/tests -q          # full suite
.venv\Scripts\python -m pytest backend/tests/test_pricing.py -q          # one file
.venv\Scripts\python -m pytest backend/tests/test_pricing.py::test_kelly -q   # one test

# Frontend checks
npx tsc --noEmit    # type-check (there is no separate build step to run for review)
npm run lint

# Jobs — every job supports --dry-run (no writes/trades)
.venv\Scripts\python -m jobs.autopilot --once --dry-run   # runs the WHOLE autonomous desk locally (--once = single pass)
.venv\Scripts\python -m jobs.auto_trade --dry-run

# Regenerate the architecture PNG after ANY module-name change (course requirement)
.venv\Scripts\python -m scripts.gen_architecture_png
```

The frontend proxies `/api/*` to `:8000` in dev (`next.config.ts`). `.venv\Scripts\python` is used directly everywhere — do not rely on venv activation. Watch for **stale uvicorn on :8000** on Windows (symptom: 404 on routes that exist on disk); `npm run down` clears it.

## Load-bearing invariants (do not break these)

- **Code does ALL arithmetic; the LLM never computes a number.** `backend/agent/pricing.py` computes fair value, edge, verdict, and Kelly size deterministically. The Judge LLM writes narrative only — `pipeline.run_judge` overwrites every number the model returns with the deterministic values. Personas emit interpretable *weights*, not math.
- **Exactly 8 LLM calls per `/api/execute`**: QueryPlanner → SearchQueryGenerator → SentimentScorer → Bull/Bear/Quant/ResolutionSkeptic (concurrent) → Judge. Fewer on short-circuits (cache hit = 0, meta/out-of-scope = 1, empty sentiment items skips SentimentScorer). Adding/removing an LLM call to the execute path changes a graded contract and must be reflected in the steps trace, the architecture PNG, and test_pipeline.py's count — don't do it casually.
- **Module names must match across three places**: the `steps[]` trace, the architecture PNG (`scripts/gen_architecture_png.py`), and `backend/agent/registry/tools.py`. The registry is the single source of truth (`CANONICAL_MODULES` derives from it); `/api/agent_info` serves it verbatim. Rename in all three or nowhere.
- **The `/api/execute` envelope is graded**: top-level fields are exactly `{status, error, response, steps}`. The extra `ui` payload is stripped unless `?ui=1`. It never returns a non-200 — pipeline exceptions become `status:"error"` envelopes (`orchestrator.run_pipeline` wraps everything, plus a 270s `asyncio.wait_for` so Vercel's 300s kill can't win).
- **No auth anywhere** (course requirement) and **single-user**: one shared paper book. `get_portfolio()` takes no args; the `strategy` column distinguishes agent vs manual trades. Do not reintroduce per-user semantics.
- **Every LLM call goes through `RunContext.call_llm`** (`backend/llm/client.py`), which captures the step (including on failure), retries invalid JSON exactly once, and enforces the timeout. Tool steps use `add_tool_step`.

## Architecture

**Backend** is a FastAPI app (`api/index.py`) deployed as a single Vercel serverless function; all real logic is in `backend/`. **Frontend** is Next.js App Router + Tailwind in `app/` + `components/`, talking to the API via `lib/api.ts`.

**The execute pipeline** (`backend/agent/orchestrator.py` orchestrates; `pipeline.py` holds each stage): QueryPlanner parses intent → MarketResolver (URL/text-search/Pinecone vector match) → EvidenceRetriever ∥ SocialScanner ∥ CrossVenueScanner (concurrent tools) → SentimentScorer (one batched call) → Council (4 personas on one shared context, `council.py`) → deterministic pricing → Judge → PaperBroker (only when `Trade: yes` and verdict ≠ PASS). A 15-min dossier cache (`intel_cache.py`) serves repeats with zero LLM calls.

**Degradation philosophy**: sources are best-effort and return `[]`/no-op instead of raising when unconfigured or blocked. Supabase/Pinecone/LLM helpers all guard on `is_configured()`. A single council persona failure degrades to a null 0.5 opinion; all four failing raises (never price a fabricated council). This is deliberate — preserve it when editing.

**Evidence sources** (`backend/data/news.py`, all keyless): GDELT, Google News RSS, curated RSS feeds + Wikipedia (these work where GDELT's IP block bites), DuckDuckGo fallback. Social (`social.py`): Polymarket comments, Bluesky (keyless), Reddit (keyless search, OAuth when creds set — often IP-blocked). **On-demand indexing**: EvidenceRetriever and MarketChat upsert everything they fetch into Supabase tagged with the market slug, so future runs retrieve it and the NewsIndexer embeds it into Pinecone.

**RAG**: Pinecone (one cosine index, dim 1536) with namespaces `markets` / `news` / `precedents` / `social`. Vector *retrieval* happens only in the request path (read-only); vector *writes* happen only in the background jobs. Relevance floors (`config.NEWS_MIN_MATCH_SCORE` etc.) are deliberately strict because the embeddings run "hot".

**Conversational layer** (`backend/agent/chat.py`, outside the 7-call pipeline): `MarketChat` (per-market Q&A, ≤2 LLM calls, searches+indexes+cites), `DeskChat` (global router → market / portfolio / control / meta / refusal), `StrategyChat` (natural-language control of the desk — the LLM proposes a settings patch, `supabase_client.sanitize_settings_patch` whitelists keys and clamps numbers before persisting).

**Autonomy layer** (`jobs/`, reuses the same pipeline): `sentinel` (perception → agenda) → `work_agenda` (investigate/trade under risk rules) → strategy jobs (`scan_arbitrage`, `market_maker`, `copy_trade`) → `manage_risk` (stop-loss/take-profit, circuit breaker, LLM-free strategy self-tuning, equity snapshots) → `resolve_positions`/`daily_briefing`. Runs on GitHub Actions cron once pushed with secrets, OR entirely locally via `jobs/autopilot.py`. `jobs/watch_live.py` is a persistent WebSocket real-time sense (needs a persistent host, not Actions). All strategies gate on `agent_settings` (toggles + risk rules + halt) read at run time.

**Config** (`backend/config.py`): central home for all pricing constants, thresholds, and feed lists. `_env()` strips whitespace (pasted CI secrets carry trailing newlines). Defaults point at the LLMod course models; local dev can override to any OpenAI-compatible provider (e.g. Gemini) via `.env`.

## Storage & deploy

Supabase (rows) + Pinecone (vectors) are Phase-3 optional — the agent runs degraded without them. Migrations in `supabase/migrations/` run in order (0001 → 0016) in the Supabase SQL editor. Background indexers run via GitHub Actions or the local autopilot, **never inside Vercel functions**.

## Gotchas

- `backend/assets/agent_examples.json` (served by `/api/agent_info` as `prompt_examples`) is a **frozen recording** and goes stale when the pipeline changes — re-record with `scripts/record_examples.py` before submission.
- `backend/config.py` `TEAM_INFO` has `TODO_*` placeholders that must be real before grading.
- Wikipedia's API 403s generic User-Agents — it needs a contact-info UA (handled in `news.py`).
- When adding a job, respect the settings gates (`strategies_allowed()`) and the `MAX_ANALYSES_PER_DAY` LLM budget.
