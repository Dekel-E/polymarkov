"""Atomic, project-wide budget for all model-provider requests.

Production uses a PostgreSQL RPC so API instances, serverless functions and
background jobs share one counter. A small process-local fallback keeps
standalone development usable when Supabase is intentionally not configured;
deployment health reports that fallback as degraded rather than global.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Literal

from backend import config
from backend.data import supabase_client

RequestKind = Literal["chat", "embedding"]


class LLMBudgetExceeded(RuntimeError):
    """Raised before a provider call when the shared daily quota is spent."""


class LLMBudgetUnavailable(RuntimeError):
    """Raised when a configured shared counter cannot be reached safely."""


_local_lock = threading.Lock()
_local_day = ""
_local_used = 0


def _normalize_rpc_data(data):
    if isinstance(data, list):
        return data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _local_reserve() -> dict:
    global _local_day, _local_used
    day = datetime.now(timezone.utc).date().isoformat()
    with _local_lock:
        if _local_day != day:
            _local_day, _local_used = day, 0
        if _local_used >= config.LLM_GLOBAL_DAILY_REQUEST_LIMIT:
            allowed = False
        else:
            _local_used += 1
            allowed = True
        return {
            "allowed": allowed,
            "day": day,
            "used": _local_used,
            "limit": config.LLM_GLOBAL_DAILY_REQUEST_LIMIT,
            "scope": "process",
        }


def reserve(kind: RequestKind) -> dict:
    """Atomically reserve one actual provider request before sending it."""
    if kind not in ("chat", "embedding"):
        raise ValueError(f"unsupported LLM request kind: {kind}")

    if not supabase_client.is_configured():
        result = _local_reserve()
    else:
        try:
            response = supabase_client.get_client().rpc(
                "reserve_llm_budget",
                {
                    "p_kind": kind,
                    "p_daily_limit": config.LLM_GLOBAL_DAILY_REQUEST_LIMIT,
                },
            ).execute()
            result = _normalize_rpc_data(response.data)
            result["scope"] = "global"
        except Exception as exc:
            # Fail closed whenever shared storage was configured: silently
            # falling back here would let parallel deployments overspend.
            raise LLMBudgetUnavailable(
                "Global LLM budget is unavailable; install migration 0017 "
                "and verify Supabase connectivity."
            ) from exc

    if not result.get("allowed"):
        raise LLMBudgetExceeded(
            "Global LLM daily request budget exhausted "
            f"({result.get('used', 0)}/{result.get('limit', config.LLM_GLOBAL_DAILY_REQUEST_LIMIT)} UTC)."
        )
    return result


def record_usage(
    kind: RequestKind,
    *,
    tokens_in: int = 0,
    tokens_out: int = 0,
    failed: bool = False,
) -> None:
    """Attach provider-reported usage to an already reserved request.

    Reservation is the enforcement boundary. Telemetry is deliberately
    best-effort because a reporting failure must not duplicate a paid request.
    """
    if not supabase_client.is_configured():
        return
    try:
        supabase_client.get_client().rpc(
            "record_llm_usage",
            {
                "p_kind": kind,
                "p_tokens_in": max(int(tokens_in or 0), 0),
                "p_tokens_out": max(int(tokens_out or 0), 0),
                "p_failed": bool(failed),
            },
        ).execute()
    except Exception:
        pass


def status() -> dict:
    """Return today's safe-to-display quota status."""
    if not supabase_client.is_configured():
        with _local_lock:
            used = _local_used if _local_day == datetime.now(timezone.utc).date().isoformat() else 0
        return {
            "day": datetime.now(timezone.utc).date().isoformat(),
            "used": used,
            "remaining": max(config.LLM_GLOBAL_DAILY_REQUEST_LIMIT - used, 0),
            "limit": config.LLM_GLOBAL_DAILY_REQUEST_LIMIT,
            "scope": "process",
        }
    try:
        response = supabase_client.get_client().rpc(
            "get_llm_budget_status",
            {"p_daily_limit": config.LLM_GLOBAL_DAILY_REQUEST_LIMIT},
        ).execute()
        result = _normalize_rpc_data(response.data)
        result["scope"] = "global"
        return result
    except Exception as exc:
        raise LLMBudgetUnavailable(
            "Global LLM budget status is unavailable; install migration 0017."
        ) from exc
