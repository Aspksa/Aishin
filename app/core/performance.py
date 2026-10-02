from __future__ import annotations

import json
import time

from ..db import connect


class PerformanceTracker:
    """Per-request stage timing with soft latency budgets."""

    DEFAULT_BUDGETS_MS = {
        "memory_consolidation": 500,
        "graph_builder": 500,
        "planner_builder": 500,
        "cognition": 700,
        "sensors_metacognition": 500,
        "verification": 2500,
        "logic_pipeline": 1000,
        "context_orchestrator": 500,
        "cloud": 5000,
        "postprocess": 500,
        "total": 8000,
    }

    def __init__(
        self,
        *,
        request_id: str,
        scope: str,
        budgets_ms: dict[str, int] | None = None,
    ) -> None:
        self.request_id = request_id
        self.scope = scope
        self.budgets_ms = dict(self.DEFAULT_BUDGETS_MS)
        if budgets_ms:
            self.budgets_ms.update(
                {
                    str(key): max(1, int(value))
                    for key, value in budgets_ms.items()
                }
            )
        self._started = time.perf_counter()
        self._last = self._started
        self.stages: dict[str, int] = {}

    def checkpoint(self, name: str) -> int:
        now = time.perf_counter()
        elapsed_ms = int((now - self._last) * 1000)
        self.stages[name] = self.stages.get(name, 0) + elapsed_ms
        self._last = now
        return elapsed_ms

    def finish(self, *, mode: str) -> dict:
        now = time.perf_counter()
        total_ms = int((now - self._started) * 1000)
        if self.stages:
            bottleneck = max(
                self.stages,
                key=lambda key: self.stages[key],
            )
        else:
            bottleneck = ""

        over = {
            key: value
            for key, value in self.stages.items()
            if key in self.budgets_ms
            and value > int(self.budgets_ms[key])
        }
        if total_ms > int(self.budgets_ms["total"]):
            over["total"] = total_ms

        status = "over_budget" if over else "within_budget"
        payload = {
            "request_id": self.request_id,
            "scope": self.scope,
            "mode": mode,
            "stages_ms": dict(self.stages),
            "budgets_ms": dict(self.budgets_ms),
            "total_ms": total_ms,
            "bottleneck": bottleneck,
            "budget_status": status,
            "over_budget": over,
        }

        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO performance_traces(
                       request_id, scope, mode, stages_json,
                       budgets_json, total_ms, bottleneck, budget_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.request_id,
                    self.scope,
                    mode,
                    json.dumps(self.stages, ensure_ascii=False),
                    json.dumps(self.budgets_ms, ensure_ascii=False),
                    total_ms,
                    bottleneck,
                    status,
                ),
            )
            conn.commit()
            payload["performance_id"] = int(cur.lastrowid)

        return payload


class PerformanceHistory:
    @staticmethod
    def recent(*, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM performance_traces
                   WHERE scope=?
                   ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["stages_ms"] = json.loads(item.pop("stages_json") or "{}")
            item["budgets_ms"] = json.loads(item.pop("budgets_json") or "{}")
            result.append(item)
        return result
