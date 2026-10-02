from __future__ import annotations

import hashlib
from dataclasses import dataclass

from ..db import (
    create_proactive_decision,
    get_proactive_decision,
    list_proactive_decisions,
    update_proactive_decision,
)
from .events import EventBus
from .execution_coordinator import ExecutionCoordinator
from .permissions import PermissionGate
from .planner import Planner, PlannerNotice
from .sensors import SensorHub
from .tools import ToolRegistry


@dataclass
class DecisionEvaluation:
    created: int
    pending: int
    attention: int
    scope: str

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "pending": self.pending,
            "attention": self.attention,
            "scope": self.scope,
        }


class ProactiveDecisionLoop:
    """Observe -> evaluate -> propose -> approve/reject -> execute.

    The loop never treats a proposal as an executed action.
    """

    def __init__(
        self,
        *,
        planner: Planner,
        sensors: SensorHub,
        tools: ToolRegistry,
        permissions: PermissionGate,
        events: EventBus,
        coordinator: ExecutionCoordinator | None = None,
    ) -> None:
        self.planner = planner
        self.sensors = sensors
        self.tools = tools
        self.permissions = permissions
        self.events = events
        self.coordinator = coordinator

    def evaluate(self, *, scope: str) -> DecisionEvaluation:
        readings = self.sensors.scan(scope=scope, persist=False)
        notices = self.planner.inspect(scope=scope)
        pending_before = list_proactive_decisions(
            scope,
            status="pending",
            limit=500,
        )
        before = {item["id"] for item in pending_before}
        pending_fingerprints = {
            item["fingerprint"] for item in pending_before
        }

        active_notice_fingerprints: set[str] = set()
        for notice in notices:
            fingerprint = self._notice_fingerprint(notice, scope=scope)
            active_notice_fingerprints.add(fingerprint)
            if fingerprint in pending_fingerprints:
                continue
            proposal = self._proposal_for_notice(
                notice,
                scope=scope,
                fingerprint=fingerprint,
            )
            if proposal is None:
                continue
            self._store_proposal(scope=scope, **proposal)
            pending_fingerprints.add(fingerprint)

        # Dismiss planner proposals whose underlying condition is already resolved.
        for item in pending_before:
            if not str(item.get("source") or "").startswith("planner:"):
                continue
            if item["fingerprint"] in active_notice_fingerprints:
                continue
            update_proactive_decision(
                int(item["id"]),
                scope=scope,
                status="dismissed",
                execution={"reason": "underlying_condition_resolved"},
            )
            pending_fingerprints.discard(item["fingerprint"])

        # Sensor-level attention that is not already represented by planner notices.
        for reading in readings:
            if reading["status"] == "ok" or reading["sensor"] == "planner":
                continue
            title = f"Проверить сигнал сенсора: {reading['sensor']}"
            rationale = (
                f"Сенсор {reading['sensor']} сообщил состояние "
                f"{reading['status']}."
            )
            fingerprint = self._fingerprint(
                "sensor",
                reading["sensor"],
                reading["status"],
                scope,
            )
            if fingerprint in pending_fingerprints:
                continue
            create_proactive_decision(
                scope=scope,
                fingerprint=fingerprint,
                source=f"sensor:{reading['sensor']}",
                title=title,
                rationale=rationale,
                priority=float(reading.get("importance", 0.5)),
                confidence=0.9,
                tool_name=None,
                capability=None,
                arguments={},
                preview={},
            )

        pending = list_proactive_decisions(scope, status="pending", limit=500)
        after = {item["id"] for item in pending}
        created = len(after - before)

        if created:
            self.events.emit(
                "proactive.decisions.created",
                scope=scope,
                payload={
                    "created": created,
                    "pending": len(pending),
                },
                importance=0.65,
            )

        return DecisionEvaluation(
            created=created,
            pending=len(pending),
            attention=len(notices),
            scope=scope,
        )

    def pending(self, *, scope: str, limit: int = 100) -> list[dict]:
        return list_proactive_decisions(
            scope,
            status="pending",
            limit=limit,
        )

    def history(
        self,
        *,
        scope: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        return list_proactive_decisions(scope, status=status, limit=limit)

    def approve(
        self,
        decision_id: int,
        *,
        scope: str,
        execute: bool = False,
    ) -> dict:
        decision = get_proactive_decision(decision_id, scope)
        if not decision:
            raise ValueError("decision not found in scope")
        if decision["status"] != "pending":
            raise ValueError("only pending decisions can be approved")

        approval = None
        if decision.get("tool_name"):
            if self.coordinator is None:
                raise ValueError("execution coordinator unavailable")
            approval = self.coordinator.issue_approval(
                decision_id,
                scope=scope,
            )

        update_proactive_decision(
            decision_id,
            scope=scope,
            status="approved",
            execution={
                "approval": approval or {},
            },
        )
        self.events.emit(
            "proactive.decision.approved",
            scope=scope,
            payload={"decision_id": decision_id},
            importance=0.6,
        )

        if execute:
            return self.execute(decision_id, scope=scope)

        result = get_proactive_decision(decision_id, scope)
        return result or {}

    def reject(
        self,
        decision_id: int,
        *,
        scope: str,
        reason: str = "",
    ) -> dict:
        decision = get_proactive_decision(decision_id, scope)
        if not decision:
            raise ValueError("decision not found in scope")
        if decision["status"] not in {"pending", "approved"}:
            raise ValueError("decision cannot be rejected in current status")

        update_proactive_decision(
            decision_id,
            scope=scope,
            status="rejected",
            execution={"reason": reason.strip()},
        )
        self.events.emit(
            "proactive.decision.rejected",
            scope=scope,
            payload={
                "decision_id": decision_id,
                "reason": reason.strip(),
            },
            importance=0.4,
        )
        result = get_proactive_decision(decision_id, scope)
        return result or {}

    def execute(self, decision_id: int, *, scope: str) -> dict:
        decision = get_proactive_decision(decision_id, scope)
        if not decision:
            raise ValueError("decision not found in scope")
        if decision["status"] != "approved":
            raise ValueError("decision must be approved before execution")

        tool_name = decision.get("tool_name")
        if not tool_name:
            update_proactive_decision(
                decision_id,
                scope=scope,
                status="dismissed",
                execution={
                    "reason": "informational_decision_has_no_tool",
                },
            )
            result = get_proactive_decision(decision_id, scope)
            return result or {}

        if self.coordinator is None:
            raise ValueError("execution coordinator unavailable")

        execution = self.coordinator.execute(
            decision_id,
            scope=scope,
        )
        success = execution.get("status") == "success"
        stale = execution.get("status") == "stale_or_blocked"
        update_proactive_decision(
            decision_id,
            scope=scope,
            status="executed" if success else ("approved" if stale else "failed"),
            execution=execution,
        )
        self.events.emit(
            "proactive.decision.executed"
            if success
            else "proactive.decision.failed",
            scope=scope,
            payload={
                "decision_id": decision_id,
                "tool": tool_name,
                "tool_status": execution.get("status"),
            },
            importance=0.75 if success else 0.9,
        )
        result = get_proactive_decision(decision_id, scope)
        return result or {}

    def prompt_block(self, *, scope: str) -> str:
        pending = self.pending(scope=scope, limit=10)
        lines = [
            "Проактивный контур Айшин.",
            "Предложение действия не является выполненным действием.",
            "Нельзя говорить, что действие выполнено, пока decision status не executed.",
        ]
        if not pending:
            lines.append("- Нет ожидающих решений.")
            return "\n".join(lines)

        lines.append("Ожидают решения Господина:")
        for item in pending:
            tool = item.get("tool_name") or "информационное"
            lines.append(
                f"- decision #{item['id']}: {item['title']} "
                f"(priority={float(item['priority']):.2f}, tool={tool})"
            )
        return "\n".join(lines)

    def _notice_fingerprint(
        self,
        notice: PlannerNotice,
        *,
        scope: str,
    ) -> str:
        if notice.goal_id is not None:
            identity = f"goal:{notice.goal_id}"
        elif notice.task_id is not None:
            identity = f"task:{notice.task_id}"
        else:
            identity = notice.message
        return self._fingerprint(
            "planner",
            notice.code,
            identity,
            scope,
        )

    def _proposal_for_notice(
        self,
        notice: PlannerNotice,
        *,
        scope: str,
        fingerprint: str,
    ) -> dict | None:
        common = {
            "source": f"planner:{notice.code}",
            "priority": 0.8 if notice.severity == "warning" else 0.55,
            "confidence": 1.0,
        }

        if notice.code == "goal_without_tasks" and notice.goal_id is not None:
            goal = next(
                (
                    item
                    for item in self.planner.goals(scope=scope, limit=200)
                    if int(item["id"]) == int(notice.goal_id)
                ),
                None,
            )
            if not goal:
                return None

            arguments = {
                "title": f"Определить следующий шаг по цели «{goal['title']}»",
                "goal_id": int(goal["id"]),
                "priority": max(float(goal["priority"]), 0.55),
                "description": (
                    "Уточнить конкретный следующий шаг. "
                    "Задача создана планировщиком после явного одобрения."
                ),
            }
            preview = self.tools.invoke(
                "planner.create_task",
                scope=scope,
                arguments=arguments,
                dry_run=True,
            )
            return {
                **common,
                "fingerprint": fingerprint,
                "title": f"Добавить следующий шаг для цели «{goal['title']}»",
                "rationale": notice.message,
                "tool_name": "planner.create_task",
                "capability": "manage_internal_plans",
                "arguments": arguments,
                "preview": preview,
            }

        if notice.code in {
            "task_overdue",
            "task_blocked",
            "waiting_dependencies",
            "invalid_due_at",
        }:
            return {
                **common,
                "fingerprint": fingerprint,
                "title": notice.message,
                "rationale": (
                    "Айшин обнаружила состояние задачи, которое требует "
                    "внимания, но не имеет безопасного автоматического "
                    "действия без дополнительного решения Господина."
                ),
                "tool_name": None,
                "capability": "proactive_notice",
                "arguments": {},
                "preview": {},
            }

        return None

    def _store_proposal(
        self,
        *,
        scope: str,
        fingerprint: str,
        source: str,
        title: str,
        rationale: str,
        priority: float,
        confidence: float,
        tool_name: str | None,
        capability: str | None,
        arguments: dict,
        preview: dict,
    ) -> int:
        return create_proactive_decision(
            scope=scope,
            fingerprint=fingerprint,
            source=source,
            title=title,
            rationale=rationale,
            priority=max(0.0, min(1.0, priority)),
            confidence=max(0.0, min(1.0, confidence)),
            tool_name=tool_name,
            capability=capability,
            arguments=arguments,
            preview=preview,
        )

    @staticmethod
    def _fingerprint(*parts: str) -> str:
        raw = "|".join(str(part).strip().casefold() for part in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
