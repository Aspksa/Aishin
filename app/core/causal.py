from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..db import connect


@dataclass
class CausalClaim:
    cause: str
    effect: str
    relation: str
    confidence: float
    evidence: list[str]
    caveat: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CausalAssessment:
    claims: list[CausalClaim]
    unresolved: list[str]
    assessment_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "claims": [item.to_dict() for item in self.claims],
            "unresolved": self.unresolved,
            "assessment_id": self.assessment_id,
        }


class CausalReasoning:
    """Conservative causal classifier over already-grounded evidence."""

    CAUSAL_MARKERS = (
        "из-за",
        "вызвал",
        "вызвала",
        "привел",
        "привела",
        "привело",
        "причина",
        "следствие",
        "caused_by",
        "resulted_in",
    )
    TEMPORAL_MARKERS = ("после", "до", "затем", "потом", "раньше")
    CONTRIBUTORY_MARKERS = ("повлиял", "повлияло", "способств", "усилил", "усилило")

    def assess(
        self,
        query: str,
        *,
        scope: str,
        evidence: list[dict],
        contradictions: list[dict],
    ) -> CausalAssessment:
        claims: list[CausalClaim] = []
        unresolved: list[str] = []

        evidence_texts = self._evidence_texts(evidence)
        combined = " ".join([query, *evidence_texts]).casefold()

        cause, effect = self._extract_explicit_pair(query)
        if cause and effect:
            relation = self._classify_relation(combined)
            support = [
                text
                for text in evidence_texts
                if self._supports_pair(text, cause, effect)
            ][:6]
            confidence = self._confidence(
                relation=relation,
                support_count=len(support),
                contradiction_count=len(contradictions),
            )
            caveat = self._caveat(
                relation=relation,
                support_count=len(support),
                contradictions=len(contradictions),
            )
            claims.append(
                CausalClaim(
                    cause=cause,
                    effect=effect,
                    relation=relation,
                    confidence=confidence,
                    evidence=support,
                    caveat=caveat,
                )
            )
        elif any(marker in combined for marker in self.CAUSAL_MARKERS):
            unresolved.append(
                "В данных есть причинная формулировка, но не удалось надёжно "
                "выделить пару причина → следствие."
            )

        assessment = CausalAssessment(
            claims=claims,
            unresolved=unresolved,
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
                """SELECT * FROM causal_assessments
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["claims"] = json.loads(item.pop("claims_json") or "[]")
            item["unresolved"] = json.loads(item.pop("unresolved_json") or "[]")
            result.append(item)
        return result

    @staticmethod
    def prompt_block(assessment: CausalAssessment) -> str:
        if not assessment.claims and not assessment.unresolved:
            return (
                "Causal Reasoning: подтверждённых причинных утверждений "
                "в текущем контексте не выделено."
            )

        lines = [
            "Causal Reasoning.",
            "Не подменяй корреляцию причинностью.",
        ]
        for claim in assessment.claims[:6]:
            lines.append(
                f"- {claim.cause} -> {claim.effect}: "
                f"relation={claim.relation}, confidence={claim.confidence:.2f}; "
                f"{claim.caveat}"
            )
        for item in assessment.unresolved[:6]:
            lines.append(f"- unresolved: {item}")
        return "\n".join(lines)

    @classmethod
    def _classify_relation(cls, text: str) -> str:
        if any(marker in text for marker in cls.CAUSAL_MARKERS):
            return "causal_candidate"
        if any(marker in text for marker in cls.CONTRIBUTORY_MARKERS):
            return "contributory"
        if any(marker in text for marker in cls.TEMPORAL_MARKERS):
            return "temporal"
        return "observed"

    @staticmethod
    def _extract_explicit_pair(query: str) -> tuple[str | None, str | None]:
        patterns = (
            r"(.{3,120}?)\s+(?:из-за|вызвал(?:а|о)?|привел(?:а|о)? к)\s+(.{3,120})",
            r"причина\s+(.{3,120}?)\s*(?:—|:|->)\s*(.{3,120})",
        )
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                cause = match.group(1).strip(" .,:;—-")
                effect = match.group(2).strip(" .,:;—-")
                if cause and effect:
                    return cause[:160], effect[:160]
        return None, None

    @staticmethod
    def _supports_pair(text: str, cause: str, effect: str) -> bool:
        hay = text.casefold()
        cause_tokens = {
            token for token in re.findall(r"[\wА-Яа-яЁё-]+", cause.casefold())
            if len(token) >= 4
        }
        effect_tokens = {
            token for token in re.findall(r"[\wА-Яа-яЁё-]+", effect.casefold())
            if len(token) >= 4
        }
        return (
            bool(cause_tokens)
            and bool(effect_tokens)
            and any(token in hay for token in cause_tokens)
            and any(token in hay for token in effect_tokens)
        )

    @staticmethod
    def _confidence(
        *,
        relation: str,
        support_count: int,
        contradiction_count: int,
    ) -> float:
        base = {
            "observed": 0.25,
            "temporal": 0.35,
            "contributory": 0.45,
            "causal_candidate": 0.50,
        }.get(relation, 0.25)
        base += min(0.30, support_count * 0.10)
        base -= min(0.35, contradiction_count * 0.12)
        return round(max(0.0, min(0.85, base)), 4)

    @staticmethod
    def _caveat(
        *,
        relation: str,
        support_count: int,
        contradictions: int,
    ) -> str:
        if contradictions:
            return "Есть противоречия; причинный вывод нельзя считать подтверждённым."
        if support_count == 0:
            return "Нет независимой evidence-опоры; это только причинная гипотеза."
        if relation == "temporal":
            return "Последовательность во времени сама по себе не доказывает причинность."
        if relation == "causal_candidate":
            return "Есть причинная формулировка и опора, но это ещё не доказанная причинность."
        return "Связь наблюдается, причинность не установлена."

    @staticmethod
    def _record(
        *,
        scope: str,
        query: str,
        assessment: CausalAssessment,
    ) -> int:
        with connect() as conn:
            cursor = conn.execute(
                """INSERT INTO causal_assessments(
                       scope, query, claims_json, unresolved_json
                   ) VALUES (?, ?, ?, ?)""",
                (
                    scope,
                    query,
                    json.dumps(
                        [item.to_dict() for item in assessment.claims],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        assessment.unresolved,
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    @staticmethod
    def _evidence_texts(evidence: list[dict]) -> list[str]:
        result: list[str] = []
        for item in evidence:
            for key in ("content", "finding", "message", "evidence"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    result.append(value.strip()[:800])
        return result
