from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..db import connect


@dataclass
class ReflectionResult:
    request_id: str
    quality_score: float
    confidence_score: float
    error_count: int
    correction_signal: bool
    weak_spots: list[str]
    metrics: dict
    reflection_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class SelfReflectionMetrics:
    """Deterministic post-response quality reflection.

    This layer measures observable runtime signals. It does not ask the model to
    grade itself and it never treats an assistant answer as proof of success.
    """

    CORRECTION_MARKERS = (
        "нет,", "не так", "ошибка", "исправ", "передел", "неправ",
        "ты ошиб", "снова", "опять",
    )

    def assess(
        self,
        *,
        request_id: str,
        scope: str,
        mode: str,
        user_message: str,
        provider_runtime: dict,
        metacognition: dict,
        verification: dict,
        decision_quality: dict,
        performance: dict,
        response_grounding: dict | None = None,
    ) -> ReflectionResult:
        weak: list[str] = []
        errors = 0

        provider_ok = bool(provider_runtime.get("available"))
        if not provider_ok:
            errors += 1
            weak.append("provider_availability")

        meta_conf = float(metacognition.get("confidence", 0.0) or 0.0)
        if meta_conf < 0.55:
            weak.append("low_confidence")

        unresolved = 0
        if isinstance(verification, dict):
            unresolved = len(verification.get("unresolved") or [])
            conflicts = len(
                (verification.get("consistency") or {}).get("conflicts") or []
            )
        else:
            conflicts = 0
        if unresolved:
            weak.append("unresolved_evidence")
        if conflicts:
            weak.append("contradictions")

        dq = float(decision_quality.get("overall", 0.0) or 0.0)
        if dq and dq < 0.55:
            weak.append("decision_basis")

        grounding = response_grounding or {}
        grounding_applicable = bool(grounding.get("applicable"))
        grounding_score = grounding.get("overall")
        grounding_value = (
            float(grounding_score)
            if grounding_applicable and grounding_score is not None
            else None
        )
        unsupported_claims = int(
            grounding.get("claims_unsupported") or 0
        )
        if grounding_value is not None and grounding_value < 0.55:
            weak.append("response_grounding")
        if grounding_applicable and unsupported_claims > 0:
            weak.append("unsupported_response_claims")

        budget_status = str(performance.get("budget_status") or "")
        if budget_status == "over_budget":
            weak.append("latency")
        total_ms = int(performance.get("total_ms", 0) or 0)

        correction = any(
            marker in user_message.casefold()
            for marker in self.CORRECTION_MARKERS
        )
        if correction:
            weak.append("user_correction")

        penalties = 0.0
        penalties += 0.28 if not provider_ok else 0.0
        penalties += max(0.0, 0.60 - meta_conf) * 0.35
        penalties += min(0.18, unresolved * 0.04)
        penalties += min(0.18, conflicts * 0.06)
        penalties += 0.12 if correction else 0.0
        penalties += 0.08 if budget_status == "over_budget" else 0.0
        if dq:
            penalties += max(0.0, 0.60 - dq) * 0.25
        if grounding_value is not None:
            penalties += max(0.0, 0.65 - grounding_value) * 0.30
            penalties += min(0.10, unsupported_claims * 0.02)

        quality = round(max(0.0, min(1.0, 1.0 - penalties)), 4)
        confidence = round(
            max(0.0, min(1.0, (meta_conf * 0.7) + (quality * 0.3))),
            4,
        )
        weak = list(dict.fromkeys(weak))

        metrics = {
            "provider_available": provider_ok,
            "metacognition_confidence": meta_conf,
            "decision_quality": dq,
            "response_grounding": grounding_value,
            "grounding_applicable": grounding_applicable,
            "unsupported_response_claims": unsupported_claims,
            "unresolved_count": unresolved,
            "contradiction_count": conflicts,
            "latency_ms": total_ms,
            "budget_status": budget_status,
        }
        result = ReflectionResult(
            request_id=request_id,
            quality_score=quality,
            confidence_score=confidence,
            error_count=errors,
            correction_signal=correction,
            weak_spots=weak,
            metrics=metrics,
        )
        result.reflection_id = self._record(
            scope=scope,
            mode=mode,
            result=result,
        )
        return result

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM self_reflection_runs
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["weak_spots"] = json.loads(item.pop("weak_spots_json") or "[]")
            item["metrics"] = json.loads(item.pop("metrics_json") or "{}")
            item["correction_signal"] = bool(item["correction_signal"])
            result.append(item)
        return result

    def summary(self, *, scope: str, limit: int = 50) -> dict:
        rows = self.recent(scope=scope, limit=limit)
        if not rows:
            return {
                "samples": 0,
                "average_quality": None,
                "average_confidence": None,
                "corrections": 0,
                "errors": 0,
                "weak_spots": {},
            }
        weak: dict[str, int] = {}
        for row in rows:
            for name in row["weak_spots"]:
                weak[name] = weak.get(name, 0) + 1
        return {
            "samples": len(rows),
            "average_quality": round(
                sum(float(x["quality_score"]) for x in rows) / len(rows), 4
            ),
            "average_confidence": round(
                sum(float(x["confidence_score"]) for x in rows) / len(rows), 4
            ),
            "corrections": sum(bool(x["correction_signal"]) for x in rows),
            "errors": sum(int(x["error_count"]) for x in rows),
            "weak_spots": dict(
                sorted(weak.items(), key=lambda x: (-x[1], x[0]))
            ),
        }

    @staticmethod
    def _record(*, scope: str, mode: str, result: ReflectionResult) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT OR REPLACE INTO self_reflection_runs(
                       request_id, scope, mode, quality_score,
                       confidence_score, error_count, correction_signal,
                       weak_spots_json, metrics_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.request_id,
                    scope,
                    mode,
                    result.quality_score,
                    result.confidence_score,
                    result.error_count,
                    int(result.correction_signal),
                    json.dumps(result.weak_spots, ensure_ascii=False),
                    json.dumps(result.metrics, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
