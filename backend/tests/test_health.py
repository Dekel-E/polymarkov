from backend import health


class _Response:
    def __init__(self, data):
        self.data = data


class _RPC:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return _Response(self.data)


class _Client:
    def rpc(self, name, _params=None):
        assert name == "deployment_health"
        return _RPC({"database": "ok", "schema_version": "0018"})


def test_health_is_ready_without_spending_model_budget(monkeypatch):
    monkeypatch.setattr(health.config, "LLMOD_API_KEY", "configured")
    monkeypatch.setattr(health.config, "LLMOD_BASE_URL", "https://llm.example")
    monkeypatch.setattr(health.config, "PINECONE_API_KEY", "configured")
    monkeypatch.setattr(health.supabase_client, "is_configured", lambda: True)
    monkeypatch.setattr(health.supabase_client, "get_client", lambda: _Client())
    monkeypatch.setattr(
        health.budget,
        "status",
        lambda: {"scope": "global", "used": 5, "remaining": 145, "limit": 150},
    )

    payload, status_code = health.deployment_health()

    assert status_code == 200
    assert payload["status"] == "healthy"
    assert payload["ready"] is True
    assert payload["checks"]["database"]["schema_version"] == "0018"
    assert payload["checks"]["budget"]["remaining"] == 145


def test_health_is_503_without_core_configuration(monkeypatch):
    monkeypatch.setattr(health.config, "LLMOD_API_KEY", "")
    monkeypatch.setattr(health.config, "LLMOD_BASE_URL", "")
    monkeypatch.setattr(health.supabase_client, "is_configured", lambda: False)

    payload, status_code = health.deployment_health()

    assert status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["ready"] is False
    assert payload["checks"]["budget"]["status"] == "process_only"
