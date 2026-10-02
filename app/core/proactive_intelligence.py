from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..db import (
    connect,
    create_proactive_decision,
    get_proactive_decision,
    update_proactive_decision,
)


@dataclass
class ProactiveIntelligenceReport:
    created: int
    pending: int
    attention: int
    scope: str
    signals: int = 0
    updated: int = 0
    resolved: int = 0
    decisions_created: int = 0
    awareness_score: float = 0.0
    trigger: str = "manual"
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "created": self.created,
            "pending": self.pending,
            "attention": self.attention,
            "scope": self.scope,
            "signals": self.signals,
            "updated": self.updated,
            "resolved": self.resolved,
            "decisions_created": self.decisions_created,
            "awareness_score": self.awareness_score,
            "trigger": self.trigger,
            "duration_ms": self.duration_ms,
        }


class ProactiveIntelligenceEngine:
    """Situation awareness and calibrated proactive attention for Aishin.

    The engine observes persisted local evidence. It can create informational
    proposals, but it cannot execute external or mutating actions by itself.
    Execution remains controlled by the existing ProactiveDecisionLoop,
    PermissionGate and ExecutionCoordinator.
    """

    VERSION = "aishin-proactive-intelligence-v1"
    FORMULA_VERSION = "situation-awareness-risk-v1"

    SOURCE_RELIABILITY = {
        "planner": 0.98,
        "sensor": 0.92,
        "verification": 0.94,
        "execution": 0.98,
        "cognitive_intelligence": 0.88,
        "learning": 0.90,
        "knowledge": 0.82,
        "situation_delta": 0.78,
        "system": 0.95,
    }

    SEVERITY_LABELS = (
        (0.84, "critical"),
        (0.68, "high"),
        (0.48, "medium"),
        (0.0, "low"),
    )

    def __init__(
        self,
        *,
        legacy_loop: Any,
        planner: Any,
        sensors: Any,
        events: Any,
    ) -> None:
        self.legacy_loop = legacy_loop
        self.planner = planner
        self.sensors = sensors
        self.events = events

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _safe_json(value: Any, default: Any) -> Any:
        if value in (None, ""):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except Exception:
            return default

    @staticmethod
    def _fingerprint(*parts: Any) -> str:
        raw = "|".join(str(part).strip().casefold() for part in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

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

    def evaluate(
        self,
        *,
        scope: str,
        trigger: str = "heartbeat",
    ) -> ProactiveIntelligenceReport:
        started = time.perf_counter()
        scope = (scope or "personal").strip() or "personal"

        legacy = self.legacy_loop.evaluate(scope=scope)
        self._sync_expectations(scope=scope)

        previous = self._latest_situation(scope=scope)
        situation = self._build_situation(scope=scope)
        delta = self._situation_delta(
            previous.get("state") if previous else {},
            situation["state"],
        )
        signals = self._collect_signals(
            scope=scope,
            situation=situation,
            previous=previous,
            delta=delta,
        )
        profile = self.attention_profile(scope=scope)
        threshold = float(profile["calibrated_threshold"])

        active_fingerprints: set[str] = set()
        created = 0
        updated = 0
        decisions_created = 0

        for signal in signals:
            stored_signal = self._upsert_signal(
                scope=scope,
                signal=signal,
            )
            if float(stored_signal["attention_score"]) < threshold:
                continue

            incident, was_created = self._upsert_incident(
                scope=scope,
                signal=signal,
                signal_id=int(stored_signal["id"]),
            )
            active_fingerprints.add(str(incident["fingerprint"]))
            if was_created:
                created += 1
            else:
                updated += 1

            if (
                float(incident["attention_score"])
                >= max(threshold, 0.70)
                and incident["status"] == "active"
            ):
                decision_id, decision_new = self._ensure_decision(
                    scope=scope,
                    incident=incident,
                )
                if decision_id is not None:
                    self._bind_decision(
                        scope=scope,
                        incident_id=int(incident["id"]),
                        decision_id=decision_id,
                    )
                if decision_new:
                    decisions_created += 1

        resolved = self._resolve_absent(
            scope=scope,
            active_fingerprints=active_fingerprints,
        )

        awareness = self._awareness_score(
            situation=situation,
            signals=signals,
            profile=profile,
        )
        snapshot_id = self._store_situation(
            scope=scope,
            trigger=trigger,
            awareness_score=awareness["overall_score"],
            situation=situation,
            delta=delta,
        )

        pending = len(self.incidents(scope=scope, status="active", limit=1000))
        attention = len(
            [
                item
                for item in self.incidents(
                    scope=scope,
                    status="active",
                    limit=1000,
                )
                if float(item["attention_score"]) >= threshold
            ]
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        self._record_run(
            scope=scope,
            trigger=trigger,
            awareness_score=awareness["overall_score"],
            signals=len(signals),
            created=created,
            updated=updated,
            resolved=resolved,
            decisions_created=decisions_created,
            duration_ms=duration_ms,
            stats={
                "legacy": legacy.to_dict(),
                "threshold": threshold,
                "snapshot_id": snapshot_id,
                "awareness": awareness,
                "delta": delta,
            },
        )

        if created or resolved or decisions_created:
            self.events.emit(
                "proactive.intelligence.scan",
                scope=scope,
                payload={
                    "trigger": trigger,
                    "signals": len(signals),
                    "created": created,
                    "updated": updated,
                    "resolved": resolved,
                    "decisions_created": decisions_created,
                    "awareness_score": awareness["overall_score"],
                    "attention_threshold": threshold,
                },
                importance=0.68 if created else 0.35,
            )

        return ProactiveIntelligenceReport(
            created=created + int(legacy.created),
            pending=pending,
            attention=attention,
            scope=scope,
            signals=len(signals),
            updated=updated,
            resolved=resolved,
            decisions_created=decisions_created,
            awareness_score=awareness["overall_score"],
            trigger=trigger,
            duration_ms=duration_ms,
        )

    def dashboard(
        self,
        *,
        scope: str,
        incident_limit: int = 80,
        signal_limit: int = 80,
        run_limit: int = 40,
        refresh: bool = False,
    ) -> dict:
        if refresh:
            self.evaluate(scope=scope, trigger="dashboard")
        situation = self._latest_situation(scope=scope)
        incidents = self.incidents(
            scope=scope,
            status=None,
            limit=incident_limit,
        )
        active = [item for item in incidents if item["status"] == "active"]
        profile = self.attention_profile(scope=scope)
        threshold = float(profile["calibrated_threshold"])
        runs = self.recent_runs(scope=scope, limit=run_limit)
        expectations = self.expectations(scope=scope, limit=100)
        signals = self.signals(scope=scope, limit=signal_limit)

        severity_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
        }
        for item in active:
            severity_counts[self._severity_label(float(item["risk_score"]))] += 1

        return {
            "version": self.VERSION,
            "formula_version": self.FORMULA_VERSION,
            "scope": scope,
            "summary": {
                "awareness_score": float(
                    situation.get("awareness_score") or 0.0
                ),
                "observed_objects": int(
                    sum(
                        int(value or 0)
                        for value in (
                            situation.get("object_counts") or {}
                        ).values()
                    )
                ),
                "active_incidents": len(active),
                "requires_attention": sum(
                    1
                    for item in active
                    if float(item["attention_score"]) >= threshold
                ),
                "critical": severity_counts["critical"],
                "high": severity_counts["high"],
                "expectations": len(
                    [
                        item
                        for item in expectations
                        if item["status"] in {"pending", "overdue"}
                    ]
                ),
                "overdue_expectations": len(
                    [
                        item
                        for item in expectations
                        if item["status"] == "overdue"
                    ]
                ),
                "attention_threshold": threshold,
            },
            "situation": situation,
            "incidents": incidents,
            "signals": signals,
            "expectations": expectations,
            "attention_profile": profile,
            "severity_counts": severity_counts,
            "runs": runs,
            "principles": [
                "Айши сообщает только о наблюдаемых локальных сигналах и явно хранит evidence.",
                "Высокий risk score не означает доказанную ошибку; confidence и verification_state показываются отдельно.",
                "Attention Manager подавляет повторяющийся шум и учитывает обратную связь Господина.",
                "Информационный инцидент не является выполненным действием.",
                "Любое изменяющее действие остаётся за Permission Gate, одобрением и ExecutionCoordinator.",
                "Исчезнувшее условие автоматически закрывает активный инцидент вместо вечного уведомления.",
            ],
        }

    def prompt_block(self, *, scope: str, limit: int = 6) -> str:
        active = self.incidents(scope=scope, status="active", limit=limit)
        lines = [
            "Proactive Intelligence Айшин.",
            "Наблюдение не является доказанным фактом ошибки, если verification_state не подтверждён.",
            "Не утверждай, что действие выполнено: инциденты только информируют и предлагают следующий шаг.",
        ]
        if not active:
            lines.append("- Активных ситуаций, требующих внимания, нет.")
            return "\n".join(lines)
        lines.append("Активные ситуации:")
        for item in active[:limit]:
            lines.append(
                f"- #{item['id']} [{self._severity_label(float(item['risk_score']))}] "
                f"{item['title']} "
                f"(risk={float(item['risk_score']):.2f}, "
                f"attention={float(item['attention_score']):.2f}, "
                f"confidence={float(item['confidence']):.2f}, "
                f"verification={item['verification_state']})."
            )
        return "\n".join(lines)

    def incidents(
        self,
        *,
        scope: str,
        status: str | None = "active",
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with connect() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM proactive_incidents
                       WHERE scope=? AND status=?
                       ORDER BY attention_score DESC, risk_score DESC, id DESC
                       LIMIT ?""",
                    (scope, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM proactive_incidents
                       WHERE scope=?
                       ORDER BY
                         CASE status
                           WHEN 'active' THEN 0
                           WHEN 'snoozed' THEN 1
                           ELSE 2
                         END,
                         attention_score DESC,
                         id DESC
                       LIMIT ?""",
                    (scope, limit),
                ).fetchall()
        return [self._decode_incident(dict(row)) for row in rows]

    def incident(self, incident_id: int, *, scope: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM proactive_incidents
                   WHERE id=? AND scope=?""",
                (incident_id, scope),
            ).fetchone()
        return self._decode_incident(dict(row)) if row else None

    def signals(self, *, scope: str, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proactive_signals
                   WHERE scope=?
                   ORDER BY attention_score DESC, last_seen_at DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = self._safe_json(
                item.pop("details_json"),
                {},
            )
            result.append(item)
        return result

    def expectations(self, *, scope: str, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proactive_expectations
                   WHERE scope=?
                   ORDER BY
                     CASE status
                       WHEN 'overdue' THEN 0
                       WHEN 'pending' THEN 1
                       ELSE 2
                     END,
                     due_at,
                     id DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = self._safe_json(
                item.pop("details_json"),
                {},
            )
            result.append(item)
        return result

    def feedback(
        self,
        incident_id: int,
        *,
        scope: str,
        feedback: str,
        reason: str = "",
    ) -> dict:
        feedback = (feedback or "").strip().casefold()
        allowed = {
            "useful",
            "noisy",
            "false_positive",
            "handled",
            "resolved",
            "snooze",
        }
        if feedback not in allowed:
            raise ValueError(
                "feedback must be useful, noisy, false_positive, handled, "
                "resolved or snooze"
            )

        incident = self.incident(incident_id, scope=scope)
        if incident is None:
            raise ValueError("incident not found in scope")

        with connect() as conn:
            conn.execute(
                """INSERT INTO proactive_attention_feedback(
                       scope, incident_id, feedback, reason
                   ) VALUES (?, ?, ?, ?)""",
                (scope, incident_id, feedback, reason[:500]),
            )

            new_status = incident["status"]
            resolved_at = None
            snoozed_until = incident.get("snoozed_until")

            if feedback in {"noisy", "false_positive"}:
                new_status = "dismissed"
                resolved_at = datetime.now(timezone.utc).isoformat()
            elif feedback in {"handled", "resolved"}:
                new_status = "resolved"
                resolved_at = datetime.now(timezone.utc).isoformat()
            elif feedback == "snooze":
                new_status = "snoozed"
                snoozed_until = (
                    datetime.now(timezone.utc) + timedelta(hours=24)
                ).isoformat()
            elif feedback == "useful" and incident["status"] == "snoozed":
                new_status = "active"
                snoozed_until = None

            conn.execute(
                """UPDATE proactive_incidents
                   SET status=?,
                       resolved_at=COALESCE(?, resolved_at),
                       snoozed_until=?,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (
                    new_status,
                    resolved_at,
                    snoozed_until,
                    incident_id,
                    scope,
                ),
            )
            conn.commit()

        if feedback in {
            "noisy",
            "false_positive",
            "handled",
            "resolved",
        }:
            self._dismiss_pending_decision(incident)

        profile = self._recalibrate_profile(scope=scope)
        self.events.emit(
            "proactive.intelligence.feedback",
            scope=scope,
            payload={
                "incident_id": incident_id,
                "feedback": feedback,
                "new_threshold": profile["calibrated_threshold"],
            },
            importance=0.25,
        )
        return {
            "incident": self.incident(incident_id, scope=scope),
            "attention_profile": profile,
        }

    def attention_profile(self, *, scope: str) -> dict:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM proactive_attention_profile
                   WHERE scope=?""",
                (scope,),
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO proactive_attention_profile(scope)
                       VALUES (?)""",
                    (scope,),
                )
                conn.commit()
                row = conn.execute(
                    """SELECT * FROM proactive_attention_profile
                       WHERE scope=?""",
                    (scope,),
                ).fetchone()
        return dict(row)

    def recent_runs(self, *, scope: str, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proactive_intelligence_runs
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["stats"] = self._safe_json(
                item.pop("stats_json"),
                {},
            )
            result.append(item)
        return result

    def _build_situation(self, *, scope: str) -> dict:
        source_health: dict[str, bool] = {}
        state: dict[str, Any] = {}
        object_counts: dict[str, int] = {}

        def scalar(
            conn: Any,
            query: str,
            params: tuple = (),
            default: float = 0.0,
        ) -> float:
            row = conn.execute(query, params).fetchone()
            if not row:
                return default
            value = row[0]
            return float(value or default)

        with connect() as conn:
            try:
                entities = int(
                    scalar(
                        conn,
                        "SELECT COUNT(*) FROM entities WHERE scope=?",
                        (scope,),
                    )
                )
                relations = int(
                    scalar(
                        conn,
                        "SELECT COUNT(*) FROM relations WHERE scope=?",
                        (scope,),
                    )
                )
                entity_types = {
                    str(row["entity_type"]): int(row["count"])
                    for row in conn.execute(
                        """SELECT entity_type, COUNT(*) AS count
                           FROM entities WHERE scope=?
                           GROUP BY entity_type ORDER BY count DESC""",
                        (scope,),
                    ).fetchall()
                }
                source_health["graph"] = True
            except Exception:
                entities = relations = 0
                entity_types = {}
                source_health["graph"] = False

            try:
                active_memories = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM memories
                           WHERE scope=? AND status='active'""",
                        (scope,),
                    )
                )
                stale_knowledge = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM knowledge_trust
                           WHERE scope=? AND trust_level='stale'""",
                        (scope,),
                    )
                )
                trusted_knowledge = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM knowledge_trust
                           WHERE scope=? AND trust_level='trusted'""",
                        (scope,),
                    )
                )
                source_health["memory"] = True
            except Exception:
                active_memories = stale_knowledge = trusted_knowledge = 0
                source_health["memory"] = False

            try:
                goals_open = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM goals
                           WHERE scope=? AND status NOT IN
                           ('completed','cancelled','closed')""",
                        (scope,),
                    )
                )
                tasks_open = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM tasks
                           WHERE scope=? AND status NOT IN
                           ('completed','cancelled','closed')""",
                        (scope,),
                    )
                )
                tasks_blocked = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM tasks
                           WHERE scope=? AND status='blocked'""",
                        (scope,),
                    )
                )
                tasks_overdue = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM tasks
                           WHERE scope=?
                             AND due_at IS NOT NULL
                             AND status NOT IN ('completed','cancelled','closed')
                             AND datetime(due_at) < datetime('now')""",
                        (scope,),
                    )
                )
                source_health["planner"] = True
            except Exception:
                goals_open = tasks_open = tasks_blocked = tasks_overdue = 0
                source_health["planner"] = False

            try:
                unresolved_verifications = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM verification_runs
                           WHERE scope=?
                             AND unresolved_json NOT IN ('[]','', '{}')
                             AND datetime(created_at) >= datetime('now','-30 days')""",
                        (scope,),
                    )
                )
                source_health["verification"] = True
            except Exception:
                unresolved_verifications = 0
                source_health["verification"] = False

            try:
                fading_skills = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM growth_skills
                           WHERE scope=? AND lifecycle='fading'""",
                        (scope,),
                    )
                )
                mastered_skills = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM growth_skills
                           WHERE scope=? AND lifecycle='mastered'""",
                        (scope,),
                    )
                )
                source_health["learning"] = True
            except Exception:
                fading_skills = mastered_skills = 0
                source_health["learning"] = False

            try:
                failed_routes = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM cognitive_intelligence_routes
                           WHERE scope=?
                             AND completed_at IS NOT NULL
                             AND successful=0
                             AND datetime(completed_at) >= datetime('now','-7 days')""",
                        (scope,),
                    )
                )
                source_health["cognition"] = True
            except Exception:
                failed_routes = 0
                source_health["cognition"] = False

            try:
                execution_failures = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM execution_attempts
                           WHERE scope=?
                             AND status IN ('failed','stale_or_blocked')
                             AND datetime(created_at) >= datetime('now','-7 days')""",
                        (scope,),
                    )
                )
                source_health["execution"] = True
            except Exception:
                execution_failures = 0
                source_health["execution"] = False

            try:
                pending_decisions = int(
                    scalar(
                        conn,
                        """SELECT COUNT(*) FROM proactive_decisions
                           WHERE scope=? AND status='pending'""",
                        (scope,),
                    )
                )
                source_health["proactive"] = True
            except Exception:
                pending_decisions = 0
                source_health["proactive"] = False

        try:
            sensor_readings = self.sensors.scan(
                scope=scope,
                persist=False,
            )
            sensor_attention = len(
                [
                    item
                    for item in sensor_readings
                    if item.get("status") not in {"ok"}
                ]
            )
            source_health["sensors"] = True
        except Exception:
            sensor_readings = []
            sensor_attention = 0
            source_health["sensors"] = False

        object_counts.update(
            {
                "entities": entities,
                "relations": relations,
                "active_memories": active_memories,
                "open_goals": goals_open,
                "open_tasks": tasks_open,
                "pending_decisions": pending_decisions,
                "mastered_skills": mastered_skills,
                "trusted_knowledge": trusted_knowledge,
            }
        )
        state.update(
            {
                "entities": entities,
                "relations": relations,
                "entity_types": entity_types,
                "active_memories": active_memories,
                "trusted_knowledge": trusted_knowledge,
                "stale_knowledge": stale_knowledge,
                "open_goals": goals_open,
                "open_tasks": tasks_open,
                "blocked_tasks": tasks_blocked,
                "overdue_tasks": tasks_overdue,
                "unresolved_verifications": unresolved_verifications,
                "mastered_skills": mastered_skills,
                "fading_skills": fading_skills,
                "failed_routes_7d": failed_routes,
                "execution_failures_7d": execution_failures,
                "pending_decisions": pending_decisions,
                "sensor_attention": sensor_attention,
                "sensor_channels": len(sensor_readings),
                "source_health": source_health,
            }
        )
        return {
            "object_counts": object_counts,
            "state": state,
        }

    def _collect_signals(
        self,
        *,
        scope: str,
        situation: dict,
        previous: dict | None,
        delta: dict,
    ) -> list[dict]:
        signals: list[dict] = []
        signals.extend(self._planner_signals(scope=scope))
        signals.extend(self._sensor_signals(scope=scope))
        signals.extend(self._verification_signals(scope=scope))
        signals.extend(self._execution_signals(scope=scope))
        signals.extend(self._cognitive_regression_signals(scope=scope))
        signals.extend(self._learning_signals(scope=scope))
        signals.extend(
            self._knowledge_signals(
                scope=scope,
                situation=situation,
                previous=previous,
            )
        )
        signals.extend(
            self._delta_signals(
                scope=scope,
                delta=delta,
                situation=situation,
            )
        )

        unique: dict[str, dict] = {}
        for signal in signals:
            key = str(signal["fingerprint"])
            current = unique.get(key)
            if current is None or float(signal["risk_score"]) > float(
                current["risk_score"]
            ):
                unique[key] = signal
        return list(unique.values())

    def _planner_signals(self, *, scope: str) -> list[dict]:
        result = []
        for notice in self.planner.inspect(scope=scope):
            if notice.goal_id is not None:
                identity = f"goal:{notice.goal_id}"
            elif notice.task_id is not None:
                identity = f"task:{notice.task_id}"
            else:
                identity = notice.message
            fingerprint = self._fingerprint(
                "planner",
                notice.code,
                identity,
                scope,
            )
            warning = notice.severity == "warning"
            severity = 0.74 if warning else 0.46
            urgency = 0.82 if notice.code == "task_overdue" else (
                0.66 if notice.code == "task_blocked" else 0.42
            )
            result.append(
                self._signal(
                    fingerprint=fingerprint,
                    signal_type=notice.code,
                    source="planner",
                    subject_type=(
                        "task" if notice.task_id is not None else "goal"
                    ),
                    subject_id=(
                        str(notice.task_id)
                        if notice.task_id is not None
                        else str(notice.goal_id or "")
                    ),
                    title=notice.message,
                    details={
                        "severity": notice.severity,
                        "code": notice.code,
                        "task_id": notice.task_id,
                        "goal_id": notice.goal_id,
                        "evidence": [
                            {
                                "source": "planner.inspect",
                                "message": notice.message,
                            }
                        ],
                        "suggested_action": self._suggest_for_planner(
                            notice.code
                        ),
                    },
                    severity=severity,
                    confidence=0.99,
                    impact=0.68 if warning else 0.48,
                    urgency=urgency,
                )
            )

        now = datetime.now(timezone.utc)
        with connect() as conn:
            rows = conn.execute(
                """SELECT id, title, status, updated_at, due_at, priority
                   FROM tasks
                   WHERE scope=?
                     AND status IN ('open','in_progress')
                   ORDER BY updated_at ASC LIMIT 200""",
                (scope,),
            ).fetchall()
        for row in rows:
            updated = self._parse_time(row["updated_at"])
            if updated is None:
                continue
            age_days = (now - updated).total_seconds() / 86400.0
            if age_days < 7:
                continue
            if row["due_at"] and self._parse_time(row["due_at"]):
                continue
            severity = min(0.72, 0.42 + age_days / 90.0)
            urgency = min(0.68, 0.30 + age_days / 60.0)
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "planner",
                        "stale_task",
                        row["id"],
                        scope,
                    ),
                    signal_type="stale_task",
                    source="planner",
                    subject_type="task",
                    subject_id=str(row["id"]),
                    title=(
                        f"Задача «{row['title']}» не менялась "
                        f"{int(age_days)} дн."
                    ),
                    details={
                        "age_days": round(age_days, 1),
                        "status": row["status"],
                        "priority": float(row["priority"] or 0.5),
                        "evidence": [
                            {
                                "source": "tasks.updated_at",
                                "value": row["updated_at"],
                            }
                        ],
                        "suggested_action": (
                            "Проверить актуальность задачи и определить "
                            "следующий конкретный шаг."
                        ),
                    },
                    severity=severity,
                    confidence=0.98,
                    impact=max(0.45, float(row["priority"] or 0.5)),
                    urgency=urgency,
                )
            )
        return result

    def _sensor_signals(self, *, scope: str) -> list[dict]:
        result = []
        try:
            readings = self.sensors.scan(scope=scope, persist=False)
        except Exception:
            return result
        for reading in readings:
            if reading.get("status") in {"ok"}:
                continue
            sensor = str(reading.get("sensor") or "unknown")
            status = str(reading.get("status") or "attention")
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "sensor",
                        sensor,
                        status,
                        scope,
                    ),
                    signal_type="sensor_attention",
                    source="sensor",
                    subject_type="sensor",
                    subject_id=sensor,
                    title=f"Сенсор {sensor}: {status}",
                    details={
                        "reading": reading,
                        "evidence": [
                            {
                                "source": "SensorHub",
                                "sensor": sensor,
                                "status": status,
                            }
                        ],
                        "suggested_action": (
                            "Открыть диагностику сенсора и проверить "
                            "причину состояния."
                        ),
                    },
                    severity=float(reading.get("importance") or 0.55),
                    confidence=0.92,
                    impact=float(reading.get("importance") or 0.55),
                    urgency=0.62,
                )
            )
        return result

    def _verification_signals(self, *, scope: str) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT id, query, final_status, unresolved_json,
                          findings_json, created_at
                   FROM verification_runs
                   WHERE scope=?
                     AND unresolved_json NOT IN ('[]','', '{}')
                     AND datetime(created_at) >= datetime('now','-14 days')
                   ORDER BY id DESC LIMIT 30""",
                (scope,),
            ).fetchall()
        result = []
        for row in rows:
            unresolved = self._safe_json(row["unresolved_json"], [])
            if not unresolved:
                continue
            text = " ".join(str(item) for item in unresolved).casefold()
            conflict = "противореч" in text or "conflict" in text
            severity = 0.82 if conflict else 0.62
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "verification",
                        row["id"],
                        scope,
                    ),
                    signal_type=(
                        "verified_conflict"
                        if conflict
                        else "unresolved_verification"
                    ),
                    source="verification",
                    subject_type="verification_run",
                    subject_id=str(row["id"]),
                    title=(
                        "Обнаружено противоречие после перепроверки"
                        if conflict
                        else "После перепроверки остались нерешённые данные"
                    ),
                    details={
                        "query": str(row["query"] or "")[:300],
                        "unresolved": unresolved[:8],
                        "findings": self._safe_json(
                            row["findings_json"],
                            [],
                        )[:8],
                        "evidence": [
                            {
                                "source": "verification_runs",
                                "id": int(row["id"]),
                                "created_at": row["created_at"],
                            }
                        ],
                        "suggested_action": (
                            "Открыть evidence перепроверки и уточнить "
                            "противоречащие или отсутствующие данные."
                        ),
                    },
                    severity=severity,
                    confidence=0.96,
                    impact=0.78 if conflict else 0.62,
                    urgency=0.72 if conflict else 0.48,
                )
            )
        return result

    def _execution_signals(self, *, scope: str) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT id, decision_id, tool_name, status,
                          revalidation_json, tool_result_json, created_at
                   FROM execution_attempts
                   WHERE scope=?
                     AND status IN ('failed','stale_or_blocked')
                     AND datetime(created_at) >= datetime('now','-7 days')
                   ORDER BY id DESC LIMIT 30""",
                (scope,),
            ).fetchall()
        result = []
        for row in rows:
            revalidation = self._safe_json(
                row["revalidation_json"],
                {},
            )
            reason = str(revalidation.get("reason") or row["status"])
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "execution",
                        row["id"],
                        scope,
                    ),
                    signal_type="execution_failure",
                    source="execution",
                    subject_type="execution_attempt",
                    subject_id=str(row["id"]),
                    title=(
                        f"Действие {row['tool_name']} не завершено: {reason}"
                    ),
                    details={
                        "decision_id": row["decision_id"],
                        "tool_name": row["tool_name"],
                        "status": row["status"],
                        "revalidation": revalidation,
                        "evidence": [
                            {
                                "source": "execution_attempts",
                                "id": int(row["id"]),
                            }
                        ],
                        "suggested_action": (
                            "Проверить состояние данных и сформировать "
                            "новое одобрение только после повторной проверки."
                        ),
                    },
                    severity=0.78,
                    confidence=0.99,
                    impact=0.78,
                    urgency=0.66,
                )
            )
        return result

    def _cognitive_regression_signals(
        self,
        *,
        scope: str,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT task_family, outcome_score, successful, completed_at
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND outcome_score IS NOT NULL
                   ORDER BY id DESC LIMIT 240""",
                (scope,),
            ).fetchall()

        grouped: dict[str, list[float]] = {}
        for row in rows:
            family = str(row["task_family"] or "general")
            grouped.setdefault(family, []).append(
                float(row["outcome_score"] or 0.0)
            )

        result = []
        for family, outcomes in grouped.items():
            if len(outcomes) < 6:
                continue
            recent = outcomes[:3]
            baseline = outcomes[3:10]
            if len(baseline) < 3:
                continue
            recent_avg = sum(recent) / len(recent)
            baseline_avg = sum(baseline) / len(baseline)
            regression = baseline_avg - recent_avg
            if recent_avg >= 0.60 and regression < 0.15:
                continue

            severity = self._clamp(
                0.48
                + max(0.0, 0.60 - recent_avg) * 0.7
                + max(0.0, regression) * 0.8,
                0.0,
                0.88,
            )
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "cognitive_regression",
                        family,
                        scope,
                    ),
                    signal_type="cognitive_regression",
                    source="cognitive_intelligence",
                    subject_type="task_family",
                    subject_id=family,
                    title=(
                        f"Качество решений в области «{family}» "
                        "снизилось относительно предыдущего опыта"
                    ),
                    details={
                        "recent_average": round(recent_avg, 4),
                        "baseline_average": round(baseline_avg, 4),
                        "regression": round(regression, 4),
                        "samples": len(outcomes),
                        "evidence": [
                            {
                                "source": "cognitive_intelligence_routes",
                                "recent": recent,
                                "baseline": baseline,
                            }
                        ],
                        "suggested_action": (
                            "Усилить Verification для этой области и "
                            "проверить деградацию связанных навыков."
                        ),
                    },
                    severity=severity,
                    confidence=min(0.96, 0.70 + len(outcomes) / 100.0),
                    impact=0.72,
                    urgency=0.54,
                )
            )
        return result

    def _learning_signals(self, *, scope: str) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT id, title, mastery_score, reliability,
                          evidence_count, freshness, updated_at
                   FROM growth_skills
                   WHERE scope=? AND lifecycle='fading'
                   ORDER BY mastery_score DESC, evidence_count DESC
                   LIMIT 30""",
                (scope,),
            ).fetchall()
        result = []
        for row in rows:
            evidence_count = float(row["evidence_count"] or 0.0)
            if evidence_count < 4:
                continue
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "fading_skill",
                        row["id"],
                        scope,
                    ),
                    signal_type="skill_degradation",
                    source="learning",
                    subject_type="growth_skill",
                    subject_id=str(row["id"]),
                    title=f"Навык «{row['title']}» начал терять актуальность",
                    details={
                        "mastery_score": float(row["mastery_score"] or 0.0),
                        "reliability": float(row["reliability"] or 0.0),
                        "evidence_count": evidence_count,
                        "freshness": float(row["freshness"] or 0.0),
                        "evidence": [
                            {
                                "source": "growth_skills",
                                "id": int(row["id"]),
                                "updated_at": row["updated_at"],
                            }
                        ],
                        "suggested_action": (
                            "Не полагаться на навык без новой проверки; "
                            "собрать свежий подтверждённый опыт."
                        ),
                    },
                    severity=0.54,
                    confidence=0.92,
                    impact=0.60,
                    urgency=0.34,
                )
            )
        return result

    def _knowledge_signals(
        self,
        *,
        scope: str,
        situation: dict,
        previous: dict | None,
    ) -> list[dict]:
        stale = int(situation["state"].get("stale_knowledge") or 0)
        if stale <= 0:
            return []
        previous_stale = int(
            (
                (previous or {}).get("state") or {}
            ).get("stale_knowledge")
            or 0
        )
        increase = max(0, stale - previous_stale)
        severity = min(0.72, 0.38 + stale / 120.0 + increase / 30.0)
        return [
            self._signal(
                fingerprint=self._fingerprint(
                    "stale_knowledge_pool",
                    scope,
                ),
                signal_type="stale_knowledge_pool",
                source="knowledge",
                subject_type="knowledge_trust",
                subject_id="stale",
                title=f"Устаревающих знаний: {stale}",
                details={
                    "stale_count": stale,
                    "previous_count": previous_stale,
                    "increase": increase,
                    "evidence": [
                        {
                            "source": "knowledge_trust",
                            "trust_level": "stale",
                            "count": stale,
                        }
                    ],
                    "suggested_action": (
                        "При использовании этих знаний требовать свежую "
                        "проверку и постепенно обновлять evidence."
                    ),
                },
                severity=severity,
                confidence=0.98,
                impact=min(0.72, 0.40 + stale / 100.0),
                urgency=0.28 + min(0.28, increase / 40.0),
            )
        ]

    def _delta_signals(
        self,
        *,
        scope: str,
        delta: dict,
        situation: dict,
    ) -> list[dict]:
        result = []
        for key, config in {
            "unresolved_verifications": (
                "Резко выросло число нерешённых перепроверок",
                3,
                0.66,
            ),
            "execution_failures_7d": (
                "Увеличилось число неуспешных исполнений",
                2,
                0.72,
            ),
            "failed_routes_7d": (
                "Увеличилось число слабых когнитивных маршрутов",
                3,
                0.58,
            ),
        }.items():
            change = float(delta.get(key, 0.0))
            title, threshold, severity = config
            if change < threshold:
                continue
            result.append(
                self._signal(
                    fingerprint=self._fingerprint(
                        "situation_delta",
                        key,
                        scope,
                    ),
                    signal_type="situation_delta",
                    source="situation_delta",
                    subject_type="situation_metric",
                    subject_id=key,
                    title=title,
                    details={
                        "metric": key,
                        "change": change,
                        "current": situation["state"].get(key),
                        "evidence": [
                            {
                                "source": "situation_snapshots",
                                "delta": change,
                            }
                        ],
                        "suggested_action": (
                            "Открыть ситуационную историю и проверить "
                            "источник резкого изменения."
                        ),
                    },
                    severity=severity,
                    confidence=0.86,
                    impact=severity,
                    urgency=0.58,
                )
            )
        return result

    def _signal(
        self,
        *,
        fingerprint: str,
        signal_type: str,
        source: str,
        subject_type: str,
        subject_id: str,
        title: str,
        details: dict,
        severity: float,
        confidence: float,
        impact: float,
        urgency: float,
    ) -> dict:
        severity = self._clamp(severity)
        confidence = self._clamp(confidence)
        impact = self._clamp(impact)
        urgency = self._clamp(urgency)
        risk = self._clamp(
            0.30 * severity
            + 0.25 * confidence
            + 0.25 * impact
            + 0.20 * urgency
        )
        source_reliability = self.SOURCE_RELIABILITY.get(source, 0.80)
        attention = self._clamp(
            risk * (0.82 + 0.18 * source_reliability)
        )
        return {
            "fingerprint": fingerprint,
            "signal_type": signal_type,
            "source": source,
            "subject_type": subject_type,
            "subject_id": str(subject_id or ""),
            "title": str(title)[:500],
            "details": details,
            "severity": round(severity, 5),
            "confidence": round(confidence, 5),
            "impact": round(impact, 5),
            "urgency": round(urgency, 5),
            "risk_score": round(risk, 5),
            "attention_score": round(attention, 5),
        }

    def _upsert_signal(self, *, scope: str, signal: dict) -> dict:
        attention = self._calibrated_attention(
            scope=scope,
            incident_type=signal["signal_type"],
            base=float(signal["attention_score"]),
        )
        with connect() as conn:
            row = conn.execute(
                """SELECT id, occurrences FROM proactive_signals
                   WHERE scope=? AND fingerprint=?""",
                (scope, signal["fingerprint"]),
            ).fetchone()
            if row:
                conn.execute(
                    """UPDATE proactive_signals
                       SET signal_type=?, source=?, subject_type=?,
                           subject_id=?, title=?, details_json=?,
                           severity=?, confidence=?, impact=?, urgency=?,
                           risk_score=?, attention_score=?,
                           status='observed',
                           occurrences=occurrences+1,
                           last_seen_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        signal["signal_type"],
                        signal["source"],
                        signal["subject_type"],
                        signal["subject_id"],
                        signal["title"],
                        json.dumps(
                            signal["details"],
                            ensure_ascii=False,
                        ),
                        signal["severity"],
                        signal["confidence"],
                        signal["impact"],
                        signal["urgency"],
                        signal["risk_score"],
                        attention,
                        int(row["id"]),
                    ),
                )
                signal_id = int(row["id"])
            else:
                cur = conn.execute(
                    """INSERT INTO proactive_signals(
                           scope, fingerprint, signal_type, source,
                           subject_type, subject_id, title, details_json,
                           severity, confidence, impact, urgency,
                           risk_score, attention_score
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        scope,
                        signal["fingerprint"],
                        signal["signal_type"],
                        signal["source"],
                        signal["subject_type"],
                        signal["subject_id"],
                        signal["title"],
                        json.dumps(
                            signal["details"],
                            ensure_ascii=False,
                        ),
                        signal["severity"],
                        signal["confidence"],
                        signal["impact"],
                        signal["urgency"],
                        signal["risk_score"],
                        attention,
                    ),
                )
                signal_id = int(cur.lastrowid)
            conn.commit()
            stored = conn.execute(
                """SELECT * FROM proactive_signals WHERE id=?""",
                (signal_id,),
            ).fetchone()
        return dict(stored)

    def _upsert_incident(
        self,
        *,
        scope: str,
        signal: dict,
        signal_id: int,
    ) -> tuple[dict, bool]:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM proactive_incidents
                   WHERE scope=? AND fingerprint=?""",
                (scope, signal["fingerprint"]),
            ).fetchone()
            evidence = signal["details"].get("evidence") or []
            suggested_action = str(
                signal["details"].get("suggested_action") or ""
            )
            verification_state = self._verification_state(signal)

            if row:
                item = dict(row)
                status = str(item["status"])
                snoozed_until = self._parse_time(item.get("snoozed_until"))
                if status == "snoozed":
                    if snoozed_until and snoozed_until > datetime.now(timezone.utc):
                        new_status = "snoozed"
                    else:
                        new_status = "active"
                elif status in {"resolved", "dismissed"}:
                    new_status = "active"
                else:
                    new_status = status

                conn.execute(
                    """UPDATE proactive_incidents
                       SET signal_id=?, incident_type=?, source=?,
                           subject_type=?, subject_id=?, title=?, summary=?,
                           evidence_json=?, suggested_action=?,
                           severity=?, confidence=?, impact=?, urgency=?,
                           risk_score=?, attention_score=?,
                           verification_state=?, status=?,
                           occurrences=occurrences+1,
                           last_seen_at=CURRENT_TIMESTAMP,
                           resolved_at=NULL,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        signal_id,
                        signal["signal_type"],
                        signal["source"],
                        signal["subject_type"],
                        signal["subject_id"],
                        signal["title"],
                        self._incident_summary(signal),
                        json.dumps(evidence, ensure_ascii=False),
                        suggested_action,
                        signal["severity"],
                        signal["confidence"],
                        signal["impact"],
                        signal["urgency"],
                        signal["risk_score"],
                        self._calibrated_attention(
                            scope=scope,
                            incident_type=signal["signal_type"],
                            base=float(signal["attention_score"]),
                        ),
                        verification_state,
                        new_status,
                        int(item["id"]),
                    ),
                )
                incident_id = int(item["id"])
                created = False
            else:
                cur = conn.execute(
                    """INSERT INTO proactive_incidents(
                           scope, fingerprint, signal_id, incident_type,
                           source, subject_type, subject_id, title, summary,
                           evidence_json, suggested_action, severity,
                           confidence, impact, urgency, risk_score,
                           attention_score, verification_state
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                 ?, ?, ?, ?)""",
                    (
                        scope,
                        signal["fingerprint"],
                        signal_id,
                        signal["signal_type"],
                        signal["source"],
                        signal["subject_type"],
                        signal["subject_id"],
                        signal["title"],
                        self._incident_summary(signal),
                        json.dumps(evidence, ensure_ascii=False),
                        suggested_action,
                        signal["severity"],
                        signal["confidence"],
                        signal["impact"],
                        signal["urgency"],
                        signal["risk_score"],
                        self._calibrated_attention(
                            scope=scope,
                            incident_type=signal["signal_type"],
                            base=float(signal["attention_score"]),
                        ),
                        verification_state,
                    ),
                )
                incident_id = int(cur.lastrowid)
                created = True
            conn.commit()
            stored = conn.execute(
                """SELECT * FROM proactive_incidents WHERE id=?""",
                (incident_id,),
            ).fetchone()

        incident = self._decode_incident(dict(stored))
        if created:
            self.events.emit(
                "proactive.incident.created",
                scope=scope,
                payload={
                    "incident_id": incident_id,
                    "incident_type": incident["incident_type"],
                    "risk_score": incident["risk_score"],
                    "attention_score": incident["attention_score"],
                    "verification_state": incident["verification_state"],
                },
                importance=min(
                    0.95,
                    max(0.35, float(incident["risk_score"])),
                ),
            )
        return incident, created

    def _ensure_decision(
        self,
        *,
        scope: str,
        incident: dict,
    ) -> tuple[int | None, bool]:
        decision_id = incident.get("decision_id")
        if decision_id:
            decision = get_proactive_decision(int(decision_id), scope)
            if decision and decision["status"] in {
                "pending",
                "approved",
            }:
                return int(decision_id), False

        existing = None
        with connect() as conn:
            row = conn.execute(
                """SELECT id FROM proactive_decisions
                   WHERE scope=? AND fingerprint=? AND status='pending'
                   ORDER BY id DESC LIMIT 1""",
                (scope, incident["fingerprint"]),
            ).fetchone()
            existing = int(row["id"]) if row else None
        if existing is not None:
            return existing, False

        decision_id = create_proactive_decision(
            scope=scope,
            fingerprint=incident["fingerprint"],
            source=f"proactive-intelligence:{incident['incident_type']}",
            title=incident["title"],
            rationale=(
                f"{incident['summary']} "
                f"Risk={float(incident['risk_score']):.2f}; "
                f"attention={float(incident['attention_score']):.2f}; "
                f"verification={incident['verification_state']}. "
                f"{incident['suggested_action']}"
            ),
            priority=float(incident["attention_score"]),
            confidence=float(incident["confidence"]),
            tool_name=None,
            capability="proactive_notice",
            arguments={},
            preview={
                "incident_id": incident["id"],
                "risk_score": incident["risk_score"],
                "attention_score": incident["attention_score"],
                "verification_state": incident["verification_state"],
            },
        )
        return int(decision_id), True

    def _bind_decision(
        self,
        *,
        scope: str,
        incident_id: int,
        decision_id: int,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE proactive_incidents
                   SET decision_id=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (decision_id, incident_id, scope),
            )
            conn.commit()

    def _resolve_absent(
        self,
        *,
        scope: str,
        active_fingerprints: set[str],
    ) -> int:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proactive_incidents
                   WHERE scope=? AND status IN ('active','snoozed')""",
                (scope,),
            ).fetchall()
            resolved = 0
            for row in rows:
                item = dict(row)
                if str(item["fingerprint"]) in active_fingerprints:
                    continue
                conn.execute(
                    """UPDATE proactive_incidents
                       SET status='resolved',
                           resolved_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (int(item["id"]),),
                )
                resolved += 1
                decision_id = item.get("decision_id")
                if decision_id:
                    decision = get_proactive_decision(
                        int(decision_id),
                        scope,
                    )
                    if decision and decision["status"] == "pending":
                        try:
                            update_proactive_decision(
                                int(decision_id),
                                scope=scope,
                                status="dismissed",
                                execution={
                                    "reason": "proactive_condition_resolved"
                                },
                            )
                        except Exception:
                            pass
            conn.commit()
        return resolved

    def _sync_expectations(self, *, scope: str) -> None:
        now = datetime.now(timezone.utc)
        active_keys: set[str] = set()

        with connect() as conn:
            tasks = conn.execute(
                """SELECT id, title, status, due_at, goal_id, priority
                   FROM tasks WHERE scope=?""",
                (scope,),
            ).fetchall()
            goals = conn.execute(
                """SELECT id, title, status, priority
                   FROM goals WHERE scope=?""",
                (scope,),
            ).fetchall()

            open_task_goal_ids = {
                int(row["goal_id"])
                for row in tasks
                if row["goal_id"] is not None
                and str(row["status"]) not in {
                    "completed",
                    "cancelled",
                    "closed",
                }
            }

            for task in tasks:
                if not task["due_at"]:
                    continue
                key = f"task_due:{int(task['id'])}"
                active_keys.add(key)
                due = self._parse_time(task["due_at"])
                terminal = str(task["status"]) in {
                    "completed",
                    "cancelled",
                    "closed",
                }
                status = (
                    "resolved"
                    if terminal
                    else "overdue"
                    if due and due < now
                    else "pending"
                )
                self._upsert_expectation_conn(
                    conn,
                    scope=scope,
                    key=key,
                    subject_type="task",
                    subject_id=str(task["id"]),
                    title=f"Срок задачи «{task['title']}»",
                    expected_state="completed_or_reviewed_before_due",
                    source="planner:task_due",
                    confidence=1.0,
                    due_at=task["due_at"],
                    status=status,
                    details={
                        "goal_id": task["goal_id"],
                        "priority": float(task["priority"] or 0.5),
                    },
                )

            for goal in goals:
                if str(goal["status"]) in {
                    "completed",
                    "cancelled",
                    "closed",
                }:
                    continue
                if int(goal["id"]) in open_task_goal_ids:
                    continue
                key = f"goal_next_step:{int(goal['id'])}"
                active_keys.add(key)
                self._upsert_expectation_conn(
                    conn,
                    scope=scope,
                    key=key,
                    subject_type="goal",
                    subject_id=str(goal["id"]),
                    title=f"Следующий шаг по цели «{goal['title']}»",
                    expected_state="has_open_task",
                    source="planner:goal_without_tasks",
                    confidence=1.0,
                    due_at=None,
                    status="pending",
                    details={
                        "priority": float(goal["priority"] or 0.5),
                    },
                )

            rows = conn.execute(
                """SELECT expectation_key FROM proactive_expectations
                   WHERE scope=? AND status IN ('pending','overdue')""",
                (scope,),
            ).fetchall()
            for row in rows:
                key = str(row["expectation_key"])
                if key in active_keys:
                    continue
                conn.execute(
                    """UPDATE proactive_expectations
                       SET status='resolved',
                           resolved_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE scope=? AND expectation_key=?""",
                    (scope, key),
                )
            conn.commit()

    @staticmethod
    def _upsert_expectation_conn(
        conn: Any,
        *,
        scope: str,
        key: str,
        subject_type: str,
        subject_id: str,
        title: str,
        expected_state: str,
        source: str,
        confidence: float,
        due_at: str | None,
        status: str,
        details: dict,
    ) -> None:
        conn.execute(
            """INSERT INTO proactive_expectations(
                   scope, expectation_key, subject_type, subject_id,
                   title, expected_state, source, confidence, due_at,
                   status, details_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(scope, expectation_key) DO UPDATE SET
                   subject_type=excluded.subject_type,
                   subject_id=excluded.subject_id,
                   title=excluded.title,
                   expected_state=excluded.expected_state,
                   source=excluded.source,
                   confidence=excluded.confidence,
                   due_at=excluded.due_at,
                   status=excluded.status,
                   details_json=excluded.details_json,
                   resolved_at=CASE
                     WHEN excluded.status='resolved' THEN CURRENT_TIMESTAMP
                     ELSE NULL
                   END,
                   updated_at=CURRENT_TIMESTAMP""",
            (
                scope,
                key,
                subject_type,
                subject_id,
                title,
                expected_state,
                source,
                confidence,
                due_at,
                status,
                json.dumps(details, ensure_ascii=False),
            ),
        )

    def _latest_situation(self, *, scope: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM situation_snapshots
                   WHERE scope=? ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["object_counts"] = self._safe_json(
            item.pop("object_counts_json"),
            {},
        )
        item["state"] = self._safe_json(item.pop("state_json"), {})
        item["delta"] = self._safe_json(item.pop("delta_json"), {})
        return item

    def _store_situation(
        self,
        *,
        scope: str,
        trigger: str,
        awareness_score: float,
        situation: dict,
        delta: dict,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO situation_snapshots(
                       scope, trigger, awareness_score,
                       object_counts_json, state_json, delta_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    trigger,
                    round(float(awareness_score), 2),
                    json.dumps(
                        situation["object_counts"],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        situation["state"],
                        ensure_ascii=False,
                    ),
                    json.dumps(delta, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    @staticmethod
    def _situation_delta(
        previous: dict,
        current: dict,
    ) -> dict:
        delta = {}
        for key, value in current.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            old = previous.get(key)
            if isinstance(old, bool) or not isinstance(old, (int, float)):
                old = 0
            delta[key] = round(float(value) - float(old), 4)
        return delta

    def _awareness_score(
        self,
        *,
        situation: dict,
        signals: list[dict],
        profile: dict,
    ) -> dict:
        source_health = situation["state"].get("source_health") or {}
        source_coverage = (
            sum(1 for value in source_health.values() if value)
            / max(1, len(source_health))
        )
        temporal = 1.0
        grounding = (
            sum(
                1
                for signal in signals
                if signal.get("details", {}).get("evidence")
            )
            / len(signals)
            if signals
            else 1.0
        )
        feedback_total = (
            int(profile.get("useful_count") or 0)
            + int(profile.get("noisy_count") or 0)
            + int(profile.get("false_positive_count") or 0)
            + int(profile.get("handled_count") or 0)
        )
        calibration = 0.50 + 0.50 * self._saturation(
            feedback_total,
            20,
        )
        overall = 100.0 * (
            0.50 * source_coverage
            + 0.20 * temporal
            + 0.20 * grounding
            + 0.10 * calibration
        )
        return {
            "overall_score": round(overall, 1),
            "source_coverage": round(source_coverage, 4),
            "temporal_coverage": round(temporal, 4),
            "grounding": round(grounding, 4),
            "attention_calibration": round(calibration, 4),
            "feedback_samples": feedback_total,
        }

    @staticmethod
    def _saturation(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(
            1.0,
            1.0 - math.exp(-max(0.0, float(value)) / target),
        )

    def _calibrated_attention(
        self,
        *,
        scope: str,
        incident_type: str,
        base: float,
    ) -> float:
        with connect() as conn:
            rows = conn.execute(
                """SELECT f.feedback
                   FROM proactive_attention_feedback f
                   JOIN proactive_incidents i ON i.id=f.incident_id
                   WHERE f.scope=? AND i.incident_type=?
                   ORDER BY f.id DESC LIMIT 50""",
                (scope, incident_type),
            ).fetchall()
        if not rows:
            return round(self._clamp(base), 5)
        useful = sum(
            1
            for row in rows
            if row["feedback"] in {"useful", "handled", "resolved"}
        )
        noisy = sum(
            1
            for row in rows
            if row["feedback"] in {"noisy", "false_positive"}
        )
        total = max(1, useful + noisy)
        modifier = 0.08 * (useful / total) - 0.16 * (noisy / total)
        return round(self._clamp(base + modifier), 5)

    def _recalibrate_profile(self, *, scope: str) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT feedback, COUNT(*) AS count
                   FROM proactive_attention_feedback
                   WHERE scope=? GROUP BY feedback""",
                (scope,),
            ).fetchall()
            counts = {
                str(row["feedback"]): int(row["count"])
                for row in rows
            }
            useful = counts.get("useful", 0)
            noisy = counts.get("noisy", 0)
            false_positive = counts.get("false_positive", 0)
            handled = (
                counts.get("handled", 0)
                + counts.get("resolved", 0)
            )
            total = useful + noisy + false_positive + handled
            if total:
                noise_ratio = (noisy + false_positive) / total
                useful_ratio = (useful + handled) / total
                threshold = self._clamp(
                    0.48
                    + 0.18 * noise_ratio
                    - 0.06 * useful_ratio,
                    0.36,
                    0.70,
                )
            else:
                threshold = 0.48
            conn.execute(
                """INSERT INTO proactive_attention_profile(
                       scope, calibrated_threshold, useful_count,
                       noisy_count, false_positive_count, handled_count
                   ) VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope) DO UPDATE SET
                       calibrated_threshold=excluded.calibrated_threshold,
                       useful_count=excluded.useful_count,
                       noisy_count=excluded.noisy_count,
                       false_positive_count=excluded.false_positive_count,
                       handled_count=excluded.handled_count,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    threshold,
                    useful,
                    noisy,
                    false_positive,
                    handled,
                ),
            )
            conn.commit()
        return self.attention_profile(scope=scope)

    def _record_run(
        self,
        *,
        scope: str,
        trigger: str,
        awareness_score: float,
        signals: int,
        created: int,
        updated: int,
        resolved: int,
        decisions_created: int,
        duration_ms: int,
        stats: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO proactive_intelligence_runs(
                       scope, trigger, awareness_score, signals_observed,
                       incidents_created, incidents_updated,
                       incidents_resolved, decisions_created,
                       duration_ms, stats_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    trigger,
                    awareness_score,
                    signals,
                    created,
                    updated,
                    resolved,
                    decisions_created,
                    duration_ms,
                    json.dumps(stats, ensure_ascii=False),
                ),
            )
            conn.commit()

    @staticmethod
    def _incident_summary(signal: dict) -> str:
        return (
            f"Источник: {signal['source']}. "
            f"Severity={float(signal['severity']):.2f}; "
            f"confidence={float(signal['confidence']):.2f}; "
            f"impact={float(signal['impact']):.2f}; "
            f"urgency={float(signal['urgency']):.2f}."
        )

    @staticmethod
    def _verification_state(signal: dict) -> str:
        source = signal["source"]
        confidence = float(signal["confidence"])
        evidence = signal.get("details", {}).get("evidence") or []
        if source in {"planner", "execution"} and confidence >= 0.95:
            return "deterministic_confirmed"
        if source == "verification":
            return "verification_observed"
        if len(evidence) >= 2 and confidence >= 0.85:
            return "corroborated"
        if confidence >= 0.85:
            return "grounded_observation"
        return "needs_review"

    @classmethod
    def _severity_label(cls, score: float) -> str:
        for threshold, label in cls.SEVERITY_LABELS:
            if score >= threshold:
                return label
        return "low"

    @staticmethod
    def _suggest_for_planner(code: str) -> str:
        return {
            "task_overdue": (
                "Проверить актуальность срока, причину задержки и "
                "определить следующий шаг."
            ),
            "task_blocked": (
                "Открыть блокирующую причину и зависимость; не менять "
                "статус автоматически."
            ),
            "waiting_dependencies": (
                "Проверить незавершённые зависимости перед продолжением."
            ),
            "goal_without_tasks": (
                "Предложить конкретный следующий шаг по цели."
            ),
            "invalid_due_at": (
                "Исправить срок только после подтверждения корректной даты."
            ),
        }.get(
            code,
            "Открыть источник сигнала и проверить текущую ситуацию.",
        )

    @staticmethod
    def _decode_incident(item: dict) -> dict:
        item["evidence"] = ProactiveIntelligenceEngine._safe_json(
            item.pop("evidence_json"),
            [],
        )
        return item

    @staticmethod
    def _dismiss_pending_decision(incident: dict) -> None:
        decision_id = incident.get("decision_id")
        if not decision_id:
            return
        try:
            decision = get_proactive_decision(
                int(decision_id),
                str(incident["scope"]),
            )
            if decision and decision["status"] == "pending":
                update_proactive_decision(
                    int(decision_id),
                    scope=str(incident["scope"]),
                    status="dismissed",
                    execution={
                        "reason": "proactive_attention_feedback"
                    },
                )
        except Exception:
            return
