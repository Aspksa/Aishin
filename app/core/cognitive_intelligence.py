from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..db import connect


@dataclass
class CognitiveRoute:
    request_id: str
    scope: str
    task_family: str
    task_label: str
    intent: str
    base_mode: str
    adapted_mode: str
    base_complexity: float
    route_confidence: float
    context_multiplier: float
    selected_skills: list[dict] = field(default_factory=list)
    selected_specializations: list[dict] = field(default_factory=list)
    selected_knowledge: list[dict] = field(default_factory=list)
    transfer_used: bool = False
    transfer_skill_ids: list[int] = field(default_factory=list)
    prior_family_experience: dict = field(default_factory=dict)
    rationale: list[str] = field(default_factory=list)
    route_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class CognitiveIntelligenceEngine:
    """Adaptive routing + evidence-grounded cognitive intelligence metrics.

    The engine never estimates "IQ" and never reconstructs hidden reasoning.
    It measures observable system capabilities from persisted evidence and uses
    durable skills only as advisory routing signals. Verification and permission
    gates always keep precedence over adaptive routing.
    """

    VERSION = "aishin-cognitive-intelligence-v1"
    FORMULA_VERSION = "cognitive-intelligence-8d-v1"

    DIMENSIONS = {
        "understanding": {
            "label": "Понимание",
            "weight": 16.0,
            "icon": "◎",
        },
        "logic": {
            "label": "Логика",
            "weight": 18.0,
            "icon": "◇",
        },
        "memory": {
            "label": "Память",
            "weight": 14.0,
            "icon": "◫",
        },
        "learning": {
            "label": "Обучение",
            "weight": 14.0,
            "icon": "↗",
        },
        "planning": {
            "label": "Планирование",
            "weight": 10.0,
            "icon": "⌘",
        },
        "self_check": {
            "label": "Самопроверка",
            "weight": 12.0,
            "icon": "✓",
        },
        "adaptation": {
            "label": "Адаптация",
            "weight": 10.0,
            "icon": "⇄",
        },
        "transfer": {
            "label": "Перенос опыта",
            "weight": 6.0,
            "icon": "∞",
        },
    }

    FAMILY_LABELS = {
        "documents": "Документы",
        "fuel": "ГСМ и путевые листы",
        "vehicles": "Автотранспорт",
        "timesheet": "Табель и рабочее время",
        "software": "Разработка и система",
        "diagnostics": "Диагностика",
        "planning": "Планирование",
        "analysis": "Аналитика",
        "knowledge": "Память и знания",
        "general": "Общий контекст",
    }

    FAMILY_MARKERS = {
        "fuel": (
            "гсм", "топлив", "бензин", "дизел", "заправ", "расход",
            "путев", "одометр", "пробег",
        ),
        "timesheet": (
            "табел", "переработ", "смен", "рабочее время", "часов",
            "выезд", "возвращен",
        ),
        "vehicles": (
            "машин", "автомоб", "гараж", "госномер", "гос. номер",
            "запчаст", "ремонт", "техник",
        ),
        "documents": (
            "документ", "договор", "счет", "счёт", "акт", "pdf",
            "скан", "распозна", "служебн", "оферт", "накладн",
        ),
        "software": (
            "python", "javascript", "typescript", "github", "api", "fastapi",
            "sql", "база данных", "сервер", "frontend", "backend", "код",
            "css", "html", "runtime", "репозитор",
        ),
        "diagnostics": (
            "ошибка", "не работает", "не запуска", "диагност", "сломал",
            "проблем", "исправ", "проверить систему",
        ),
        "planning": (
            "план", "этап", "реализ", "архитект", "что дальше",
            "сделай", "задач", "цель", "проект",
        ),
        "analysis": (
            "анализ", "сравни", "противореч", "причин", "почему",
            "вариант", "проверь", "оцен", "рассчитай",
        ),
        "knowledge": (
            "памят", "знани", "обуч", "интеллект", "навык", "опыт",
            "развит", "гипотез",
        ),
    }

    STOP_TOKENS = {
        "котор", "этот", "это", "того", "чтобы", "если", "только", "сразу",
        "очень", "будет", "можно", "нужно", "надо", "сделай", "давай",
        "the", "and", "with", "from", "that", "this", "для", "как",
    }

    MODE_ORDER = {
        "FAST": 0,
        "PLAN": 1,
        "DEEP": 2,
        "VERIFY": 3,
        "DIAGNOSE": 4,
    }

    def __init__(self, *, growth: Any, events: Any | None = None) -> None:
        self.growth = growth
        self.events = events

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _sat(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(1.0, 1.0 - math.exp(-max(0.0, float(value)) / target))

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        tokens = set(re.findall(r"[a-zа-яё0-9]{3,}", (text or "").casefold()))
        return {
            token
            for token in tokens
            if token not in cls.STOP_TOKENS
        }

    @classmethod
    def classify_task(cls, query: str, *, intent: str) -> tuple[str, list[dict]]:
        text = (query or "").casefold()
        scores: list[tuple[str, float, list[str]]] = []
        for family, markers in cls.FAMILY_MARKERS.items():
            hits = [marker for marker in markers if marker in text]
            if not hits:
                continue
            score = min(1.0, 0.34 + 0.17 * len(hits))
            scores.append((family, score, hits[:5]))

        if not scores:
            if intent == "action":
                return "planning", [
                    {
                        "family": "planning",
                        "score": 0.42,
                        "signals": ["intent:action"],
                    }
                ]
            if intent == "verification":
                return "analysis", [
                    {
                        "family": "analysis",
                        "score": 0.42,
                        "signals": ["intent:verification"],
                    }
                ]
            return "general", []

        scores.sort(key=lambda item: item[1], reverse=True)
        signals = [
            {
                "family": family,
                "score": round(score, 4),
                "signals": hits,
            }
            for family, score, hits in scores[:4]
        ]
        return scores[0][0], signals

    def route(
        self,
        *,
        request_id: str,
        scope: str,
        query: str,
        intent: str,
        base_mode: str,
        base_complexity: float,
        metacognition: dict,
    ) -> CognitiveRoute:
        task_family, family_signals = self.classify_task(
            query,
            intent=intent,
        )
        query_tokens = self._tokens(query)

        skills = self.growth.skills(scope=scope, limit=250)
        specializations = self.growth.specializations(scope=scope, limit=100)
        knowledge = self.growth.knowledge_trust(scope=scope, limit=300)

        selected_skills = self._rank_skills(
            query_tokens=query_tokens,
            task_family=task_family,
            items=skills,
        )
        selected_specializations = self._rank_specializations(
            query_tokens=query_tokens,
            task_family=task_family,
            items=specializations,
        )
        selected_knowledge = self._rank_knowledge(
            query_tokens=query_tokens,
            task_family=task_family,
            items=knowledge,
        )

        prior = self._prior_family_experience(
            scope=scope,
            task_family=task_family,
        )
        transfer_skill_ids = self._transfer_candidates(
            scope=scope,
            task_family=task_family,
            selected_skill_ids=[
                int(item["id"])
                for item in selected_skills
                if item.get("id") is not None
            ],
        )
        transfer_used = bool(transfer_skill_ids)

        skill_signal = self._average(
            [
                self._clamp(float(item.get("mastery_score") or 0.0) / 100.0)
                * float(item.get("match_score") or 0.0)
                for item in selected_skills
            ]
        )
        knowledge_signal = self._average(
            [
                self._clamp(float(item.get("trust_score") or 0.0))
                * float(item.get("match_score") or 0.0)
                for item in selected_knowledge
            ]
        )
        specialization_signal = self._average(
            [
                self._clamp(float(item.get("overall_score") or 0.0) / 100.0)
                * float(item.get("match_score") or 0.0)
                for item in selected_specializations
            ]
        )
        prior_signal = self._clamp(float(prior.get("average_outcome") or 0.0))
        meta_signal = self._clamp(
            float(metacognition.get("confidence") or 0.0)
        )
        available_signals = [
            value
            for value in (
                skill_signal,
                knowledge_signal,
                specialization_signal,
                prior_signal,
            )
            if value > 0
        ]
        evidence_signal = self._average(available_signals)
        route_confidence = self._clamp(
            0.72 * evidence_signal + 0.28 * meta_signal
        )

        adapted_mode, mode_reason = self._adapt_mode(
            base_mode=base_mode,
            base_complexity=base_complexity,
            intent=intent,
            task_family=task_family,
            route_confidence=route_confidence,
            metacognition=metacognition,
            transfer_used=transfer_used,
        )
        context_multiplier = self._context_multiplier(
            mode=adapted_mode,
            route_confidence=route_confidence,
            transfer_used=transfer_used,
        )

        rationale = [
            f"task_family={task_family}",
            f"base_mode={base_mode}",
            f"adapted_mode={adapted_mode}",
            f"route_confidence={route_confidence:.2f}",
            mode_reason,
        ]
        if selected_skills:
            rationale.append(
                f"durable_skills_selected={len(selected_skills)}"
            )
        if selected_specializations:
            rationale.append(
                f"specializations_selected={len(selected_specializations)}"
            )
        if selected_knowledge:
            rationale.append(
                f"trusted_knowledge_selected={len(selected_knowledge)}"
            )
        if transfer_used:
            rationale.append(
                "Обнаружен подтверждённый перенос навыка между типами задач."
            )
        for signal in family_signals[:3]:
            rationale.append(
                f"family_signal:{signal['family']}={signal['score']:.2f}"
            )

        route = CognitiveRoute(
            request_id=request_id,
            scope=scope,
            task_family=task_family,
            task_label=self.FAMILY_LABELS.get(task_family, task_family),
            intent=intent,
            base_mode=base_mode,
            adapted_mode=adapted_mode,
            base_complexity=round(float(base_complexity), 4),
            route_confidence=round(route_confidence, 4),
            context_multiplier=round(context_multiplier, 3),
            selected_skills=selected_skills,
            selected_specializations=selected_specializations,
            selected_knowledge=selected_knowledge,
            transfer_used=transfer_used,
            transfer_skill_ids=transfer_skill_ids,
            prior_family_experience=prior,
            rationale=rationale,
        )
        route.route_id = self._record_route(route=route, query=query)
        self._emit(
            "intelligence.route.selected",
            scope=scope,
            payload={
                "request_id": request_id,
                "task_family": task_family,
                "base_mode": base_mode,
                "adapted_mode": adapted_mode,
                "route_confidence": route.route_confidence,
                "skills": len(selected_skills),
                "knowledge": len(selected_knowledge),
                "transfer_used": transfer_used,
            },
            importance=0.25,
        )
        return route

    def adapt_logic_plan(self, plan: Any, route: CognitiveRoute) -> Any:
        original_mode = str(getattr(plan, "mode", route.base_mode) or "FAST")
        target_mode = route.adapted_mode
        if self.MODE_ORDER.get(target_mode, 0) > self.MODE_ORDER.get(
            original_mode,
            0,
        ):
            plan.mode = target_mode

        if plan.mode in {"VERIFY", "DIAGNOSE"}:
            plan.verification_required = True

        plan.rule_hits.append(
            {
                "rule_id": "intelligence.adaptive_skill_router",
                "description": (
                    f"Adaptive Skill Router: family={route.task_family}, "
                    f"confidence={route.route_confidence:.2f}, "
                    f"skills={len(route.selected_skills)}, "
                    f"transfer={route.transfer_used}."
                ),
            }
        )

        if route.selected_skills:
            skill_names = ", ".join(
                str(item.get("title") or item.get("skill_key") or "")[:70]
                for item in route.selected_skills[:3]
            )
            plan.selected_strategy = (
                f"{plan.selected_strategy} "
                f"Подключить подтверждённый operational experience: "
                f"{skill_names}."
            )
        if route.transfer_used:
            plan.alternatives.append(
                "Проверить применимость перенесённого опыта к текущему типу задачи."
            )
        return plan

    def prompt_block(self, route: CognitiveRoute) -> str:
        lines = [
            "Aishin Cognitive Intelligence Router.",
            f"Тип задачи: {route.task_label} ({route.task_family}).",
            f"Адаптивный режим: {route.adapted_mode}.",
            f"Route confidence: {route.route_confidence:.2f}.",
            "Operational skills и trusted knowledge ниже являются только "
            "подсказками маршрутизации. Текущие evidence, Verification Engine "
            "и Permission Gate имеют приоритет.",
        ]
        if route.selected_skills:
            lines.append("Подходящие подтверждённые навыки:")
            for item in route.selected_skills[:5]:
                lines.append(
                    f"- {str(item.get('title') or item.get('skill_key') or '')[:140]} "
                    f"(mastery={float(item.get('mastery_score') or 0.0):.1f}, "
                    f"reliability={float(item.get('reliability') or 0.0):.2f}, "
                    f"evidence={float(item.get('evidence_count') or 0.0):.1f})"
                )
        if route.selected_knowledge:
            lines.append("Релевантные знания с измеренным trust:")
            for item in route.selected_knowledge[:5]:
                lines.append(
                    f"- {str(item.get('label') or '')[:150]} "
                    f"(trust={float(item.get('trust_score') or 0.0):.2f}, "
                    f"level={item.get('trust_level')})"
                )
        if route.transfer_used:
            lines.append(
                "Есть перенос опыта из других типов задач. Не считать его "
                "автоматически применимым: проверить соответствие текущим данным."
            )
        return "\n".join(lines)

    def complete_route(
        self,
        *,
        request_id: str,
        scope: str,
        decision_quality: float,
        reflection_quality: float,
        provider_available: bool,
        unresolved_count: int,
    ) -> dict:
        dq = self._clamp(decision_quality)
        reflection = self._clamp(reflection_quality)
        provider_signal = 1.0 if provider_available else 0.55
        penalty = min(0.35, max(0, int(unresolved_count)) * 0.07)
        outcome = self._clamp(
            0.45 * dq
            + 0.35 * reflection
            + 0.20 * provider_signal
            - penalty
        )
        successful = outcome >= 0.72 and int(unresolved_count) == 0

        with connect() as conn:
            conn.execute(
                """UPDATE cognitive_intelligence_routes
                   SET outcome_score=?,
                       successful=?,
                       unresolved_count=?,
                       completed_at=CURRENT_TIMESTAMP
                   WHERE request_id=? AND scope=?""",
                (
                    round(outcome, 5),
                    1 if successful else 0,
                    int(unresolved_count),
                    request_id,
                    scope,
                ),
            )
            conn.commit()

        self._emit(
            "intelligence.route.completed",
            scope=scope,
            payload={
                "request_id": request_id,
                "outcome_score": round(outcome, 4),
                "successful": successful,
                "unresolved_count": int(unresolved_count),
            },
            importance=0.3,
        )
        return {
            "request_id": request_id,
            "outcome_score": round(outcome, 4),
            "successful": successful,
            "unresolved_count": int(unresolved_count),
        }

    def dashboard(
        self,
        *,
        scope: str,
        history_limit: int = 90,
        route_limit: int = 30,
        persist: bool = True,
    ) -> dict:
        current = self.current(scope=scope, persist=persist)
        dimensions = current["dimensions"]
        ordered = sorted(
            dimensions.items(),
            key=lambda pair: float(pair[1]["score"]),
            reverse=True,
        )
        return {
            "current": current,
            "strengths": [
                {
                    "key": key,
                    "label": value["label"],
                    "score": value["score"],
                    "why": value["why"],
                }
                for key, value in ordered[:3]
            ],
            "growth_priorities": [
                {
                    "key": key,
                    "label": value["label"],
                    "score": value["score"],
                    "why": value["why"],
                }
                for key, value in sorted(
                    dimensions.items(),
                    key=lambda pair: float(pair[1]["score"]),
                )[:3]
            ],
            "routes": self.routes(scope=scope, limit=route_limit),
            "latest_route": self.latest_route(scope=scope),
            "transfer_map": self.transfer_map(scope=scope),
            "history": self.history(scope=scope, limit=history_limit),
        }

    def current(self, *, scope: str, persist: bool = False) -> dict:
        result = self._calculate(scope=scope)
        if persist:
            self._persist_snapshot(scope=scope, result=result)
        return result

    def routes(self, *, scope: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM cognitive_intelligence_routes
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [self._decode_route(dict(row)) for row in rows]

    def latest_route(self, *, scope: str) -> dict:
        items = self.routes(scope=scope, limit=1)
        return items[0] if items else {}

    def history(self, *, scope: str, limit: int = 90) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM cognitive_intelligence_snapshots
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["dimensions"] = json.loads(
                item.pop("dimensions_json") or "{}"
            )
            item["evidence"] = json.loads(
                item.pop("evidence_json") or "{}"
            )
            item["route_stats"] = json.loads(
                item.pop("route_stats_json") or "{}"
            )
            result.append(item)
        return result

    def transfer_map(self, *, scope: str) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT selected_skill_ids_json, task_family,
                          outcome_score, successful
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND successful=1
                   ORDER BY id DESC LIMIT 500""",
                (scope,),
            ).fetchall()
            skill_rows = conn.execute(
                """SELECT id, title, mastery_score, lifecycle
                   FROM growth_skills WHERE scope=?""",
                (scope,),
            ).fetchall()

        skill_names = {
            int(row["id"]): dict(row)
            for row in skill_rows
        }
        families: dict[int, set[str]] = defaultdict(set)
        uses: dict[int, int] = defaultdict(int)
        outcomes: dict[int, list[float]] = defaultdict(list)
        for row in rows:
            try:
                skill_ids = json.loads(
                    row["selected_skill_ids_json"] or "[]"
                )
            except Exception:
                skill_ids = []
            for skill_id in skill_ids:
                try:
                    sid = int(skill_id)
                except (TypeError, ValueError):
                    continue
                families[sid].add(str(row["task_family"] or "general"))
                uses[sid] += 1
                if row["outcome_score"] is not None:
                    outcomes[sid].append(float(row["outcome_score"]))

        result = []
        for skill_id, family_set in families.items():
            if len(family_set) < 2:
                continue
            skill = skill_names.get(skill_id, {})
            result.append(
                {
                    "skill_id": skill_id,
                    "title": skill.get("title") or f"skill:{skill_id}",
                    "mastery_score": float(
                        skill.get("mastery_score") or 0.0
                    ),
                    "lifecycle": skill.get("lifecycle") or "",
                    "families": sorted(family_set),
                    "family_count": len(family_set),
                    "successful_uses": uses[skill_id],
                    "average_outcome": round(
                        self._average(outcomes[skill_id]),
                        4,
                    ),
                }
            )
        result.sort(
            key=lambda item: (
                item["family_count"],
                item["average_outcome"],
                item["mastery_score"],
            ),
            reverse=True,
        )
        return result[:50]

    def _rank_skills(
        self,
        *,
        query_tokens: set[str],
        task_family: str,
        items: list[dict],
    ) -> list[dict]:
        ranked = []
        for item in items:
            if item.get("lifecycle") not in {"established", "mastered"}:
                continue
            text = (
                f"{item.get('category') or ''} "
                f"{item.get('title') or ''} "
                f"{item.get('skill_key') or ''}"
            )
            overlap = self._token_overlap(query_tokens, self._tokens(text))
            candidate_family, _ = self.classify_task(
                text,
                intent="conversation",
            )
            family_match = 1.0 if candidate_family == task_family else 0.0
            mastery = self._clamp(
                float(item.get("mastery_score") or 0.0) / 100.0
            )
            reliability = self._clamp(float(item.get("reliability") or 0.0))
            match = self._clamp(
                0.46 * overlap
                + 0.24 * family_match
                + 0.18 * mastery
                + 0.12 * reliability
            )
            if match < 0.22:
                continue
            copy = dict(item)
            copy["match_score"] = round(match, 4)
            ranked.append(copy)
        ranked.sort(
            key=lambda item: (
                float(item["match_score"]),
                float(item.get("mastery_score") or 0.0),
            ),
            reverse=True,
        )
        return ranked[:5]

    def _rank_specializations(
        self,
        *,
        query_tokens: set[str],
        task_family: str,
        items: list[dict],
    ) -> list[dict]:
        ranked = []
        for item in items:
            if item.get("level") not in {
                "developing",
                "strong",
                "mastered",
            }:
                continue
            text = (
                f"{item.get('label') or ''} "
                f"{item.get('specialization_key') or ''}"
            )
            overlap = self._token_overlap(query_tokens, self._tokens(text))
            candidate_family, _ = self.classify_task(
                text,
                intent="conversation",
            )
            family_match = 1.0 if candidate_family == task_family else 0.0
            strength = self._clamp(
                float(item.get("overall_score") or 0.0) / 100.0
            )
            match = self._clamp(
                0.48 * overlap + 0.30 * family_match + 0.22 * strength
            )
            if match < 0.20:
                continue
            copy = dict(item)
            copy["match_score"] = round(match, 4)
            ranked.append(copy)
        ranked.sort(
            key=lambda item: (
                float(item["match_score"]),
                float(item.get("overall_score") or 0.0),
            ),
            reverse=True,
        )
        return ranked[:3]

    def _rank_knowledge(
        self,
        *,
        query_tokens: set[str],
        task_family: str,
        items: list[dict],
    ) -> list[dict]:
        ranked = []
        for item in items:
            if item.get("trust_level") not in {"trusted", "supported"}:
                continue
            label = str(item.get("label") or "")
            overlap = self._token_overlap(query_tokens, self._tokens(label))
            candidate_family, _ = self.classify_task(
                label,
                intent="conversation",
            )
            family_match = 1.0 if candidate_family == task_family else 0.0
            trust = self._clamp(float(item.get("trust_score") or 0.0))
            match = self._clamp(
                0.56 * overlap + 0.18 * family_match + 0.26 * trust
            )
            if match < 0.25:
                continue
            copy = dict(item)
            copy["match_score"] = round(match, 4)
            ranked.append(copy)
        ranked.sort(
            key=lambda item: (
                float(item["match_score"]),
                float(item.get("trust_score") or 0.0),
            ),
            reverse=True,
        )
        return ranked[:6]

    @staticmethod
    def _token_overlap(left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        intersection = len(left & right)
        denominator = max(1, min(len(left), 8))
        return min(1.0, intersection / denominator)

    def _adapt_mode(
        self,
        *,
        base_mode: str,
        base_complexity: float,
        intent: str,
        task_family: str,
        route_confidence: float,
        metacognition: dict,
        transfer_used: bool,
    ) -> tuple[str, str]:
        base_mode = base_mode if base_mode in self.MODE_ORDER else "FAST"
        status = str(metacognition.get("status") or "")
        confidence = self._clamp(
            float(metacognition.get("confidence") or 0.0)
        )

        if base_mode in {"VERIFY", "DIAGNOSE"}:
            return base_mode, "Safety mode preserved; router never downgrades it."
        if intent == "verification" or status in {
            "needs_verification",
            "insufficient_data",
        }:
            return "VERIFY", "Недостаточная опора требует Verification."
        if confidence < 0.34 and base_mode == "FAST":
            return "VERIFY", "Низкий metacognitive confidence."
        if base_mode == "FAST" and transfer_used:
            return "DEEP", "Перенос опыта требует проверки применимости."
        if (
            base_mode == "FAST"
            and float(base_complexity) >= 0.44
            and route_confidence < 0.55
        ):
            return "DEEP", "Сложная задача при слабом подтверждённом опыте."
        if (
            base_mode == "FAST"
            and task_family == "planning"
            and intent == "action"
        ):
            return "PLAN", "Задача действия маршрутизирована через планирование."
        return base_mode, "Базовый Logic Engine уже выбрал достаточный режим."

    def _context_multiplier(
        self,
        *,
        mode: str,
        route_confidence: float,
        transfer_used: bool,
    ) -> float:
        base = {
            "FAST": 0.95,
            "PLAN": 1.08,
            "DEEP": 1.15,
            "VERIFY": 1.24,
            "DIAGNOSE": 1.24,
        }.get(mode, 1.0)
        if transfer_used:
            base += 0.05
        if route_confidence < 0.30 and mode in {"DEEP", "VERIFY", "DIAGNOSE"}:
            base += 0.03
        return max(0.90, min(1.30, base))

    def _prior_family_experience(
        self,
        *,
        scope: str,
        task_family: str,
    ) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT outcome_score, successful
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND task_family=?
                     AND outcome_score IS NOT NULL
                   ORDER BY id DESC LIMIT 60""",
                (scope, task_family),
            ).fetchall()
        outcomes = [
            float(row["outcome_score"] or 0.0)
            for row in rows
        ]
        successes = sum(int(row["successful"] or 0) for row in rows)
        return {
            "samples": len(rows),
            "successful": successes,
            "success_rate": round(
                successes / len(rows),
                4,
            ) if rows else 0.0,
            "average_outcome": round(
                self._average(outcomes),
                4,
            ),
        }

    def _transfer_candidates(
        self,
        *,
        scope: str,
        task_family: str,
        selected_skill_ids: list[int],
    ) -> list[int]:
        if not selected_skill_ids:
            return []
        with connect() as conn:
            rows = conn.execute(
                """SELECT task_family, selected_skill_ids_json
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND successful=1
                   ORDER BY id DESC LIMIT 400""",
                (scope,),
            ).fetchall()
        other_families: dict[int, set[str]] = defaultdict(set)
        selected = set(selected_skill_ids)
        for row in rows:
            family = str(row["task_family"] or "general")
            if family == task_family:
                continue
            try:
                ids = json.loads(row["selected_skill_ids_json"] or "[]")
            except Exception:
                ids = []
            for value in ids:
                try:
                    skill_id = int(value)
                except (TypeError, ValueError):
                    continue
                if skill_id in selected:
                    other_families[skill_id].add(family)
        return sorted(other_families)

    def _record_route(self, *, route: CognitiveRoute, query: str) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT OR REPLACE INTO cognitive_intelligence_routes(
                       request_id, scope, query_preview, task_family, intent,
                       base_mode, adapted_mode, route_confidence,
                       context_multiplier, selected_skill_ids_json,
                       selected_specialization_ids_json,
                       selected_knowledge_ids_json, transfer_used,
                       transfer_skill_ids_json, rationale_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    route.request_id,
                    route.scope,
                    query[:500],
                    route.task_family,
                    route.intent,
                    route.base_mode,
                    route.adapted_mode,
                    route.route_confidence,
                    route.context_multiplier,
                    json.dumps(
                        [
                            int(item["id"])
                            for item in route.selected_skills
                            if item.get("id") is not None
                        ]
                    ),
                    json.dumps(
                        [
                            int(item["id"])
                            for item in route.selected_specializations
                            if item.get("id") is not None
                        ]
                    ),
                    json.dumps(
                        [
                            int(item["id"])
                            for item in route.selected_knowledge
                            if item.get("id") is not None
                        ]
                    ),
                    1 if route.transfer_used else 0,
                    json.dumps(route.transfer_skill_ids),
                    json.dumps(route.rationale, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    @staticmethod
    def _decode_route(item: dict) -> dict:
        for field_name in (
            "selected_skill_ids_json",
            "selected_specialization_ids_json",
            "selected_knowledge_ids_json",
            "transfer_skill_ids_json",
            "rationale_json",
        ):
            target = field_name.removesuffix("_json")
            try:
                item[target] = json.loads(item.pop(field_name) or "[]")
            except Exception:
                item[target] = []
        item["transfer_used"] = bool(item.get("transfer_used"))
        if item.get("successful") is not None:
            item["successful"] = bool(item["successful"])
        return item

    def _calculate(self, *, scope: str) -> dict:
        with connect() as conn:
            meta_rows = conn.execute(
                """SELECT confidence, evidence_score, contradiction_count
                   FROM metacognitive_assessments
                   WHERE scope=? ORDER BY id DESC LIMIT 120""",
                (scope,),
            ).fetchall()
            decision_rows = conn.execute(
                """SELECT overall FROM decision_quality_scores
                   WHERE scope=? ORDER BY id DESC LIMIT 120""",
                (scope,),
            ).fetchall()
            reflection_rows = conn.execute(
                """SELECT quality_score, confidence_score, error_count,
                          correction_signal
                   FROM self_reflection_runs
                   WHERE scope=? ORDER BY id DESC LIMIT 120""",
                (scope,),
            ).fetchall()
            verification_rows = conn.execute(
                """SELECT unresolved_json FROM verification_runs
                   WHERE scope=? ORDER BY id DESC LIMIT 120""",
                (scope,),
            ).fetchall()
            memory_row = conn.execute(
                """SELECT COUNT(*) AS total, AVG(confidence) AS avg_conf
                   FROM memories WHERE scope=? AND status='active'""",
                (scope,),
            ).fetchone()
            trust_row = conn.execute(
                """SELECT COUNT(*) AS total,
                          AVG(trust_score) AS avg_trust,
                          SUM(CASE WHEN trust_level='trusted'
                              THEN 1 ELSE 0 END) AS trusted
                   FROM knowledge_trust WHERE scope=?""",
                (scope,),
            ).fetchone()
            skill_row = conn.execute(
                """SELECT COUNT(*) AS total,
                          AVG(mastery_score) AS avg_mastery,
                          SUM(CASE WHEN lifecycle IN ('established','mastered')
                              THEN 1 ELSE 0 END) AS durable,
                          SUM(CASE WHEN lifecycle='mastered'
                              THEN 1 ELSE 0 END) AS mastered,
                          SUM(evidence_count) AS evidence
                   FROM growth_skills WHERE scope=?""",
                (scope,),
            ).fetchone()
            spec_row = conn.execute(
                """SELECT COUNT(*) AS total,
                          AVG(overall_score) AS avg_score
                   FROM growth_specializations WHERE scope=?""",
                (scope,),
            ).fetchone()
            strategy_row = conn.execute(
                """SELECT
                       (SELECT COUNT(*) FROM logic_strategies WHERE scope=?)
                           AS total,
                       (SELECT COUNT(*) FROM strategy_quality_state
                        WHERE scope=? AND lifecycle='trusted') AS trusted""",
                (scope, scope),
            ).fetchone()
            goal_rows = conn.execute(
                """SELECT status FROM goals WHERE scope=?""",
                (scope,),
            ).fetchall()
            task_rows = conn.execute(
                """SELECT status FROM tasks WHERE scope=?""",
                (scope,),
            ).fetchall()
            action_rows = conn.execute(
                """SELECT decision_quality FROM action_selections
                   WHERE scope=? ORDER BY id DESC LIMIT 100""",
                (scope,),
            ).fetchall()
            route_rows = conn.execute(
                """SELECT * FROM cognitive_intelligence_routes
                   WHERE scope=? AND outcome_score IS NOT NULL
                   ORDER BY id DESC LIMIT 160""",
                (scope,),
            ).fetchall()

        meta_count = len(meta_rows)
        avg_meta_conf = self._average(
            [float(row["confidence"] or 0.0) for row in meta_rows]
        )
        avg_meta_evidence = self._average(
            [float(row["evidence_score"] or 0.0) for row in meta_rows]
        )
        contradiction_rate = (
            sum(
                1
                for row in meta_rows
                if int(row["contradiction_count"] or 0) > 0
            ) / meta_count
            if meta_count
            else 0.0
        )

        understanding_quality = (
            0.52 * avg_meta_evidence + 0.48 * avg_meta_conf
        )
        understanding = (
            100.0
            * understanding_quality
            * (0.52 + 0.48 * self._sat(meta_count, 50))
            * (1.0 - 0.22 * contradiction_rate)
        )

        decision_quality = self._average(
            [float(row["overall"] or 0.0) for row in decision_rows]
        )
        strategy_total = int(strategy_row["total"] or 0)
        strategy_trusted = int(strategy_row["trusted"] or 0)
        strategy_ratio = (
            strategy_trusted / strategy_total
            if strategy_total
            else 0.0
        )
        logic_base = (
            0.62 * decision_quality
            + 0.20 * avg_meta_evidence
            + 0.18 * strategy_ratio
        )
        logic_volume = self._sat(
            len(decision_rows) + strategy_trusted * 2,
            70,
        )
        logic = 100.0 * logic_base * (0.50 + 0.50 * logic_volume)

        memory_total = int(memory_row["total"] or 0)
        avg_memory_conf = float(memory_row["avg_conf"] or 0.0)
        trust_total = int(trust_row["total"] or 0)
        avg_trust = float(trust_row["avg_trust"] or 0.0)
        trusted = int(trust_row["trusted"] or 0)
        trusted_ratio = trusted / trust_total if trust_total else 0.0
        memory_base = (
            0.38 * avg_memory_conf
            + 0.40 * avg_trust
            + 0.22 * trusted_ratio
        )
        memory_volume = self._sat(memory_total + trust_total, 180)
        memory = 100.0 * memory_base * (0.48 + 0.52 * memory_volume)

        skill_total = int(skill_row["total"] or 0)
        avg_mastery = float(skill_row["avg_mastery"] or 0.0) / 100.0
        durable = int(skill_row["durable"] or 0)
        mastered = int(skill_row["mastered"] or 0)
        skill_evidence = float(skill_row["evidence"] or 0.0)
        durable_ratio = durable / skill_total if skill_total else 0.0
        mastered_ratio = mastered / skill_total if skill_total else 0.0
        avg_spec = float(spec_row["avg_score"] or 0.0) / 100.0
        learning_base = (
            0.40 * avg_mastery
            + 0.24 * durable_ratio
            + 0.16 * mastered_ratio
            + 0.20 * avg_spec
        )
        learning_volume = self._sat(skill_evidence + durable * 3, 60)
        learning = 100.0 * learning_base * (0.50 + 0.50 * learning_volume)

        planner_statuses = [
            str(row["status"] or "").casefold()
            for row in list(goal_rows) + list(task_rows)
        ]
        planner_total = len(planner_statuses)
        planner_completed = sum(
            1
            for status in planner_statuses
            if status in {"done", "completed", "closed", "success"}
        )
        completion_ratio = (
            planner_completed / planner_total
            if planner_total
            else 0.0
        )
        action_quality = self._average(
            [float(row["decision_quality"] or 0.0) for row in action_rows]
        )
        planning_volume = self._sat(planner_total + len(action_rows), 45)
        planning_base = (
            0.52 * completion_ratio
            + 0.38 * action_quality
            + 0.10 * self._sat(planner_total, 12)
        )
        planning = 100.0 * planning_base * (0.45 + 0.55 * planning_volume)

        reflection_quality = self._average(
            [float(row["quality_score"] or 0.0) for row in reflection_rows]
        )
        reflection_conf = self._average(
            [float(row["confidence_score"] or 0.0) for row in reflection_rows]
        )
        verification_clean = self._verification_clean_rate(verification_rows)
        correction_rate = (
            sum(
                int(row["correction_signal"] or 0)
                + min(1, int(row["error_count"] or 0))
                for row in reflection_rows
            ) / (2 * len(reflection_rows))
            if reflection_rows
            else 0.0
        )
        self_check_base = (
            0.33 * reflection_quality
            + 0.19 * reflection_conf
            + 0.28 * verification_clean
            + 0.20 * avg_meta_conf
        )
        self_check_volume = self._sat(
            len(reflection_rows) + len(verification_rows),
            55,
        )
        self_check = (
            100.0
            * self_check_base
            * (0.52 + 0.48 * self_check_volume)
            * (1.0 - 0.18 * min(1.0, correction_rate))
        )

        routes = [dict(row) for row in route_rows]
        route_count = len(routes)
        route_outcome = self._average(
            [float(row["outcome_score"] or 0.0) for row in routes]
        )
        route_success_rate = (
            sum(int(row["successful"] or 0) for row in routes) / route_count
            if route_count
            else 0.0
        )
        route_confidence = self._average(
            [float(row["route_confidence"] or 0.0) for row in routes]
        )
        routed_with_skill = 0
        changed_mode = 0
        for row in routes:
            try:
                skill_ids = json.loads(
                    row["selected_skill_ids_json"] or "[]"
                )
            except Exception:
                skill_ids = []
            if skill_ids:
                routed_with_skill += 1
            if str(row["base_mode"]) != str(row["adapted_mode"]):
                changed_mode += 1
        skill_use_rate = (
            routed_with_skill / route_count
            if route_count
            else 0.0
        )
        adaptation_base = (
            0.44 * route_outcome
            + 0.24 * route_success_rate
            + 0.18 * route_confidence
            + 0.14 * skill_use_rate
        )
        adaptation_volume = self._sat(route_count, 45)
        adaptation = (
            100.0
            * adaptation_base
            * (0.42 + 0.58 * adaptation_volume)
        )

        transfer = self._transfer_metrics_from_routes(
            routes=routes,
        )
        transfer_score = float(transfer["score"])

        raw_scores = {
            "understanding": understanding,
            "logic": logic,
            "memory": memory,
            "learning": learning,
            "planning": planning,
            "self_check": self_check,
            "adaptation": adaptation,
            "transfer": transfer_score,
        }

        evidence = {
            "understanding": {
                "metacognition_samples": meta_count,
                "average_confidence": round(avg_meta_conf, 4),
                "average_evidence": round(avg_meta_evidence, 4),
                "contradiction_rate": round(contradiction_rate, 4),
            },
            "logic": {
                "decision_samples": len(decision_rows),
                "decision_quality": round(decision_quality, 4),
                "trusted_strategies": strategy_trusted,
                "strategies_total": strategy_total,
            },
            "memory": {
                "active_memories": memory_total,
                "average_memory_confidence": round(avg_memory_conf, 4),
                "knowledge_trust_records": trust_total,
                "trusted_knowledge": trusted,
                "average_trust": round(avg_trust, 4),
            },
            "learning": {
                "skills_total": skill_total,
                "durable_skills": durable,
                "mastered_skills": mastered,
                "skill_evidence": round(skill_evidence, 2),
                "specializations": int(spec_row["total"] or 0),
            },
            "planning": {
                "planner_items": planner_total,
                "completed_items": planner_completed,
                "completion_rate": round(completion_ratio, 4),
                "action_samples": len(action_rows),
                "action_quality": round(action_quality, 4),
            },
            "self_check": {
                "reflection_samples": len(reflection_rows),
                "reflection_quality": round(reflection_quality, 4),
                "verification_samples": len(verification_rows),
                "verification_clean_rate": round(verification_clean, 4),
                "correction_rate": round(correction_rate, 4),
            },
            "adaptation": {
                "routes": route_count,
                "average_outcome": round(route_outcome, 4),
                "success_rate": round(route_success_rate, 4),
                "average_route_confidence": round(route_confidence, 4),
                "skill_use_rate": round(skill_use_rate, 4),
                "mode_changes": changed_mode,
            },
            "transfer": transfer,
        }

        dimensions = {}
        weighted = 0.0
        for key, meta in self.DIMENSIONS.items():
            score = round(max(0.0, min(100.0, raw_scores[key])), 1)
            dimensions[key] = {
                "label": meta["label"],
                "icon": meta["icon"],
                "weight": meta["weight"],
                "score": score,
                "why": self._dimension_why(
                    key=key,
                    score=score,
                    evidence=evidence[key],
                ),
                "evidence": evidence[key],
            }
            weighted += score * (float(meta["weight"]) / 100.0)

        route_stats = {
            "completed_routes": route_count,
            "successful_routes": sum(
                int(row["successful"] or 0)
                for row in routes
            ),
            "skill_routed": routed_with_skill,
            "mode_changes": changed_mode,
            "transfer_routes": sum(
                1 for row in routes if int(row["transfer_used"] or 0)
            ),
        }

        return {
            "version": self.VERSION,
            "formula_version": self.FORMULA_VERSION,
            "scope": scope,
            "overall_score": round(weighted, 1),
            "dimensions": dimensions,
            "evidence": evidence,
            "route_stats": route_stats,
            "principles": [
                "Это не IQ и не оценка человеческого интеллекта.",
                "Каждый балл строится только из сохранённых измеримых сигналов.",
                "Новые способности получают ограниченный score до накопления evidence.",
                "Adaptive Router может только сохранить или усилить режим Logic Engine, но не ослабить Verification.",
                "Перенос опыта засчитывается только после успешного применения одного навыка в разных типах задач.",
                "Внешний AI-провайдер не добавляет intelligence points напрямую.",
            ],
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _verification_clean_rate(rows: list[Any]) -> float:
        if not rows:
            return 0.0
        clean = 0
        for row in rows:
            try:
                unresolved = json.loads(row["unresolved_json"] or "[]")
            except Exception:
                unresolved = ["parse_error"]
            if not unresolved:
                clean += 1
        return clean / len(rows)

    def _transfer_metrics_from_routes(self, *, routes: list[dict]) -> dict:
        successful = [
            row
            for row in routes
            if int(row.get("successful") or 0) == 1
        ]
        skill_families: dict[int, set[str]] = defaultdict(set)
        transfer_successes = 0
        for row in successful:
            family = str(row.get("task_family") or "general")
            try:
                ids = json.loads(row.get("selected_skill_ids_json") or "[]")
            except Exception:
                ids = []
            for value in ids:
                try:
                    skill_families[int(value)].add(family)
                except (TypeError, ValueError):
                    continue
            if int(row.get("transfer_used") or 0):
                transfer_successes += 1

        transferable = {
            skill_id: families
            for skill_id, families in skill_families.items()
            if len(families) >= 2
        }
        transferable_count = len(transferable)
        family_breadth = self._average(
            [
                min(1.0, (len(families) - 1) / 3.0)
                for families in transferable.values()
            ]
        )
        transfer_route_rate = (
            transfer_successes / len(successful)
            if successful
            else 0.0
        )
        score = 100.0 * (
            0.50 * self._sat(transferable_count, 5)
            + 0.30 * family_breadth
            + 0.20 * transfer_route_rate
        )
        score *= 0.45 + 0.55 * self._sat(len(successful), 30)
        return {
            "score": round(score, 1),
            "successful_routes": len(successful),
            "transferable_skills": transferable_count,
            "average_family_breadth": round(family_breadth, 4),
            "successful_transfer_routes": transfer_successes,
            "transfer_route_rate": round(transfer_route_rate, 4),
        }

    def _dimension_why(
        self,
        *,
        key: str,
        score: float,
        evidence: dict,
    ) -> str:
        if key == "understanding":
            return (
                f"{evidence['metacognition_samples']} проверок контекста; "
                f"средняя evidence={evidence['average_evidence']:.2f}, "
                f"confidence={evidence['average_confidence']:.2f}."
            )
        if key == "logic":
            return (
                f"{evidence['decision_samples']} решений; качество "
                f"{evidence['decision_quality']:.2f}; trusted strategies "
                f"{evidence['trusted_strategies']}/{evidence['strategies_total']}."
            )
        if key == "memory":
            return (
                f"{evidence['active_memories']} активных воспоминаний; "
                f"{evidence['trusted_knowledge']} trusted knowledge; "
                f"средний trust={evidence['average_trust']:.2f}."
            )
        if key == "learning":
            return (
                f"{evidence['durable_skills']} устойчивых навыков, "
                f"{evidence['mastered_skills']} mastered; evidence "
                f"{evidence['skill_evidence']:.1f}."
            )
        if key == "planning":
            return (
                f"{evidence['completed_items']}/{evidence['planner_items']} "
                f"задач/целей завершено; action quality "
                f"{evidence['action_quality']:.2f}."
            )
        if key == "self_check":
            return (
                f"{evidence['reflection_samples']} self-reflection; "
                f"{evidence['verification_samples']} verification; "
                f"clean rate={evidence['verification_clean_rate']:.2f}."
            )
        if key == "adaptation":
            return (
                f"{evidence['routes']} адаптивных маршрутов; success "
                f"{evidence['success_rate']:.2f}; skill use "
                f"{evidence['skill_use_rate']:.2f}."
            )
        if key == "transfer":
            return (
                f"{evidence['transferable_skills']} навыков успешно применены "
                f"в нескольких типах задач; transfer routes "
                f"{evidence['successful_transfer_routes']}."
            )
        return f"score={score:.1f}"

    def _persist_snapshot(self, *, scope: str, result: dict) -> None:
        with connect() as conn:
            recent = conn.execute(
                """SELECT id FROM cognitive_intelligence_snapshots
                   WHERE scope=?
                     AND datetime(created_at) >= datetime('now', '-1 hour')
                   ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()
            if recent:
                return
            conn.execute(
                """INSERT INTO cognitive_intelligence_snapshots(
                       scope, formula_version, overall_score,
                       dimensions_json, evidence_json, route_stats_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    result["formula_version"],
                    float(result["overall_score"]),
                    json.dumps(result["dimensions"], ensure_ascii=False),
                    json.dumps(result["evidence"], ensure_ascii=False),
                    json.dumps(result["route_stats"], ensure_ascii=False),
                ),
            )
            conn.commit()

    def _emit(
        self,
        event_type: str,
        *,
        scope: str,
        payload: dict,
        importance: float,
    ) -> None:
        if self.events is None:
            return
        try:
            self.events.emit(
                event_type,
                scope=scope,
                payload=payload,
                importance=importance,
            )
        except Exception:
            pass

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0
