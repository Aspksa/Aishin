from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..ai import AIManager
from .events import EventBus
from .graph import KnowledgeGraph


_ALLOWED_ENTITY_TYPES = {
    "person",
    "assistant",
    "project",
    "document",
    "organization",
    "vehicle",
    "place",
    "object",
    "task",
    "decision",
    "event",
}

_ALLOWED_RELATIONS = {
    "assists",
    "develops",
    "belongs_to",
    "part_of",
    "mentions",
    "related_to",
    "owns",
    "uses",
    "works_on",
    "created",
    "made_decision",
    "concerns",
    "assigned_to",
    "depends_on",
    "located_at",
    "works_for",
    "applies_to",
    "references",
    "replaces",
    "caused_by",
    "resulted_in",
}

_GRAPH_SIGNALS = (
    "проект",
    "документ",
    "файл",
    "договор",
    "счёт",
    "счет",
    "машин",
    "автомоб",
    "сотрудник",
    "организац",
    "компан",
    "задач",
    "решили",
    "решение",
    "событ",
    "место",
    "работ",
    "вместе",
    "aishin",
    "айшин",
)

_SECRET_RE = re.compile(
    r"(парол|password|api[_ -]?key|секретн.*ключ|token|токен|bearer|private[_ -]?key)",
    re.IGNORECASE,
)


@dataclass
class GraphBuildOutcome:
    considered: bool
    provider_used: bool
    entities: int = 0
    relations: int = 0
    ignored: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class GraphBuilder:
    """Extracts grounded entities and relations into Aishin's world model."""

    def __init__(
        self,
        *,
        ai: AIManager,
        graph: KnowledgeGraph,
        events: EventBus,
    ) -> None:
        self.ai = ai
        self.graph = graph
        self.events = events

    @staticmethod
    def should_consider(text: str) -> bool:
        lowered = text.lower()
        return (
            len(text.strip()) >= 18
            and any(signal in lowered for signal in _GRAPH_SIGNALS)
        )

    def ingest(self, text: str, *, scope: str) -> GraphBuildOutcome:
        considered = self.should_consider(text)
        outcome = GraphBuildOutcome(
            considered=considered,
            provider_used=False,
        )
        if not considered:
            outcome.reason = "low_signal"
            return outcome

        if _SECRET_RE.search(text):
            outcome.ignored += 1
            outcome.reason = "possible_secret"
            return outcome

        extracted = self._extract(text, scope=scope)
        if extracted is None:
            outcome.reason = "provider_unavailable_or_invalid"
            return outcome

        outcome.provider_used = True
        refs: dict[str, int] = {}

        for entity in extracted.get("entities", [])[:10]:
            if not isinstance(entity, dict):
                outcome.ignored += 1
                continue

            ref = str(entity.get("ref") or "").strip()
            entity_type = str(entity.get("type") or "").strip().lower()
            mention = str(entity.get("mention") or "").strip()
            name = str(entity.get("name") or "").strip()
            evidence = str(entity.get("evidence") or mention).strip()

            if (
                not ref
                or entity_type not in _ALLOWED_ENTITY_TYPES
                or not self._grounded(mention, text)
                or not self._grounded(evidence, text)
            ):
                outcome.ignored += 1
                continue

            canonical = name if 1 < len(name) <= 120 else mention
            entity_id = self.graph.entity(
                scope=scope,
                entity_type=entity_type,
                name=canonical,
                data={
                    "mention": mention,
                    "source": "conversation_graph_extraction",
                },
                evidence=evidence,
            )
            refs[ref] = entity_id
            outcome.entities += 1

        for relation in extracted.get("relations", [])[:12]:
            if not isinstance(relation, dict):
                outcome.ignored += 1
                continue

            source_ref = str(relation.get("source") or "").strip()
            target_ref = str(relation.get("target") or "").strip()
            relation_type = str(relation.get("type") or "").strip().lower()
            evidence = str(relation.get("evidence") or "").strip()

            if (
                source_ref not in refs
                or target_ref not in refs
                or source_ref == target_ref
                or relation_type not in _ALLOWED_RELATIONS
                or not self._grounded(evidence, text)
            ):
                outcome.ignored += 1
                continue

            try:
                confidence = max(
                    0.0,
                    min(1.0, float(relation.get("confidence", 0.8))),
                )
            except (TypeError, ValueError):
                outcome.ignored += 1
                continue

            if confidence < 0.70:
                outcome.ignored += 1
                continue

            self.graph.relate(
                scope=scope,
                source_id=refs[source_ref],
                relation_type=relation_type,
                target_id=refs[target_ref],
                confidence=confidence,
                evidence=evidence,
            )
            outcome.relations += 1

        self.events.emit(
            "knowledge_graph.updated",
            scope=scope,
            payload=outcome.to_dict(),
            importance=0.4,
        )
        outcome.reason = "processed"
        return outcome

    @staticmethod
    def _grounded(fragment: str, text: str) -> bool:
        fragment = fragment.strip()
        if len(fragment) < 2:
            return False
        return fragment.casefold() in text.casefold()

    def _extract(self, text: str, *, scope: str) -> dict | None:
        system = """Ты модуль построения графа знаний Айшин.
Верни ТОЛЬКО JSON без markdown:
{
  "entities":[
    {
      "ref":"e1",
      "type":"person|assistant|project|document|organization|vehicle|place|object|task|decision|event",
      "mention":"точный фрагмент из сообщения",
      "name":"каноническое короткое имя",
      "evidence":"точный фрагмент из сообщения"
    }
  ],
  "relations":[
    {
      "source":"e1",
      "type":"assists|develops|belongs_to|part_of|mentions|related_to|owns|uses|works_on|created|made_decision|concerns|assigned_to|depends_on|located_at|works_for|applies_to|references|replaces|caused_by|resulted_in",
      "target":"e2",
      "evidence":"точный фрагмент из сообщения, подтверждающий связь",
      "confidence":0.0
    }
  ]
}
Правила:
- Только явно указанные сущности и связи.
- mention и evidence должны быть дословными фрагментами сообщения пользователя.
- Не делай выводов о личности, здоровье, религии, политике или других чувствительных свойствах.
- Не извлекай пароли, ключи, токены и секреты.
- Не создавай сущность для каждого обычного существительного.
- Максимум 10 сущностей и 12 связей.
- Если данных нет: {"entities":[],"relations":[]}.
"""
        reply = self.ai.chat(
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": f"Scope: {scope}\nСообщение:\n{text}",
                }
            ],
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

        if not isinstance(data, dict):
            return None
        if not isinstance(data.get("entities", []), list):
            return None
        if not isinstance(data.get("relations", []), list):
            return None
        return data
