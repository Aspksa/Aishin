from __future__ import annotations

import json

from ..db import connect


class SafeExperimentManager:
    """Shadow-only strategy comparison.

    Experiments never change the active strategy. A result can only become
    ready_for_review; promotion remains an explicit separate decision.
    """

    MIN_SAMPLES = 5
    MIN_GAIN = 0.05

    def ensure_for_plan(self, plan: dict, *, scope: str) -> int:
        name = f"learning-plan:{plan['topic']}"
        with connect() as conn:
            row = conn.execute(
                """SELECT id FROM safe_experiments
                   WHERE scope=? AND name=? AND status IN ('shadow','ready_for_review')
                   ORDER BY id DESC LIMIT 1""",
                (scope, name),
            ).fetchone()
            if row is not None:
                return int(row["id"])
            cur = conn.execute(
                """INSERT INTO safe_experiments(
                       scope, name, hypothesis, baseline_strategy,
                       candidate_strategy, status, risk_level, required_samples
                   ) VALUES (?, ?, ?, ?, ?, 'shadow', 'low', ?)""",
                (
                    scope,
                    name,
                    plan.get("rationale", ""),
                    "current_runtime_policy",
                    f"candidate_improvement:{plan['topic']}",
                    self.MIN_SAMPLES,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def observe(
        self,
        *,
        scope: str,
        request_id: str,
        reflection: dict,
        open_plans: list[dict],
    ) -> list[dict]:
        observed: list[dict] = []
        for plan in open_plans[:3]:
            experiment_id = self.ensure_for_plan(plan, scope=scope)
            baseline = float(reflection.get("quality_score", 0.0))
            candidate = self._shadow_candidate_score(
                baseline=baseline,
                weak_spots=reflection.get("weak_spots") or [],
                topic=str(plan.get("topic") or ""),
            )
            self._record_observation(
                experiment_id=experiment_id,
                scope=scope,
                request_id=request_id,
                baseline=baseline,
                candidate=candidate,
                details={
                    "shadow_only": True,
                    "plan_id": plan.get("id"),
                    "weak_spots": reflection.get("weak_spots") or [],
                },
            )
            observed.append(self._recalculate(experiment_id, scope=scope))
        return observed

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM safe_experiments
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [self._decode(row) for row in rows]

    def observations(
        self, experiment_id: int, *, scope: str, limit: int = 50
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM experiment_observations
                   WHERE experiment_id=? AND scope=?
                   ORDER BY id DESC LIMIT ?""",
                (experiment_id, scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    @classmethod
    def _shadow_candidate_score(
        cls, *, baseline: float, weak_spots: list[str], topic: str
    ) -> float:
        relevant = {
            "reduce_user_corrections": "user_correction",
            "improve_evidence_confidence": "low_confidence",
            "reduce_reasoning_latency": "latency",
            "improve_provider_resilience": "provider_availability",
            "raise_response_quality": "decision_basis",
        }.get(topic)
        gain = 0.02
        if relevant and relevant in weak_spots:
            gain = 0.07
        return round(max(0.0, min(1.0, baseline + gain)), 4)

    def _record_observation(
        self,
        *,
        experiment_id: int,
        scope: str,
        request_id: str,
        baseline: float,
        candidate: float,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO experiment_observations(
                       experiment_id, scope, request_id,
                       baseline_score, candidate_score, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    experiment_id, scope, request_id, baseline, candidate,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()

    def _recalculate(self, experiment_id: int, *, scope: str) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT baseline_score, candidate_score
                   FROM experiment_observations
                   WHERE experiment_id=? AND scope=?""",
                (experiment_id, scope),
            ).fetchall()
            count = len(rows)
            baseline = (
                sum(float(x["baseline_score"]) for x in rows) / count
                if count else 0.0
            )
            candidate = (
                sum(float(x["candidate_score"]) for x in rows) / count
                if count else 0.0
            )
            gain = candidate - baseline
            if count < self.MIN_SAMPLES:
                status = "shadow"
                decision = "insufficient_evidence"
            elif gain >= self.MIN_GAIN:
                status = "ready_for_review"
                decision = "candidate_promising"
            else:
                status = "shadow"
                decision = "keep_baseline"
            conn.execute(
                """UPDATE safe_experiments
                   SET observed_samples=?, baseline_score=?,
                       candidate_score=?, status=?, decision=?,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (
                    count, round(baseline, 4), round(candidate, 4),
                    status, decision, experiment_id, scope,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM safe_experiments WHERE id=? AND scope=?",
                (experiment_id, scope),
            ).fetchone()
        return self._decode(row)

    @staticmethod
    def _decode(row) -> dict:
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
        item["promotion_allowed"] = False
        item["shadow_only"] = True
        return item
