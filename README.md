# Polymarkov

An AI agent that produces a **pre-trade intelligence dossier** for a Polymarket market — news (GDELT), social sentiment, resolution-risk analysis, and a multi-persona AI council — then issues a **BUY_YES / BUY_NO / PASS** verdict with a fractional-Kelly position size, and can paper-trade it against the live CLOB order book.

> Educational course project. Paper trading only. **Not financial advice.**

## Architecture

`QueryPlanner → MarketResolver → EvidenceRetriever + SocialScanner → SentimentScorer → Council (BullAnalyst, BearAnalyst, QuantAnalyst, ResolutionSkeptic) → Judge → PaperBroker`, with background jobs `MarketIndexer` / `NewsIndexer` keeping Supabase + Pinecone warm. Exactly **7 LLM calls per execute**; all price/fee/edge/Kelly arithmetic is deterministic code ([backend/agent/pricing.py](backend/agent/pricing.py)).

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

## Local development

```bash
# 1. Env
cp .env.example .env       # then fill in the values

# 2. Backend (Python 3.12)
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
npm run dev:api            # FastAPI on :8000

# 3. Frontend (separate terminal)
npm install
npm run dev                # Next.js on :3000, /api/* proxied to :8000
```

Open http://localhost:3000.

## Notes

- The taker-fee table in [backend/config.py](backend/config.py) is a config default — re-check against Polymarket fee docs at deploy time.
- Background indexers run via GitHub Actions ([.github/workflows/indexers.yml](.github/workflows/indexers.yml)), never inside Vercel functions.

---

Vercel URL: {url}
GitHub Repo URL: {url}
