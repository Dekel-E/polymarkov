"""Read checked-in GitHub Actions configuration plus their latest heartbeats."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from backend import config
from backend.data import supabase_client

WORKFLOW_JOBS = (
    {
        "workflow": "automation", "job": "trade-and-refresh", "label": "Trade & refresh",
        "cadence": "every 4 hours", "timeout_minutes": 30,
    },
    {
        "workflow": "autonomy", "job": "watch-and-act", "label": "Watch & act",
        "cadence": "hourly", "timeout_minutes": 20,
    },
    {
        "workflow": "autonomy", "job": "briefing", "label": "Relations & briefing",
        "cadence": "daily", "timeout_minutes": 10,
    },
    {
        "workflow": "indexers", "job": "index", "label": "Market/news/social index",
        "cadence": "every 2 hours", "timeout_minutes": 20,
    },
    {
        "workflow": "indexers", "job": "resolve", "label": "Resolve positions",
        "cadence": "daily", "timeout_minutes": 20,
    },
)


def _schedule_enabled(workflow: str) -> bool:
    path = config.REPO_ROOT / ".github" / "workflows" / f"{workflow}.yml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"^\s*schedule\s*:", text, flags=re.MULTILINE) is not None


def automation_status() -> dict:
    rows = supabase_client.get_automation_heartbeats()
    by_key = {(row.get("workflow"), row.get("job")): row for row in rows}
    schedules = {
        item["workflow"]: _schedule_enabled(item["workflow"])
        for item in WORKFLOW_JOBS
    }
    jobs = []
    now = datetime.now(timezone.utc)
    for item in WORKFLOW_JOBS:
        row = by_key.get((item["workflow"], item["job"]), {})
        status = row.get("status") or "never_run"
        if status == "running" and row.get("updated_at"):
            try:
                updated = datetime.fromisoformat(str(row["updated_at"]).replace("Z", "+00:00"))
                if (now - updated).total_seconds() > (item["timeout_minutes"] + 5) * 60:
                    status = "stale"
            except (TypeError, ValueError):
                pass
        jobs.append(
            {
                **item,
                "schedule_enabled": schedules[item["workflow"]],
                "status": status,
                "event": row.get("event"),
                "run_id": row.get("run_id"),
                "run_attempt": row.get("run_attempt"),
                "started_at": row.get("started_at"),
                "finished_at": row.get("finished_at"),
                "updated_at": row.get("updated_at"),
                "run_url": row.get("run_url"),
                "commit_sha": row.get("commit_sha"),
            }
        )
    return {
        "source": "github_actions",
        "schedules_enabled": any(schedules.values()),
        "jobs": jobs,
        "checked_at": now.isoformat(),
    }
