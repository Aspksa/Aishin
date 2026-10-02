from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class AIReply:
    text: str
    provider: str
    model: str
    available: bool = True


@dataclass
class EmbeddingReply:
    vectors: list[list[float]]
    provider: str
    model: str
    dimensions: int
    available: bool = True
    error: str = ""


class AIProvider(Protocol):
    name: str

    def health(self) -> dict: ...

    def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, str]],
    ) -> AIReply: ...

    def embed(self, texts: list[str]) -> EmbeddingReply: ...
