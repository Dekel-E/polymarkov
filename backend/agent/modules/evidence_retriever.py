"""EvidenceRetriever — deterministic tool: cached + live news -> ≤8 clusters.

Pinecone semantic search over cached news, live GDELT top-up, near-duplicate
removal (cosine > 0.92, keep highest-authority domain), event clustering
(same-day + cosine > 0.80), plus up to 5 resolved precedents for base rates.
Degrades gracefully: without Pinecone/embeddings it falls back to GDELT-only
with one cluster per article.
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass, field

from backend import config
from backend.agent.types import EvidenceCluster, Precedent, QueryPlan
from backend.data import gdelt, google_news, pinecone_client, web_search
from backend.llm import embeddings
from backend.llm.client import RunContext

MODULE = "EvidenceRetriever"

# rough authority ranking for duplicate resolution
_TIER1 = {"reuters.com", "apnews.com", "bloomberg.com", "ft.com", "wsj.com", "bbc.com"}


@dataclass
class EvidencePack:
    clusters: list[EvidenceCluster] = field(default_factory=list)
    precedents: list[Precedent] = field(default_factory=list)


def _authority(domain: str) -> int:
    return 2 if domain in _TIER1 else 1


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _day(published_at: str | None) -> str:
    return (published_at or "")[:10]


def cluster_articles(articles: list[dict], vectors: list[list[float]] | None) -> list[list[dict]]:
    """Dedup near-duplicates, then group same-day similar articles."""
    if not vectors:
        return [[a] for a in articles[: config.MAX_EVIDENCE_CLUSTERS]]

    # near-duplicate removal: keep the highest-authority representative
    kept: list[int] = []
    for i in range(len(articles)):
        dup_of = next(
            (j for j in kept if _cosine(vectors[i], vectors[j]) > config.DEDUP_COSINE_THRESHOLD),
            None,
        )
        if dup_of is None:
            kept.append(i)
        elif _authority(articles[i]["domain"]) > _authority(articles[dup_of]["domain"]):
            kept[kept.index(dup_of)] = i

    # event clustering: same day + cosine > threshold
    clusters: list[list[int]] = []
    for i in kept:
        home = next(
            (
                c
                for c in clusters
                if _day(articles[c[0]].get("published_at")) == _day(articles[i].get("published_at"))
                and _cosine(vectors[i], vectors[c[0]]) > config.CLUSTER_COSINE_THRESHOLD
            ),
            None,
        )
        if home is not None:
            home.append(i)
        else:
            clusters.append([i])

    return [[articles[i] for i in c] for c in clusters[: config.MAX_EVIDENCE_CLUSTERS]]


async def _pinecone_news(query: str) -> list[dict]:
    if not (pinecone_client.is_configured() and embeddings.is_configured()):
        return []
    try:
        vector = await asyncio.to_thread(embeddings.embed_one, query)
        matches = await asyncio.to_thread(pinecone_client.query, "news", vector, 12)
    except Exception:
        return []
    return [
        {
            "url": m["metadata"].get("url", ""),
            "title": m["metadata"].get("title", ""),
            "domain": m["metadata"].get("domain", ""),
            "published_at": m["metadata"].get("date") or None,
        }
        for m in matches
        # below the floor = merely nearest, not related — that's how a
        # geopolitics market once got a page of World Cup "evidence"
        if m["metadata"].get("url") and m["score"] >= config.NEWS_MIN_MATCH_SCORE
    ]


async def _precedents(question: str) -> list[Precedent]:
    if not (pinecone_client.is_configured() and embeddings.is_configured()):
        return []
    try:
        vector = await asyncio.to_thread(embeddings.embed_one, question)
        matches = await asyncio.to_thread(
            pinecone_client.query, "precedents", vector, config.MAX_PRECEDENTS
        )
    except Exception:
        return []
    out = []
    for m in matches:
        meta = m["metadata"]
        if m["score"] < config.PRECEDENT_MIN_MATCH_SCORE:
            continue
        if meta.get("outcome") in ("YES", "NO"):
            out.append(
                Precedent(
                    market_id=m["id"],
                    question=meta.get("question", ""),
                    category=meta.get("category", "other"),
                    outcome=meta["outcome"],
                )
            )
    return out


async def retrieve_evidence(ctx: RunContext, plan: QueryPlan, market) -> EvidencePack:
    news_query = " ".join(plan.entities[:3]) or market.question

    # two Google News angles: the planner's entities AND the literal question
    gnews_queries = [news_query]
    if market.question and market.question.lower() != news_query.lower():
        gnews_queries.append(market.question)

    gdelt_live, cached, precedents, *gnews_batches = await asyncio.gather(
        gdelt.fetch_articles(news_query),
        _pinecone_news(market.question),
        _precedents(market.question),
        *(google_news.fetch_articles(q, max_records=config.GNEWS_MAX_RECORDS) for q in gnews_queries),
    )
    gnews_live = [a for batch in gnews_batches for a in batch]

    # merge, dedup by url (live wins: it's fresher)
    by_url = {a["url"]: a for a in cached}
    by_url.update({a["url"]: a for a in gdelt_live})
    by_url.update({a["url"]: a for a in gnews_live})

    # web fallback: when the news feeds run thin, the agent searches the
    # open web itself (the top clusters get crawled for excerpts below)
    web_results: list[dict] = []
    if config.WEB_SEARCH_ENABLED and len(by_url) < config.WEB_SEARCH_MIN_ARTICLES:
        web_results = await web_search.search(news_query)
        for a in web_results:
            by_url.setdefault(a["url"], a)

    articles = list(by_url.values())
    live = gdelt_live + gnews_live + web_results

    vectors: list[list[float]] | None = None
    if articles and embeddings.is_configured():
        try:
            vectors = await asyncio.to_thread(
                embeddings.embed, [a["title"] or a["url"] for a in articles]
            )
        except Exception:
            vectors = None

    grouped = cluster_articles(articles, vectors)
    clusters = [
        EvidenceCluster(
            id=f"c{i + 1}",
            headline=group[0]["title"] or group[0]["url"],
            date=group[0].get("published_at"),
            source=group[0]["domain"],
            url=group[0]["url"],
            summary=(
                f"{len(group)} related articles" if len(group) > 1 else ""
            ),
            article_ids=[a["url"] for a in group],
        )
        for i, group in enumerate(grouped)
    ]

    # read the actual pages of the top clusters so the council argues over
    # substance, not headlines (bounded: N pages, short excerpts)
    to_read = clusters[: config.EXCERPT_CLUSTERS]
    if to_read:
        texts = await asyncio.gather(
            *(gdelt.fetch_article_text(c.url, max_chars=config.EXCERPT_MAX_CHARS) for c in to_read)
        )
        for cluster, text in zip(to_read, texts):
            cluster.excerpt = text

    ctx.add_tool_step(
        MODULE,
        f"news_query={news_query!r}; gdelt={len(gdelt_live)} google_news={len(gnews_live)} "
        f"web_search={len(web_results)} cached={len(cached)} articles",
        {
            "clusters": [
                {"id": c.id, "headline": c.headline, "source": c.source, "date": c.date}
                for c in clusters
            ],
            "precedents": [
                {"question": p.question, "outcome": p.outcome} for p in precedents
            ],
        },
    )
    return EvidencePack(clusters=clusters, precedents=precedents)
