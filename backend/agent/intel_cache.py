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

# System prompts are static files — storing them verbatim in every cached
# step bloats rows ~10x. Store a marker, rehydrate on read.
_PROMPT_FILE_BY_MODULE = {
    "QueryPlanner": "query_planner",
    "SentimentScorer": "sentiment_scorer",
    "BullAnalyst": "council_bull",
    "BearAnalyst": "council_bear",
    "QuantAnalyst": "council_quant",
    "ResolutionSkeptic": "council_resolution_skeptic",
    "Judge": "judge",
}
_TOOL_MARKER = "@tool"
_PROMPT_MARKER_RE = re.compile(r"^@prompt:([a-z_]+)$")


def _slim_steps(steps: list[dict]) -> list[dict]:
    from backend.llm.client import TOOL_SYSTEM_PROMPT

    slimmed = []
    for step in steps:
        prompt = dict(step.get("prompt") or {})
        module = step.get("module", "")
        if prompt.get("system_prompt") == TOOL_SYSTEM_PROMPT:
            prompt["system_prompt"] = _TOOL_MARKER
        elif module in _PROMPT_FILE_BY_MODULE:
            prompt["system_prompt"] = f"@prompt:{_PROMPT_FILE_BY_MODULE[module]}"
        slimmed.append({**step, "prompt": prompt})
    return slimmed


def _rehydrate_steps(steps: list[dict]) -> list[dict]:
    from backend.llm.client import TOOL_SYSTEM_PROMPT, load_prompt

    restored = []
    for step in steps:
        prompt = dict(step.get("prompt") or {})
        sp = prompt.get("system_prompt", "")
        if sp == _TOOL_MARKER:
            prompt["system_prompt"] = TOOL_SYSTEM_PROMPT
        else:
            match = _PROMPT_MARKER_RE.match(sp)
            if match:
                try:
                    prompt["system_prompt"] = load_prompt(match.group(1))
                except OSError:
                    prompt["system_prompt"] = "(prompt file unavailable)"
        restored.append({**step, "prompt": prompt})
    return restored


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


def get(slug: str, max_age_s: Optional[float] = None) -> Optional[dict]:
    """Fresh cached payload for a market (steps rehydrated), or None.

    `max_age_s` overrides the default TTL — MarketChat accepts a much older
    dossier as context than the execute pipeline would serve."""
    ttl = max_age_s if max_age_s is not None else config.INTEL_CACHE_TTL_S
    payload = None
    hit = _MEM.get(slug)
    if hit and time.time() - hit[0] < ttl:
        payload = hit[1]
    elif supabase_client.is_configured():
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
        if rows:
            candidate = rows[0]["payload"]
            if _age_s(candidate.get("created_at") or rows[0]["created_at"]) < ttl:
                payload = candidate
                if ttl <= config.INTEL_CACHE_TTL_S:  # don't let stale reads repopulate the fast path
                    _MEM[slug] = (time.time(), payload)
    if payload is None:
        return None
    return {**payload, "steps": _rehydrate_steps(payload.get("steps") or [])}


def put(slug: str, response: str, steps: list[Any], ui: dict) -> None:
    payload = {
        "response": response,
        "steps": _slim_steps(steps),
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
