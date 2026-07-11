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


def test_steps_slimmed_in_storage_and_rehydrated_on_read():
    from backend.llm.client import TOOL_SYSTEM_PROMPT, load_prompt

    judge_prompt = load_prompt("judge")
    steps = [
        {"module": "Judge", "prompt": {"system_prompt": judge_prompt, "user_prompt": "u1"}, "response": {}},
        {"module": "MarketResolver", "prompt": {"system_prompt": TOOL_SYSTEM_PROMPT, "user_prompt": "u2"}, "response": {}},
        {"module": "Unknown", "prompt": {"system_prompt": "custom", "user_prompt": "u3"}, "response": {}},
    ]
    intel_cache.put("slim-market", "resp", steps, {})

    stored = intel_cache._MEM["slim-market"][1]["steps"]
    assert stored[0]["prompt"]["system_prompt"] == "@prompt:judge"  # deduplicated
    assert stored[1]["prompt"]["system_prompt"] == "@tool"
    assert stored[2]["prompt"]["system_prompt"] == "custom"  # unknown kept verbatim
    assert len(str(stored)) < len(str(steps)) / 2  # the bloat actually went away

    restored = intel_cache.get("slim-market")["steps"]
    assert restored[0]["prompt"]["system_prompt"] == judge_prompt  # byte-identical
    assert restored[1]["prompt"]["system_prompt"] == TOOL_SYSTEM_PROMPT
    assert restored[0]["prompt"]["user_prompt"] == "u1"


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
