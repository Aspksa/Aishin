from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..db import connect


@dataclass
class CounterfactualScenario:
    action: str
    expected_effects: list[str]
    risks: list[str]
    reversibility: str
    confidence: float
    evidence: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CounterfactualAssessment:
    mode: str
    scenarios: list[CounterfactualScenario]
    assumptions: list[str]
    unresolved: list[str]
    assessment_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "scenarios": [item.to_dict() for item in self.scenarios],
            "assumptions": self.assumptions,
            "unresolved": self.unresolved,
            "assessment_id": self.assessment_id,
        }


class CounterfactualReasoning:
    """Conservative what-if analysis over already-grounded evidence."""

    ACTIVE_MODES = {"DEEP", "PLAN", "VERIFY", "DIAGNOSE"}

    def assess(
        self,
        query: str,
        *,
        scope: str,
        mode: str,
        alternatives: list[str],
        hypotheses: dict | None,
        causal: dict | None,
        evidence: list[dict],
        contradictions: list[dict],
    ) -> CounterfactualAssessment:
        if mode not in self.ACTIVE_MODES:
            assessment = CounterfactualAssessment(
                mode=mode,
                scenarios=[],
                assumptions=[],
                unresolved=[],
            )
            assessment.assessment_id = self._record(
                scope=scope,
                query=query,
                assessment=assessment,
            )
            return assessment

        evidence_texts = self._evidence_texts(evidence)
        candidate_actions = self._candidate_actions(
            query=query,
            alternatives=alternatives,
            hypotheses=hypotheses,
        )

        scenarios: list[CounterfactualScenario] = []
        unresolved: list[str] = []

        for action in candidate_actions[:4]:
            support = [
                text
                for text in evidence_texts
                if self._shares_signal(action, text)
            ][:5]

            effects = self._effects_from_causal(
                action,
                causal=causal,
            )
            if not effects and support:
                effects = [
                    "Может изменить состояние, связанное с подтверждённым контекстом."
                ]

            if not effects:
                effects = [
                    "Последствие не подтверждено доступными evidence; это только сценарий."
                ]
                unresolved.append(
                    f"Для варианта «{action}» недостаточно evidence для оценки эффекта."
                )

            risks = self._risks_for(
                action,
                contradictions=contradictions,
                support_count=len(support),
            )
            reversibility = self._reversibility(action)
            confidence = self._confidence(
                support_count=len(support),
                contradiction_count=len(contradictions),
                has_causal=bool(effects and "только сценарий" not in effects[0]),
            )

            scenarios.append(
                CounterfactualScenario(
                    action=action,
                    expected_effects=effects[:5],
                    risks=risks,
                    reversibility=reversibility,
                    confidence=confidence,
                    evidence=support,
                )
            )

        assumptions = [
            "Сценарии описывают возможные последствия по текущему контексту, а не гарантированный прогноз.",
            "Если исходные данные изменятся, оценку нужно пересчитать.",
        ]
        if contradictions:
            assumptions.append(
                "В evidence есть противоречия, поэтому причинные и прогнозные выводы ограничены."
            )

        assessment = CounterfactualAssessment(
            mode=mode,
            scenarios=scenarios,
            assumptions=assumptions,
            unresolved=self._unique(unresolved),
        )
        assessment.assessment_id = self._record(
            scope=scope,
            query=query,
            assessment=assessment,
        )
        return assessment

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM counterfactual_assessments
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["scenarios"] = json.loads(item.pop("scenarios_json") or "[]")
            item["assumptions"] = json.loads(item.pop("assumptions_json") or "[]")
            item["unresolved"] = json.loads(item.pop("unresolved_json") or "[]")
            result.append(item)
        return result

    @staticmethod
    def prompt_block(assessment: CounterfactualAssessment) -> str:
        if not assessment.scenarios:
            return "Counterfactual Reasoning: what-if анализ для этого режима не требовался."

        lines = [
            "Counterfactual Reasoning.",
            "Это условные сценарии, а не гарантированные прогнозы.",
        ]
        for item in assessment.scenarios[:4]:
            lines.append(
                f"- Если: {item.action}; confidence={item.confidence:.2f}; "
                f"reversibility={item.reversibility}; "
                f"effects={'; '.join(item.expected_effects[:3])}"
            )
            if item.risks:
                lines.append(f"  risks={'; '.join(item.risks[:3])}")

        for item in assessment.unresolved[:5]:
            lines.append(f"- unresolved: {item}")

        return "\n".join(lines)

    @staticmethod
    def _candidate_actions(
        *,
        query: str,
        alternatives: list[str],
        hypotheses: dict | None,
    ) -> list[str]:
        result: list[str] = []

        for item in alternatives:
            text = str(item).strip()
            if text and text not in result:
                result.append(text)

        if hypotheses:
            selected = hypotheses.get("selected_test") or {}
            title = str(selected.get("title") or "").strip()
            if title and title not in result:
                result.append(title)

        query_text = query.strip()
        if query_text and not result:
            result.append(f"Выполнить действие из запроса: {query_text[:220]}")

        return result[:6]

    @staticmethod
    def _effects_from_causal(
        action: str,
        *,
        causal: dict | None,
    ) -> list[str]:
        if not causal:
            return []

        effects: list[str] = []
        action_fold = action.casefold()

        for claim in causal.get("claims", [])[:6]:
            cause = str(claim.get("cause") or "").strip()
            effect = str(claim.get("effect") or "").strip()
            relation = str(claim.get("relation") or "")
            if not cause or not effect:
                continue
            if any(
                token in action_fold
                for token in cause.casefold().split()
                if len(token) >= 4
            ):
                effects.append(
                    f"Возможный эффект: {effect} "
                    f"(relation={relation}, confidence={float(claim.get('confidence', 0.0)):.2f})."
                )

        return effects

    @staticmethod
    def _risks_for(
        action: str,
        *,
        contradictions: list[dict],
        support_count: int,
    ) -> list[str]:
        risks: list[str] = []

        text = action.casefold()
        if any(marker in text for marker in ("удал", "перезапис", "замен", "update", "обнов")):
            risks.append("Изменение может быть частично необратимым без backup/rollback.")
        if any(marker in text for marker in ("внеш", "cloud", "api", "отправ")):
            risks.append("Есть внешняя зависимость или сетевой фактор.")
        if contradictions:
            risks.append("Есть нерешённые противоречия в evidence.")
        if support_count == 0:
            risks.append("Нет прямой evidence-опоры для ожидаемого эффекта.")

        return risks[:4]

    @staticmethod
    def _reversibility(action: str) -> str:
        text = action.casefold()
        if any(marker in text for marker in ("удал", "delete", "перезапис")):
            return "low"
        if any(marker in text for marker in ("измен", "обнов", "update", "запис")):
            return "medium"
        return "high"

    @staticmethod
    def _confidence(
        *,
        support_count: int,
        contradiction_count: int,
        has_causal: bool,
    ) -> float:
        score = 0.25
        score += min(0.35, support_count * 0.09)
        if has_causal:
            score += 0.15
        score -= min(0.35, contradiction_count * 0.10)
        return round(max(0.05, min(0.85, score)), 4)

    @staticmethod
    def _evidence_texts(evidence: list[dict]) -> list[str]:
        result: list[str] = []
        for item in evidence:
            for key in ("content", "finding", "message", "evidence"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    result.append(value.strip()[:800])
        return result

    @staticmethod
    def _shares_signal(left: str, right: str) -> bool:
        l_tokens = {
            token for token in left.casefold().split()
            if len(token) >= 5
        }
        r = right.casefold()
        return any(token in r for token in l_tokens)

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _record(
        *,
        scope: str,
        query: str,
        assessment: CounterfactualAssessment,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO counterfactual_assessments(
                       scope, query, mode, scenarios_json,
                       assumptions_json, unresolved_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    query[:1200],
                    assessment.mode,
                    json.dumps(
                        [item.to_dict() for item in assessment.scenarios],
                        ensure_ascii=False,
                    ),
                    json.dumps(assessment.assumptions, ensure_ascii=False),
                    json.dumps(assessment.unresolved, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
