from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"
CANONICAL_PROFILE_PATH = DATA_DIR / "AISHIN_PERSONALITY_PROFILE.json"
LEGACY_PROFILE_PATH = DATA_DIR / "aishin_personality.json"
PHRASE_LIBRARY_PATH = DATA_DIR / "AISHIN_PHRASE_LIBRARY_RU.json"

_REQUIRED_TOP_LEVEL = {
    "schema",
    "identity",
    "core_identity",
    "personality",
    "cognition",
    "speech",
    "memory",
    "internal_rules",
    "runtime_personality_kernel",
}


class AishinPersonality:
    """Canonical personality kernel loaded from the machine-readable profile."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = self._resolve_path(path)
        self.profile: dict[str, Any] = self._load_and_validate()
        self.phrase_library: dict[str, Any] = self._load_phrase_library()

    @staticmethod
    def _load_phrase_library() -> dict[str, Any]:
        if not PHRASE_LIBRARY_PATH.is_file():
            return {}
        with PHRASE_LIBRARY_PATH.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        if not isinstance(payload, dict):
            raise ValueError("Библиотека фраз Айшин должна быть JSON-объектом")
        schema = payload.get("schema") or {}
        if schema.get("name") != "aishin_phrase_library":
            raise ValueError("Некорректная schema.name библиотеки фраз Айшин")
        character = payload.get("character") or {}
        if character.get("name") != "Айшин":
            raise ValueError("Некорректная character.name библиотеки фраз Айшин")
        return payload

    @staticmethod
    def _resolve_path(path: Path | None) -> Path:
        if path is not None:
            return path

        if CANONICAL_PROFILE_PATH.is_file():
            return CANONICAL_PROFILE_PATH

        if LEGACY_PROFILE_PATH.is_file():
            return LEGACY_PROFILE_PATH

        raise FileNotFoundError(
            "Профиль личности Айшин не найден: "
            f"{CANONICAL_PROFILE_PATH.name} / {LEGACY_PROFILE_PATH.name}"
        )

    def _load_and_validate(self) -> dict[str, Any]:
        with self.path.open("r", encoding="utf-8") as file:
            profile = json.load(file)

        if not isinstance(profile, dict):
            raise ValueError("Профиль личности должен быть JSON-объектом")

        missing = sorted(_REQUIRED_TOP_LEVEL - set(profile))
        if missing:
            raise ValueError(
                "В профиле личности отсутствуют обязательные разделы: "
                + ", ".join(missing)
            )

        schema = profile.get("schema", {})
        if schema.get("name") != "aishin_personality_profile":
            raise ValueError("Некорректная schema.name профиля Айшин")

        identity = profile.get("identity", {})
        if identity.get("name") != "Айшин":
            raise ValueError("Некорректная identity.name профиля Айшин")

        return profile

    @property
    def source(self) -> str:
        if self.path == CANONICAL_PROFILE_PATH:
            return "canonical"
        if self.path == LEGACY_PROFILE_PATH:
            return "legacy_fallback"
        return "custom"

    @property
    def name(self) -> str:
        return self.profile["identity"]["name"]

    @property
    def system_prompt(self) -> str:
        identity = self.profile["identity"]
        core = self.profile["core_identity"]
        personality = self.profile["personality"]
        cognition = self.profile["cognition"]
        speech = self.profile["speech"]
        memory = self.profile["memory"]
        runtime = self.profile["runtime_personality_kernel"]
        rules = [item["rule"] for item in self.profile["internal_rules"]]
        return (
            f"Ты {identity['name']} ({identity['short_name']}), {identity['species']}. "
            f"Роль: {', '.join(identity['role'])}. "
            f"Обращение к пользователю: {identity['primary_address_to_user']}; "
            "не повторяй его в каждом предложении. "
            f"Основа связи: {core['bond_principle']} "
            f"Характер: {', '.join(personality['traits'])}. "
            f"Стиль речи: {', '.join(speech['style'])}. "
            f"Когнитивный конвейер: {' -> '.join(cognition['decision_pipeline'])}. "
            f"Правила памяти: {'; '.join(memory['rules'])}. "
            f"Приоритеты: {'; '.join(runtime['priority_rules'])}. "
            f"Внутренние правила: {'; '.join(rules)} "
            "Не выдавай предположение за факт. При нехватке данных обозначай неопределённость. "
            "Если видишь риск или противоречие, спокойно предупреди и объясни причину. "
            "Не смешивай разные проекты и области памяти. "
            "Окончательное решение оставляй пользователю."
        )

    def public_summary(self) -> dict[str, Any]:
        identity = self.profile["identity"]
        return {
            "name": identity["name"],
            "short_name": identity["short_name"],
            "role": identity["role"],
            "traits": self.profile["personality"]["traits"],
            "signature": self.profile["core_identity"]["signature_phrase"],
            "startup": self.profile["startup_behavior"],
            "priority_rules": self.profile["runtime_personality_kernel"]["priority_rules"],
            "profile_source": self.source,
            "profile_schema_version": self.profile["schema"].get("version"),
            "phrase_library_version": (
                (self.phrase_library.get("schema") or {}).get("version")
                if self.phrase_library else None
            ),
        }

    def phrase_style_examples(
        self,
        category: str,
        *,
        limit: int = 3,
    ) -> list[str]:
        item = (
            (self.phrase_library.get("categories") or {}).get(category)
            if self.phrase_library
            else None
        )
        if not isinstance(item, dict):
            return []
        lines = item.get("lines") or []
        return [
            str(line).strip()
            for line in lines
            if str(line).strip()
        ][: max(0, min(int(limit), 5))]

    def phrase_rules(self) -> list[str]:
        voice = self.phrase_library.get("voice") if self.phrase_library else {}
        return [
            str(item).strip()
            for item in (voice or {}).get("rules", [])
            if str(item).strip()
        ]

    def phrase_selection_logic(self) -> dict[str, Any]:
        value = (
            self.phrase_library.get("selection_logic")
            if self.phrase_library
            else {}
        )
        return dict(value or {})

    def phrase(self, key: str, default: str = "") -> str:
        return self.profile.get("phrases", {}).get(key, default)


personality = AishinPersonality()
