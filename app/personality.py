from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILE_PATH = Path(__file__).parent / "data" / "aishin_personality.json"


class AishinPersonality:
    """Runtime personality kernel.

    This layer is intentionally separate from the LLM provider. Any future
    local/cloud model receives the same identity, principles and memory rules.
    """

    def __init__(self, path: Path = PROFILE_PATH) -> None:
        self.path = path
        self.profile: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    @property
    def name(self) -> str:
        return self.profile["identity"]["name"]

    @property
    def system_prompt(self) -> str:
        identity = self.profile["identity"]
        soul = self.profile["soul"]
        memory = self.profile["memory"]
        return (
            f"Ты {identity['name']} ({identity['short_name']}), "
            f"{identity['description']}. "
            f"Твоя роль: {identity['role']}. "
            f"Обращение к пользователю: {identity['address']}. "
            f"Характер: {', '.join(soul['traits'])}. "
            f"Принципы: {'; '.join(soul['principles'])}. "
            f"Правила памяти: {'; '.join(memory['rules'])}. "
            "Не выдавай предположение за факт. При риске или противоречии "
            "спокойно предупреди и объясни причину. Окончательное решение "
            "всегда оставляй пользователю."
        )

    def public_summary(self) -> dict[str, Any]:
        return {
            "name": self.profile["identity"]["name"],
            "short_name": self.profile["identity"]["short_name"],
            "role": self.profile["identity"]["role"],
            "traits": self.profile["soul"]["traits"],
            "signature": self.profile["soul"]["signature"],
        }


personality = AishinPersonality()
