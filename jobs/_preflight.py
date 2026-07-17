"""Report which credentials are present or missing (names only, never values)."""

from __future__ import annotations

import sys

from backend import config


def report() -> dict:
    checks = {
        "LLMOD_API_KEY": bool(config.LLMOD_API_KEY),
        "LLMOD_BASE_URL": bool(config.LLMOD_BASE_URL),
        "SUPABASE_URL": bool(config.SUPABASE_URL),
        "SUPABASE_SERVICE_KEY": bool(config.SUPABASE_SERVICE_KEY),
        "PINECONE_API_KEY": bool(config.PINECONE_API_KEY),
        "PINECONE_INDEX": bool(config.PINECONE_INDEX),
    }
    print("preflight:")
    for name, present in checks.items():
        print(f"  {name}: {'set' if present else 'MISSING'}")
    print(f"  models: llm={config.LLM_MODEL} embed={config.EMBEDDING_MODEL} dim={config.EMBEDDING_DIM}")
    return checks


def require(*names: str) -> None:
    """Exit 1 if any required credential is missing."""
    checks = report()
    missing = [n for n in names if not checks.get(n, False)]
    if missing:
        print(
            f"\nFATAL: missing required secrets: {', '.join(missing)}\n"
            "Add them in GitHub -> repo Settings -> Secrets and variables -> "
            "Actions (see README), then re-run."
        )
        sys.exit(1)
