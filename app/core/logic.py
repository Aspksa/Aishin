from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from ..db import connect


MODES = {"FAST", "DEEP", "VERIFY", "PLAN", "DIAGNOSE"}


@dataclass
class LogicPlan:
    mode: str
    complexity: float
    rule_hits: list[dict]
    verification_required: bool
    selected_strategy: str
    alternatives: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LogicTrace:
    mode: str
    complexity: float
    confidence: float
    selected_strategy: str
    rule_hits: list[dict]
    evidence: list[dict]
    contradictions: list[dict]
    alternatives: list[str]
    unresolved: list[str]
    verification_required: bool
    journal_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class LogicEngine:
    """Deterministic reasoning controller for Aishin.

    It records a technical decision trace, not private chain-of-thought.
    """

    ERROR_MARKERS = (
        "ошибка",
        "не работает",
        "не запуска",
        "сломал",
        "сломалось",
        "почему не",
        "проблем",
        "диагност",
        "исправ",
    )
    PLAN_MARKERS = (
        "план",
        "этап",
        "дальше",
        "что делать",
        "сделай",
        "реализ",
        "задач",
        "цель",
        "по шаг",
    )
    COMPLEX_MARKERS = (
        "сравни",
        "вариант",
        "противореч",
        "зависим",
        "причин",
        "последств",
        "архитект",
        "проанализ",
        "подроб",
        "комплекс",
    )

    def prepare(
        self,
        query: str,
        *,
        intent: str,
        metacognition_status: str,
        metacognition_confidence: float,
        contradiction_count: int,
        planner_notices: list[dict],
    ) -> LogicPlan:
        text = query.casefold()
        rule_hits: list[dict] = []

        complexity = self._complexity_score(
            query,
            intent=intent,
            contradiction_count=contradiction_count,
            planner_notices=planner_notices,
        )

        mode = "FAST"
        strategy = "Короткая линейная обработка подтверждённого контекста."
        alternatives = [
            "Ответить по текущему подтверждённому контексту.",
        ]

        if any(marker in text for marker in self.ERROR_MARKERS):
            mode = "DIAGNOSE"
            strategy = (
                "Собрать симптомы, проверить вероятные причины и отделить "
                "наблюдаемые факты от гипотез."
            )
            alternatives = [
                "Проверить состояние и симптомы.",
                "Сопоставить с памятью и событиями.",
                "Локализовать наиболее подтверждённую причину.",
            ]
            rule_hits.append(
                self._rule(
                    "logic.diagnose.error_signal",
                    "В запросе обнаружен сигнал диагностики/ошибки.",
                )
            )

        elif intent == "verification" or metacognition_status in {
            "needs_verification",
            "insufficient_data",
        }:
            mode = "VERIFY"
            strategy = (
                "Расширить доказательную базу и перепроверить противоречия "
                "до вывода."
            )
            alternatives = [
                "Перепроверить память и semantic recall.",
                "Сверить Knowledge Graph и сенсоры.",
                "Сохранить неопределённость, если конфликт не разрешён.",
            ]
            rule_hits.append(
                self._rule(
                    "logic.verify.low_confidence_or_verification_intent",
                    "Требуется проверка или метакогнитивная опора недостаточна.",
                )
            )

        elif intent == "action" and any(
            marker in text for marker in self.PLAN_MARKERS
        ):
            mode = "PLAN"
            strategy = (
                "Разложить цель на проверяемые шаги, зависимости и точки "
                "контроля до действия."
            )
            alternatives = [
                "Определить цель и критерий завершения.",
                "Выделить зависимости и порядок.",
                "Сформировать следующий безопасный шаг.",
            ]
            rule_hits.append(
                self._rule(
                    "logic.plan.action_with_plan_signal",
                    "Запрос действия содержит признаки планирования.",
                )
            )

        elif complexity >= 0.58:
            mode = "DEEP"
            strategy = (
                "Рассмотреть несколько технических вариантов, сравнить их "
                "по evidence и рискам, затем выбрать обоснованный путь."
            )
            alternatives = [
                "Сохранить текущий подход.",
                "Проверить альтернативную интерпретацию.",
                "Выбрать вариант с лучшей доказательной опорой и меньшим риском.",
            ]
            rule_hits.append(
                self._rule(
                    "logic.deep.complexity_threshold",
                    f"Сложность запроса {complexity:.2f} превышает порог.",
                )
            )

        else:
            rule_hits.append(
                self._rule(
                    "logic.fast.default",
                    "Нет признаков, требующих тяжёлого режима.",
                )
            )

        if contradiction_count > 0:
            rule_hits.append(
                self._rule(
                    "logic.conflict.detected",
                    f"Обнаружено противоречий: {contradiction_count}.",
                )
            )
            if mode not in {"DIAGNOSE", "VERIFY"}:
                mode = "VERIFY"
                strategy = (
                    "Сначала разрешить или явно сохранить противоречия, "
                    "затем формировать вывод."
                )

        if metacognition_confidence < 0.42 and mode == "FAST":
            mode = "VERIFY"
            strategy = (
                "Недостаточная доказательная опора: расширить проверку "
                "до финального ответа."
            )
            rule_hits.append(
                self._rule(
                    "logic.verify.low_confidence_threshold",
                    f"Confidence {metacognition_confidence:.2f} ниже 0.42.",
                )
            )

        verification_required = mode in {"VERIFY", "DIAGNOSE"}

        return LogicPlan(
            mode=mode,
            complexity=complexity,
            rule_hits=rule_hits,
            verification_required=verification_required,
            selected_strategy=strategy,
            alternatives=alternatives,
        )

    def finalize(
        self,
        *,
        scope: str,
        query: str,
        intent: str,
        plan: LogicPlan,
        memories: list[dict],
        final_metacognition: dict,
        verification: dict | None,
        graph_stats: dict,
        planner_notices: list[dict],
        additional_evidence: list[dict] | None = None,
        additional_contradictions: list[dict] | None = None,
    ) -> LogicTrace:
        evidence = self._build_evidence(
            memories=memories,
            verification=verification,
            graph_stats=graph_stats,
            planner_notices=planner_notices,
            additional_evidence=additional_evidence or [],
        )
        contradictions = self._collect_contradictions(
            memories=memories,
            verification=verification,
            additional_contradictions=additional_contradictions or [],
        )

        unresolved: list[str] = []
        for item in contradictions:
            if item.get("resolution") == "unresolved":
                unresolved.append(str(item.get("summary") or "Противоречие"))

        if verification:
            for item in verification.get("unresolved", [])[:8]:
                text = str(item).strip()
                if text and text not in unresolved:
                    unresolved.append(text)

        status = str(final_metacognition.get("status") or "")
        if status == "insufficient_data":
            unresolved.append("Недостаточно доказательной опоры для уверенного вывода.")
        elif status == "needs_verification":
            unresolved.append("После проверки остаются противоречия.")

        trace = LogicTrace(
            mode=plan.mode,
            complexity=plan.complexity,
            confidence=float(final_metacognition.get("confidence", 0.0)),
            selected_strategy=plan.selected_strategy,
            rule_hits=plan.rule_hits,
            evidence=evidence,
            contradictions=contradictions,
            alternatives=plan.alternatives,
            unresolved=self._unique(unresolved),
            verification_required=plan.verification_required,
        )

        trace.journal_id = self._record(
            scope=scope,
            query=query,
            intent=intent,
            trace=trace,
        )
        self._record_rule_hits(
            scope=scope,
            mode=trace.mode,
            rule_hits=trace.rule_hits,
        )
        return trace

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM logic_decisions
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            for field_name in (
                "evidence_json",
                "contradictions_json",
                "alternatives_json",
                "unresolved_json",
                "rule_hits_json",
            ):
                key = field_name.removesuffix("_json")
                item[key] = json.loads(item.pop(field_name) or "[]")
            item["verification_required"] = bool(item["verification_required"])
            result.append(item)
        return result

    @staticmethod
    def prompt_block(trace: LogicTrace) -> str:
        lines = [
            "Aishin Logic Engine v1.",
            f"Режим мышления: {trace.mode}.",
            f"Сложность: {trace.complexity:.2f}.",
            f"Технический confidence: {trace.confidence:.2f}.",
            f"Стратегия: {trace.selected_strategy}",
            "Используй только доказательную опору из контекста и явно "
            "отделяй факты от гипотез.",
        ]

        if trace.contradictions:
            lines.append("Противоречия:")
            for item in trace.contradictions[:6]:
                lines.append(
                    f"- {item.get('summary')} "
                    f"(resolution={item.get('resolution')})"
                )

        if trace.unresolved:
            lines.append("Нерешённые пункты:")
            for item in trace.unresolved[:6]:
                lines.append(f"- {item}")

        if trace.mode == "FAST":
            lines.append("Отвечай кратко и линейно; не усложняй без причины.")
        elif trace.mode == "DEEP":
            lines.append(
                "Сравни технически релевантные варианты, но в ответе показывай "
                "только выводы, критерии и проверяемые основания, а не скрытую "
                "цепочку внутренних рассуждений."
            )
        elif trace.mode == "VERIFY":
            lines.append(
                "Не делай уверенный вывод, пока противоречия не разрешены "
                "или явно не обозначены."
            )
        elif trace.mode == "PLAN":
            lines.append(
                "Строй план через цель, зависимости, следующий шаг и критерий "
                "завершения; не считай план выполнением."
            )
        elif trace.mode == "DIAGNOSE":
            lines.append(
                "Разделяй симптомы, подтверждённые причины и гипотезы. "
                "Предлагай проверку гипотез до исправления."
            )

        return "\n".join(lines)

    def _record(
        self,
        *,
        scope: str,
        query: str,
        intent: str,
        trace: LogicTrace,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO logic_decisions(
                       scope, query, intent, mode, complexity, confidence,
                       selected_strategy, evidence_json, contradictions_json,
                       alternatives_json, unresolved_json, rule_hits_json,
                       verification_required
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    query[:1200],
                    intent,
                    trace.mode,
                    trace.complexity,
                    trace.confidence,
                    trace.selected_strategy,
                    json.dumps(trace.evidence, ensure_ascii=False),
                    json.dumps(trace.contradictions, ensure_ascii=False),
                    json.dumps(trace.alternatives, ensure_ascii=False),
                    json.dumps(trace.unresolved, ensure_ascii=False),
                    json.dumps(trace.rule_hits, ensure_ascii=False),
                    1 if trace.verification_required else 0,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _record_rule_hits(
        self,
        *,
        scope: str,
        mode: str,
        rule_hits: list[dict],
    ) -> None:
        if not rule_hits:
            return
        with connect() as conn:
            for item in rule_hits:
                conn.execute(
                    """INSERT INTO logic_rule_events(
                           scope, rule_id, mode, details_json
                       ) VALUES (?, ?, ?, ?)""",
                    (
                        scope,
                        item.get("rule_id", "unknown"),
                        mode,
                        json.dumps(item, ensure_ascii=False),
                    ),
                )
            conn.commit()

    @classmethod
    def _complexity_score(
        cls,
        query: str,
        *,
        intent: str,
        contradiction_count: int,
        planner_notices: list[dict],
    ) -> float:
        text = query.casefold()
        score = min(0.28, len(query) / 1800)
        score += min(0.18, query.count("?") * 0.05)
        score += min(
            0.24,
            sum(1 for marker in cls.COMPLEX_MARKERS if marker in text) * 0.06,
        )
        score += min(0.16, contradiction_count * 0.08)
        score += min(0.08, len(planner_notices) * 0.02)
        if intent in {"verification", "action"}:
            score += 0.08
        return round(max(0.0, min(1.0, score)), 4)

    @staticmethod
    def _build_evidence(
        *,
        memories: list[dict],
        verification: dict | None,
        graph_stats: dict,
        planner_notices: list[dict],
        additional_evidence: list[dict],
    ) -> list[dict]:
        evidence: list[dict] = []

        for item in memories[:10]:
            evidence.append(
                {
                    "source": "memory",
                    "id": item.get("id"),
                    "kind": item.get("kind"),
                    "confidence": item.get("confidence"),
                    "retrieval_score": item.get("retrieval_score"),
                    "content": str(item.get("content") or "")[:500],
                }
            )

        if graph_stats:
            evidence.append(
                {
                    "source": "knowledge_graph",
                    "entities": int(graph_stats.get("entities", 0) or 0),
                    "relations": int(graph_stats.get("relations", 0) or 0),
                }
            )

        for notice in planner_notices[:6]:
            evidence.append(
                {
                    "source": "planner",
                    "severity": notice.get("severity"),
                    "code": notice.get("code"),
                    "message": notice.get("message"),
                }
            )

        if verification:
            for item in verification.get("findings", [])[:8]:
                evidence.append(
                    {
                        "source": "verification",
                        "finding": str(item)[:500],
                    }
                )

        for item in additional_evidence[:12]:
            safe = {
                "source": str(item.get("source") or "external"),
                "source_type": item.get("source_type"),
                "source_ref": item.get("source_ref"),
                "source_group": item.get("source_group"),
                "independence": item.get("independence"),
                "confidence": item.get("confidence"),
                "retrieval_score": item.get("retrieval_score"),
                "content": str(item.get("content") or "")[:700],
                "provenance": item.get("provenance") or {},
            }
            for key in ("document_id", "chunk_id", "filename"):
                if item.get(key) is not None:
                    safe[key] = item.get(key)
            evidence.append(safe)

        return evidence

    @staticmethod
    def _collect_contradictions(
        *,
        memories: list[dict],
        verification: dict | None,
        additional_contradictions: list[dict],
    ) -> list[dict]:
        conflicts: list[dict] = []

        for item in memories:
            kind = str(item.get("kind") or "").casefold()
            tags = {str(tag).casefold() for tag in item.get("tags", [])}
            if "contradict" in kind or "contradiction" in tags or "profile_conflict" in tags:
                conflicts.append(
                    {
                        "source": "memory",
                        "memory_id": item.get("id"),
                        "summary": str(item.get("content") or "")[:500],
                        "resolution": "unresolved",
                    }
                )

        if verification:
            consistency = verification.get("consistency") or {}
            for item in consistency.get("conflicts", [])[:8]:
                conflicts.append(
                    {
                        "source": "verification",
                        "summary": str(item)[:500],
                        "resolution": "unresolved",
                    }
                )

        for item in additional_contradictions[:12]:
            conflicts.append(
                {
                    "source": str(item.get("source") or "document"),
                    "summary": str(
                        item.get("summary")
                        or item.get("resolution")
                        or "Document contradiction"
                    )[:500],
                    "resolution": (
                        "unresolved"
                        if str(item.get("status") or "open") == "open"
                        else str(item.get("status") or "unresolved")
                    ),
                    "contradiction_id": item.get("id"),
                }
            )

        return conflicts

    @staticmethod
    def _rule(rule_id: str, reason: str) -> dict:
        return {"rule_id": rule_id, "reason": reason}

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
