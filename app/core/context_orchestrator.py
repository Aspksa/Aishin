from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..db import connect
from ..personality import personality
from .graph import KnowledgeGraph
from .memory import MemorySystem
from .personal import PersonalAishin
from .planner import Planner
from .self_model import SelfModel


@dataclass(frozen=True)
class ContextBudget:
    history: int
    memories: int
    graph_entities: int
    planner_items: int
    verification_items: int
    sensor_items: int


@dataclass
class ContextTrace:
    mode: str
    budget: dict
    selected: dict
    estimated_chars: int
    trace_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ContextOrchestrator:
    """Mode-aware prompt composer for Aishin.

    It chooses what enters the final model context; it does not delete source data.
    """

    BUDGETS = {
        "FAST": ContextBudget(4, 4, 0, 2, 0, 2),
        "DEEP": ContextBudget(8, 8, 8, 5, 4, 4),
        "VERIFY": ContextBudget(6, 12, 12, 4, 8, 5),
        "PLAN": ContextBudget(6, 6, 6, 12, 3, 3),
        "DIAGNOSE": ContextBudget(8, 10, 8, 8, 8, 6),
    }

    def __init__(
        self,
        *,
        memory: MemorySystem,
        graph: KnowledgeGraph,
        planner: Planner,
    ) -> None:
        self.memory = memory
        self.graph = graph
        self.planner = planner
        self.personal = PersonalAishin()
        self.self_model = SelfModel()

    def budget_for(self, mode: str) -> ContextBudget:
        return self.BUDGETS.get(mode, self.BUDGETS["FAST"])

    def compose(
        self,
        query: str,
        *,
        scope: str,
        mode: str,
        memories: list[dict],
        verification: dict | None,
        sensor_readings: list[dict],
    ) -> tuple[str, ContextTrace]:
        budget = self.budget_for(mode)

        selected_memories = memories[: budget.memories]
        graph_entities = (
            self.graph.search(query, scope=scope, limit=budget.graph_entities)
            if budget.graph_entities
            else []
        )
        planner_items = self._planner_items(
            scope=scope,
            limit=budget.planner_items,
        )
        verification_items = self._verification_items(
            verification,
            limit=budget.verification_items,
        )
        sensors = sensor_readings[: budget.sensor_items]

        blocks = [
            personality.system_prompt,
            self.self_model.prompt_block(),
            self.personal.prompt_block(scope=scope),
            (
                "Context Orchestrator: "
                f"режим={mode}; используй только отобранный контекст ниже. "
                "Отсутствие блока не означает отсутствие данных в долговременной памяти."
            ),
        ]

        if selected_memories:
            blocks.append(
                "Working Memory:\\n"\n                + self.memory.context_block(selected_memories)
            )

        if graph_entities:
            lines = ["Relevant Knowledge Graph entities:"]
            for item in graph_entities:
                lines.append(
                    f"- {item.get('entity_type')}: "
                    f"{item.get('canonical_name')} "
                    f"data={json.dumps(item.get('data') or {}, ensure_ascii=False)}"
                )
            blocks.append("\\n".join(lines))

        if planner_items:
            lines = ["Relevant Planner items:"]
            for item in planner_items:
                lines.append(
                    f"- {item['kind']} #{item['id']}: "
                    f"{item['title']} status={item['status']}"
                )
            blocks.append("\\n".join(lines))

        if verification_items:
            lines = ["Verification evidence:"]
            for item in verification_items:
                lines.append(f"- {item}")
            blocks.append("
".join(lines))

        if sensors:
            lines = ["Selected Sensor state:"]
            for item in sensors:
                lines.append(
                    f"- {item.get('sensor')}: status={item.get('status')}"
                )
            blocks.append("
".join(lines))

        prompt = "\\n\\n".join(block for block in blocks if block)
        selected = {
            "memory_ids": [item.get("id") for item in selected_memories],
            "graph_entity_ids": [item.get("id") for item in graph_entities],
            "planner": planner_items,
            "verification_count": len(verification_items),
            "sensors": [item.get("sensor") for item in sensors],
        }

        trace = ContextTrace(
            mode=mode,
            budget=asdict(budget),
            selected=selected,
            estimated_chars=len(prompt),
        )
        trace.trace_id = self._record(
            scope=scope,
            query=query,
            trace=trace,
        )
        return prompt, trace

    def history_limit(self, mode: str) -> int:
        return self.budget_for(mode).history

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM context_traces
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["budget"] = json.loads(item.pop("budget_json") or "{}")
            item["selected"] = json.loads(item.pop("selected_json") or "{}")
            result.append(item)
        return result

    def _planner_items(self, *, scope: str, limit: int) -> list[dict]:
        if limit <= 0:
            return []

        tasks = self.planner.tasks(scope=scope, limit=limit)
        goals = self.planner.goals(scope=scope, limit=limit)
        result: list[dict] = []

        for item in tasks:
            if item.get("status") in {"completed", "cancelled"}:
                continue
            result.append(
                {
                    "kind": "task",
                    "id": item["id"],
                    "title": item["title"],
                    "status": item["status"],
                    "priority": item.get("priority", 0.5),
                }
            )

        for item in goals:
            if item.get("status") in {"completed", "cancelled"}:
                continue
            result.append(
                {
                    "kind": "goal",
                    "id": item["id"],
                    "title": item["title"],
                    "status": item["status"],
                    "priority": item.get("priority", 0.5),
                }
            )

        result.sort(
            key=lambda item: float(item.get("priority", 0.0)),
            reverse=True,
        )
        return result[:limit]

    @staticmethod
    def _verification_items(
        verification: dict | None,
        *,
        limit: int,
    ) -> list[str]:
        if not verification or limit <= 0:
            return []

        result: list[str] = []
        for key in ("findings", "unresolved"):
            for item in verification.get(key, []) or []:
                text = str(item).strip()
                if text:
                    result.append(text)
                if len(result) >= limit:
                    return result
        return result

    @staticmethod
    def _record(
        *,
        scope: str,
        query: str,
        trace: ContextTrace,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO context_traces(
                       scope, mode, query, budget_json,
                       selected_json, estimated_chars
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    trace.mode,
                    query[:1200],
                    json.dumps(trace.budget, ensure_ascii=False),
                    json.dumps(trace.selected, ensure_ascii=False),
                    trace.estimated_chars,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
