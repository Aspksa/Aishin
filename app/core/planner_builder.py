from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..ai import AIManager
from .events import EventBus
from .planner import Planner


_SIGNALS = (
    "надо ",
    "нужно ",
    "сделай",
    "сделаем",
    "будем делать",
    "потом ",
    "следующий шаг",
    "цель ",
    "задача ",
    "хочу сделать",
    "не забудь",
)

_SECRET_RE = re.compile(
    r"(парол|password|api[_ -]?key|секретн.*ключ|token|токен|bearer|private[_ -]?key)",
    re.IGNORECASE,
)


@dataclass
class PlanningOutcome:
    considered: bool
    provider_used: bool
    goals_created: int = 0
    tasks_created: int = 0
    ignored: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class PlannerBuilder:
    """Grounded extraction of explicit goals/tasks from conversation."""

    def __init__(
        self,
        *,
        ai: AIManager,
        planner: Planner,
        events: EventBus,
    ) -> None:
        self.ai = ai
        self.planner = planner
        self.events = events

    @staticmethod
    def should_consider(text: str) -> bool:
        lowered = text.lower()
        return len(text.strip()) >= 8 and any(signal in lowered for signal in _SIGNALS)

    def ingest(self, text: str, *, scope: str) -> PlanningOutcome:
        outcome = PlanningOutcome(
            considered=self.should_consider(text),
            provider_used=False,
        )
        if not outcome.considered:
            outcome.reason = "low_signal"
            return outcome

        if _SECRET_RE.search(text):
            outcome.ignored += 1
            outcome.reason = "possible_secret"
            return outcome

        data = self._extract(text, scope=scope)
        if data is None:
            outcome.reason = "provider_unavailable_or_invalid"
            return outcome

        outcome.provider_used = True

        existing_goals = {
            item["title"].strip().casefold()
            for item in self.planner.goals(scope=scope, limit=200)
        }
        existing_tasks = {
            item["title"].strip().casefold()
            for item in self.planner.tasks(scope=scope, limit=300)
            if item["status"] not in {"cancelled"}
        }

        goal_refs: dict[str, int] = {}

        for item in data.get("goals", [])[:4]:
            if not isinstance(item, dict):
                outcome.ignored += 1
                continue

            ref = str(item.get("ref") or "").strip()
            title = str(item.get("title") or "").strip()
            evidence = str(item.get("evidence") or "").strip()
            if (
                not ref
                or not title
                or len(title) > 160
                or not self._grounded(evidence, text)
            ):
                outcome.ignored += 1
                continue

            key = title.casefold()
            if key in existing_goals:
                outcome.ignored += 1
                continue

            try:
                priority = max(0.0, min(1.0, float(item.get("priority", 0.6))))
            except (TypeError, ValueError):
                priority = 0.6

            goal_id = self.planner.create_goal(
                scope=scope,
                title=title,
                description=str(item.get("description") or "").strip()[:1000],
                priority=priority,
                source="conversation_planner",
                evidence=evidence,
                due_at=self._safe_due_at(item.get("due_at")),
            )
            goal_refs[ref] = goal_id
            existing_goals.add(key)
            outcome.goals_created += 1

        for item in data.get("tasks", [])[:8]:
            if not isinstance(item, dict):
                outcome.ignored += 1
                continue

            title = str(item.get("title") or "").strip()
            evidence = str(item.get("evidence") or "").strip()
            if not title or len(title) > 180 or not self._grounded(evidence, text):
                outcome.ignored += 1
                continue

            key = title.casefold()
            if key in existing_tasks:
                outcome.ignored += 1
                continue

            try:
                priority = max(0.0, min(1.0, float(item.get("priority", 0.6))))
            except (TypeError, ValueError):
                priority = 0.6

            goal_ref = str(item.get("goal_ref") or "").strip()
            goal_id = goal_refs.get(goal_ref)

            self.planner.create_task(
                scope=scope,
                title=title,
                description=str(item.get("description") or "").strip()[:1200],
                goal_id=goal_id,
                priority=priority,
                source="conversation_planner",
                evidence=evidence,
                due_at=self._safe_due_at(item.get("due_at")),
            )
            existing_tasks.add(key)
            outcome.tasks_created += 1

        outcome.reason = "processed"
        self.events.emit(
            "planner.ingested",
            scope=scope,
            payload=outcome.to_dict(),
            importance=0.4,
        )
        return outcome

    @staticmethod
    def _grounded(fragment: str, text: str) -> bool:
        fragment = fragment.strip()
        return len(fragment) >= 3 and fragment.casefold() in text.casefold()

    @staticmethod
    def _safe_due_at(value) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        # Only accept an explicit ISO-like date supplied by the extraction layer.
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?", text):
            return text
        return None

    def _extract(self, text: str, *, scope: str) -> dict | None:
        system = """Ты модуль внутреннего планировщика личной Айшин.
Верни ТОЛЬКО JSON:
{
  "goals":[
    {
      "ref":"g1",
      "title":"краткая цель",
      "description":"описание без домыслов",
      "priority":0.0,
      "due_at":null,
      "evidence":"точная цитата пользователя"
    }
  ],
  "tasks":[
    {
      "title":"конкретная задача",
      "description":"описание без домыслов",
      "goal_ref":"g1 или null",
      "priority":0.0,
      "due_at":null,
      "evidence":"точная цитата пользователя"
    }
  ]
}
Правила:
- Создавай только цели и задачи, которые пользователь явно выразил.
- evidence обязана быть дословным фрагментом сообщения пользователя.
- Не придумывай сроки. due_at указывай только если пользователь явно назвал календарную дату/время, иначе null.
- Не создавай действий с паролями, токенами и секретами.
- Не превращай обычный вопрос в задачу.
- Не создавай больше 4 целей и 8 задач.
- Если планировать нечего: {"goals":[],"tasks":[]}.
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
        if not isinstance(data.get("goals", []), list):
            return None
        if not isinstance(data.get("tasks", []), list):
            return None
        return data
