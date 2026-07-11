import pytest

from backend.agent import intel_cache
from backend.data.polymarket import infer_category


@pytest.fixture(autouse=True)
def clean_cache():
    intel_cache.clear_memory()
    yield
    intel_cache.clear_memory()


# ---------------------------------------------------------------------------
# slug_from_prompt — the zero-LLM fast path trigger
# ---------------------------------------------------------------------------


def test_slug_from_templated_prompt():
    assert (
        intel_cache.slug_from_prompt("Market: fed-rate-cut-september\nFocus: all\nTrade: no")
        == "fed-rate-cut-september"
    )


def test_trade_prompts_never_hit_cache():
    assert intel_cache.slug_from_prompt("Market: fed-rate-cut\nFocus: all\nTrade: yes") is None


def test_free_text_prompt_returns_none():
    assert intel_cache.slug_from_prompt("what are the odds the fed cuts rates?") is None


# ---------------------------------------------------------------------------
# get/put with TTL (memory layer; Supabase is off in tests)
# ---------------------------------------------------------------------------


def test_put_then_get(monkeypatch):
    intel_cache.put("some-market", "the dossier", [], {"verdict": {"verdict": "PASS"}})
    hit = intel_cache.get("some-market")
    assert hit is not None
    assert hit["response"] == "the dossier"
    assert hit["created_at"]


def test_expired_entry_is_ignored(monkeypatch):
    intel_cache.put("some-market", "old dossier", [], {})
    monkeypatch.setattr(intel_cache.config, "INTEL_CACHE_TTL_S", 0)
    assert intel_cache.get("some-market") is None


def test_miss_returns_none():
    assert intel_cache.get("never-analyzed") is None


# ---------------------------------------------------------------------------
# category inference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Will Spain win the 2026 FIFA World Cup?", "sports"),
        ("Will Bitcoin hit $200k by December?", "crypto"),
        ("Will the Fed cut rates in September?", "economics"),
        ("Will Israel and Iran reach a ceasefire by July 31?", "geopolitics"),
        ("Will Adanech Abiebie be the next Prime Minister of Ethiopia?", "politics"),
        ("Will OpenAI release GPT-6 this year?", "tech"),
        ("Will the movie win Best Picture at the Oscars?", "culture"),
        ("Will a hurricane make landfall in Florida in August?", "weather"),
        ("Will the mystery event happen?", "other"),
    ],
)
def test_infer_category(question, expected):
    assert infer_category(question) == expected
