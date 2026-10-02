from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..db import connect


@dataclass
class DecisionQuality:
    overall: float
    components: dict[str, float]
    warnings: list[str]
    recommendation: str
    score_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class DecisionQualityScorer:
    """Score evidence quality of a decision, not whether the decision is objectively right."""

    def score(
        self,
        query: str,
        *,
        scope: str,
        mode: str,
        logic_confidence: float,
        evidence: list[dict],
        contradictions: list[dict],
        unresolved: list[str],
        verification: dict | None,
        hypotheses: dict | None,
        counterfactual: dict | None,
    ) -> DecisionQuality:
        evidence_quality = self._evidence_quality(evidence)
        verification_quality = self._verification_quality(verification)
        uncertainty_control = max(
            0.0,
            min(1.0, 1.0 - 0.12 * len(unresolved)),
        )
        contradiction_control = max(
            0.0,
            min(1.0, 1.0 - 0.18 * len(contradictions)),
        )
        alternative_coverage = self._alternative_coverage(
            hypotheses=hypotheses,
            counterfactual=counterfactual,
        )
        reversibility = self._reversibility(counterfactual)

        components = {
            "logic_confidence": round(max(0.0, min(1.0, logic_confidence)), 4),
            "evidence_quality": evidence_quality,
            "verification_quality": verification_quality,
            "uncertainty_control": round(uncertainty_control, 4),
            "contradiction_control": round(contradiction_control, 4),
            "alternative_coverage": alternative_coverage,
            "reversibility": reversibility,
        }

        weights = {
            "logic_confidence": 0.18,
            "evidence_quality": 0.20,
            "verification_quality": 0.16,
            "uncertainty_control": 0.14,
            "contradiction_control": 0.14,
            "alternative_coverage": 0.10,
            "reversibility": 0.08,
        }
        overall = round(
            sum(components[key] * weights[key] for key in weights),
            4,
        )

        warnings: list[str] = []
        if evidence_quality < 0.45:
            warnings.append("Слабая evidence-опора.")
        if contradiction_control < 0.65:
            warnings.append("Нерешённые противоречия ухудшают качество решения.")
        if uncertainty_control < 0.65:
            warnings.append("Слишком много нерешённых пунктов.")
        if alternative_coverage < 0.35 and mode in {"DEEP", "PLAN", "VERIFY", "DIAGNOSE"}:
            warnings.append("Альтернативы рассмотрены недостаточно.")
        if reversibility < 0.5:
            warnings.append("Решение трудно откатить; нужен backup/approval.")

        recommendation = self._recommendation(
            overall=overall,
            warnings=warnings,
        )

        result = DecisionQuality(
            overall=overall,
            components=components,
            warnings=warnings,
            recommendation=recommendation,
        )
        result.score_id = self._record(
            scope=scope,
            query=query,
            mode=mode,
            result=result,
        )
        return result

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM decision_quality_scores
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["components"] = json.loads(item.pop("components_json") or "{}")
            item["warnings"] = json.loads(item.pop("warnings_json") or "[]")
            result.append(item)
        return result

    @staticmethod
    def prompt_block(result: DecisionQuality) -> str:
        lines = [
            "Decision Quality Scoring.",
            f"overall={result.overall:.2f}.",
            f"recommendation={result.recommendation}.",
            "Это оценка качества основания решения, а не гарантия правильности.",
        ]
        for warning in result.warnings[:5]:
            lines.append(f"- warning: {warning}")
        return "\n".join(lines)

    @staticmethod
    def _evidence_quality(evidence: list[dict]) -> float:
        if not evidence:
            return 0.0

        scores: list[float] = []
        for item in evidence[:16]:
            confidence = item.get("confidence")
            retrieval = item.get("retrieval_score")
            if confidence is not None:
                scores.append(max(0.0, min(1.0, float(confidence))))
            elif retrieval is not None:
                scores.append(max(0.0, min(1.0, float(retrieval))))
            else:
                scores.append(0.55)

        return round(sum(scores) / len(scores), 4)

    @staticmethod
    def _verification_quality(verification: dict | None) -> float:
        if not verification or not verification.get("ran"):
            return 0.45

        checks = verification.get("checks", []) or []
        unresolved = verification.get("unresolved", []) or []
        if not checks:
            return 0.35

        good = sum(
            1
            for item in checks
            if str(item.get("status") or "") in {"ok", "success"}
        )
        base = good / max(1, len(checks))
        penalty = min(0.50, len(unresolved) * 0.08)
        return round(max(0.0, min(1.0, base - penalty)), 4)

    @staticmethod
    def _alternative_coverage(
        *,
        hypotheses: dict | None,
        counterfactual: dict | None,
    ) -> float:
        hypothesis_count = len((hypotheses or {}).get("hypotheses", []) or [])
        scenario_count = len((counterfactual or {}).get("scenarios", []) or [])
        return round(
            min(1.0, hypothesis_count * 0.16 + scenario_count * 0.18),
            4,
        )

    @staticmethod
    def _reversibility(counterfactual: dict | None) -> float:
        scenarios = (counterfactual or {}).get("scenarios", []) or []
        if not scenarios:
            return 0.6

        map_score = {"high": 1.0, "medium": 0.6, "low": 0.2}
        values = [
            map_score.get(str(item.get("reversibility") or ""), 0.5)
            for item in scenarios
        ]
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _recommendation(
        *,
        overall: float,
        warnings: list[str],
    ) -> str:
        if overall >= 0.78 and not warnings:
            return "evidence_sufficient_for_considered_action"
        if overall >= 0.58:
            return "proceed_cautiously_or_verify_remaining_risks"
        return "do_not_treat_as_ready_for_action"

    @staticmethod
    def _record(
        *,
        scope: str,
        query: str,
        mode: str,
        result: DecisionQuality,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO decision_quality_scores(
                       scope, query, mode, overall,
                       components_json, warnings_json, recommendation
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    query[:1200],
                    mode,
                    result.overall,
                    json.dumps(result.components, ensure_ascii=False),
                    json.dumps(result.warnings, ensure_ascii=False),
                    result.recommendation,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
