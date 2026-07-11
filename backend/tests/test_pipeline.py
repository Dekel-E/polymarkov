"""End-to-end pipeline test with a mocked LLM and mocked external APIs.

Verifies the Phase 5 contract offline: ok/error envelope, exactly 7 LLM
steps with canonical module names, tool steps in the trace, citations
flowing through, and the dossier/ui assembly.
"""

import pytest

from backend import config
from backend.agent import orchestrator
from backend.agent.types import MarketState, Step, StepPrompt
from backend.data import gdelt, polymarket, social
from backend.llm.client import RunContext, TOOL_SYSTEM_PROMPT

# ---------------------------------------------------------------------------
# Canned LLM responses per module
# ---------------------------------------------------------------------------

CANNED = {
    "QueryPlanner": {
        "in_scope": True,
        "market_query": "fed rate cut september",
        "market_url": None,
        "entities": ["Federal Reserve", "rate cut", "FOMC"],
        "intel_focus": ["news", "socials", "resolution"],
        "wants_trade": False,
        "language": "English",
        "reason": None,
    },
    "SentimentScorer": {
        "items": [
            {"id": "c1", "sentiment": 0.6, "stance": "yes"},
            {"id": "c2", "sentiment": -0.2, "stance": "no"},
            {"id": "c3", "sentiment": 0.1, "stance": "neutral"},
            {"id": "s1", "sentiment": 0.4, "stance": "yes"},
        ]
    },
    "BullAnalyst": {
        "thesis": "Officials signalled openness to a cut (c1); positioning follows (s1).",
        "evidence_weights": [
            {
                "evidence_id": "c1",
                "direction": "yes",
                "strength": 0.5,
                "reliability": 0.9,
                "already_priced_in": 0.3,
                "citation": "https://reuters.example/fed",
            }
        ],
        "estimated_probability": 0.62,
        "confidence": "medium",
        "red_flags": ["CPI print could reverse the narrative"],
    },
    "BearAnalyst": {
        "thesis": "Inflation remains sticky per the latest read (c2).",
        "evidence_weights": [
            {
                "evidence_id": "c2",
                "direction": "no",
                "strength": 0.3,
                "reliability": 0.8,
                "already_priced_in": 0.5,
                "citation": "https://cnbc.example/inflation",
            }
        ],
        "estimated_probability": 0.48,
        "confidence": "medium",
        "red_flags": [],
    },
    "QuantAnalyst": {
        "thesis": "Tight spread, healthy depth and volume; the mid is informative.",
        "evidence_weights": [],
        "estimated_probability": 0.55,
        "confidence": "medium",
        "red_flags": [],
    },
    "ResolutionSkeptic": {
        "thesis": "Criteria reference the official FOMC statement; little ambiguity.",
        "evidence_weights": [],
        "estimated_probability": 0.55,
        "confidence": "high",
        "red_flags": ["resolution_risk: low — objective single-source criteria"],
    },
    "Judge": {
        "verdict": "IGNORED",
        "fair_probability": 0.99,  # must be overwritten by deterministic value
        "net_edge_pts": 0.99,
        "confidence": "medium",
        "suggested_size_pct_bankroll": 99.0,
        "summary": "The council leans YES on fresh signals (c1) while sticky inflation (c2) is the main counterargument.",
        "key_risks": ["CPI print on Aug 12 (c2)"],
        "council_digest": {"bull": "cut signalled", "bear": "inflation sticky", "quant": "mid informative", "skeptic": "low risk"},
    },
}

FIXTURE_MARKET = MarketState(
    question="Will the Fed cut rates in September?",
    slug="fed-rate-cut-september",
    event_id="411",
    end_date="2026-09-30T00:00:00Z",
    resolution_criteria="Resolves YES if the FOMC lowers the target range at the September meeting.",
    category="economics",
    yes_token_id="tok-yes",
    mid=0.50,
    best_bid=0.49,
    best_ask=0.51,
    spread=0.02,
    depth_at_ask_usd=10_000.0,
    volume24h=2_000_000.0,
    price_history_7d=[(1.0, 0.47), (2.0, 0.50)],
)

ARTICLES = [
    {"url": "https://reuters.example/fed", "title": "Fed officials signal openness to cut", "domain": "reuters.com", "published_at": "2026-07-10T10:00:00+00:00"},
    {"url": "https://cnbc.example/inflation", "title": "Inflation stickier than hoped", "domain": "cnbc.com", "published_at": "2026-07-09T10:00:00+00:00"},
    {"url": "https://ft.example/markets", "title": "Traders split on September", "domain": "ft.com", "published_at": "2026-07-08T10:00:00+00:00"},
]

POSTS = [
    {"text": "September cut is basically locked", "source": "polymarket_comments", "url": "", "created_at": "2026-07-10T12:00:00Z"},
]


