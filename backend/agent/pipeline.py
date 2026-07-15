"""The /api/execute pipeline stages, in run order.

QueryPlanner (LLM #1) -> MarketResolver (tool) -> EvidenceRetriever ∥
SocialScanner ∥ CrossVenueScanner (tools) -> SentimentScorer (LLM #2) ->
[council.py: LLM #3-#6] -> Judge (LLM #7). Module names here are canonical
(registry/tools.py); the orchestrator wires the stages together.
"""

from __future__ import annotations

import asyncio
import json
import math
from dataclasses import dataclass, field
from typing import Optional

from backend import config
from backend.agent.council import time_context
from backend.agent.types import (
    EvidenceCluster,
    JudgeOutput,
    MarketState,
    PersonaOpinion,
    Precedent,
    PricingResult,
    QueryPlan,
    SocialPost,
    SocialPulse,
)
from backend.data import kalshi, news, pinecone_client, polymarket, social
from backend.llm import embeddings
from backend.llm.client import RunContext, load_prompt
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# QueryPlanner — LLM call #1: user prompt -> structured research plan
# ---------------------------------------------------------------------------


async def plan_query(ctx: RunContext, user_prompt: str) -> QueryPlan:
    raw = await ctx.call_llm("QueryPlanner", load_prompt("query_planner"), user_prompt)
    if isinstance(raw, dict) and raw.get("intent") not in ("market", "meta", "out_of_scope"):
        raw.pop("intent", None)  # fall back to the schema default
    try:
        return QueryPlan.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"QueryPlanner returned an unexpected schema: {exc}") from exc


# ---------------------------------------------------------------------------
# MarketResolver — deterministic tool: plan -> exactly one MarketState.
# Resolution ladder: pasted URL/slug -> Gamma text search (clear winner by
# volume) -> Pinecone vector match -> otherwise top candidates to pick from.
# ---------------------------------------------------------------------------

CLEAR_WINNER_VOLUME_RATIO = 3.0
VECTOR_MATCH_MIN_SCORE = 0.45


@dataclass
class ResolveResult:
    market: Optional[MarketState] = None
    candidates: list[dict] = field(default_factory=list)


def _candidate(m: dict) -> dict:
    return {
        "slug": m["slug"],
        "question": m["question"],
        "mid": m["mid"],
        "volume24h": m["volume24h"],
    }


async def _vector_match(query: str) -> Optional[str]:
    """Best market slug from the Pinecone `markets` namespace, if confident."""
    if not (pinecone_client.is_configured() and embeddings.is_configured()):
        return None
    try:
        vector = await asyncio.to_thread(embeddings.embed_one, query)
        matches = await asyncio.to_thread(pinecone_client.query, "markets", vector, 3)
    except Exception:
        return None
    if matches and matches[0]["score"] >= VECTOR_MATCH_MIN_SCORE:
        return matches[0]["metadata"].get("slug") or matches[0]["id"]
    return None


async def resolve_market(ctx: RunContext, plan) -> ResolveResult:
    query = plan.market_query or " ".join(plan.entities) or ""
    result = ResolveResult()
    how = ""

    # 1) explicit URL/slug
    ref = polymarket.parse_market_ref(plan.market_url or "")
    if ref:
        result.market = await polymarket.get_market_state(ref)
        how = f"url ref {ref!r}"

    # 2) Gamma text search with a clear winner
    if result.market is None and query:
        found = await polymarket.search_markets(query, limit=5)
        found = [m for m in found if m["yes_token_id"]]
        if len(found) == 1 or (
            len(found) > 1
            and found[0]["volume24h"] >= CLEAR_WINNER_VOLUME_RATIO * max(found[1]["volume24h"], 1e-9)
        ):
            result.market = await polymarket.get_market_state(found[0]["slug"])
            how = f"text search {query!r} (clear winner)"
        elif found:
            # 3) vector match against indexed markets
            slug = await _vector_match(query)
            if slug:
                result.market = await polymarket.get_market_state(slug)
                how = f"vector match {query!r} -> {slug!r}"
            if result.market is None:
                result.candidates = [_candidate(m) for m in found[:3]]
                how = f"ambiguous text search {query!r}"

    if result.market is None and not result.candidates:
        raise RuntimeError(
            f"No Polymarket market found for {query or plan.market_url!r}. "
            "Try pasting the market URL or being more specific."
        )

    ctx.add_tool_step(
        "MarketResolver",
        f"market_url={plan.market_url!r} market_query={query!r} -> resolved via {how}",
        (
            {
                "slug": result.market.slug,
                "question": result.market.question,
                "mid": result.market.mid,
                "spread": result.market.spread,
                "depth_at_ask_usd": result.market.depth_at_ask_usd,
            }
            if result.market
            else {"candidates": result.candidates}
        ),
    )
    return result


