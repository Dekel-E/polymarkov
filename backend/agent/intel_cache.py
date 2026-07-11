"""Dossier cache: skip the whole 7-call pipeline for repeat market requests.

Two layers: an in-process dict (fast, also the only layer when Supabase is
off) and the Supabase `intel_cache` table (survives serverless cold starts).
Payload = {response, steps, ui, created_at}. Trades always bypass this.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from backend import config
from backend.data import supabase_client

_MEM: dict[str, tuple[float, dict]] = {}  # slug -> (unix_ts, payload)

_PROMPT_SLUG_RE = re.compile(r"market:\s*([a-z0-9][a-z0-9-]{5,})\s*$", re.IGNORECASE | re.MULTILINE)
_WANTS_TRADE_RE = re.compile(r"trade:\s*yes", re.IGNORECASE)


def slug_from_prompt(prompt: str) -> Optional[str]:
    """Extract the slug from the GUI's templated prompt ('Market: <slug>').

    Lets repeat requests skip even the QueryPlanner call. Returns None for
    free-text prompts (they go through the planner as usual) and for
    prompts that ask to trade.
    """
    if _WANTS_TRADE_RE.search(prompt):
        return None
    match = _PROMPT_SLUG_RE.search(prompt)
    return match.group(1).lower() if match else None


def _age_s(created_at: str) -> float:
    try:
        dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds()
    except ValueError:
        return float("inf")


def get(slug: str) -> Optional[dict]:
    """Fresh cached payload for a market, or None."""
    hit = _MEM.get(slug)
    if hit and time.time() - hit[0] < config.INTEL_CACHE_TTL_S:
        return hit[1]

    if not supabase_client.is_configured():
        return None
    try:
        rows = (
            supabase_client.get_client()
            .table("intel_cache")
            .select("payload,created_at")
            .eq("market_id", slug)
            .limit(1)
            .execute()
            .data
        )
    except Exception:
        return None
    if not rows:
        return None
    payload = rows[0]["payload"]
    if _age_s(payload.get("created_at") or rows[0]["created_at"]) >= config.INTEL_CACHE_TTL_S:
        return None
    _MEM[slug] = (time.time(), payload)
    return payload


def put(slug: str, response: str, steps: list[Any], ui: dict) -> None:
    payload = {
        "response": response,
        "steps": steps,
        "ui": ui,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _MEM[slug] = (time.time(), payload)
    if not supabase_client.is_configured():
        return
    try:
        supabase_client.get_client().table("intel_cache").upsert(
            {"market_id": slug, "payload": payload, "created_at": payload["created_at"]}
        ).execute()
    except Exception:
        pass  # cache write failures must never break a run


def clear_memory() -> None:
    """Test hook."""
    _MEM.clear()
