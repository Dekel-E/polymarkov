"""Course-contract tests for the four graded endpoints (Project PDF §2).

The /api/execute response "must match exactly these top-level fields":
{status, error, response, steps}. The GUI's extra dossier payload is only
present when explicitly requested with ?ui=1.
"""

from fastapi.testclient import TestClient

import api.index as api_index
from backend import config
from backend.agent.types import ExecuteOut, Step, StepPrompt

client = TestClient(api_index.app)

_STEP = Step(
    module="QueryPlanner",
    prompt=StepPrompt(system_prompt="sys", user_prompt="user"),
    response={"in_scope": True},
)


def _ok_result() -> ExecuteOut:
    return ExecuteOut(
        status="ok", error=None, response="dossier", steps=[_STEP], ui={"verdict": {}}
    )


def test_execute_envelope_has_exactly_the_course_fields(monkeypatch):
    async def fake_pipeline(prompt: str, history=None) -> ExecuteOut:
        return _ok_result()

    monkeypatch.setattr(api_index, "run_pipeline", fake_pipeline)
    data = client.post("/api/execute", json={"prompt": "hi"}).json()
    assert set(data) == {"status", "error", "response", "steps"}
    assert data["status"] == "ok" and data["error"] is None
    assert data["response"] == "dossier"


def test_execute_ui_flag_adds_gui_payload(monkeypatch):
    async def fake_pipeline(prompt: str, history=None) -> ExecuteOut:
        return _ok_result()

    monkeypatch.setattr(api_index, "run_pipeline", fake_pipeline)
    data = client.post("/api/execute?ui=1", json={"prompt": "hi"}).json()
    assert set(data) == {"status", "error", "response", "steps", "ui"}
    assert data["ui"] == {"verdict": {}}


def test_execute_error_envelope(monkeypatch):
    async def fake_pipeline(prompt: str, history=None) -> ExecuteOut:
        raise RuntimeError("boom")

    monkeypatch.setattr(api_index, "run_pipeline", fake_pipeline)
    res = client.post("/api/execute", json={"prompt": "hi"})
    assert res.status_code == 200  # errors ride the envelope, never a 500
    data = res.json()
    assert set(data) == {"status", "error", "response", "steps"}
    assert data["status"] == "error"
    assert data["response"] is None
    assert data["steps"] == []
    assert "boom" in data["error"]


def test_execute_step_schema(monkeypatch):
    async def fake_pipeline(prompt: str, history=None) -> ExecuteOut:
        return _ok_result()

    monkeypatch.setattr(api_index, "run_pipeline", fake_pipeline)
    steps = client.post("/api/execute", json={"prompt": "hi"}).json()["steps"]
    for step in steps:
        assert set(step) == {"module", "prompt", "response"}
        assert set(step["prompt"]) == {"system_prompt", "user_prompt"}
        assert step["module"] in config.CANONICAL_MODULES


def test_no_auth_endpoints():
    """Course requirement: no auth guards anywhere — the register endpoint
    must not exist and desk endpoints must work without credentials."""
    res = client.post("/api/auth/register", json={"email": "a@b.c", "password": "x" * 8})
    assert res.status_code == 404


def test_team_info_schema():
    data = client.get("/api/team_info").json()
    assert set(data) == {"group_batch_order_number", "team_name", "students"}
    assert isinstance(data["students"], list) and data["students"]
    for student in data["students"]:
        assert set(student) == {"name", "email"}


def test_agent_info_includes_required_fields():
    data = client.get("/api/agent_info").json()
    assert set(data) >= {"description", "purpose", "prompt_template", "prompt_examples"}
    assert data["prompt_template"].get("template")


def test_model_architecture_is_png():
    res = client.get("/api/model_architecture")
    assert res.status_code == 200, "architecture.png missing — run scripts/gen_architecture_png.py"
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
