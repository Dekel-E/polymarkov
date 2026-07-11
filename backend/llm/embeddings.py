"""Embeddings via LLMod.ai (OpenAI-compatible), batched. No local ML libs."""

from __future__ import annotations

from functools import lru_cache

from backend import config

BATCH_SIZE = 100
MAX_INPUT_CHARS = 4000  # embeddings don't need full documents


def is_configured() -> bool:
    return bool(config.LLMOD_API_KEY and config.LLMOD_BASE_URL)


@lru_cache(maxsize=1)
def _client():
    from openai import OpenAI

    return OpenAI(api_key=config.LLMOD_API_KEY, base_url=config.LLMOD_BASE_URL)


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts (batched). Raises RuntimeError if LLMod is unconfigured."""
    if not is_configured():
        raise RuntimeError(
            "LLMod is not configured — set LLMOD_API_KEY and LLMOD_BASE_URL in .env"
        )
    if not texts:
        return []
    clipped = [t[:MAX_INPUT_CHARS] if t else " " for t in texts]
    vectors: list[list[float]] = []
    for i in range(0, len(clipped), BATCH_SIZE):
        batch = clipped[i : i + BATCH_SIZE]
        try:
            # pin the output dimension so Pinecone stays compatible across
            # providers (text-embedding-3-* and gemini-embedding-001 support it)
            resp = _client().embeddings.create(
                model=config.EMBEDDING_MODEL, input=batch, dimensions=config.EMBEDDING_DIM
            )
        except Exception as exc:
            if "dimensions" not in str(exc):
                raise
            resp = _client().embeddings.create(model=config.EMBEDDING_MODEL, input=batch)
        vectors.extend(d.embedding for d in resp.data)
    return vectors


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
