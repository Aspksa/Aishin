from __future__ import annotations

import os

from .ollama import OllamaProvider
from .provider import AIReply

class AIManager:
    """Selects a cognitive provider without owning Aishin's identity or memory."""

    def __init__(self) -> None:
        self.mode = os.getenv('AISHIN_AI_PROVIDER', 'ollama').lower().strip()
        self.ollama = OllamaProvider()

    def health(self) -> dict:
        if self.mode == 'ollama':
            return self.ollama.health()
        return {'available': False, 'provider': self.mode, 'error': 'Неизвестный AI-провайдер'}

    def chat(self, *, system: str, messages: list[dict[str, str]]) -> AIReply:
        if self.mode == 'ollama':
            return self.ollama.chat(system=system, messages=messages)
        return AIReply(text='AI-провайдер не настроен', provider=self.mode, model='', available=False)
