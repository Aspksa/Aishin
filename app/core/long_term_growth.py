from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any

from ..db import connect


class LongTermGrowthEngine:
    """Durable, evidence-grounded development of Aishin.

    This engine does not invent capabilities. It promotes skills only from
    persisted learning patterns and strategy quality records, tracks trust only
    for knowledge that has an explicit confidence signal, and applies bounded
    freshness decay without deleting historical experience.
    """

    VERSION = "aishin-long-term-growth-v1"

    CATEGORY_LABELS = {
        "logic_strategy_feedback": "Логика и стратегии",
        "tool_execution": "Инструменты и действия",
        "performance_bottleneck": "Производительность",
        "memory_change": "Память",
        "graph_change": "Граф знаний",
        "self_reflection": "Самоанализ",
        "context_budget": "Контекст",
        "experiment": "Безопасные эксперименты",
        "execution": "Исполнение",
    }

    def __init__(self, *, events: Any | None = None) -> None:
        self.events = events

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _sat(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(1.0, 1.0 - math.exp(-max(0.0, float(value)) / target))

    @staticmethod
    def _parse_time(value: Any) -> datetime | None:
        if not value:
            return None
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _age_days(self, value: Any) -> float:
        parsed = self._parse_time(value)
        if parsed is None:
            return 0.0
        delta = datetime.now(timezone.utc) - parsed
        return max(0.0, delta.total_seconds() / 86400.0)

    def _freshness(
        self,
        value: Any,
        *,
        half_life_days: float,
        floor: float,
    ) -> float:
        age_days = self._age_days(value)
        if half_life_days <= 0:
            return 1.0
        factor = math.pow(0.5, age_days / half_life_days)
        return self._clamp(floor + (1.0 - floor) * factor)

    def refresh(
        self,
        *,
        scope: str,
        persist_snapshot: bool = True,
    ) -> dict:
        scope = (scope or "personal").strip() or "personal"
        skill_changes = self._refresh_skills(scope=scope)
        trust_changes = self._refresh_knowledge_trust(scope=scope)
        specialization_changes = self._refresh_specializations(scope=scope)
        summary = self._summary(scope=scope)
        summary["refresh"] = {
            "skill_changes": skill_changes,
            "knowledge_changes": trust_changes,
            "specialization_changes": specialization_changes,
        }
        if persist_snapshot:
            self._persist_snapshot(scope=scope, summary=summary)
        return summary

    def summary(self, *, scope: str) -> dict:
        return self._summary(scope=(scope or "personal").strip() or "personal")

    def skills(
        self,
        *,
        scope: str,
        lifecycle: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            if lifecycle:
                rows = conn.execute(
                    """SELECT * FROM growth_skills
                       WHERE scope=? AND lifecycle=?
                       ORDER BY mastery_score DESC, evidence_count DESC, id DESC
                       LIMIT ?""",
                    (scope, lifecycle, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM growth_skills
                       WHERE scope=?
                       ORDER BY
                         CASE lifecycle
                           WHEN 'mastered' THEN 0
                           WHEN 'established' THEN 1
                           WHEN 'forming' THEN 2
                           WHEN 'fading' THEN 3
                           ELSE 4
                         END,
                         mastery_score DESC,
                         evidence_count DESC,
                         id DESC
                       LIMIT ?""",
                    (scope, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def specializations(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 200))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM growth_specializations
                   WHERE scope=?
                   ORDER BY overall_score DESC, evidence_count DESC, id DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def knowledge_trust(
        self,
        *,
        scope: str,
        trust_level: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            if trust_level:
                rows = conn.execute(
                    """SELECT * FROM knowledge_trust
                       WHERE scope=? AND trust_level=?
                       ORDER BY trust_score DESC, id DESC
                       LIMIT ?""",
                    (scope, trust_level, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM knowledge_trust
                       WHERE scope=?
                       ORDER BY
                         CASE trust_level
                           WHEN 'trusted' THEN 0
                           WHEN 'supported' THEN 1
                           WHEN 'provisional' THEN 2
                           WHEN 'stale' THEN 3
                           ELSE 4
                         END,
                         trust_score DESC,
                         id DESC
                       LIMIT ?""",
                    (scope, limit),
                ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
            result.append(item)
        return result

    def history(
        self,
        *,
        scope: str,
        limit: int = 90,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM long_term_growth_snapshots
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            result.append(item)
        return result

    def recent_events(
        self,
        *,
        scope: str,
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM long_term_growth_events
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def _refresh_skills(self, *, scope: str) -> int:
        changed = 0
        with connect() as conn:
            pattern_rows = conn.execute(
                """SELECT
                       p.id,
                       p.category,
                       p.pattern_key,
                       p.observations,
                       p.successes,
                       p.failures,
                       p.score,
                       p.last_seen_at,
                       p.updated_at,
                       COALESCE(q.lifecycle, 'candidate') AS quality_lifecycle,
                       COALESCE(q.effective_score, p.score) AS effective_score,
                       COALESCE(q.contradiction_rate, 0.0) AS contradiction_rate,
                       COALESCE(m.weighted_observations, p.observations)
                           AS weighted_observations,
                       COALESCE(m.weighted_successes, p.successes)
                           AS weighted_successes,
                       COALESCE(m.weighted_failures, p.failures)
                           AS weighted_failures,
                       COALESCE(m.evidence_confidence, 0.5)
                           AS evidence_confidence
                   FROM learning_patterns p
                   LEFT JOIN learning_pattern_quality q ON q.pattern_id=p.id
                   LEFT JOIN learning_evidence_metrics m ON m.pattern_id=p.id
                   WHERE p.scope=?
                   ORDER BY p.id DESC
                   LIMIT 1000""",
                (scope,),
            ).fetchall()

            strategy_rows = conn.execute(
                """SELECT
                       s.id,
                       s.strategy_key,
                       s.mode,
                       s.strategy,
                       s.successes,
                       s.failures,
                       s.reliability,
                       s.last_used_at,
                       s.updated_at,
                       COALESCE(q.lifecycle, 'candidate') AS quality_lifecycle,
                       COALESCE(q.effective_reliability, s.reliability)
                           AS effective_reliability,
                       COALESCE(q.drift_score, 0.0) AS drift_score,
                       COALESCE(q.evidence_count, s.successes + s.failures)
                           AS evidence_count
                   FROM logic_strategies s
                   LEFT JOIN strategy_quality_state q ON q.strategy_id=s.id
                   WHERE s.scope=?
                   ORDER BY s.id DESC
                   LIMIT 500""",
                (scope,),
            ).fetchall()

        for row in pattern_rows:
            item = dict(row)
            evidence = float(item["weighted_observations"] or 0.0)
            successes = float(item["weighted_successes"] or 0.0)
            failures = float(item["weighted_failures"] or 0.0)
            reliability = self._clamp(item["effective_score"] or 0.0)
            evidence_confidence = self._clamp(
                item["evidence_confidence"] or 0.0
            )
            contradiction = self._clamp(
                item["contradiction_rate"] or 0.0
            )
            freshness = self._freshness(
                item["last_seen_at"] or item["updated_at"],
                half_life_days=240.0,
                floor=0.30,
            )
            evidence_strength = self._sat(evidence, 8.0)
            success_ratio = (
                (successes + 1.0) / (successes + failures + 2.0)
            )
            stability = self._clamp(
                0.35 * evidence_strength
                + 0.30 * (1.0 - contradiction)
                + 0.20 * success_ratio
                + 0.15 * evidence_confidence
            )
            mastery = 100.0 * self._clamp(
                0.40 * reliability
                + 0.22 * evidence_strength
                + 0.18 * success_ratio
                + 0.20 * stability
            )
            mastery *= 0.82 + 0.18 * freshness
            lifecycle = self._skill_lifecycle(
                mastery=mastery,
                evidence=evidence,
                stability=stability,
                freshness=freshness,
                source_lifecycle=item["quality_lifecycle"],
            )
            category = str(item["category"] or "learning")
            skill_key = f"pattern:{category}:{item['pattern_key']}"
            title = self._skill_title(
                category=category,
                key=str(item["pattern_key"] or "pattern"),
            )
            if self._upsert_skill(
                scope=scope,
                skill_key=skill_key,
                source_type="pattern",
                source_id=int(item["id"]),
                category=category,
                title=title,
                lifecycle=lifecycle,
                mastery=mastery,
                reliability=reliability,
                evidence=evidence,
                successes=successes,
                failures=failures,
                freshness=freshness,
                stability=stability,
                last_evidence_at=item["last_seen_at"] or item["updated_at"],
            ):
                changed += 1

        for row in strategy_rows:
            item = dict(row)
            evidence = float(item["evidence_count"] or 0.0)
            successes = float(item["successes"] or 0.0)
            failures = float(item["failures"] or 0.0)
            reliability = self._clamp(
                item["effective_reliability"] or 0.0
            )
            drift = self._clamp(item["drift_score"] or 0.0)
            freshness = self._freshness(
                item["last_used_at"] or item["updated_at"],
                half_life_days=180.0,
                floor=0.25,
            )
            evidence_strength = self._sat(evidence, 6.0)
            success_ratio = (
                (successes + 1.0) / (successes + failures + 2.0)
            )
            stability = self._clamp(
                0.40 * evidence_strength
                + 0.30 * (1.0 - drift)
                + 0.30 * success_ratio
            )
            mastery = 100.0 * self._clamp(
                0.44 * reliability
                + 0.22 * evidence_strength
                + 0.18 * success_ratio
                + 0.16 * stability
            )
            mastery *= 0.80 + 0.20 * freshness
            lifecycle = self._skill_lifecycle(
                mastery=mastery,
                evidence=evidence,
                stability=stability,
                freshness=freshness,
                source_lifecycle=item["quality_lifecycle"],
            )
            mode = str(item["mode"] or "general").upper()
            category = f"strategy:{mode.lower()}"
            strategy_text = str(item["strategy"] or item["strategy_key"] or "")
            title = strategy_text[:120] or f"Стратегия {mode}"
            skill_key = f"strategy:{item['strategy_key']}"
            if self._upsert_skill(
                scope=scope,
                skill_key=skill_key,
                source_type="strategy",
                source_id=int(item["id"]),
                category=category,
                title=title,
                lifecycle=lifecycle,
                mastery=mastery,
                reliability=reliability,
                evidence=evidence,
                successes=successes,
                failures=failures,
                freshness=freshness,
                stability=stability,
                last_evidence_at=item["last_used_at"] or item["updated_at"],
            ):
                changed += 1

        return changed

    def _skill_lifecycle(
        self,
        *,
        mastery: float,
        evidence: float,
        stability: float,
        freshness: float,
        source_lifecycle: str,
    ) -> str:
        if source_lifecycle == "deprecated":
            return "fading"
        if freshness < 0.42 and evidence >= 4:
            return "fading"
        if mastery >= 80.0 and evidence >= 8 and stability >= 0.72:
            return "mastered"
        if mastery >= 62.0 and evidence >= 4 and stability >= 0.56:
            return "established"
        return "forming"

    def _upsert_skill(
        self,
        *,
        scope: str,
        skill_key: str,
        source_type: str,
        source_id: int,
        category: str,
        title: str,
        lifecycle: str,
        mastery: float,
        reliability: float,
        evidence: float,
        successes: float,
        failures: float,
        freshness: float,
        stability: float,
        last_evidence_at: Any,
    ) -> bool:
        with connect() as conn:
            old = conn.execute(
                """SELECT lifecycle, mastery_score
                   FROM growth_skills
                   WHERE scope=? AND skill_key=?""",
                (scope, skill_key),
            ).fetchone()
            conn.execute(
                """INSERT INTO growth_skills(
                       scope, skill_key, source_type, source_id,
                       category, title, lifecycle, mastery_score,
                       reliability, evidence_count, successes, failures,
                       freshness, stability, last_evidence_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             CURRENT_TIMESTAMP)
                   ON CONFLICT(scope, skill_key) DO UPDATE SET
                       source_type=excluded.source_type,
                       source_id=excluded.source_id,
                       category=excluded.category,
                       title=excluded.title,
                       lifecycle=excluded.lifecycle,
                       mastery_score=excluded.mastery_score,
                       reliability=excluded.reliability,
                       evidence_count=excluded.evidence_count,
                       successes=excluded.successes,
                       failures=excluded.failures,
                       freshness=excluded.freshness,
                       stability=excluded.stability,
                       last_evidence_at=excluded.last_evidence_at,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    skill_key,
                    source_type,
                    source_id,
                    category,
                    title,
                    lifecycle,
                    round(mastery, 2),
                    round(reliability, 5),
                    round(evidence, 3),
                    round(successes, 3),
                    round(failures, 3),
                    round(freshness, 5),
                    round(stability, 5),
                    last_evidence_at,
                ),
            )
            conn.commit()

        old_lifecycle = str(old["lifecycle"]) if old else ""
        old_score = float(old["mastery_score"] or 0.0) if old else 0.0
        changed = old is None or old_lifecycle != lifecycle or abs(
            old_score - mastery
        ) >= 1.0
        if old_lifecycle and old_lifecycle != lifecycle:
            self._record_growth_event(
                scope=scope,
                subject_type="skill",
                subject_key=skill_key,
                event_type="lifecycle_changed",
                old_state=old_lifecycle,
                new_state=lifecycle,
                score=mastery,
                details={
                    "category": category,
                    "evidence_count": evidence,
                    "reliability": reliability,
                    "freshness": freshness,
                },
            )
        return changed

    def _refresh_knowledge_trust(self, *, scope: str) -> int:
        changed = 0
        with connect() as conn:
            conn.execute(
                """DELETE FROM knowledge_trust
                   WHERE scope=? AND subject_type='memory'
                     AND subject_id NOT IN (
                       SELECT id FROM memories
                       WHERE scope=? AND status='active'
                     )""",
                (scope, scope),
            )
            conn.execute(
                """DELETE FROM knowledge_trust
                   WHERE scope=? AND subject_type='relation'
                     AND subject_id NOT IN (
                       SELECT id FROM relations WHERE scope=?
                     )""",
                (scope, scope),
            )
            conn.commit()
            memory_rows = conn.execute(
                """SELECT id, kind, content, confidence, importance, source,
                          fingerprint, memory_key, created_at, updated_at,
                          last_accessed_at
                   FROM memories
                   WHERE scope=? AND status='active'
                   ORDER BY id DESC
                   LIMIT 1200""",
                (scope,),
            ).fetchall()
            relation_rows = conn.execute(
                """SELECT r.id, r.relation_type, r.confidence, r.evidence,
                          r.created_at,
                          s.canonical_name AS source_name,
                          t.canonical_name AS target_name
                   FROM relations r
                   JOIN entities s ON s.id=r.source_entity_id
                   JOIN entities t ON t.id=r.target_entity_id
                   WHERE r.scope=?
                   ORDER BY r.id DESC
                   LIMIT 1200""",
                (scope,),
            ).fetchall()

        key_counts: Counter[str] = Counter()
        for row in memory_rows:
            item = dict(row)
            key = str(
                item.get("memory_key")
                or item.get("fingerprint")
                or ""
            ).strip()
            if key:
                key_counts[key] += 1

        for row in memory_rows:
            item = dict(row)
            key = str(
                item.get("memory_key")
                or item.get("fingerprint")
                or ""
            ).strip()
            corroboration_count = max(0, key_counts.get(key, 1) - 1) if key else 0
            corroboration = self._sat(corroboration_count, 2.0)
            base = self._clamp(item.get("confidence") or 0.0)
            importance = self._clamp(item.get("importance") or 0.0)
            freshness = self._freshness(
                item.get("last_accessed_at")
                or item.get("updated_at")
                or item.get("created_at"),
                half_life_days=540.0,
                floor=0.45,
            )
            trust = self._clamp(
                0.58 * base
                + 0.17 * freshness
                + 0.13 * corroboration
                + 0.12 * importance
            )
            level = self._trust_level(
                score=trust,
                freshness=freshness,
            )
            reasons = [
                f"confidence={base:.2f}",
                f"freshness={freshness:.2f}",
                f"corroboration={corroboration:.2f}",
                f"importance={importance:.2f}",
            ]
            if self._upsert_knowledge(
                scope=scope,
                subject_type="memory",
                subject_id=int(item["id"]),
                category=str(item.get("kind") or "memory"),
                label=str(item.get("content") or "")[:180],
                base_confidence=base,
                freshness=freshness,
                corroboration=corroboration,
                conflict_penalty=0.0,
                trust=trust,
                trust_level=level,
                evidence_count=1 + corroboration_count,
                reasons=reasons,
                last_seen_at=(
                    item.get("last_accessed_at")
                    or item.get("updated_at")
                    or item.get("created_at")
                ),
            ):
                changed += 1

        for row in relation_rows:
            item = dict(row)
            base = self._clamp(item.get("confidence") or 0.0)
            freshness = self._freshness(
                item.get("created_at"),
                half_life_days=720.0,
                floor=0.55,
            )
            has_evidence = bool(str(item.get("evidence") or "").strip())
            corroboration = 0.18 if has_evidence else 0.0
            trust = self._clamp(
                0.72 * base
                + 0.18 * freshness
                + 0.10 * corroboration
            )
            level = self._trust_level(
                score=trust,
                freshness=freshness,
            )
            label = (
                f"{item.get('source_name') or 'сущность'} "
                f"—{item.get('relation_type') or 'связь'}→ "
                f"{item.get('target_name') or 'сущность'}"
            )
            reasons = [
                f"confidence={base:.2f}",
                f"freshness={freshness:.2f}",
                "evidence=present" if has_evidence else "evidence=absent",
            ]
            if self._upsert_knowledge(
                scope=scope,
                subject_type="relation",
                subject_id=int(item["id"]),
                category=f"relation:{item.get('relation_type') or 'generic'}",
                label=label[:180],
                base_confidence=base,
                freshness=freshness,
                corroboration=corroboration,
                conflict_penalty=0.0,
                trust=trust,
                trust_level=level,
                evidence_count=2 if has_evidence else 1,
                reasons=reasons,
                last_seen_at=item.get("created_at"),
            ):
                changed += 1

        return changed

    def _trust_level(self, *, score: float, freshness: float) -> str:
        if freshness < 0.48:
            return "stale"
        if score >= 0.84:
            return "trusted"
        if score >= 0.68:
            return "supported"
        if score >= 0.50:
            return "provisional"
        return "weak"

    def _upsert_knowledge(
        self,
        *,
        scope: str,
        subject_type: str,
        subject_id: int,
        category: str,
        label: str,
        base_confidence: float,
        freshness: float,
        corroboration: float,
        conflict_penalty: float,
        trust: float,
        trust_level: str,
        evidence_count: int,
        reasons: list[str],
        last_seen_at: Any,
    ) -> bool:
        with connect() as conn:
            old = conn.execute(
                """SELECT trust_level, trust_score
                   FROM knowledge_trust
                   WHERE scope=? AND subject_type=? AND subject_id=?""",
                (scope, subject_type, subject_id),
            ).fetchone()
            conn.execute(
                """INSERT INTO knowledge_trust(
                       scope, subject_type, subject_id, category, label,
                       base_confidence, freshness, corroboration,
                       conflict_penalty, trust_score, trust_level,
                       evidence_count, reasons_json, last_seen_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             CURRENT_TIMESTAMP)
                   ON CONFLICT(scope, subject_type, subject_id) DO UPDATE SET
                       category=excluded.category,
                       label=excluded.label,
                       base_confidence=excluded.base_confidence,
                       freshness=excluded.freshness,
                       corroboration=excluded.corroboration,
                       conflict_penalty=excluded.conflict_penalty,
                       trust_score=excluded.trust_score,
                       trust_level=excluded.trust_level,
                       evidence_count=excluded.evidence_count,
                       reasons_json=excluded.reasons_json,
                       last_seen_at=excluded.last_seen_at,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    subject_type,
                    subject_id,
                    category,
                    label,
                    round(base_confidence, 5),
                    round(freshness, 5),
                    round(corroboration, 5),
                    round(conflict_penalty, 5),
                    round(trust, 5),
                    trust_level,
                    int(evidence_count),
                    json.dumps(reasons, ensure_ascii=False),
                    last_seen_at,
                ),
            )
            conn.commit()

        old_level = str(old["trust_level"]) if old else ""
        old_score = float(old["trust_score"] or 0.0) if old else 0.0
        changed = old is None or old_level != trust_level or abs(
            old_score - trust
        ) >= 0.03
        if old_level and old_level != trust_level:
            self._record_growth_event(
                scope=scope,
                subject_type="knowledge",
                subject_key=f"{subject_type}:{subject_id}",
                event_type="trust_changed",
                old_state=old_level,
                new_state=trust_level,
                score=trust * 100.0,
                details={
                    "category": category,
                    "freshness": freshness,
                    "base_confidence": base_confidence,
                },
            )
        return changed

    def _refresh_specializations(self, *, scope: str) -> int:
        with connect() as conn:
            rows = conn.execute(
                """SELECT category, lifecycle, mastery_score, reliability,
                          evidence_count
                   FROM growth_skills
                   WHERE scope=?""",
                (scope,),
            ).fetchall()
            trust_row = conn.execute(
                """SELECT AVG(trust_score) AS avg_trust
                   FROM knowledge_trust
                   WHERE scope=? AND trust_level != 'weak'""",
                (scope,),
            ).fetchone()

        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[str(row["category"] or "general")].append(dict(row))

        global_trust = float(trust_row["avg_trust"] or 0.0) if trust_row else 0.0
        changed = 0
        for category, items in grouped.items():
            count = len(items)
            mastered = sum(
                1 for item in items if item["lifecycle"] == "mastered"
            )
            evidence = sum(float(item["evidence_count"] or 0.0) for item in items)
            depth = (
                sum(float(item["mastery_score"] or 0.0) for item in items)
                / max(1, count)
                / 100.0
            )
            breadth = self._sat(count, 5.0)
            reliability = (
                sum(float(item["reliability"] or 0.0) for item in items)
                / max(1, count)
            )
            trust = self._clamp(
                0.65 * reliability + 0.35 * global_trust
            )
            overall = 100.0 * self._clamp(
                0.52 * depth
                + 0.22 * breadth
                + 0.26 * trust
            )
            volume_factor = 0.62 + 0.38 * self._sat(evidence, 18.0)
            overall *= volume_factor
            level = self._specialization_level(
                score=overall,
                skill_count=count,
                mastered=mastered,
                evidence=evidence,
            )
            label = self._category_label(category)
            if self._upsert_specialization(
                scope=scope,
                key=category,
                label=label,
                skill_count=count,
                mastered=mastered,
                evidence=evidence,
                depth=depth,
                breadth=breadth,
                trust=trust,
                overall=overall,
                level=level,
            ):
                changed += 1
        return changed

    def _specialization_level(
        self,
        *,
        score: float,
        skill_count: int,
        mastered: int,
        evidence: float,
    ) -> str:
        if score >= 82.0 and mastered >= 2 and evidence >= 20:
            return "mastered"
        if score >= 68.0 and skill_count >= 2 and evidence >= 10:
            return "strong"
        if score >= 48.0 and evidence >= 4:
            return "developing"
        return "forming"

    def _upsert_specialization(
        self,
        *,
        scope: str,
        key: str,
        label: str,
        skill_count: int,
        mastered: int,
        evidence: float,
        depth: float,
        breadth: float,
        trust: float,
        overall: float,
        level: str,
    ) -> bool:
        with connect() as conn:
            old = conn.execute(
                """SELECT level, overall_score
                   FROM growth_specializations
                   WHERE scope=? AND specialization_key=?""",
                (scope, key),
            ).fetchone()
            conn.execute(
                """INSERT INTO growth_specializations(
                       scope, specialization_key, label, skill_count,
                       mastered_skills, evidence_count, depth_score,
                       breadth_score, trust_score, overall_score, level,
                       updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             CURRENT_TIMESTAMP)
                   ON CONFLICT(scope, specialization_key) DO UPDATE SET
                       label=excluded.label,
                       skill_count=excluded.skill_count,
                       mastered_skills=excluded.mastered_skills,
                       evidence_count=excluded.evidence_count,
                       depth_score=excluded.depth_score,
                       breadth_score=excluded.breadth_score,
                       trust_score=excluded.trust_score,
                       overall_score=excluded.overall_score,
                       level=excluded.level,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    key,
                    label,
                    skill_count,
                    mastered,
                    round(evidence, 3),
                    round(depth, 5),
                    round(breadth, 5),
                    round(trust, 5),
                    round(overall, 2),
                    level,
                ),
            )
            conn.commit()

        old_level = str(old["level"]) if old else ""
        old_score = float(old["overall_score"] or 0.0) if old else 0.0
        changed = old is None or old_level != level or abs(old_score - overall) >= 1.0
        if old_level and old_level != level:
            self._record_growth_event(
                scope=scope,
                subject_type="specialization",
                subject_key=key,
                event_type="level_changed",
                old_state=old_level,
                new_state=level,
                score=overall,
                details={
                    "skill_count": skill_count,
                    "mastered_skills": mastered,
                    "evidence_count": evidence,
                },
            )
        return changed

    def _summary(self, *, scope: str) -> dict:
        with connect() as conn:
            skill_row = conn.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN lifecycle IN ('established','mastered')
                           THEN 1 ELSE 0 END) AS durable,
                       SUM(CASE WHEN lifecycle='mastered'
                           THEN 1 ELSE 0 END) AS mastered,
                       SUM(CASE WHEN lifecycle='fading'
                           THEN 1 ELSE 0 END) AS fading,
                       AVG(mastery_score) AS avg_mastery,
                       AVG(freshness) AS avg_skill_freshness,
                       SUM(evidence_count) AS evidence
                   FROM growth_skills WHERE scope=?""",
                (scope,),
            ).fetchone()
            trust_row = conn.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN trust_level='trusted'
                           THEN 1 ELSE 0 END) AS trusted,
                       SUM(CASE WHEN trust_level='supported'
                           THEN 1 ELSE 0 END) AS supported,
                       SUM(CASE WHEN trust_level='stale'
                           THEN 1 ELSE 0 END) AS stale,
                       AVG(trust_score) AS avg_trust,
                       AVG(freshness) AS avg_freshness
                   FROM knowledge_trust WHERE scope=?""",
                (scope,),
            ).fetchone()
            spec_row = conn.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN level IN ('strong','mastered')
                           THEN 1 ELSE 0 END) AS strong,
                       AVG(overall_score) AS avg_score
                   FROM growth_specializations WHERE scope=?""",
                (scope,),
            ).fetchone()

        total_skills = int(skill_row["total"] or 0)
        durable = int(skill_row["durable"] or 0)
        mastered = int(skill_row["mastered"] or 0)
        fading = int(skill_row["fading"] or 0)
        avg_mastery = float(skill_row["avg_mastery"] or 0.0)
        evidence = float(skill_row["evidence"] or 0.0)
        avg_skill_freshness = float(
            skill_row["avg_skill_freshness"] or 0.0
        )

        knowledge_total = int(trust_row["total"] or 0)
        trusted = int(trust_row["trusted"] or 0)
        supported = int(trust_row["supported"] or 0)
        stale = int(trust_row["stale"] or 0)
        avg_trust = float(trust_row["avg_trust"] or 0.0)
        avg_freshness = float(trust_row["avg_freshness"] or 0.0)

        specializations = int(spec_row["total"] or 0)
        strong_specializations = int(spec_row["strong"] or 0)
        avg_specialization = float(spec_row["avg_score"] or 0.0)

        volume = self._sat(
            evidence + trusted + supported + strong_specializations * 4,
            60.0,
        )
        raw = (
            0.45 * (avg_mastery / 100.0)
            + 0.25 * (avg_specialization / 100.0)
            + 0.30 * avg_trust
        )
        overall = 100.0 * raw * (0.52 + 0.48 * volume)

        return {
            "version": self.VERSION,
            "scope": scope,
            "overall_score": round(overall, 1),
            "skills": {
                "total": total_skills,
                "durable": durable,
                "mastered": mastered,
                "forming": max(0, total_skills - durable - fading),
                "fading": fading,
                "average_mastery": round(avg_mastery, 1),
                "average_freshness": round(avg_skill_freshness, 4),
                "evidence_count": round(evidence, 2),
            },
            "knowledge": {
                "total": knowledge_total,
                "trusted": trusted,
                "supported": supported,
                "stale": stale,
                "average_trust": round(avg_trust, 4),
                "average_freshness": round(avg_freshness, 4),
            },
            "specializations": {
                "total": specializations,
                "strong": strong_specializations,
                "average_score": round(avg_specialization, 1),
            },
            "principles": [
                "Навык появляется только из сохранённых learning patterns или logic strategies.",
                "Mastered требует достаточного объёма evidence, стабильности и качества.",
                "Старый опыт не удаляется: его вес уменьшается через freshness.",
                "Доверие к знанию не заменяет Verification Engine.",
                "Внешний AI-провайдер не добавляет баллы напрямую.",
            ],
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _persist_snapshot(self, *, scope: str, summary: dict) -> None:
        with connect() as conn:
            recent = conn.execute(
                """SELECT id FROM long_term_growth_snapshots
                   WHERE scope=?
                     AND datetime(created_at) >= datetime('now', '-1 hour')
                   ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()
            if recent:
                return
            skills = summary["skills"]
            knowledge = summary["knowledge"]
            specializations = summary["specializations"]
            conn.execute(
                """INSERT INTO long_term_growth_snapshots(
                       scope, overall_score, durable_skills, mastered_skills,
                       specializations, trusted_knowledge, stale_knowledge,
                       average_trust, average_freshness, payload_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    float(summary["overall_score"]),
                    int(skills["durable"]),
                    int(skills["mastered"]),
                    int(specializations["total"]),
                    int(knowledge["trusted"]),
                    int(knowledge["stale"]),
                    float(knowledge["average_trust"]),
                    float(knowledge["average_freshness"]),
                    json.dumps(summary, ensure_ascii=False),
                ),
            )
            conn.commit()

    def _record_growth_event(
        self,
        *,
        scope: str,
        subject_type: str,
        subject_key: str,
        event_type: str,
        old_state: str,
        new_state: str,
        score: float,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO long_term_growth_events(
                       scope, subject_type, subject_key, event_type,
                       old_state, new_state, score, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    subject_type,
                    subject_key,
                    event_type,
                    old_state,
                    new_state,
                    round(float(score), 3),
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
        if self.events is not None:
            try:
                self.events.emit(
                    f"growth.{event_type}",
                    scope=scope,
                    payload={
                        "subject_type": subject_type,
                        "subject_key": subject_key,
                        "old_state": old_state,
                        "new_state": new_state,
                        "score": round(float(score), 3),
                    },
                    importance=0.35,
                )
            except Exception:
                pass

    def _skill_title(self, *, category: str, key: str) -> str:
        label = self._category_label(category)
        clean_key = key.replace("_", " ").replace(":", " · ").strip()
        return f"{label}: {clean_key}"[:160]

    def _category_label(self, category: str) -> str:
        if category.startswith("strategy:"):
            return f"Логика · {category.split(':', 1)[1].upper()}"
        if category in self.CATEGORY_LABELS:
            return self.CATEGORY_LABELS[category]
        cleaned = category.replace("_", " ").replace(":", " · ").strip()
        return cleaned[:80].capitalize() or "Общее развитие"
