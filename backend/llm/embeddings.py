"""Embeddings via LLMod.ai (OpenAI-compatible), batched. No local ML libs."""

from __future__ import annotations

from functools import lru_cache

from backend import config
from backend.llm import budget

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

        def _provider_request(*, dimensions: bool):
            # Every physical embedding batch shares the same atomic quota as
            # chat calls. A provider-compatibility retry is another request.
            budget.reserve("embedding")
            kwargs = {"model": config.EMBEDDING_MODEL, "input": batch}
            if dimensions:
                kwargs["dimensions"] = config.EMBEDDING_DIM
            try:
                response = _client().embeddings.create(**kwargs)
            except Exception:
                budget.record_usage("embedding", failed=True)
                raise
            usage = getattr(response, "usage", None)
            tokens = int(getattr(usage, "total_tokens", 0) or 0)
            budget.record_usage("embedding", tokens_in=tokens)
            return response

        try:
            # pin the output dimension so Pinecone stays compatible across providers
            resp = _provider_request(dimensions=True)
        except Exception as exc:
            if "dimensions" not in str(exc):
                raise
            resp = _provider_request(dimensions=False)
        vectors.extend(d.embedding for d in resp.data)
    return vectors


def embed_one(text: str) -> list[float]:
    return embed([text])[0]
