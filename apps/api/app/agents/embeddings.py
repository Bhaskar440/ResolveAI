"""Embedding clients for the policy knowledge base.

Real vectors come from Gemini's embedding API. If the API is unavailable, a
deterministic hashed bag-of-words embedder is used and labelled as such — it is a
fallback, never presented as a model embedding.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger("resolveai.embeddings")

EMBED_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
TOKEN_RE = re.compile(r"[a-z0-9]+")


class EmbeddingError(RuntimeError):
    pass


class Embedder(Protocol):
    name: str
    dimensions: int
    kind: str

    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_one(self, text: str) -> list[float]: ...


class GeminiEmbedder:
    kind = "gemini"

    def __init__(self, model: str, dimensions: int = 768):
        self.name = model
        self.dimensions = dimensions
        self.api_key = get_settings().llm_api_key
        if not self.api_key:
            raise EmbeddingError("Gemini API key is not configured")

    async def _call(self, texts: list[str]) -> list[list[float]]:
        url = f"{EMBED_ROOT}/{self.name}:batchEmbedContents"
        requests = [
            {
                "model": f"models/{self.name}",
                "content": {"parts": [{"text": text[:8000]}]},
                "outputDimensionality": self.dimensions,
            }
            for text in texts
        ]
        last_error = ""
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.post(
                        url, params={"key": self.api_key}, json={"requests": requests}
                    )
                if response.status_code == 200:
                    payload = response.json()
                    vectors = [
                        [float(value) for value in item.get("values", [])]
                        for item in payload.get("embeddings", [])
                    ]
                    if len(vectors) != len(texts) or any(
                        len(vector) != self.dimensions for vector in vectors
                    ):
                        raise EmbeddingError(
                            f"embedding shape mismatch: expected {len(texts)}x{self.dimensions}"
                        )
                    return vectors
                last_error = f"{response.status_code}: {response.text[:200]}"
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
            except Exception as exc:  # noqa: BLE001 - retry boundary, re-raised as EmbeddingError
                last_error = str(exc)[:200]
            if attempt == 0:
                await asyncio.sleep(1.0)
        raise EmbeddingError(last_error or "embedding request failed")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 20):
            vectors.extend(await self._call(texts[start : start + 20]))
        return vectors

    async def embed_one(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


class HashEmbedder:
    """Deterministic fallback used only when the embedding API is unavailable."""

    kind = "hash"
    name = "hash-768"

    def __init__(self, dimensions: int = 768):
        self.dimensions = dimensions

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.lower()):
            if len(token) < 3:
                continue
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    async def embed_one(self, text: str) -> list[float]:
        return self._vector(text)


def get_embedder(prefer: str | None = None) -> Embedder:
    settings = get_settings()
    model = prefer or settings.knowledge_embedding_model
    dimensions = settings.knowledge_embedding_dimensions
    if model == "hash-768":
        return HashEmbedder(dimensions)
    if settings.llm_api_key and model:
        return GeminiEmbedder(model, dimensions)
    return HashEmbedder(dimensions)
