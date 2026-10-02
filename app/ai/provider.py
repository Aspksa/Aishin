from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

@dataclass
class AIReply:
    text: str
    provider: str
    model: str
    available: bool = True

class AIProvider(Protocol):
    name: str
    def health(self) -> dict: ...
    def chat(self, *, system: str, messages: list[dict[str, str]]) -> AIReply: ...
