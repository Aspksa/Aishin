from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..ai import AIManager
from ..db import log_memory_change
from .events import EventBus
from .memory import MemoryCandidate, MemorySystem
from .personal import PersonalAishin

_SECRET_RE = re.compile(
    r"(парол|password|api[_ -]?key|секретн.*ключ|token|токен|bearer|private[_ -]?key)",
    re.IGNORECASE,
)

_HIGH_SIGNAL = (
    "запомни",
    "помни",
    "сохрани",
    "я хочу",
    "я предпочитаю",
    "мне нравится",
    "я люблю",
    "я не люблю",
    "для меня важно",
    "всегда делай",
    "никогда не",
    "мы решили",
    "мы договорились",
    "вместе будем",
    "вместе развивать",
    "теперь",
    "больше не",
    "вместо этого",
)

_EXPLICIT_MEMORY = ("запомни", "помни", "сохрани")


@dataclass
class ConsolidationOutcome:
    considered: bool
    provider_used: bool
    created: int = 0
    reinforced: int = 0
    superseded: int = 0
    conflicts: int = 0
    profile_updates: int = 0
    relationship_updates: int = 0
    timeline_updates: int = 0
    ignored: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class MemoryConsolidator:
    """Grounded memory consolidation for Aishin."""

    def __init__(
        self,
        *,
        ai: AIManager,
        memory: MemorySystem,
        personal: PersonalAishin,
        events: EventBus,
    ) -> None:
        self.ai = ai
        self.memory = memory
        self.personal = personal
        self.events = events

    @staticmethod
    def should_consider(text: str) -> bool:
        lowered = text.lower()
        if len(text.strip()) < 8:
            return False
        return any(marker in lowered for marker in _HIGH_SIGNAL)

    @staticmethod
    def _is_explicit_memory_request(text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in _EXPLICIT_MEMORY)

    def consolidate_turn(self, user_text: str, *, scope: str) -> ConsolidationOutcome:
        outcome = ConsolidationOutcome(
            considered=self.should_consider(user_text),
            provider_used=False,
        )
        if not outcome.considered:
            return outcome

        if _SECRET_RE.search(user_text):
            outcome.ignored += 1
            self.events.emit(
                "memory.consolidation.skipped",
                scope=scope,
                payload={"reason": "possible_secret"},
                importance=0.8,
            )
            return outcome

        candidates = self._extract_with_ai(user_text, scope=scope)
        if candidates is not None:
            outcome.provider_used = True
            self._apply_candidates(
                candidates,
                user_text=user_text,
                scope=scope,
                outcome=outcome,
            )
        else:
            self._fallback(user_text, scope=scope, outcome=outcome)

        self.events.emit(
            "memory.consolidation.completed",
            scope=scope,
            payload=outcome.to_dict(),
            importance=0.5,
        )
        return outcome

    def _extract_with_ai(self, user_text: str, *, scope: str) -> list[dict] | None:
        system = """Ты модуль консолидации памяти личной AI-помощницы Айшин.
Верни ТОЛЬКО JSON без markdown в формате:
{"memories":[
  {
    "target":"personal_memory|project_memory|master_profile|relationship|timeline",
    "kind":"preference|rule|goal|decision|fact|shared_decision|event",
    "key":"короткий стабильный ключ или null",
    "content":"краткий факт без домыслов",
    "evidence":"точная цитата из сообщения пользователя",
    "confidence":0.0,
    "importance":0.0,
    "supersedes":false,
    "sensitive":false
  }
]}
Правила:
- Извлекай только то, что прямо сказано пользователем.
- Не додумывай имя, возраст, здоровье, политику, религию, адрес, пароли, ключи и другие секреты.
- Если факт временный, бытовой или не стоит долговременной памяти — не сохраняй.
- Для изменения старого предпочтения или правила ставь supersedes=true.
- target=relationship только для явных совместных договорённостей или значимой общей истории.
- target=master_profile только для устойчивых личных предпочтений или правил пользователя.
- target=timeline только для события или принятого решения.
- evidence обязана быть дословным фрагментом пользовательского сообщения.
- Максимум 4 записи.
- Если сохранять нечего: {"memories":[]}.
"""
        prompt = (
            f"Текущая область памяти: {scope}\n"
            "Сообщение пользователя:\n"
            f"{user_text}"
        )
        reply = self.ai.chat(
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if not reply.available:
            return None

        raw = reply.text.strip()
        fence = chr(96) * 3
        if raw.startswith(fence):
            raw = re.sub(r"^.{3}(?:json)?\s*", "", raw, count=1)
            raw = re.sub(r"\s*.{3}$", "", raw, count=1)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None

        memories = data.get("memories")
        if not isinstance(memories, list):
            return None
        return memories[:4]

    @staticmethod
    def _grounded(candidate: dict, user_text: str) -> bool:
        evidence = str(candidate.get("evidence") or "").strip()
        if len(evidence) < 3:
            return False
        return evidence.casefold() in user_text.casefold()

    @staticmethod
    def _safe_key(raw) -> str | None:
        if raw is None:
            return None
        key = re.sub(r"[^a-zA-Z0-9_.:-]+", "_", str(raw).strip()).strip("_")
        return key[:96] or None

    def _apply_candidates(
        self,
        candidates: list[dict],
        *,
        user_text: str,
        scope: str,
        outcome: ConsolidationOutcome,
    ) -> None:
        explicit = self._is_explicit_memory_request(user_text)

        for item in candidates:
            if not isinstance(item, dict) or not self._grounded(item, user_text):
                outcome.ignored += 1
                continue

            if bool(item.get("sensitive")) and not explicit:
                outcome.ignored += 1
                continue

            target = str(item.get("target") or "").strip()
            kind = str(item.get("kind") or "fact").strip()[:64]
            content = str(item.get("content") or "").strip()
            if len(content) < 3 or len(content) > 700:
                outcome.ignored += 1
                continue

            try:
                confidence = max(0.0, min(1.0, float(item.get("confidence", 0.7))))
                importance = max(0.0, min(1.0, float(item.get("importance", 0.6))))
            except (TypeError, ValueError):
                outcome.ignored += 1
                continue

            if confidence < 0.70 or importance < 0.50:
                outcome.ignored += 1
                continue

            memory_key = self._safe_key(item.get("key"))
            supersedes = bool(item.get("supersedes", False))
            evidence = str(item.get("evidence") or "").strip()

            if target in {"personal_memory", "project_memory"}:
                target_scope = "personal" if target == "personal_memory" else scope
                decision = self.memory.consolidate(
                    MemoryCandidate(
                        content=content,
                        kind=kind,
                        scope=target_scope,
                        confidence=confidence,
                        importance=importance,
                        tags=("auto_consolidated", f"evidence:{evidence[:120]}"),
                        memory_key=memory_key,
                        supersedes=supersedes,
                    ),
                    source="conversation_consolidation",
                )
                if decision.action == "created":
                    outcome.created += 1
                elif decision.action == "reinforced":
                    outcome.reinforced += 1
                elif decision.action == "superseded":
                    outcome.superseded += 1
                elif decision.action == "conflict_saved":
                    outcome.conflicts += 1
                else:
                    outcome.ignored += 1
                continue

            if target == "master_profile":
                if not memory_key:
                    outcome.ignored += 1
                    continue
                self.personal.set_profile_value(
                    memory_key,
                    content,
                    source="conversation_consolidation",
                    confidence=confidence,
                )
                self.personal.add_timeline(
                    event_type="master_profile_update",
                    title="Профиль Господина уточнён",
                    details=f"{memory_key}: {content}",
                    scope="personal",
                    importance=importance,
                )
                log_memory_change(
                    "personal",
                    None,
                    "master_profile_update",
                    "grounded_conversation_fact",
                    after={
                        "key": memory_key,
                        "content": content,
                        "evidence": evidence,
                        "confidence": confidence,
                    },
                )
                outcome.profile_updates += 1
                continue

            if target == "relationship":
                self.personal.remember_relationship(
                    content,
                    kind=kind or "shared_history",
                    importance=importance,
                    confidence=confidence,
                    source="conversation_consolidation",
                )
                self.personal.add_timeline(
                    event_type="relationship_memory",
                    title="Совместная память",
                    details=content,
                    scope="relationship",
                    importance=importance,
                )
                outcome.relationship_updates += 1
                continue

            if target == "timeline":
                self.personal.add_timeline(
                    event_type=kind or "event",
                    title=content[:120],
                    details=evidence,
                    scope=scope,
                    importance=importance,
                )
                outcome.timeline_updates += 1
                continue

            outcome.ignored += 1

    def _fallback(
        self,
        user_text: str,
        *,
        scope: str,
        outcome: ConsolidationOutcome,
    ) -> None:
        lowered = user_text.lower()

        if self._is_explicit_memory_request(user_text):
            decision = self.memory.consolidate(
                MemoryCandidate(
                    content=user_text.strip(),
                    kind="explicit_user_memory",
                    scope=scope,
                    confidence=1.0,
                    importance=0.9,
                    tags=("explicit", "fallback"),
                ),
                source="explicit_user_request",
            )
            if decision.action == "created":
                outcome.created += 1
            elif decision.action == "reinforced":
                outcome.reinforced += 1
            elif decision.action == "superseded":
                outcome.superseded += 1
            elif decision.action == "conflict_saved":
                outcome.conflicts += 1
            return

        if any(
            marker in lowered
            for marker in (
                "мы решили",
                "мы договорились",
                "вместе будем",
                "вместе развивать",
            )
        ):
            self.personal.remember_relationship(
                user_text.strip(),
                kind="shared_decision",
                importance=0.85,
                confidence=0.9,
                source="fallback_consolidation",
            )
            self.personal.add_timeline(
                event_type="shared_decision",
                title="Совместная договорённость",
                details=user_text.strip(),
                scope="relationship",
                importance=0.85,
            )
            outcome.relationship_updates += 1
            return

        outcome.ignored += 1
