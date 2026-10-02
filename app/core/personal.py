from __future__ import annotations

from dataclasses import dataclass

from ..db import (
    add_relationship_memory,
    add_timeline_event,
    find_relationship_by_fingerprint,
    get_master_profile,
    recent_relationship_memories,
    recent_timeline,
    set_master_profile_value,
    update_relationship_strength,
)
from .memory import fingerprint


@dataclass
class PersonalContext:
    master_profile: dict
    relationship_memory: list[dict]
    timeline: list[dict]


class PersonalAishin:
    """Personal continuity layer for one primary user.

    It intentionally keeps the owner's profile, the shared relationship history
    and the personal timeline separate from project-specific memories.
    """

    def profile(self) -> dict:
        return get_master_profile()

    def set_profile_value(
        self,
        key: str,
        value,
        *,
        source: str = "explicit_user",
        confidence: float = 1.0,
    ) -> None:
        set_master_profile_value(
            key.strip(),
            value,
            source=source,
            confidence=confidence,
        )

    def remember_relationship(
        self,
        content: str,
        *,
        kind: str = "shared_history",
        importance: float = 0.8,
        confidence: float = 1.0,
        source: str = "conversation",
    ) -> int:
        clean = content.strip()
        fp = fingerprint(clean)
        existing = find_relationship_by_fingerprint(fp)
        if existing:
            update_relationship_strength(
                existing["id"],
                confidence=max(float(existing["confidence"]), confidence),
                importance=max(float(existing["importance"]), importance),
            )
            return int(existing["id"])

        return add_relationship_memory(
            kind=kind,
            content=clean,
            importance=importance,
            confidence=confidence,
            source=source,
            fingerprint=fp,
        )

    def add_timeline(
        self,
        *,
        event_type: str,
        title: str,
        details: str = "",
        scope: str = "personal",
        importance: float = 0.5,
        occurred_at: str | None = None,
    ) -> int:
        return add_timeline_event(
            event_type=event_type,
            title=title,
            details=details,
            scope=scope,
            importance=importance,
            occurred_at=occurred_at,
        )

    def context(self, *, scope: str = "personal") -> PersonalContext:
        return PersonalContext(
            master_profile=self.profile(),
            relationship_memory=recent_relationship_memories(limit=10),
            timeline=recent_timeline(limit=10, scope=scope),
        )

    def prompt_block(self, *, scope: str = "personal") -> str:
        context = self.context(scope=scope)
        parts: list[str] = [
            "Личный контекст Айшин. Это не общий сервис: у Айшин один основной Господин.",
            "Не выдумывай отсутствующие личные сведения. Учитывай только сохранённые данные.",
        ]

        if context.master_profile:
            parts.append("Профиль Господина:")
            for key, item in context.master_profile.items():
                parts.append(
                    f"- {key}: {item['value']} "
                    f"(source={item['source']}, confidence={item['confidence']:.2f})"
                )

        if context.relationship_memory:
            parts.append("Важная совместная история:")
            for item in context.relationship_memory:
                parts.append(
                    f"- [{item['kind']}; confidence={item['confidence']:.2f}] "
                    f"{item['content']}"
                )

        if context.timeline:
            parts.append("Недавняя личная временная линия:")
            for item in reversed(context.timeline):
                suffix = f": {item['details']}" if item["details"] else ""
                parts.append(
                    f"- {item['occurred_at']} · {item['title']}{suffix}"
                )

        return "\n".join(parts)

    @staticmethod
    def looks_relationship_explicit(text: str) -> bool:
        lowered = text.lower()
        markers = (
            "мы решили",
            "мы договорились",
            "наша договор",
            "наша история",
            "между нами",
            "вместе будем",
            "вместе будем делать",
            "вместе развивать",
            "запомни нашу",
            "запомни, что мы",
        )
        return any(marker in lowered for marker in markers)
