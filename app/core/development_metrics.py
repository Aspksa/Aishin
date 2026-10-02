from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone

from ..db import connect


class DevelopmentMetricsEngine:
    """Transparent development metrics for the local Aishin project.

    The score is derived only from persisted Aishin data. Cloud provider
    identity, model brand and self-generated claims never contribute directly.
    """

    FORMULA_VERSION = "aishin-development-v1"
    WEIGHTS = {
        "memory": 0.20,
        "knowledge": 0.20,
        "connections": 0.15,
        "analytics": 0.10,
        "accuracy": 0.10,
        "error_learning": 0.10,
        "strategies": 0.10,
        "user_help": 0.05,
    }
    LABELS = {
        "memory": "Память",
        "knowledge": "Знания",
        "connections": "Связи",
        "analytics": "Аналитика",
        "accuracy": "Точность",
        "error_learning": "Обучение на ошибках",
        "strategies": "Стратегии",
        "user_help": "Помощь пользователю",
    }
    ICONS = {
        "memory": "◈",
        "knowledge": "✦",
        "connections": "⌁",
        "analytics": "◎",
        "accuracy": "✓",
        "error_learning": "↻",
        "strategies": "◇",
        "user_help": "♡",
    }

    def current(self, *, scope: str, persist: bool = True) -> dict:
        counters = self._counters(scope=scope)
        components = self._components(counters)
        overall = round(
            sum(
                components[key]["score"] * self.WEIGHTS[key]
                for key in self.WEIGHTS
            ),
            1,
        )

        previous = self._comparison_snapshot(scope=scope, days=30)
        monthly_delta = 0.0
        reasons: list[dict] = []
        if previous:
            monthly_delta = round(
                overall - float(previous.get("overall_score") or 0.0),
                1,
            )
            reasons = self._growth_reasons(
                previous=previous,
                current_counters=counters,
                current_components=components,
            )
        else:
            reasons = [
                {
                    "kind": "history",
                    "value": 0,
                    "text": "История развития ещё накапливается.",
                }
            ]

        payload = {
            "scope": scope,
            "formula_version": self.FORMULA_VERSION,
            "overall_score": overall,
            "monthly_delta": monthly_delta,
            "weights": {
                key: round(value * 100, 1)
                for key, value in self.WEIGHTS.items()
            },
            "components": components,
            "counters": counters,
            "growth_reasons": reasons,
            "learning_now": self._learning_now(scope=scope),
            "mastered": self._mastered(scope=scope),
            "growth_needs": self._growth_needs(components),
            "principle": (
                "Показываются только фактически сохранённые данные Айшин. "
                "Cloud.ru не добавляет баллы развитию."
            ),
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }
        if persist:
            self._persist_snapshot(payload)
        return payload

    def history(self, *, scope: str, days: int = 30) -> list[dict]:
        days = max(1, min(3650, int(days)))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM development_snapshots
                   WHERE scope=?
                     AND datetime(created_at) >= datetime('now', ?)
                   ORDER BY id ASC""",
                (scope, f"-{days} days"),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["components"] = json.loads(item.pop("components_json") or "{}")
            item["counters"] = json.loads(item.pop("counters_json") or "{}")
            item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
            result.append(item)
        return result

    @staticmethod
    def _sat(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        value = max(0.0, float(value))
        return min(1.0, 1.0 - math.exp(-value / target))

    @staticmethod
    def _avg(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    def _counters(self, *, scope: str) -> dict:
        with connect() as conn:
            def scalar(sql: str, params: tuple = ()) -> float:
                row = conn.execute(sql, params).fetchone()
                return float(row[0] or 0) if row else 0.0

            events = int(scalar("SELECT COUNT(*) FROM events WHERE scope=?", (scope,)))
            memories = int(scalar(
                "SELECT COUNT(*) FROM memories WHERE scope=? AND status='active'",
                (scope,),
            ))
            memory_confidence = scalar(
                """SELECT AVG(confidence) FROM memories
                   WHERE scope=? AND status='active'""",
                (scope,),
            )
            memory_kinds = int(scalar(
                """SELECT COUNT(DISTINCT kind) FROM memories
                   WHERE scope=? AND status='active'""",
                (scope,),
            ))
            entities = int(scalar("SELECT COUNT(*) FROM entities WHERE scope=?", (scope,)))
            entity_types = int(scalar(
                "SELECT COUNT(DISTINCT entity_type) FROM entities WHERE scope=?",
                (scope,),
            ))
            relations = int(scalar("SELECT COUNT(*) FROM relations WHERE scope=?", (scope,)))
            relation_confidence = scalar(
                "SELECT AVG(confidence) FROM relations WHERE scope=?",
                (scope,),
            )
            documents = int(scalar(
                """SELECT COUNT(*) FROM entities
                   WHERE scope=? AND (
                     lower(entity_type) LIKE '%document%'
                     OR lower(entity_type) LIKE '%документ%'
                   )""",
                (scope,),
            ))
            decision_rows = conn.execute(
                """SELECT overall FROM decision_quality_scores
                   WHERE scope=? ORDER BY id DESC LIMIT 100""",
                (scope,),
            ).fetchall()
            decision_quality = self._avg(
                [float(row["overall"] or 0.0) for row in decision_rows]
            )
            verification_rows = conn.execute(
                """SELECT unresolved_json FROM verification_runs
                   WHERE scope=? ORDER BY id DESC LIMIT 100""",
                (scope,),
            ).fetchall()
            verification_unresolved = 0
            for row in verification_rows:
                try:
                    verification_unresolved += len(
                        json.loads(row["unresolved_json"] or "[]")
                    )
                except Exception:
                    pass
            hypothesis_runs = int(scalar(
                "SELECT COUNT(*) FROM hypothesis_runs WHERE scope=?",
                (scope,),
            ))
            reflection_rows = conn.execute(
                """SELECT quality_score, confidence_score, error_count,
                          correction_signal
                   FROM self_reflection_runs
                   WHERE scope=? ORDER BY id DESC LIMIT 100""",
                (scope,),
            ).fetchall()
            reflection_quality = self._avg(
                [float(row["quality_score"] or 0.0) for row in reflection_rows]
            )
            reflection_confidence = self._avg(
                [float(row["confidence_score"] or 0.0) for row in reflection_rows]
            )
            correction_signals = sum(
                int(row["correction_signal"] or 0) for row in reflection_rows
            )
            reflection_errors = sum(
                int(row["error_count"] or 0) for row in reflection_rows
            )
            logic_feedback = int(scalar(
                "SELECT COUNT(*) FROM logic_learning_events WHERE scope=?",
                (scope,),
            ))
            logic_successes = int(scalar(
                """SELECT COUNT(*) FROM logic_learning_events
                   WHERE scope=? AND outcome='success'""",
                (scope,),
            ))
            patterns_total = int(scalar(
                "SELECT COUNT(*) FROM learning_patterns WHERE scope=?",
                (scope,),
            ))
            trusted_patterns = int(scalar(
                """SELECT COUNT(*) FROM learning_pattern_quality
                   WHERE scope=? AND lifecycle='trusted'""",
                (scope,),
            ))
            evidence_confidence = scalar(
                """SELECT AVG(evidence_confidence)
                   FROM learning_evidence_metrics WHERE scope=?""",
                (scope,),
            )
            strategies_total = int(scalar(
                "SELECT COUNT(*) FROM logic_strategies WHERE scope=?",
                (scope,),
            ))
            trusted_strategies = int(scalar(
                """SELECT COUNT(*) FROM strategy_quality_state
                   WHERE scope=? AND lifecycle='trusted'""",
                (scope,),
            ))
            tool_total = int(scalar(
                "SELECT COUNT(*) FROM tool_actions WHERE scope=?",
                (scope,),
            ))
            tool_successes = int(scalar(
                """SELECT COUNT(*) FROM tool_actions
                   WHERE scope=? AND status='success'""",
                (scope,),
            ))
            messages = int(scalar(
                "SELECT COUNT(*) FROM messages WHERE scope=?",
                (scope,),
            ))
            durable_skills = int(scalar(
                """SELECT COUNT(*) FROM growth_skills
                   WHERE scope=? AND lifecycle IN ('established','mastered')""",
                (scope,),
            ))
            mastered_skills = int(scalar(
                """SELECT COUNT(*) FROM growth_skills
                   WHERE scope=? AND lifecycle='mastered'""",
                (scope,),
            ))
            specializations = int(scalar(
                "SELECT COUNT(*) FROM growth_specializations WHERE scope=?",
                (scope,),
            ))
            strong_specializations = int(scalar(
                """SELECT COUNT(*) FROM growth_specializations
                   WHERE scope=? AND level IN ('strong','mastered')""",
                (scope,),
            ))
            trusted_knowledge = int(scalar(
                """SELECT COUNT(*) FROM knowledge_trust
                   WHERE scope=? AND trust_level='trusted'""",
                (scope,),
            ))
            stale_knowledge = int(scalar(
                """SELECT COUNT(*) FROM knowledge_trust
                   WHERE scope=? AND trust_level='stale'""",
                (scope,),
            ))
            average_knowledge_trust = scalar(
                "SELECT AVG(trust_score) FROM knowledge_trust WHERE scope=?",
                (scope,),
            )

        knowledge_items = memories + entities
        return {
            "experience_events": events,
            "knowledge_items": knowledge_items,
            "active_memories": memories,
            "memory_confidence": round(memory_confidence, 4),
            "memory_kinds": memory_kinds,
            "entities": entities,
            "entity_types": entity_types,
            "connections": relations,
            "connection_confidence": round(relation_confidence, 4),
            "studied_documents": documents,
            "analysis_runs": len(decision_rows),
            "decision_quality": round(decision_quality, 4),
            "verification_runs": len(verification_rows),
            "verification_unresolved": verification_unresolved,
            "hypothesis_runs": hypothesis_runs,
            "confirmed_hypotheses": 0,
            "reflection_samples": len(reflection_rows),
            "reflection_quality": round(reflection_quality, 4),
            "reflection_confidence": round(reflection_confidence, 4),
            "error_signals": correction_signals + reflection_errors,
            "logic_feedback": logic_feedback,
            "logic_successes": logic_successes,
            "patterns": patterns_total,
            "trusted_patterns": trusted_patterns,
            "evidence_confidence": round(evidence_confidence, 4),
            "strategies": strategies_total,
            "trusted_strategies": trusted_strategies,
            "tool_actions": tool_total,
            "tool_successes": tool_successes,
            "messages": messages,
            "durable_skills": durable_skills,
            "mastered_skills": mastered_skills,
            "specializations": specializations,
            "strong_specializations": strong_specializations,
            "trusted_knowledge": trusted_knowledge,
            "stale_knowledge": stale_knowledge,
            "average_knowledge_trust": round(average_knowledge_trust, 4),
        }

    def _components(self, c: dict) -> dict:
        memory = (
            0.45 * self._sat(c["active_memories"], 120)
            + 0.35 * c["memory_confidence"]
            + 0.20 * self._sat(c["memory_kinds"], 8)
        )
        knowledge = (
            0.55 * self._sat(c["knowledge_items"], 300)
            + 0.25 * self._sat(c["entity_types"], 12)
            + 0.20 * c["memory_confidence"]
        )
        connections = (
            0.60 * self._sat(c["connections"], 350)
            + 0.40 * c["connection_confidence"]
        )
        analytics = (
            0.55 * c["decision_quality"]
            + 0.25 * self._sat(c["verification_runs"], 40)
            + 0.20 * self._sat(c["hypothesis_runs"], 30)
        )

        reflection_volume = self._sat(c["reflection_samples"], 25)
        correction_rate = (
            min(1.0, c["error_signals"] / c["reflection_samples"])
            if c["reflection_samples"] else 0.0
        )
        accuracy_base = (
            0.60 * c["reflection_quality"]
            + 0.20 * c["reflection_confidence"]
            + 0.20 * (1.0 - correction_rate)
        )
        accuracy = accuracy_base * reflection_volume

        feedback_volume = self._sat(c["logic_feedback"], 15)
        feedback_success = (
            c["logic_successes"] / c["logic_feedback"]
            if c["logic_feedback"] else 0.0
        )
        error_learning = (
            0.45 * feedback_volume
            + 0.35 * feedback_success * feedback_volume
            + 0.20 * self._sat(c["trusted_patterns"], 15)
        )

        trusted_strategy_ratio = (
            c["trusted_strategies"] / c["strategies"]
            if c["strategies"] else 0.0
        )
        strategies = (
            0.45 * self._sat(c["trusted_patterns"], 20)
            + 0.30 * trusted_strategy_ratio
            + 0.25 * c["evidence_confidence"]
        )

        tool_volume = self._sat(c["tool_actions"], 40)
        tool_success = (
            c["tool_successes"] / c["tool_actions"]
            if c["tool_actions"] else 0.0
        )
        user_help = (
            0.30 * self._sat(c["messages"], 120)
            + 0.35 * tool_volume * tool_success
            + 0.35 * c["reflection_quality"] * reflection_volume
        )

        values = {
            "memory": memory,
            "knowledge": knowledge,
            "connections": connections,
            "analytics": analytics,
            "accuracy": accuracy,
            "error_learning": error_learning,
            "strategies": strategies,
            "user_help": user_help,
        }
        return {
            key: {
                "label": self.LABELS[key],
                "icon": self.ICONS[key],
                "weight": round(self.WEIGHTS[key] * 100, 1),
                "score": round(max(0.0, min(1.0, value)) * 100, 1),
                "evidence": self._component_evidence(key, c),
            }
            for key, value in values.items()
        }

    @staticmethod
    def _component_evidence(key: str, c: dict) -> str:
        evidence = {
            "memory": (
                f"{c['active_memories']} активных записей · "
                f"{c['memory_kinds']} типов памяти"
            ),
            "knowledge": (
                f"{c['knowledge_items']} элементов знаний · "
                f"{c['entities']} сущностей"
            ),
            "connections": (
                f"{c['connections']} связей · "
                f"средняя уверенность {round(c['connection_confidence'] * 100)}%"
            ),
            "analytics": (
                f"{c['analysis_runs']} оценок качества решений · "
                f"{c['verification_runs']} проверок"
            ),
            "accuracy": (
                f"{c['reflection_samples']} самооценок · "
                f"качество {round(c['reflection_quality'] * 100)}%"
            ),
            "error_learning": (
                f"{c['logic_feedback']} подтверждённых feedback-событий · "
                f"{c['error_signals']} сигналов ошибок"
            ),
            "strategies": (
                f"{c['trusted_patterns']} trusted-паттернов · "
                f"{c['trusted_strategies']} trusted-стратегий"
            ),
            "user_help": (
                f"{c['messages']} сообщений · "
                f"{c['tool_successes']}/{c['tool_actions']} успешных действий"
            ),
        }
        return evidence[key]

    def _persist_snapshot(self, payload: dict) -> None:
        scope = str(payload["scope"])
        with connect() as conn:
            recent = conn.execute(
                """SELECT id FROM development_snapshots
                   WHERE scope=?
                     AND datetime(created_at) >= datetime('now', '-1 hour')
                   ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()
            if recent:
                return
            conn.execute(
                """INSERT INTO development_snapshots(
                       scope, formula_version, overall_score,
                       components_json, counters_json, reasons_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    self.FORMULA_VERSION,
                    float(payload["overall_score"]),
                    json.dumps(payload["components"], ensure_ascii=False),
                    json.dumps(payload["counters"], ensure_ascii=False),
                    json.dumps(payload["growth_reasons"], ensure_ascii=False),
                ),
            )
            conn.commit()

    def _comparison_snapshot(self, *, scope: str, days: int) -> dict | None:
        target = datetime.now(timezone.utc) - timedelta(days=days)
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM development_snapshots
                   WHERE scope=? AND datetime(created_at) <= datetime(?)
                   ORDER BY id DESC LIMIT 1""",
                (scope, target.isoformat()),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["components"] = json.loads(item.pop("components_json") or "{}")
        item["counters"] = json.loads(item.pop("counters_json") or "{}")
        item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
        return item

    def _growth_reasons(
        self,
        *,
        previous: dict,
        current_counters: dict,
        current_components: dict,
    ) -> list[dict]:
        old = previous.get("counters") or {}
        candidates = [
            ("studied_documents", "изученных документов"),
            ("knowledge_items", "элементов знаний"),
            ("connections", "связей"),
            ("trusted_patterns", "trusted-паттернов"),
            ("trusted_strategies", "trusted-стратегий"),
            ("tool_successes", "успешных действий"),
        ]
        reasons: list[dict] = []
        for key, label in candidates:
            delta = int(current_counters.get(key, 0)) - int(old.get(key, 0))
            if delta:
                sign = "+" if delta > 0 else ""
                reasons.append(
                    {
                        "kind": key,
                        "value": delta,
                        "text": f"{sign}{delta} {label}",
                    }
                )

        old_components = previous.get("components") or {}
        for key, item in current_components.items():
            old_score = float((old_components.get(key) or {}).get("score") or 0.0)
            delta = round(float(item["score"]) - old_score, 1)
            if abs(delta) >= 0.5:
                sign = "+" if delta > 0 else ""
                reasons.append(
                    {
                        "kind": f"component:{key}",
                        "value": delta,
                        "text": f"{item['label']}: {sign}{delta} п.п.",
                    }
                )
        return reasons[:8] or [
            {
                "kind": "stable",
                "value": 0,
                "text": "Значимых изменений за период не обнаружено.",
            }
        ]

    @staticmethod
    def _learning_now(*, scope: str) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT topic, rationale, priority, status, target_metric
                   FROM learning_plans
                   WHERE scope=? AND status='open'
                   ORDER BY priority DESC, id DESC LIMIT 6""",
                (scope,),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _mastered(*, scope: str) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT p.category, p.pattern_key, q.effective_score,
                          p.observations
                   FROM learning_patterns p
                   JOIN learning_pattern_quality q ON q.pattern_id=p.id
                   WHERE p.scope=? AND q.lifecycle='trusted'
                   ORDER BY q.effective_score DESC, p.observations DESC
                   LIMIT 6""",
                (scope,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _growth_needs(self, components: dict) -> list[dict]:
        ordered = sorted(
            components.items(),
            key=lambda pair: float(pair[1]["score"]),
        )
        return [
            {
                "key": key,
                "label": item["label"],
                "icon": item["icon"],
                "score": item["score"],
                "why": item["evidence"],
            }
            for key, item in ordered[:4]
        ]
