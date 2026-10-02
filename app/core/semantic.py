from __future__ import annotations

import math

from ..ai import AIManager
from ..db import (
    active_memories_missing_vector,
    active_memory_vectors,
    upsert_memory_vector,
)
from .memory import fingerprint


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class SemanticMemory:
    """Cloud.ru embedding index with SQLite persistence and graceful fallback."""

    def __init__(self, ai: AIManager) -> None:
        self.ai = ai

    def health(self) -> dict:
        return self.ai.embedding_health()

    def ensure_index(self, *, scope: str, batch_size: int = 32) -> dict:
        health = self.ai.embedding_health()
        if not health.get("configured"):
            return {"indexed": 0, "available": False, "reason": "not_configured"}

        model = str(health.get("model") or "")
        pending = active_memories_missing_vector(
            scope,
            model,
            limit=max(1, min(batch_size, 64)),
        )
        if not pending:
            return {"indexed": 0, "available": True, "reason": "up_to_date"}

        reply = self.ai.embed([item["content"] for item in pending])
        if not reply.available:
            return {
                "indexed": 0,
                "available": False,
                "reason": reply.error or "embedding_failed",
            }

        indexed = 0
        for item, vector in zip(pending, reply.vectors):
            upsert_memory_vector(
                memory_id=int(item["id"]),
                scope=scope,
                model=reply.model,
                vector=vector,
                content_hash=fingerprint(item["content"]),
            )
            indexed += 1

        return {
            "indexed": indexed,
            "available": True,
            "model": reply.model,
            "dimensions": reply.dimensions,
        }

    def search(
        self,
        query: str,
        *,
        scope: str,
        limit: int = 8,
        min_similarity: float = 0.22,
    ) -> list[dict]:
        query = query.strip()
        if not query:
            return []

        self.ensure_index(scope=scope)

        reply = self.ai.embed([query])
        if not reply.available or not reply.vectors:
            return []

        query_vector = reply.vectors[0]
        scored: list[tuple[float, dict]] = []

        for item in active_memory_vectors(scope):
            similarity = cosine_similarity(query_vector, item["vector"])
            if similarity < min_similarity:
                continue

            confidence = float(item.get("confidence", 0.0))
            importance = float(item.get("importance", 0.0))
            rank = (0.78 * similarity) + (0.11 * confidence) + (0.11 * importance)

            result = dict(item)
            result.pop("vector", None)
            result["semantic_similarity"] = round(similarity, 6)
            result["retrieval_score"] = round(rank, 6)
            result["retrieval"] = "semantic"
            scored.append((rank, result))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in scored[: max(1, limit)]]
