from types import SimpleNamespace

import pytest

from backend.llm import budget


class _Response:
    def __init__(self, data):
        self.data = data


class _RPC:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return _Response(self.data)


class _Client:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def rpc(self, name, params=None):
        self.calls.append((name, params))
        return _RPC(self.data)


def test_global_budget_reserves_through_atomic_rpc(monkeypatch):
    client = _Client({"allowed": True, "used": 7, "limit": 150})
    monkeypatch.setattr(budget.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(budget.supabase_client, "get_client", lambda: client)

    result = budget.reserve("chat")

    assert result["scope"] == "global"
    assert result["used"] == 7
    assert client.calls == [
        (
            "reserve_llm_budget",
            {"p_kind": "chat", "p_daily_limit": budget.config.LLM_GLOBAL_DAILY_REQUEST_LIMIT},
        )
    ]


def test_global_budget_stops_before_provider_call(monkeypatch):
    client = _Client({"allowed": False, "used": 150, "limit": 150})
    monkeypatch.setattr(budget.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(budget.supabase_client, "get_client", lambda: client)

    with pytest.raises(budget.LLMBudgetExceeded, match="150/150"):
        budget.reserve("embedding")


def test_configured_budget_fails_closed_when_rpc_is_missing(monkeypatch):
    class BrokenClient:
        def rpc(self, _name, _params=None):
            raise RuntimeError("function not found")

    monkeypatch.setattr(budget.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(budget.supabase_client, "get_client", lambda: BrokenClient())

    with pytest.raises(budget.LLMBudgetUnavailable, match="migration 0017"):
        budget.reserve("chat")


@pytest.mark.asyncio
async def test_chat_provider_request_is_reserved_and_reported(monkeypatch):
    from backend.llm import client as llm_client

    reserved = []
    recorded = []
    monkeypatch.setattr(llm_client.budget, "reserve", lambda kind: reserved.append(kind))
    monkeypatch.setattr(
        llm_client.budget,
        "record_usage",
        lambda kind, **usage: recorded.append((kind, usage)),
    )

    async def create(**_kwargs):
        return SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=4),
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))],
        )

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm_client, "_client", lambda: fake)
    ctx = llm_client.RunContext()

    assert await ctx._completion("system", [{"role": "user", "content": "hello"}]) == '{"ok": true}'
    assert reserved == ["chat"]
    assert recorded == [("chat", {"tokens_in": 11, "tokens_out": 4})]


def test_embedding_batches_share_the_same_budget(monkeypatch):
    from backend.llm import embeddings

    reserved = []
    recorded = []
    monkeypatch.setattr(embeddings.budget, "reserve", lambda kind: reserved.append(kind))
    monkeypatch.setattr(
        embeddings.budget,
        "record_usage",
        lambda kind, **usage: recorded.append((kind, usage)),
    )

    def create(**kwargs):
        assert kwargs["input"] == ["hello"]
        return SimpleNamespace(
            usage=SimpleNamespace(total_tokens=2),
            data=[SimpleNamespace(embedding=[0.1, 0.2])],
        )

    fake = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    monkeypatch.setattr(embeddings, "_client", lambda: fake)

    assert embeddings.embed(["hello"]) == [[0.1, 0.2]]
    assert reserved == ["embedding"]
    assert recorded == [("embedding", {"tokens_in": 2})]
