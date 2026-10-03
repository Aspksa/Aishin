from __future__ import annotations

from dataclasses import asdict, dataclass

from ..db import (
    add_metacognitive_assessment,
    recent_metacognitive_assessments,
)


@dataclass
class MetacognitiveAssessment:
    status: str
    confidence: float
    evidence_score: float
    contradiction_count: int
    missing_data: list[str]
    reasons: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class Metacognition:
    """Deterministic confidence and evidence control before answer generation."""

    HIGH_STAKES_INTENTS = {"verification", "action"}

    def assess(
        self,
        *,
        scope: str,
        intent: str,
        recalled_memories: list[dict],
        semantic_used: bool,
        planner_notices: list[dict],
        sensor_readings: list[dict],
        graph_stats: dict,
        verification_conflicts: int = 0,
        verification_missing: int = 0,
        external_evidence: list[dict] | None = None,
        external_contradictions: int = 0,
    ) -> MetacognitiveAssessment:
        reasons: list[str] = []
        missing: list[str] = []

        memory_count = len(recalled_memories)
        contradiction_count = 0

        confidences: list[float] = []
        retrieval_scores: list[float] = []

        for item in recalled_memories:
            confidences.append(float(item.get("confidence", 0.0)))
            retrieval_scores.append(float(item.get("retrieval_score", 0.0)))

            kind = str(item.get("kind") or "").casefold()
            tags = {
                str(tag).casefold()
                for tag in item.get("tags", [])
            }
            if (
                "contradict" in kind
                or "contradiction" in tags
                or "profile_conflict" in tags
            ):
                contradiction_count += 1

        avg_confidence = (
            sum(confidences) / len(confidences)
            if confidences
            else 0.0
        )
        avg_retrieval = (
            sum(retrieval_scores) / len(retrieval_scores)
            if retrieval_scores
            else 0.0
        )

        evidence_score = 0.0
        if memory_count:
            evidence_score += min(0.35, 0.07 * memory_count)
            evidence_score += 0.30 * avg_confidence
            evidence_score += 0.20 * avg_retrieval
            if semantic_used:
                evidence_score += 0.10
        else:
            if intent in self.HIGH_STAKES_INTENTS:
                missing.append("Нет релевантных воспоминаний в рабочем контексте.")
                reasons.append("Рабочая память не дала прямой опоры.")
            else:
                reasons.append(
                    "Для обычного разговора отсутствие персональной памяти "
                    "само по себе не считается ошибкой данных."
                )

        external_evidence = external_evidence or []
        independent_support_groups: set[str] = set()
        if memory_count:
            independent_support_groups.add("memory")

        if external_evidence:
            weighted_scores: list[tuple[float, float]] = []
            source_groups: dict[str, float] = {}
            derived_types = {
                "verification",
                "trusted_claim",
                "knowledge_graph",
                "messages",
            }
            for item in external_evidence[:16]:
                source_type = str(
                    item.get("source_type")
                    or item.get("source")
                    or "external"
                ).casefold()
                source_ref = str(item.get("source_ref") or "").strip()
                group = str(item.get("source_group") or "").strip()
                if source_type in {"memory", "semantic_memory"}:
                    group = "memory"
                elif not group and item.get("document_id") is not None:
                    group = f"document:{item.get('document_id')}"
                elif not group:
                    group = (
                        f"{source_type}:{source_ref}"
                        if source_ref
                        else source_type
                    )

                try:
                    independence = max(
                        0.0,
                        min(1.0, float(item.get("independence", 1.0))),
                    )
                except (TypeError, ValueError):
                    independence = 1.0

                score = item.get("confidence")
                if score is None:
                    score = item.get("retrieval_score")
                try:
                    normalized = max(
                        0.0,
                        min(1.0, float(score or 0.0)),
                    )
                except (TypeError, ValueError):
                    normalized = 0.0

                weighted_scores.append((normalized, independence))
                source_groups[group] = max(
                    source_groups.get(group, 0.0),
                    independence,
                )

                if (
                    independence >= 0.75
                    and source_type not in derived_types
                ):
                    independent_support_groups.add(group)

            effective_group_mass = sum(source_groups.values())
            evidence_score += min(
                0.22,
                0.08 * effective_group_mass,
            )
            weight_total = sum(weight for _, weight in weighted_scores)
            if weighted_scores and weight_total > 0:
                evidence_score += 0.18 * (
                    sum(
                        score * weight
                        for score, weight in weighted_scores
                    )
                    / weight_total
                )
            reasons.append(
                "Внешних grounded evidence в контексте: "
                f"{len(external_evidence)}; "
                f"source groups: {len(source_groups)}; "
                "независимых первичных опор: "
                f"{len(independent_support_groups)}."
            )

        if external_contradictions:
            contradiction_count += int(external_contradictions)
            reasons.append(
                "Внешних открытых противоречий: "
                f"{int(external_contradictions)}."
            )

        entities = int(graph_stats.get("entities", 0) or 0)
        relations = int(graph_stats.get("relations", 0) or 0)
        if entities > 0:
            evidence_score += min(0.05, entities / 2000)
        if relations > 0:
            evidence_score += min(0.05, relations / 2000)

        warning_notices = [
            item
            for item in planner_notices
            if item.get("severity") == "warning"
        ]
        sensor_attention = [
            item
            for item in sensor_readings
            if item.get("status") not in {"ok"}
        ]

        if warning_notices:
            reasons.append(
                f"Планировщик сообщает предупреждений: {len(warning_notices)}."
            )
        if sensor_attention:
            reasons.append(
                f"Сенсоры требуют внимания: {len(sensor_attention)}."
            )

        if verification_conflicts:
            contradiction_count += int(verification_conflicts)
            reasons.append(
                f"Verification Engine подтвердил противоречий: {verification_conflicts}."
            )

        if verification_missing:
            missing.append(
                f"После перепроверки осталось нерешённых пунктов: {verification_missing}."
            )
            evidence_score -= min(0.20, 0.04 * verification_missing)

        if contradiction_count:
            reasons.append(
                f"Всего обнаружено противоречий: {contradiction_count}."
            )
            evidence_score -= min(0.35, 0.15 * contradiction_count)

        independent_support_shortfall = (
            intent in self.HIGH_STAKES_INTENTS
            and len(independent_support_groups) < 2
        )
        if independent_support_shortfall:
            missing.append(
                "Для проверки или действия недостаточно независимых "
                "первичных доказательных опор."
            )
            evidence_score -= 0.10

        confidence = max(0.0, min(1.0, evidence_score))

        if contradiction_count > 0:
            status = "needs_verification"
        elif independent_support_shortfall:
            status = (
                "cautious"
                if confidence >= 0.25
                else "insufficient_data"
            )
        elif confidence >= 0.72:
            status = "confident"
        elif confidence >= 0.42:
            status = "cautious"
        elif intent == "conversation":
            status = "cautious"
        else:
            status = "insufficient_data"

        if status == "confident":
            reasons.append("Контекст имеет достаточную подтверждённую опору.")
        elif status == "cautious":
            reasons.append("Опора есть, но её недостаточно для уверенного утверждения.")
        elif status == "needs_verification":
            reasons.append("Перед уверенным ответом нужно разрешить противоречия.")
        else:
            reasons.append("Данных недостаточно для уверенного вывода.")

        assessment = MetacognitiveAssessment(
            status=status,
            confidence=round(confidence, 4),
            evidence_score=round(max(0.0, min(1.0, evidence_score)), 4),
            contradiction_count=contradiction_count,
            missing_data=missing,
            reasons=reasons,
        )

        add_metacognitive_assessment(
            scope=scope,
            intent=intent,
            status=assessment.status,
            confidence=assessment.confidence,
            evidence_score=assessment.evidence_score,
            contradiction_count=assessment.contradiction_count,
            missing_data=assessment.missing_data,
            reasons=assessment.reasons,
        )
        return assessment

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        return recent_metacognitive_assessments(scope, limit=limit)

    @staticmethod
    def prompt_block(assessment: MetacognitiveAssessment) -> str:
        lines = [
            "Метакогнитивная проверка Айшин.",
            f"Статус: {assessment.status}.",
            f"Confidence: {assessment.confidence:.2f}.",
            f"Evidence score: {assessment.evidence_score:.2f}.",
            f"Противоречий: {assessment.contradiction_count}.",
        ]

        if assessment.missing_data:
            lines.append("Чего не хватает:")
            for item in assessment.missing_data[:5]:
                lines.append(f"- {item}")

        lines.append(
            "Правило ответа: не повышай уверенность выше оценки ядра. "
            "Если status=needs_verification — явно скажи, что есть противоречия. "
            "Если status=insufficient_data — не выдавай догадку за факт и укажи, "
            "каких данных не хватает. Если status=cautious — формулируй вывод осторожно."
        )
        return "\n".join(lines)
