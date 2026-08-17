"""Publish a GitHub Actions job's start/final state to the Strategy Desk."""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from backend.data import supabase_client


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("start", "finish"))
    parser.add_argument(
        "--status", choices=("success", "failure", "cancelled", "skipped"), default="success"
    )
    args = parser.parse_args()

    workflow = _env("GITHUB_WORKFLOW", "local")
    job = _env("GITHUB_JOB", "unknown")
    run_id = _env("GITHUB_RUN_ID", "local")
    now = datetime.now(timezone.utc).isoformat()
    server = _env("GITHUB_SERVER_URL", "https://github.com")
    repository = _env("GITHUB_REPOSITORY")
    row = {
        "workflow": workflow,
        "job": job,
        "run_id": run_id,
        "run_attempt": int(_env("GITHUB_RUN_ATTEMPT", "1")),
        "event": _env("GITHUB_EVENT_NAME", "local"),
        "status": "running" if args.phase == "start" else args.status,
        "updated_at": now,
        "run_url": f"{server}/{repository}/actions/runs/{run_id}" if repository else None,
        "commit_sha": _env("GITHUB_SHA") or None,
    }
    row["started_at" if args.phase == "start" else "finished_at"] = now
    supabase_client.record_automation_heartbeat(row)
    print(f"heartbeat: {workflow}/{job} -> {row['status']}")


if __name__ == "__main__":
    main()
