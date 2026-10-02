from __future__ import annotations

import json

from ..db import connect
from .self_reflection import SelfReflectionMetrics


class LearningPlanner:
    """Turns repeated measured weaknesses into explicit learning objectives."""

    def __init__(self, reflection: SelfReflectionMetrics) -> None:
        self.reflection = reflection

    def refresh(self, *, scope: str) -> list[dict]:
        summary = self.reflection.summary(scope=scope, limit=50)
        if summary["samples"] < 3:
            return self.open_plans(scope=scope)

        candidates: list[tuple[str, str, float, str, list[str]]] = []
        weak = summary["weak_spots"]
        samples = max(1, int(summary["samples"]))

        def rate(name: str) -> float:
            return float(weak.get(name, 0)) / samples

        if rate("user_correction") >= 0.15:
            candidates.append((
                "reduce_user_corrections",
                "Снизить долю повторных исправлений после ответов.",
                min(1.0, 0.55 + rate("user_correction")),
                "correction_rate",
                ["user_correction"],
            ))
        if rate("low_confidence") >= 0.20 or rate("unresolved_evidence") >= 0.20:
            candidates.append((
                "improve_evidence_confidence",
                "Улучшить достаточность evidence и калибровку уверенности.",
                min(1.0, 0.50 + max(
                    rate("low_confidence"), rate("unresolved_evidence")
                )),
                "confidence_score",
                ["low_confidence", "unresolved_evidence"],
            ))
        if rate("latency") >= 0.15:
            candidates.append((
                "reduce_reasoning_latency",
                "Снизить перегрузку тяжёлого когнитивного контура.",
                min(1.0, 0.50 + rate("latency")),
                "latency_ms",
                ["latency"],
            ))
        if rate("provider_availability") >= 0.10:
            candidates.append((
                "improve_provider_resilience",
                "Уменьшить влияние отказов внешнего AI-провайдера.",
                min(1.0, 0.60 + rate("provider_availability")),
                "provider_error_rate",
                ["provider_availability"],
            ))
        if (
            summary["average_quality"] is not None
            and float(summary["average_quality"]) < 0.70
        ):
            candidates.append((
                "raise_response_quality",
                "Поднять устойчивую измеряемую оценку качества ответов.",
                min(1.0, 1.0 - float(summary["average_quality"]) + 0.45),
                "average_quality",
                ["quality_below_target"],
            ))

        for topic, rationale, priority, target, evidence in candidates:
            self._upsert_open(
                scope=scope,
                topic=topic,
                rationale=rationale,
                priority=round(priority, 4),
                target_metric=target,
                evidence=evidence,
            )
        return self.open_plans(scope=scope)

    def open_plans(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM learning_plans
                   WHERE scope=? AND status='open'
                   ORDER BY priority DESC, id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def recent(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM learning_plans
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def set_status(self, plan_id: int, *, scope: str, status: str) -> dict:
        if status not in {"open", "testing", "completed", "dismissed"}:
            raise ValueError("Некорректный статус learning plan")
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM learning_plans WHERE id=? AND scope=?",
                (plan_id, scope),
            ).fetchone()
            if row is None:
                raise ValueError("Learning plan не найден")
            conn.execute(
                """UPDATE learning_plans
                   SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (status, plan_id),
            )
            conn.execute(
                """INSERT INTO learning_plan_events(
                       scope, plan_id, event, details_json
                   ) VALUES (?, ?, ?, ?)""",
                (scope, plan_id, "status_changed", json.dumps(
                    {"status": status}, ensure_ascii=False
                )),
            )
            conn.commit()
        return {"id": plan_id, "status": status}

    def _upsert_open(
        self,
        *,
        scope: str,
        topic: str,
        rationale: str,
        priority: float,
        target_metric: str,
        evidence: list[str],
    ) -> int:
        with connect() as conn:
            row = conn.execute(
                """SELECT id, priority FROM learning_plans
                   WHERE scope=? AND topic=? AND status='open'
                   ORDER BY id DESC LIMIT 1""",
                (scope, topic),
            ).fetchone()
            if row is not None:
                plan_id = int(row["id"])
                if abs(float(row["priority"]) - priority) >= 0.02:
                    conn.execute(
                        """UPDATE learning_plans
                           SET priority=?, rationale=?, target_metric=?,
                               evidence_json=?, updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (
                            priority, rationale, target_metric,
                            json.dumps(evidence, ensure_ascii=False), plan_id,
                        ),
                    )
                    conn.execute(
                        """INSERT INTO learning_plan_events(
                               scope, plan_id, event, details_json
                           ) VALUES (?, ?, 'refreshed', ?)""",
                        (
                            scope, plan_id,
                            json.dumps({"priority": priority}, ensure_ascii=False),
                        ),
                    )
                    conn.commit()
                return plan_id

            cur = conn.execute(
                """INSERT INTO learning_plans(
                       scope, topic, rationale, priority, target_metric,
                       evidence_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope, topic, rationale, priority, target_metric,
                    json.dumps(evidence, ensure_ascii=False),
                ),
            )
            plan_id = int(cur.lastrowid)
            conn.execute(
                """INSERT INTO learning_plan_events(
                       scope, plan_id, event, details_json
                   ) VALUES (?, ?, 'created', ?)""",
                (
                    scope, plan_id,
                    json.dumps({"priority": priority}, ensure_ascii=False),
                ),
            )
            conn.commit()
            return plan_id

    @staticmethod
    def _decode(row) -> dict:
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        return item
