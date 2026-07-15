"""Pydantic contracts for the whole pipeline.

This file is the single source of truth for shapes; lib/types.ts mirrors the
ones the frontend consumes.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Course-mandated envelope
# ---------------------------------------------------------------------------


class StepPrompt(BaseModel):
    system_prompt: str
    user_prompt: str


class Step(BaseModel):
    module: str
    prompt: StepPrompt
    response: Any


class ExecuteIn(BaseModel):
    prompt: str
    # optional back-and-forth support: [{role: user|assistant, content: str}]
    history: list[dict] = Field(default_factory=list)


class ExecuteOut(BaseModel):
    status: Literal["ok", "error"]
    error: Optional[str] = None
    response: Optional[str] = None
    steps: list[Step] = Field(default_factory=list)
    # Optional structured payload for the GUI; graders read `response`.
    ui: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# QueryPlanner output (§3.1)
# ---------------------------------------------------------------------------


class QueryPlan(BaseModel):
    in_scope: bool
    intent: Literal["market", "meta", "out_of_scope"] = "market"
    market_query: Optional[str] = None
    market_url: Optional[str] = None
    entities: list[str] = Field(default_factory=list)
    intel_focus: list[str] = Field(default_factory=lambda: ["news", "socials", "resolution"])
    wants_trade: bool = False
    language: str = "English"
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Market state (§3.2)
# ---------------------------------------------------------------------------


class MarketState(BaseModel):
    question: str
    slug: str
    event_id: str = ""  # Gamma event id (used for the comments API)
    end_date: Optional[str] = None
    resolution_criteria: str = ""
    category: str = "other"
    yes_token_id: str
    mid: float
    best_bid: Optional[float] = None
    best_ask: Optional[float] = None
    spread: Optional[float] = None
    depth_at_ask_usd: float = 0.0
    volume24h: float = 0.0
    price_history_7d: list[tuple[float, float]] = Field(default_factory=list)  # (ts, price)


# ---------------------------------------------------------------------------
# Evidence & social
# ---------------------------------------------------------------------------


class Article(BaseModel):
    id: str
    url: str
    title: str
    domain: str
    published_at: Optional[str] = None
    snippet: str = ""
    sentiment: Optional[float] = None            # -1..1, filled by SentimentScorer
    stance: Optional[Literal["yes", "no", "neutral"]] = None


class EvidenceCluster(BaseModel):
    id: str                                       # e.g. "c1"
    headline: str
    date: Optional[str] = None
    source: str = ""
    url: str = ""
    summary: str = ""
    excerpt: str = ""                             # readable text fetched from the page
    sentiment: Optional[float] = None
    stance: Optional[Literal["yes", "no", "neutral"]] = None
    article_ids: list[str] = Field(default_factory=list)


class Precedent(BaseModel):
    market_id: str
    question: str
    category: str = "other"
    outcome: Literal["YES", "NO"]
    final_mid_7d_before: Optional[float] = None


class SocialPost(BaseModel):
    id: str                                       # e.g. "s1"
    text: str
    source: str
    url: str = ""
    created_at: Optional[str] = None
    sentiment: Optional[float] = None
    stance: Optional[Literal["yes", "no", "neutral"]] = None


class SocialPulse(BaseModel):
    posts: list[SocialPost] = Field(default_factory=list)
    mention_velocity: Optional[float] = None
    note: str = ""


# ---------------------------------------------------------------------------
# Council (§3.6)
# ---------------------------------------------------------------------------


class EvidenceWeight(BaseModel):
    evidence_id: str
    direction: Literal["yes", "no"]
    strength: float = Field(ge=0, le=1)
    reliability: float = Field(ge=0, le=1)
    already_priced_in: float = Field(ge=0, le=1)
    citation: str = ""


class PersonaOpinion(BaseModel):
    thesis: str
    evidence_weights: list[EvidenceWeight] = Field(default_factory=list)
    estimated_probability: float = Field(ge=0, le=1)
    confidence: Literal["low", "medium", "high"]
    red_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Pricing & verdict (§6)
# ---------------------------------------------------------------------------


class PricingResult(BaseModel):
    prior: float
    fair: float
    fair_adj: float
    gross_edge_pts: float
    half_spread: float
    taker_fee: float
    slippage: float = 0.0
    net_edge_pts: float
    verdict: Literal["BUY_YES", "BUY_NO", "PASS"]
    pass_reasons: list[str] = Field(default_factory=list)
    suggested_size_pct_bankroll: float = 0.0
    resolution_risk: Literal["low", "medium", "high"] = "medium"


class JudgeOutput(BaseModel):
    verdict: Literal["BUY_YES", "BUY_NO", "PASS"]
    fair_probability: float
    net_edge_pts: float
    confidence: Literal["low", "medium", "high"]
    suggested_size_pct_bankroll: float
    summary: str
    key_risks: list[str] = Field(default_factory=list)
    council_digest: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Paper trading (§3.8)
# ---------------------------------------------------------------------------


class FillReport(BaseModel):
    position_id: str
    market_id: str
    side: Literal["BUY_YES", "BUY_NO"]
    size_usd: float
    vwap: float
    slippage_bps: float
    fee_paid: float
    levels_consumed: int
