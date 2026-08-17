from backend import automation_status, config


def test_automation_status_merges_workflows_and_heartbeats(monkeypatch):
    monkeypatch.setattr(
        automation_status.supabase_client,
        "get_automation_heartbeats",
        lambda: [{
            "workflow": "automation", "job": "trade-and-refresh", "status": "success",
            "event": "workflow_dispatch", "run_id": "42", "updated_at": "2026-08-17T12:00:00Z",
        }],
    )
    monkeypatch.setattr(automation_status, "_schedule_enabled", lambda name: name == "automation")
    data = automation_status.automation_status()
    first = data["jobs"][0]
    assert data["schedules_enabled"] is True
    assert first["status"] == "success"
    assert first["event"] == "workflow_dispatch"
    assert first["schedule_enabled"] is True
    assert data["jobs"][1]["status"] == "never_run"


def test_checked_in_workflows_are_instrumented_and_manual_only():
    expected_jobs = {"automation": 1, "autonomy": 2, "indexers": 2}
    for workflow, count in expected_jobs.items():
        text = (config.REPO_ROOT / ".github" / "workflows" / f"{workflow}.yml").read_text("utf-8")
        assert text.count("python -m jobs.heartbeat start") == count
        assert text.count("python -m jobs.heartbeat finish") == count
        assert automation_status._schedule_enabled(workflow) is False


def test_old_running_heartbeat_is_marked_stale(monkeypatch):
    monkeypatch.setattr(
        automation_status.supabase_client,
        "get_automation_heartbeats",
        lambda: [{
            "workflow": "automation", "job": "trade-and-refresh", "status": "running",
            "updated_at": "2020-01-01T00:00:00Z",
        }],
    )
    monkeypatch.setattr(automation_status, "_schedule_enabled", lambda _name: False)
    assert automation_status.automation_status()["jobs"][0]["status"] == "stale"
