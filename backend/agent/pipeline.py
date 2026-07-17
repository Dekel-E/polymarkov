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
from backend.data import kalshi, news, pinecone_client, polymarket, social, supabase_client
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


async def _empty_articles() -> list[dict]:
    """A completed no-op coroutine — keeps asyncio.gather positional when a
    source is feature-flagged off."""
    return []


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

    # curated RSS + Wikipedia are keyless and work where GDELT's IP block bites
    rss_feeds = news.rss_feeds_for(market.category) if config.RSS_ENABLED else []
    wiki_query = market.question or news_query

    gdelt_live, cached, precedents, rss_live, wiki_live, *gnews_batches = await asyncio.gather(
        news.gdelt_articles(news_query),
        _pinecone_news(market.question),
        _precedents(market.question),
        news.rss_articles(news_query, rss_feeds) if rss_feeds else _empty_articles(),
        news.wikipedia_articles(wiki_query) if config.WIKI_ENABLED else _empty_articles(),
        *(news.google_news_articles(q, max_records=config.GNEWS_MAX_RECORDS) for q in gnews_queries),
    )
    gnews_live = [a for batch in gnews_batches for a in batch]

    # merge, dedup by url (live wins: it's fresher)
    by_url = {a["url"]: a for a in cached}
    for a in gdelt_live + gnews_live + rss_live + wiki_live:
        by_url[a["url"]] = a

    # web fallback: when the news feeds run thin, the agent searches the
    # open web itself (the top clusters get crawled for excerpts below)
    web_results: list[dict] = []
    if config.WEB_SEARCH_ENABLED and len(by_url) < config.WEB_SEARCH_MIN_ARTICLES:
        web_results = await news.web_search(news_query)
        for a in web_results:
            by_url.setdefault(a["url"], a)

    articles = list(by_url.values())

    # Embed the market question + every article title in ONE call, then GATE
    # OUT live articles that are semantically unrelated to the question — the
    # fix for off-topic exhibits. (Cached Pinecone news already cleared a
    # higher floor upstream, so it survives this lower one.)
    vectors: list[list[float]] | None = None
    dropped_offtopic = 0
    if articles and embeddings.is_configured():
        try:
            embedded = await asyncio.to_thread(
                embeddings.embed,
                [market.question, *[a["title"] or a["url"] for a in articles]],
            )
            q_vec, title_vecs = embedded[0], embedded[1:]
            kept = [
                (a, v)
                for a, v in zip(articles, title_vecs)
                if _cosine(v, q_vec) >= config.LIVE_EVIDENCE_MIN_SCORE
            ]
            dropped_offtopic = len(articles) - len(kept)
            articles = [a for a, _ in kept]
            vectors = [v for _, v in kept]
        except Exception:
            vectors = None

    # index on demand: persist only the RELEVANT articles, tagged with this
    # market, so future runs retrieve them (and the NewsIndexer embeds them
    # into Pinecone). Gating first means the market's cache is never polluted
    # with off-topic noise. Best-effort — a cache write must never break a run.
    if articles:
        try:
            await asyncio.to_thread(
                supabase_client.upsert_articles,
                [{**a, "entities": [market.slug]} for a in articles if a.get("url")],
            )
        except Exception:  # noqa: BLE001
            pass

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
    # substance, not headlines (bounded: N pages, short excerpts). Sources
    # that carry their own text (Wikipedia) are used verbatim, never crawled.
    pre_text = {a["url"]: a["fetched_text"] for a in articles if a.get("fetched_text")}

    async def _excerpt(url: str) -> str:
        if url in pre_text:
            return pre_text[url][: config.EXCERPT_MAX_CHARS]
        return await news.fetch_article_text(url, max_chars=config.EXCERPT_MAX_CHARS)

    to_read = clusters[: config.EXCERPT_CLUSTERS]
    if to_read:
        texts = await asyncio.gather(*(_excerpt(c.url) for c in to_read))
        for cluster, text in zip(to_read, texts):
            cluster.excerpt = text

    ctx.add_tool_step(
        "EvidenceRetriever",
        f"news_query={news_query!r}; gdelt={len(gdelt_live)} google_news={len(gnews_live)} "
        f"rss={len(rss_live)} wikipedia={len(wiki_live)} web_search={len(web_results)} "
        f"cached={len(cached)} articles; dropped {dropped_offtopic} off-topic "
        f"(< {config.LIVE_EVIDENCE_MIN_SCORE} cosine to the market question)",
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

    # top up from the RedditIndexer's warm cache (indexed posts tagged with
    # this market) — live scrapes run thin when sources rate-limit
    raw_posts = list(data["posts"])
    if len(raw_posts) < config.MAX_SOCIAL_POSTS:
        seen = {p.get("url") for p in raw_posts if p.get("url")}
        indexed = await asyncio.to_thread(
            supabase_client.get_social_posts_for, market.slug, config.MAX_SOCIAL_POSTS
        )
        for row in indexed:
            if row["url"] in seen:
                continue
            raw_posts.append(
                {"text": row["text"], "source": row["source"], "url": row["url"],
                 "created_at": row.get("posted_at")}
            )
            seen.add(row["url"])
            if len(raw_posts) >= config.MAX_SOCIAL_POSTS:
                break

    posts = [
        SocialPost(
            id=f"s{i + 1}",
            text=p["text"],
            source=p["source"],
            url=p.get("url", ""),
            created_at=p.get("created_at"),
        )
        for i, p in enumerate(raw_posts)
    ]
    note = data["note"]
    if len(raw_posts) > len(data["posts"]):
        note += f" (+{len(raw_posts) - len(data['posts'])} indexed posts from the Reddit cache)"
    pulse = SocialPulse(posts=posts, mention_velocity=data["mention_velocity"], note=note)

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
    try:
        raw = await ctx.call_llm("SentimentScorer", load_prompt("sentiment_scorer"), user_prompt)
    except Exception as exc:  # noqa: BLE001 — scoring is enrichment, not a hard
        # dependency: leave items unscored instead of killing the run. The
        # failed call is still recorded in steps[] by call_llm.
        print(f"SentimentScorer degraded, items left unscored: {type(exc).__name__}")
        return

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
