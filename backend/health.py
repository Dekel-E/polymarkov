"""Cheap deployment readiness checks with no paid provider requests."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from backend import config
from backend.data import supabase_client
from backend.llm import budget


def deployment_health() -> tuple[dict, int]:
    """Return a non-secret health payload and its appropriate HTTP status.

    Database/schema and LLM configuration are required for the core product.
    Pinecone is best-effort because live retrieval still works without vector
    search. We intentionally do not ping the LLM: health probes must be cheap
    and must never consume the global model budget.
    """
    checks: dict[str, dict] = {
        "api": {"status": "ok"},
        "llm": {
            "status": "configured"
            if config.LLMOD_API_KEY and config.LLMOD_BASE_URL
            else "not_configured"
        },
        "vector_store": {
            "status": "configured"
            if config.PINECONE_API_KEY and config.PINECONE_INDEX
            else "not_configured"
        },
    }

    database_ok = False
    if not supabase_client.is_configured():
        checks["database"] = {"status": "not_configured"}
        checks["budget"] = {
            "status": "process_only",
            "limit": config.LLM_GLOBAL_DAILY_REQUEST_LIMIT,
        }
    else:
        started = time.monotonic()
        try:
            response = supabase_client.get_client().rpc("deployment_health").execute()
            db_data = response.data
            if isinstance(db_data, list):
                db_data = db_data[0] if db_data else {}
            if not isinstance(db_data, dict) or db_data.get("schema_version") != "0017":
                raise RuntimeError("database schema is not at migration 0017")
            checks["database"] = {
                "status": "ok",
                "schema_version": db_data["schema_version"],
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            database_ok = True
            checks["budget"] = {"status": "ok", **budget.status()}
        except Exception:
            checks["database"] = {
                "status": "error",
                "latency_ms": int((time.monotonic() - started) * 1000),
                "detail": "database or schema check failed",
            }
            checks["budget"] = {"status": "unavailable"}

    llm_ok = checks["llm"]["status"] == "configured"
    vector_ok = checks["vector_store"]["status"] == "configured"
    ready = database_ok and llm_ok
    if not ready:
        status, http_status = "unhealthy", 503
    elif not vector_ok:
        status, http_status = "degraded", 200
    else:
        status, http_status = "healthy", 200

    return (
        {
            "service": "polymarkov",
            "status": status,
            "ready": ready,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "checks": checks,
        },
        http_status,
    )