# ---------------------------------------------------------------------------
# EvidenceRetriever — deterministic tool: cached + live news -> ≤8 clusters.
# Pinecone semantic search over cached news, live GDELT/Google News top-up,
# near-duplicate removal (cosine > 0.92, keep highest-authority domain),
# event clustering (same-day + cosine > 0.80), up to 5 resolved precedents.
# Degrades gracefully without Pinecone/embeddings.
# ---------------------------------------------------------------------------

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
        news.gdelt_articles(news_query),
        _pinecone_news(market.question),
        _precedents(market.question),
        *(news.google_news_articles(q, max_records=config.GNEWS_MAX_RECORDS) for q in gnews_queries),
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
        web_results = await news.web_search(news_query)
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
            *(news.fetch_article_text(c.url, max_chars=config.EXCERPT_MAX_CHARS) for c in to_read)
        )
        for cluster, text in zip(to_read, texts):
            cluster.excerpt = text

    ctx.add_tool_step(
        "EvidenceRetriever",
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


# ---------------------------------------------------------------------------
# SocialScanner — deterministic tool: recent posts + mention velocity
# ---------------------------------------------------------------------------


async def scan_social(ctx: RunContext, plan: QueryPlan, market: MarketState) -> SocialPulse:
    query = plan.market_query or market.question
    data = await social.gather_social(market.event_id, query, limit=config.MAX_SOCIAL_POSTS)

    posts = [
        SocialPost(
            id=f"s{i + 1}",
            text=p["text"],
            source=p["source"],
            url=p.get("url", ""),
            created_at=p.get("created_at"),
        )
        for i, p in enumerate(data["posts"])
    ]
    pulse = SocialPulse(posts=posts, mention_velocity=data["mention_velocity"], note=data["note"])

    ctx.add_tool_step(
        "SocialScanner",
        f"event_id={market.event_id!r} query={query!r}",
        {
            "posts": len(posts),
            "sources": sorted({p.source for p in posts}),
            "mention_velocity": pulse.mention_velocity,
            "note": pulse.note,
        },
    )
    return pulse


# ---------------------------------------------------------------------------
# CrossVenueScanner — deterministic tool: same-event odds from Kalshi.
# A second venue pricing the same event is a market-consensus prior no news
# source can provide; the match is conservative — when unsure, nothing.
# ---------------------------------------------------------------------------


async def scan_cross_venue(ctx: RunContext, market: MarketState) -> Optional[dict]:
    result = await kalshi.find_matching_event(market.question)
    ctx.add_tool_step(
        "CrossVenueScanner",
        f"question={market.question!r}",
        result
        if result
        else {"found": False, "note": "no confident Kalshi match for this event"},
    )
    return result


# ---------------------------------------------------------------------------
# SentimentScorer — LLM call #2: ONE batched call scoring all news + posts
# ---------------------------------------------------------------------------

_STANCES = ("yes", "no", "neutral")


async def score_sentiment(
    ctx: RunContext,
    market: MarketState,
    clusters: list[EvidenceCluster],
    pulse: SocialPulse,
) -> None:
    """Mutates clusters/posts in place with sentiment + stance."""
    items = [
        {"id": c.id, "text": f"{c.headline} — {c.source}, {c.date or 'undated'}"}
        for c in clusters
    ] + [{"id": p.id, "text": p.text[:280]} for p in pulse.posts]
    if not items:
        return  # nothing to score; skipping the call saves budget

    user_prompt = (
        f"Market question: {market.question}\n"
        f"Resolution criteria (excerpt): {market.resolution_criteria[:500]}\n\n"
        f"Items to score:\n{json.dumps(items, ensure_ascii=False, indent=1)}"
    )
    raw = await ctx.call_llm("SentimentScorer", load_prompt("sentiment_scorer"), user_prompt)

    scored: dict[str, tuple[float, str]] = {}
    for row in raw.get("items", []) if isinstance(raw, dict) else []:
        try:
            sentiment = max(-1.0, min(1.0, float(row["sentiment"])))
            stance = row.get("stance", "neutral")
            scored[str(row["id"])] = (
                sentiment,
                stance if stance in _STANCES else "neutral",
            )
        except (KeyError, TypeError, ValueError):
            continue

    for c in clusters:
        if c.id in scored:
            c.sentiment, c.stance = scored[c.id]
    for p in pulse.posts:
        if p.id in scored:
            p.sentiment, p.stance = scored[p.id]


# ---------------------------------------------------------------------------
# Judge — pricing.py computes the decision (code), then LLM call #7 writes
# the dossier narrative. The LLM may NOT change the numbers: whatever it
# returns, the deterministic values are copied over its output.
# ---------------------------------------------------------------------------

_DIGEST_KEYS = {"BullAnalyst": "bull", "BearAnalyst": "bear", "QuantAnalyst": "quant", "ResolutionSkeptic": "skeptic"}


def _council_block(council: dict[str, PersonaOpinion]) -> str:
    parts = []
    for name, o in council.items():
        parts.append(
            f"--- {name} ---\n"
            f"P(YES): {o.estimated_probability:.2f} (confidence {o.confidence})\n"
            f"Thesis: {o.thesis}\n"
            f"Red flags: {'; '.join(o.red_flags) or 'none'}"
        )
    return "\n".join(parts)


def _numbers_block(pricing: PricingResult) -> str:
    data = {
        "verdict": pricing.verdict,
        "fair_probability": pricing.fair_adj,
        "net_edge_pts": pricing.net_edge_pts,
        "suggested_size_pct_bankroll": pricing.suggested_size_pct_bankroll,
        "market_mid": pricing.prior,
        "gross_edge_pts": pricing.gross_edge_pts,
        "half_spread": pricing.half_spread,
        "taker_fee": pricing.taker_fee,
        "resolution_risk": pricing.resolution_risk,
        "pass_reasons": pricing.pass_reasons,
    }
    return json.dumps(data, indent=1)


async def run_judge(
    ctx: RunContext,
    market: MarketState,
    council: dict[str, PersonaOpinion],
    pricing: PricingResult,
) -> JudgeOutput:
    user_prompt = (
        f"Market: {market.question}\n"
        f"Current mid: {market.mid:.3f} | Ends: {market.end_date or 'n/a'}\n"
        f"{time_context(market.end_date)}\n\n"
        f"== COUNCIL OPINIONS ==\n{_council_block(council)}\n\n"
        f"== COMPUTED DECISION (FINAL — copy these values exactly) ==\n"
        f"{_numbers_block(pricing)}"
    )
    raw = await ctx.call_llm("Judge", load_prompt("judge"), user_prompt)
    raw = raw if isinstance(raw, dict) else {}

    digest_raw = raw.get("council_digest") or {}
    digest = {
        key: str(digest_raw.get(key) or f"{name}: P(YES) {council[name].estimated_probability:.2f}")
        for name, key in _DIGEST_KEYS.items()
        if name in council
    }
    confidence = raw.get("confidence")
    if confidence not in ("low", "medium", "high"):
        confidence = "low"

    # Deterministic values ALWAYS win — the LLM's numbers are discarded.
    return JudgeOutput(
        verdict=pricing.verdict,
        fair_probability=pricing.fair_adj,
        net_edge_pts=pricing.net_edge_pts,
        confidence=confidence,
        suggested_size_pct_bankroll=pricing.suggested_size_pct_bankroll,
        summary=str(raw.get("summary") or "No narrative produced."),
        key_risks=[str(r) for r in (raw.get("key_risks") or [])][:5],
        council_digest=digest,
    )