@pytest.fixture
def mocked_pipeline(monkeypatch):
    async def fake_call_llm(self, module, system_prompt, user_prompt):
        assert module in CANNED, f"unexpected LLM module {module}"
        response = CANNED[module]
        self.steps.append(
            Step(
                module=module,
                prompt=StepPrompt(system_prompt=system_prompt, user_prompt=user_prompt),
                response=response,
            )
        )
        return response

    async def fake_search(query, limit=10):
        return [{"slug": FIXTURE_MARKET.slug, "question": FIXTURE_MARKET.question, "yes_token_id": "tok-yes", "mid": 0.5, "volume24h": 2_000_000.0}]

    async def fake_state(slug_or_id):
        return FIXTURE_MARKET

    async def fake_articles(query, timespan=None, max_records=None, **kw):
        return ARTICLES

    async def fake_social(event_id, query, limit=20):
        return {"posts": POSTS, "mention_velocity": 1.5, "note": "1 post from polymarket_comments."}

    monkeypatch.setattr(RunContext, "call_llm", fake_call_llm)
    monkeypatch.setattr(polymarket, "search_markets", fake_search)
    monkeypatch.setattr(polymarket, "get_market_state", fake_state)
    monkeypatch.setattr(gdelt, "fetch_articles", fake_articles)
    monkeypatch.setattr(social, "gather_social", fake_social)


LLM_MODULES = {"QueryPlanner", "SentimentScorer", "BullAnalyst", "BearAnalyst", "QuantAnalyst", "ResolutionSkeptic", "Judge"}
TOOL_MODULES = {"MarketResolver", "EvidenceRetriever", "SocialScanner"}


async def test_full_run_envelope_and_steps(mocked_pipeline):
    result = await orchestrator.run_pipeline("analyze the fed september rate cut market")

    assert result.status == "ok"
    assert result.error is None
    assert result.response

    llm_steps = [s for s in result.steps if s.prompt.system_prompt != TOOL_SYSTEM_PROMPT]
    tool_steps = [s for s in result.steps if s.prompt.system_prompt == TOOL_SYSTEM_PROMPT]
    assert {s.module for s in llm_steps} == LLM_MODULES
    assert len(llm_steps) == 7, "exactly 7 LLM calls per execute"
    assert {s.module for s in tool_steps} == TOOL_MODULES
    assert all(s.module in config.CANONICAL_MODULES for s in result.steps)
    assert result.steps[0].module == "QueryPlanner"
    assert result.steps[-1].module == "Judge"


async def test_deterministic_numbers_override_judge(mocked_pipeline):
    result = await orchestrator.run_pipeline("analyze the fed september rate cut market")
    ui = result.ui
    assert ui is not None
    # the Judge's fabricated 0.99/99.0 must have been replaced by pricing.py
    assert ui["verdict"]["fair_probability"] != 0.99
    assert ui["verdict"]["suggested_size_pct_bankroll"] <= config.MAX_SIZE_PCT_BANKROLL * 100
    assert ui["verdict"]["verdict"] in ("BUY_YES", "BUY_NO", "PASS")


async def test_dossier_content(mocked_pipeline):
    result = await orchestrator.run_pipeline("analyze the fed september rate cut market")
    assert "## Verdict" in result.response
    assert "financial advice" in result.response.lower()  # disclaimer present
    assert "educational tool" in result.response.lower()
    assert "c1" in result.response  # evidence ids surface in the dossier
    assert result.ui["news"], "clusters must reach the ui payload"
    assert result.ui["council"]["skeptic"]["red_flags"][0].startswith("resolution_risk: low")
    # sentiment applied back onto clusters by id
    scored = {c["id"]: c["sentiment"] for c in result.ui["news"]}
    assert scored["c1"] == 0.6


async def test_out_of_scope_refusal(mocked_pipeline, monkeypatch):
    refusal = dict(CANNED["QueryPlanner"], in_scope=False, reason="I only analyze Polymarket markets.")
    monkeypatch.setitem(CANNED, "QueryPlanner", refusal)
    try:
        result = await orchestrator.run_pipeline("write me a poem about cats")
    finally:
        pass
    assert result.status == "ok"
    assert "Polymarket" in result.response
    assert len(result.steps) == 1  # only QueryPlanner ran


async def test_failure_returns_error_envelope(monkeypatch):
    async def boom(self, module, system_prompt, user_prompt):
        raise RuntimeError("LLM is down")

    monkeypatch.setattr(RunContext, "call_llm", boom)
    result = await orchestrator.run_pipeline("analyze anything")
    assert result.status == "error"
    assert "LLM is down" in result.error
    assert result.response is None
    assert result.steps == []


async def test_ambiguous_market_returns_candidates(mocked_pipeline, monkeypatch):
    async def many(query, limit=10):
        return [
            {"slug": f"market-{i}", "question": f"Candidate {i}?", "yes_token_id": "t", "mid": 0.5, "volume24h": 1000.0}
            for i in range(3)
        ]

    monkeypatch.setattr(polymarket, "search_markets", many)
    result = await orchestrator.run_pipeline("analyze the fed september rate cut market")
    assert result.status == "ok"
    assert "pick" in result.response.lower()
    assert "market-0" in result.response
