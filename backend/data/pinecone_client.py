"""Thin Pinecone wrapper: one index, dim 1536, cosine, namespaces
`markets` / `news` / `precedents` / `social`. Degrades to no-ops when unconfigured.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from backend import config

NAMESPACES = ("markets", "news", "precedents", "social")


def is_configured() -> bool:
    return bool(config.PINECONE_API_KEY and config.PINECONE_INDEX)


@lru_cache(maxsize=1)
def _pc():
    from pinecone import Pinecone  # deferred: import is slow

    return Pinecone(api_key=config.PINECONE_API_KEY)


def ensure_index() -> None:
    """Create the serverless index if it doesn't exist yet (idempotent)."""
    from pinecone import ServerlessSpec

    pc = _pc()
    if not pc.has_index(config.PINECONE_INDEX):
        pc.create_index(
            name=config.PINECONE_INDEX,
            dimension=config.EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )


@lru_cache(maxsize=1)
def get_index():
    ensure_index()
    return _pc().Index(config.PINECONE_INDEX)


def upsert_vectors(namespace: str, items: list[dict], batch_size: int = 100) -> int:
    """items: [{id, values, metadata}]. Returns vectors written."""
    if not is_configured() or not items:
        return 0
    index = get_index()
    for i in range(0, len(items), batch_size):
        index.upsert(vectors=items[i : i + batch_size], namespace=namespace)
    return len(items)


def query(
    namespace: str,
    vector: list[float],
    top_k: int = 10,
    filter: Optional[dict] = None,
) -> list[dict]:
    """Returns [{id, score, metadata}] best-first. [] when unconfigured."""
    if not is_configured():
        return []
    resp = get_index().query(
        vector=vector,
        top_k=top_k,
        namespace=namespace,
        filter=filter,
        include_metadata=True,
    )
    return [
        {"id": m["id"], "score": m["score"], "metadata": dict(m.get("metadata") or {})}
        for m in resp.get("matches", [])
    ]


def namespace_count(namespace: str) -> int:
    if not is_configured():
        return 0
    stats = get_index().describe_index_stats()
    ns = (stats.get("namespaces") or {}).get(namespace) or {}
    return int(ns.get("vector_count", 0))
