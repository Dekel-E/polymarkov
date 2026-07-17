"""EvidenceRetriever relevance gate: off-topic live articles must not become
exhibits (they're dropped by embedding cosine to the market question)."""

from __future__ import annotations

import pytest

from backend.agent import pipeline
from backend.agent.types import QueryPlan
from backend.data import news, pinecone_client, social, supabase_client
from backend.llm import embeddings
from backend.llm.client import RunContext
from backend.tests.test_market_chat import make_market

# deterministic 2-D embeddings: on-topic aligns with the question axis,
# off-topic is orthogonal (cosine 0) — cleanly straddling the 0.55 floor
_ON = [1.0, 0.0]
_OFF = [0.0, 1.0]


def _vec_for(text: str) -> list[float]:
    return _OFF if "bakery" in text.lower() else _ON


@pytest.fixture
def evidence_world(monkeypatch):
    async def empty(*a, **k):
        return []

    async def gnews(query, max_records=10, days=7):
        return [
            {"url": "https://news.ex/fed", "title": "Fed signals a rate cut", "domain": "news.ex", "published_at": "2026-07-10"},
            {"url": "https://news.ex/cake", "title": "Local bakery wins an award", "domain": "news.ex", "published_at": "2026-07-10"},
        ]

    async def fake_text(url, max_chars=500):
        return "page text"

    monkeypatch.setattr(news, "gdelt_articles", empty)
    monkeypatch.setattr(news, "google_news_articles", gnews)
    monkeypatch.setattr(news, "web_search", empty)
    monkeypatch.setattr(news, "rss_articles", empty)
    monkeypatch.setattr(news, "wikipedia_articles", empty)
    monkeypatch.setattr(news, "fetch_article_text", fake_text)
    monkeypatch.setattr(social, "gather_social", empty)
    monkeypatch.setattr(pinecone_client, "is_configured", lambda: False)
    monkeypatch.setattr(supabase_client, "is_configured", lambda: False)
    monkeypatch.setattr(supabase_client, "upsert_articles", lambda rows: len(rows))
    monkeypatch.setattr(embeddings, "is_configured", lambda: True)
    monkeypatch.setattr(embeddings, "embed", lambda texts: [_vec_for(t) for t in texts])


@pytest.mark.asyncio
async def test_offtopic_article_is_gated_out(evidence_world):
    plan = QueryPlan(in_scope=True, market_query="fed rate cut", entities=["Fed", "rates"])
    pack = await pipeline.retrieve_evidence(RunContext(), plan, make_market())
    headlines = [c.headline for c in pack.clusters]
    assert any("Fed" in h for h in headlines)          # on-topic kept
    assert all("bakery" not in h.lower() for h in headlines)  # off-topic dropped


@pytest.mark.asyncio
async def test_gate_disabled_without_embeddings(monkeypatch, evidence_world):
    # no embeddings -> no semantic gate, both articles pass through
    monkeypatch.setattr(embeddings, "is_configured", lambda: False)
    plan = QueryPlan(in_scope=True, market_query="fed rate cut", entities=["Fed"])
    pack = await pipeline.retrieve_evidence(RunContext(), plan, make_market())
    headlines = [c.headline.lower() for c in pack.clusters]
    assert any("bakery" in h for h in headlines)  # ungated: the noisy one survives
