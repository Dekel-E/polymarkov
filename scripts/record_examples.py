"""Freeze two real agent runs into agent_info's prompt_examples (prompt,
full_response, and the full steps list from the current pipeline).

Usage:
    python -m scripts.record_examples [--slug <market-slug>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

from backend import config
from backend.agent import intel_cache
from backend.agent.orchestrator import run_pipeline
from backend.data import polymarket, supabase_client

OUT_FILE = config.ASSETS_DIR / "agent_examples.json"

OUT_OF_SCOPE_PROMPT = "write me a poem about cats"


async def pick_market(slug: str | None) -> str:
    if slug:
        return slug
    markets = await polymarket.get_trending_markets(100)
    cutoff = datetime.now(timezone.utc) + timedelta(days=14)
    for m in markets:
        try:
            end_date = datetime.fromisoformat(str(m.get("end_date", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if (
            end_date > cutoff
            and m["yes_token_id"]
            and 0.05 <= m["mid"] <= 0.95
            and m.get("spread")
            and m["spread"] <= 0.05
        ):
            return m["slug"]
    raise SystemExit("no liquid market resolving at least 14 days out — pass --slug explicitly")


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
    required_steps = {
        "QueryPlanner",
        "MarketResolver",
        "SearchQueryGenerator",
        "EvidenceRetriever",
        "SocialScanner",
        "CrossVenueScanner",
        "MicrostructureScanner",
        "SmartMoneyScanner",
        "PricingEngine",
        "Judge",
    }
    recorded_steps = {step.module for step in analysis.steps}
    missing_steps = sorted(required_steps - recorded_steps)
    if analysis.status != "ok" or missing_steps:
        raise SystemExit(
            f"analysis run unusable: status={analysis.status} "
            f"steps={len(analysis.steps)} missing={missing_steps} error={analysis.error}"
        )
    resolver_steps = [step for step in analysis.steps if step.module == "MarketResolver"]
    resolved_slug = resolver_steps[-1].response.get("slug") if resolver_steps else None
    if resolved_slug != slug:
        raise SystemExit(
            f"analysis resolved the wrong market: requested={slug!r} resolved={resolved_slug!r}"
        )

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
