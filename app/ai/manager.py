from __future__ import annotations

import os

from .cloudru import CloudRuProvider
from .provider import AIReply, EmbeddingReply


class AIManager:
    """Selects Aishin's cloud cognitive provider without owning identity or memory."""

    def __init__(self) -> None:
        self.mode = os.getenv("AISHIN_AI_PROVIDER", "cloudru").lower().strip()
        self.cloudru = CloudRuProvider()

    def health(self) -> dict:
        if self.mode in {"cloudru", "cloud.ru"}:
            return self.cloudru.health()
        return {
            "available": False,
            "provider": self.mode,
            "error": "Неизвестный AI-провайдер",
        }

    def chat(self, *, system: str, messages: list[dict[str, str]]) -> AIReply:
        if self.mode in {"cloudru", "cloud.ru"}:
            return self.cloudru.chat(system=system, messages=messages)
        return AIReply(
            text="AI-провайдер не настроен",
            provider=self.mode,
            model="",
            available=False,
        )


    def embed(self, texts: list[str]) -> EmbeddingReply:
        if self.mode in {"cloudru", "cloud.ru"}:
            return self.cloudru.embed(texts)
        return EmbeddingReply(
            vectors=[],
            provider=self.mode,
            model="",
            dimensions=0,
            available=False,
            error="Embedding-провайдер не настроен",
        )

    def embedding_health(self) -> dict:
        if self.mode in {"cloudru", "cloud.ru"}:
            base = self.cloudru.health()
            return {
                "available": base.get("available", False),
                "provider": self.cloudru.name,
                "model": self.cloudru.embedding_model,
                "dimensions": self.cloudru.embedding_dimensions,
                "configured": bool(self.cloudru.api_key),
                "error": base.get("error"),
            }
        return {
            "available": False,
            "provider": self.mode,
            "error": "Embedding-провайдер не настроен",
        }
