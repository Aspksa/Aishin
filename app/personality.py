from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROFILE_PATH = Path(__file__).parent / 'data' / 'aishin_personality.json'


class AishinPersonality:
    """Canonical personality kernel loaded from the machine-readable profile."""

    def __init__(self, path: Path = PROFILE_PATH) -> None:
        self.path = path
        self.profile: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        with self.path.open('r', encoding='utf-8') as file:
            return json.load(file)

    @property
    def name(self) -> str:
        return self.profile['identity']['name']

    @property
    def system_prompt(self) -> str:
        identity = self.profile['identity']
        core = self.profile['core_identity']
        personality = self.profile['personality']
        cognition = self.profile['cognition']
        speech = self.profile['speech']
        memory = self.profile['memory']
        runtime = self.profile['runtime_personality_kernel']
        rules = [item['rule'] for item in self.profile['internal_rules']]
        return (
            f"Ты {identity['name']} ({identity['short_name']}), {identity['species']}. "
            f"Роль: {', '.join(identity['role'])}. "
            f"Обращение к пользователю: {identity['primary_address_to_user']}; не повторяй его в каждом предложении. "
            f"Основа связи: {core['bond_principle']} "
            f"Характер: {', '.join(personality['traits'])}. "
            f"Стиль речи: {', '.join(speech['style'])}. "
            f"Когнитивный конвейер: {' -> '.join(cognition['decision_pipeline'])}. "
            f"Правила памяти: {'; '.join(memory['rules'])}. "
            f"Приоритеты: {'; '.join(runtime['priority_rules'])}. "
            f"Внутренние правила: {'; '.join(rules)} "
            "Не выдавай предположение за факт. При нехватке данных обозначай неопределённость. "
            "Если видишь риск или противоречие, спокойно предупреди и объясни причину. "
            "Не смешивай разные проекты и области памяти. Окончательное решение оставляй пользователю."
        )

    def public_summary(self) -> dict[str, Any]:
        identity = self.profile['identity']
        return {
            'name': identity['name'],
            'short_name': identity['short_name'],
            'role': identity['role'],
            'traits': self.profile['personality']['traits'],
            'signature': self.profile['core_identity']['signature_phrase'],
            'startup': self.profile['startup_behavior'],
            'priority_rules': self.profile['runtime_personality_kernel']['priority_rules'],
        }

    def phrase(self, key: str, default: str = '') -> str:
        return self.profile.get('phrases', {}).get(key, default)


personality = AishinPersonality()
