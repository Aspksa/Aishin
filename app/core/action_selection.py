from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..db import connect
from .permissions import PermissionGate
from .tools import ToolRegistry


@dataclass
class ActionCandidate:
    action: str
    utility: float
    benefit: float
    risk_penalty: float
    reversibility_penalty: float
    permission_penalty: float
    uncertainty_penalty: float
    matched_tool: str | None
    capability: str | None
    permission_mode: str | None
    requires_approval: bool
    execution_state: str
    rationale: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ActionSelectionResult:
    mode: str
    candidates: list[ActionCandidate]
    selected: ActionCandidate | None
    selection_state: str
    selection_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "candidates": [item.to_dict() for item in self.candidates],
            "selected": self.selected.to_dict() if self.selected else {},
            "selection_state": self.selection_state,
            "selection_id": self.selection_id,
        }


class ActionSelector:
    """Rank action candidates by expected utility without executing them."""

    def __init__(
        self,
        *,
        tools: ToolRegistry,
        permissions: PermissionGate,
    ) -> None:
        self.tools = tools
        self.permissions = permissions

    def select(
        self,
        query: str,
        *,
        scope: str,
        mode: str,
        counterfactual: dict,
        decision_quality: dict,
        unresolved: list[str],
    ) -> ActionSelectionResult:
        quality = max(
            0.0,
            min(1.0, float(decision_quality.get("overall", 0.0))),
        )
        scenarios = counterfactual.get("scenarios", []) or []

        candidates: list[ActionCandidate] = []
        for scenario in scenarios[:6]:
            action = str(scenario.get("action") or "").strip()
            if not action:
                continue

            confidence = max(
                0.0,
                min(1.0, float(scenario.get("confidence", 0.0))),
            )
            benefit = round(confidence * quality, 4)

            risks = scenario.get("risks", []) or []
            risk_penalty = min(0.50, len(risks) * 0.10)

            reversibility = str(
                scenario.get("reversibility") or "medium"
            ).casefold()
            reversibility_penalty = {
                "high": 0.0,
                "medium": 0.12,
                "low": 0.30,
            }.get(reversibility, 0.15)

            tool = self._match_tool(action)
            capability = None
            permission_mode = None
            permission_penalty = 0.0
            requires_approval = False
            execution_state = "proposal_only"

            if tool:
                spec = self.tools.SPECS[tool]
                capability = spec.capability
                permission_mode = self.permissions.mode(capability)

                if permission_mode == "deny":
                    permission_penalty = 0.55
                    execution_state = "blocked_by_permission"
                elif permission_mode == "ask":
                    permission_penalty = 0.10
                    requires_approval = True
                    execution_state = "approval_required"
                else:
                    execution_state = "eligible_for_tool_registry"

                if spec.destructive:
                    reversibility_penalty = max(
                        reversibility_penalty,
                        0.35,
                    )
                    requires_approval = True
                    execution_state = "approval_required"

            uncertainty_penalty = min(
                0.30,
                len(unresolved) * 0.05,
            )

            raw = (
                benefit
                - risk_penalty
                - reversibility_penalty
                - permission_penalty
                - uncertainty_penalty
            )
            utility = round(max(0.0, min(1.0, raw)), 4)

            rationale = [
                f"benefit={benefit:.2f}",
                f"risk_penalty={risk_penalty:.2f}",
                f"reversibility_penalty={reversibility_penalty:.2f}",
                f"permission_penalty={permission_penalty:.2f}",
                f"uncertainty_penalty={uncertainty_penalty:.2f}",
            ]

            candidates.append(
                ActionCandidate(
                    action=action,
                    utility=utility,
                    benefit=benefit,
                    risk_penalty=round(risk_penalty, 4),
                    reversibility_penalty=round(
                        reversibility_penalty,
                        4,
                    ),
                    permission_penalty=round(permission_penalty, 4),
                    uncertainty_penalty=round(
                        uncertainty_penalty,
                        4,
                    ),
                    matched_tool=tool,
                    capability=capability,
                    permission_mode=permission_mode,
                    requires_approval=requires_approval,
                    execution_state=execution_state,
                    rationale=rationale,
                )
            )

        candidates.sort(
            key=lambda item: item.utility,
            reverse=True,
        )

        selected = candidates[0] if candidates else None
        selection_state = "proposal_only"
        if selected is not None:
            selection_state = selected.execution_state

        result = ActionSelectionResult(
            mode=mode,
            candidates=candidates,
            selected=selected,
            selection_state=selection_state,
        )
        result.selection_id = self._record(
            scope=scope,
            query=query,
            decision_quality=quality,
            result=result,
        )
        return result

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM action_selections
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["candidates"] = json.loads(
                item.pop("candidates_json") or "[]"
            )
            item["selected"] = json.loads(
                item.pop("selected_json") or "{}"
            )
            result.append(item)
        return result

    @staticmethod
    def prompt_block(result: ActionSelectionResult) -> str:
        if result.selected is None:
            return "Action Selection: подходящего кандидата на действие нет."

        selected = result.selected
        lines = [
            "Action Selection / Expected Utility.",
            f"Кандидат: {selected.action}",
            f"utility={selected.utility:.2f}.",
            f"execution_state={selected.execution_state}.",
            "Выбор кандидата НЕ означает выполнение.",
        ]

        if selected.matched_tool:
            lines.append(
                f"matched_tool={selected.matched_tool}; "
                f"permission={selected.permission_mode}; "
                f"requires_approval={selected.requires_approval}."
            )

        if selected.execution_state == "blocked_by_permission":
            lines.append(
                "Действие нельзя предлагать как исполнимое, пока permission=deny."
            )
        elif selected.requires_approval:
            lines.append(
                "Перед реальным вызовом инструмента требуется явное подтверждение Господина."
            )

        return "\n".join(lines)

    def _match_tool(self, action: str) -> str | None:
        text = action.casefold()

        if any(
            marker in text
            for marker in (
                "прочитать файл",
                "проверить файл",
                "открыть файл",
                "read file",
            )
        ):
            return "project.read_text"

        if any(
            marker in text
            for marker in (
                "записать файл",
                "изменить файл",
                "обновить файл",
                "write file",
            )
        ):
            return "project.write_text"

        if any(
            marker in text
            for marker in (
                "создать задачу",
                "добавить задачу",
                "create task",
            )
        ):
            return "planner.create_task"

        if any(
            marker in text
            for marker in (
                "изменить статус задачи",
                "закрыть задачу",
                "обновить статус задачи",
            )
        ):
            return "planner.set_task_status"

        return None

    @staticmethod
    def _record(
        *,
        scope: str,
        query: str,
        decision_quality: float,
        result: ActionSelectionResult,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO action_selections(
                       scope, query, mode, candidates_json,
                       selected_json, decision_quality, selection_state
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    query[:1200],
                    result.mode,
                    json.dumps(
                        [item.to_dict() for item in result.candidates],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        result.selected.to_dict()
                        if result.selected
                        else {},
                        ensure_ascii=False,
                    ),
                    decision_quality,
                    result.selection_state,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
