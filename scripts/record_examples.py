"""Freeze two real agent runs into agent_info's prompt_examples (prompt,
full_response, and the full steps list).

Usage:
    python -m scripts.record_examples [--slug <market-slug>]
"""

from __future__ import annotations

import argparse
import asyncio
import json

from backend import config
from backend.agent import intel_cache
from backend.agent.orchestrator import run_pipeline
from backend.data import polymarket, supabase_client

OUT_FILE = config.ASSETS_DIR / "agent_examples.json"

OUT_OF_SCOPE_PROMPT = "write me a poem about cats"


async def pick_market(slug: str | None) -> str:
    if slug:
        return slug
    for m in await polymarket.get_trending_markets(20):
        if m["yes_token_id"] and 0.05 <= m["mid"] <= 0.95 and m.get("spread") and m["spread"] <= 0.05:
            return m["slug"]
    raise SystemExit("no suitable market found — pass --slug explicitly")


def clear_cache(slug: str) -> None:
    """The example must be a fresh full run, not a cache hit."""
    intel_cache.clear_memory()
    if supabase_client.is_configured():
        try:
            supabase_client.get_client().table("intel_cache").delete().eq("market_id", slug).execute()
        except Exception:
            pass


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slug", default=None)
    args = parser.parse_args()

    slug = await pick_market(args.slug)
    prompt = f"Market: {slug}\nFocus: all\nTrade: no"
    clear_cache(slug)

    print(f"recording example 1 (full analysis): {slug}")
    analysis = await run_pipeline(prompt)
    if analysis.status != "ok" or len(analysis.steps) < 7:
        raise SystemExit(f"analysis run unusable: status={analysis.status} steps={len(analysis.steps)}")

    print("recording example 2 (out-of-scope refusal)")
    refusal = await run_pipeline(OUT_OF_SCOPE_PROMPT)
    if refusal.status != "ok":
        raise SystemExit(f"refusal run unusable: {refusal.error}")

    examples = [
        {
            "prompt": prompt,
            "full_response": analysis.response,
            "steps": [s.model_dump() for s in analysis.steps],
        },
        {
            "prompt": OUT_OF_SCOPE_PROMPT,
            "full_response": refusal.response,
            "steps": [s.model_dump() for s in refusal.steps],
        },
    ]
    OUT_FILE.write_text(json.dumps(examples, ensure_ascii=False, indent=1), encoding="utf-8")
    size_kb = OUT_FILE.stat().st_size // 1024
    print(f"wrote {OUT_FILE} ({size_kb} KB, {len(examples)} examples)")


if __name__ == "__main__":
    asyncio.run(main())
