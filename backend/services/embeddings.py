"""
Embedding service — turns text into vectors using Gemini `gemini-embedding-001`.

Key points:
- task_type matters for quality: RETRIEVAL_DOCUMENT when storing KB chunks,
  RETRIEVAL_QUERY when embedding a user question. Same model, different framing.
- output_dimensionality is pinned to settings.EMBEDDING_DIMENSION (3072) so it
  always matches the DB column (halfvec(3072)).
- Vectors are L2-normalized. gemini-embedding-001 is pre-normalized at 3072, but
  truncated dims (768/1536) are NOT — normalizing always keeps cosine correct.
- The google-genai client is sync, so calls are pushed to a thread for async use.

Nothing here talks to the DB. It only produces vectors.
"""
from __future__ import annotations

import asyncio
import logging
import math

from backend.config import settings

log = logging.getLogger("embeddings")

_client = None


def _get_client():
    """Lazy singleton google-genai client (raises clearly if key/SDK missing)."""
    global _client
    if _client is None:
        try:
            from google import genai  # google-genai package
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "google-genai not installed. Add `google-genai>=0.3` and pip install."
            ) from exc
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is empty — cannot create embeddings.")
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        return vec
    return [v / norm for v in vec]


def _embed_sync(texts: list[str], task_type: str) -> list[list[float]]:
    """Blocking embed call. Batched to respect request-size limits."""
    from google.genai import types

    client = _get_client()
    out: list[list[float]] = []
    batch = max(1, settings.EMBEDDING_BATCH_SIZE)

    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        resp = client.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=chunk,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=settings.EMBEDDING_DIMENSION,
            ),
        )
        for emb in resp.embeddings:
            out.append(_l2_normalize(list(emb.values)))
    return out


async def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Embed a list of texts. Returns one vector per input text (order preserved)."""
    texts = [t if t is not None else "" for t in texts]
    if not texts:
        return []
    return await asyncio.to_thread(_embed_sync, texts, task_type)


async def embed_query(text: str) -> list[float] | None:
    """Embed a single search query. Returns None on empty input or failure."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        vecs = await embed_texts([text], task_type="RETRIEVAL_QUERY")
        return vecs[0] if vecs else None
    except Exception:
        log.exception("embed_query failed")
        return None


def to_pgvector_literal(vec: list[float]) -> str:
    """Format a vector as the pgvector text literal '[v1,v2,...]'.

    We pass vectors as strings and CAST(... AS halfvec) in SQL. This works on
    both psycopg2 and psycopg3 without needing the pgvector type adapter
    registered on the connection — keeps the code driver-agnostic.
    """
    return "[" + ",".join(repr(float(v)) for v in vec) + "]"