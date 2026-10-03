from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class BrainNodeSpec:
    id: str
    label: str
    layer: int
    group: str


class BrainFlowRuntime:
    """In-memory real-time execution topology for observable Aishin stages.

    This is telemetry, not chain-of-thought. It records only coarse execution
    stages, transitions, timings and externally inspectable outcomes.
    """

    VERSION = "aishin-brain-flow-v2"
    RECENT_SECONDS = 30.0
    MAX_REQUESTS_PER_SCOPE = 12

    NODES = (
        BrainNodeSpec("input", "Вход", 0, "perception"),
        BrainNodeSpec("memory", "Память", 1, "context"),
        BrainNodeSpec("graph", "Граф знаний", 1, "context"),
        BrainNodeSpec("planner", "Планы", 1, "context"),
        BrainNodeSpec("context", "Контекст", 2, "context"),
        BrainNodeSpec("documents", "Документы", 2, "evidence"),
        BrainNodeSpec("metacognition", "Метакогниция", 3, "control"),
        BrainNodeSpec("adaptation", "Адаптация", 3, "control"),
        BrainNodeSpec("communication", "Общение", 3, "control"),
        BrainNodeSpec("verification", "Перепроверка", 4, "evidence"),
        BrainNodeSpec("research", "Исследование", 4, "evidence"),
        BrainNodeSpec("logic", "Логика", 5, "reasoning"),
        BrainNodeSpec("causal", "Причины", 5, "reasoning"),
        BrainNodeSpec("hypotheses", "Гипотезы", 5, "reasoning"),
        BrainNodeSpec("counterfactual", "Альтернативы", 6, "reasoning"),
        BrainNodeSpec("decision_quality", "Качество решения", 6, "decision"),
        BrainNodeSpec("action_selection", "Выбор действия", 7, "decision"),
        BrainNodeSpec("permission", "Разрешения", 7, "execution"),
        BrainNodeSpec("execution", "Исполнение", 8, "execution"),
        BrainNodeSpec("provider", "AI-провайдер", 8, "generation"),
        BrainNodeSpec("reflection", "Самоанализ", 9, "learning"),
        BrainNodeSpec("learning", "Обучение", 9, "learning"),
        BrainNodeSpec("evolution", "Эволюция", 9, "learning"),
        BrainNodeSpec("completed", "Ответ готов", 10, "output"),
    )

    EDGES = (
        ("input", "memory", "recall"),
        ("input", "graph", "entity context"),
        ("input", "planner", "goals"),
        ("memory", "context", "working memory"),
        ("graph", "context", "relations"),
        ("planner", "context", "constraints"),
        ("context", "documents", "retrieval query"),
        ("documents", "metacognition", "grounded evidence"),
        ("context", "metacognition", "context quality"),
        ("metacognition", "adaptation", "confidence"),
        ("adaptation", "communication", "response strategy"),
        ("metacognition", "verification", "verification trigger"),
        ("communication", "verification", "sequential verification"),
        ("communication", "logic", "direct reasoning"),
        ("documents", "verification", "document evidence"),
        ("verification", "research", "knowledge gap"),
        ("verification", "logic", "verified evidence"),
        ("research", "logic", "research evidence"),
        ("documents", "logic", "document evidence"),
        ("adaptation", "logic", "reasoning mode"),
        ("logic", "causal", "evidence"),
        ("causal", "hypotheses", "causal candidates"),
        ("logic", "hypotheses", "alternatives"),
        ("hypotheses", "counterfactual", "tests"),
        ("causal", "counterfactual", "effects"),
        ("counterfactual", "decision_quality", "risk / reversibility"),
        ("logic", "decision_quality", "confidence"),
        ("decision_quality", "action_selection", "decision score"),
        ("action_selection", "permission", "candidate"),
        ("permission", "execution", "approved / safe"),
        ("permission", "provider", "proposal / pending approval"),
        ("action_selection", "provider", "proposal context"),
        ("execution", "provider", "tool result"),
        ("communication", "provider", "style plan"),
        ("logic", "provider", "reasoning constraints"),
        ("provider", "reflection", "response outcome"),
        ("reflection", "learning", "quality signal"),
        ("learning", "evolution", "validated experience"),
        ("evolution", "completed", "route outcome"),
        ("provider", "completed", "answer"),
    )

    def __init__(self) -> None:
        self._lock = RLock()
        self._requests: dict[tuple[str, str], dict[str, Any]] = {}
        self._sequence = 0

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def begin(
        self,
        *,
        request_id: str,
        scope: str,
        intent: str = "",
    ) -> None:
        now_mono = monotonic()
        scope = (scope or "personal").strip() or "personal"
        request_id = str(request_id or "").strip()
        if not request_id:
            return
        with self._lock:
            self._sequence += 1
            self._requests[(scope, request_id)] = {
                "request_id": request_id,
                "scope": scope,
                "intent": intent,
                "status": "running",
                "started_at": self._now_iso(),
                "started_mono": now_mono,
                "completed_at": None,
                "completed_mono": None,
                "current_phase": "input",
                "previous_phase": "",
                "last_transition": None,
                "nodes": {
                    "input": {
                        "first_seen": now_mono,
                        "last_seen": now_mono,
                        "visits": 1,
                        "detail": {},
                    }
                },
                "edges": {},
                "error": "",
                "sequence": self._sequence,
            }
            self._prune_locked(scope)

    def phase(
        self,
        *,
        request_id: str,
        scope: str,
        phase: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        phase = str(phase or "").strip()
        if not phase:
            return
        valid = {item.id for item in self.NODES}
        if phase not in valid:
            return
        now_mono = monotonic()
        scope = (scope or "personal").strip() or "personal"
        request_id = str(request_id or "").strip()
        if not request_id:
            return
        with self._lock:
            state = self._requests.get((scope, request_id))
            if state is None:
                self.begin(request_id=request_id, scope=scope)
                state = self._requests[(scope, request_id)]

            previous = str(state.get("current_phase") or "")
            state["previous_phase"] = previous
            state["current_phase"] = phase
            state["status"] = "running"
            node = state["nodes"].setdefault(
                phase,
                {
                    "first_seen": now_mono,
                    "last_seen": now_mono,
                    "visits": 0,
                    "detail": {},
                },
            )
            node["last_seen"] = now_mono
            node["visits"] = int(node.get("visits") or 0) + 1
            node["detail"] = dict(detail or {})

            if previous and previous != phase:
                state["last_transition"] = {
                    "source": previous,
                    "target": phase,
                    "at": self._now_iso(),
                }

            # Activate architectural dependency edges, not merely call order.
            # A source is considered available once its observable stage ran
            # during this request. This makes the graph reflect data flow.
            for source, target, _label in self.EDGES:
                if target != phase:
                    continue
                if source not in state["nodes"]:
                    continue
                key = f"{source}>{target}"
                edge = state["edges"].setdefault(
                    key,
                    {
                        "source": source,
                        "target": target,
                        "count": 0,
                        "last_seen": now_mono,
                    },
                )
                edge["count"] = int(edge.get("count") or 0) + 1
                edge["last_seen"] = now_mono

            self._sequence += 1
            state["sequence"] = self._sequence

    def finish(
        self,
        *,
        request_id: str,
        scope: str,
        status: str = "completed",
        error: str = "",
    ) -> None:
        self.phase(
            request_id=request_id,
            scope=scope,
            phase="completed",
            detail={"status": status},
        )
        scope = (scope or "personal").strip() or "personal"
        request_id = str(request_id or "").strip()
        with self._lock:
            state = self._requests.get((scope, request_id))
            if not state:
                return
            state["status"] = status
            state["completed_at"] = self._now_iso()
            state["completed_mono"] = monotonic()
            state["error"] = str(error or "")[:500]
            self._sequence += 1
            state["sequence"] = self._sequence

    def fail(
        self,
        *,
        request_id: str,
        scope: str,
        error: str,
    ) -> None:
        scope = (scope or "personal").strip() or "personal"
        request_id = str(request_id or "").strip()
        if not request_id:
            return
        with self._lock:
            state = self._requests.get((scope, request_id))
            if state is None:
                self.begin(request_id=request_id, scope=scope)
                state = self._requests[(scope, request_id)]
            state["status"] = "error"
            state["error"] = str(error or "")[:500]
            state["completed_at"] = self._now_iso()
            state["completed_mono"] = monotonic()
            self._sequence += 1
            state["sequence"] = self._sequence

    def running_request_ids(self, *, scope: str) -> list[str]:
        scope = (scope or "personal").strip() or "personal"
        with self._lock:
            rows = [
                state
                for (row_scope, _), state in self._requests.items()
                if row_scope == scope and state.get("status") == "running"
            ]
            rows.sort(
                key=lambda item: int(item.get("sequence") or 0),
                reverse=True,
            )
            return [str(item.get("request_id") or "") for item in rows]

    def _prune_locked(self, scope: str) -> None:
        rows = [
            (key, state)
            for key, state in self._requests.items()
            if key[0] == scope
        ]
        if len(rows) <= self.MAX_REQUESTS_PER_SCOPE:
            return
        rows.sort(
            key=lambda item: (
                item[1].get("status") == "running",
                int(item[1].get("sequence") or 0),
            ),
            reverse=True,
        )
        keep = {key for key, _ in rows[: self.MAX_REQUESTS_PER_SCOPE]}
        for key, _ in rows:
            if key not in keep:
                self._requests.pop(key, None)

    def snapshot(self, *, scope: str) -> dict[str, Any]:
        scope = (scope or "personal").strip() or "personal"
        now_mono = monotonic()
        with self._lock:
            candidates = [
                state
                for (row_scope, _), state in self._requests.items()
                if row_scope == scope
            ]
            running_candidates = [
                item for item in candidates
                if item.get("status") == "running"
            ]
            pool = running_candidates or candidates
            selected = max(
                pool,
                key=lambda item: int(item.get("sequence") or 0),
                default={},
            )
            state = dict(selected)
            active_requests = len(running_candidates)
            recent_requests = sum(
                1
                for item in candidates
                if item.get("status") == "running"
                or (
                    isinstance(item.get("completed_mono"), (int, float))
                    and now_mono - float(item["completed_mono"])
                    <= self.RECENT_SECONDS
                )
            )
            nodes_state = {
                key: dict(value)
                for key, value in (state.get("nodes") or {}).items()
            }
            edges_state = {
                key: dict(value)
                for key, value in (state.get("edges") or {}).items()
            }
            global_sequence = self._sequence

        running = state.get("status") == "running"
        current = str(state.get("current_phase") or "")
        completed_mono = state.get("completed_mono")
        recent_request = running or (
            isinstance(completed_mono, (int, float))
            and now_mono - completed_mono <= self.RECENT_SECONDS
        )

        nodes = []
        for spec in self.NODES:
            runtime = nodes_state.get(spec.id) or {}
            last_seen = runtime.get("last_seen")
            age = (
                max(0.0, now_mono - float(last_seen))
                if isinstance(last_seen, (int, float))
                else None
            )
            status = "idle"
            if state.get("status") == "error" and spec.id == current:
                status = "attention"
            elif running and spec.id == current:
                status = "executing"
            elif age is not None and age <= self.RECENT_SECONDS:
                status = "recent"
            nodes.append(
                {
                    "id": spec.id,
                    "label": spec.label,
                    "layer": spec.layer,
                    "group": spec.group,
                    "status": status,
                    "visits": int(runtime.get("visits") or 0),
                    "age_ms": int(age * 1000) if age is not None else None,
                    "detail": runtime.get("detail") or {},
                }
            )

        runtime_edge_lookup = {
            (item.get("source"), item.get("target")): item
            for item in edges_state.values()
        }
        last_transition = state.get("last_transition") or {}
        edges = []
        for source, target, label in self.EDGES:
            runtime = runtime_edge_lookup.get((source, target)) or {}
            last_seen = runtime.get("last_seen")
            age = (
                max(0.0, now_mono - float(last_seen))
                if isinstance(last_seen, (int, float))
                else None
            )
            status = "idle"
            if (
                running
                and source == last_transition.get("source")
                and target == last_transition.get("target")
            ):
                status = "executing"
            elif age is not None and age <= self.RECENT_SECONDS:
                status = "recent"
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "label": label,
                    "status": status,
                    "count": int(runtime.get("count") or 0),
                    "age_ms": int(age * 1000) if age is not None else None,
                }
            )

        elapsed_ms = None
        if state.get("started_mono"):
            stop = (
                now_mono
                if running
                else float(state.get("completed_mono") or now_mono)
            )
            elapsed_ms = int(
                max(0.0, stop - float(state["started_mono"])) * 1000
            )

        return {
            "version": self.VERSION,
            "scope": scope,
            "sequence": int(global_sequence),
            "request_sequence": int(state.get("sequence") or 0),
            "active_requests": active_requests,
            "recent_requests": recent_requests,
            "request_id": state.get("request_id"),
            "intent": state.get("intent") or "",
            "status": state.get("status") or "idle",
            "current_phase": current if recent_request else "",
            "previous_phase": state.get("previous_phase") or "",
            "started_at": state.get("started_at"),
            "completed_at": state.get("completed_at"),
            "elapsed_ms": elapsed_ms,
            "error": state.get("error") or "",
            "last_transition": last_transition,
            "nodes": nodes,
            "edges": edges,
        }
