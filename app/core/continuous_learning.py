from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from ..db import connect
from .events import EventBus
from .learning_quality import LearningQualityGate
from .state import StateManager


@dataclass(frozen=True)
class LearningModeDecision:
    mode: str
    reason: str
    batch_size: int

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "reason": self.reason,
            "batch_size": self.batch_size,
        }


class ContinuousLearningEngine:
    """Always-on local learning around the model.

    It learns from persisted outcomes and system telemetry, not from hidden
    chain-of-thought or unverified self-generated claims.
    """

    MODES = {"REALTIME", "BACKGROUND", "IDLE", "MAINTENANCE"}

    def __init__(
        self,
        *,
        state: StateManager,
        events: EventBus,
        interval_seconds: float = 15.0,
        scopes: tuple[str, ...] = ("personal",),
    ) -> None:
        self.state = state
        self.events = events
        self.interval_seconds = max(2.0, min(60.0, float(interval_seconds)))
        normalized_scopes = tuple(
            dict.fromkeys(
                str(scope).strip()
                for scope in scopes
                if str(scope).strip()
            )
        )
        self.scopes = normalized_scopes or ("personal",)
        self._stop = asyncio.Event()
        self._last_mode: dict[str, str] = {}
        self._last_cycle_recorded_at: dict[str, float] = {}
        self.quality_gate = LearningQualityGate()

    def prepare_start(self) -> None:
        self._stop.clear()

    async def run(self) -> None:
        last_scope = self.scopes[0]
        try:
            while not self._stop.is_set():
                for scope in self.scopes:
                    if self._stop.is_set():
                        break
                    last_scope = scope
                    try:
                        await asyncio.to_thread(
                            self.run_cycle,
                            scope=scope,
                        )
                    except Exception as exc:
                        try:
                            self._set_worker_status(
                                scope=scope,
                                status="error",
                                reason=str(exc)[:300],
                            )
                        except Exception:
                            pass

                try:
                    await asyncio.wait_for(
                        self._stop.wait(),
                        timeout=self.interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            for scope in self.scopes:
                try:
                    self._set_worker_status(
                        scope=scope,
                        status="stopped",
                    )
                except Exception:
                    pass

    def stop(self) -> None:
        self._stop.set()

    def run_cycle(self, *, scope: str) -> dict:
        started = time.perf_counter()
        self._set_worker_status(scope=scope, status="running")
        enqueued = self._sync_sources(scope=scope)
        queue_depth, high_priority = self._queue_stats(scope=scope)
        state = self.state.load()

        decision = self.select_mode(
            scope=scope,
            queue_depth=queue_depth,
            high_priority=high_priority,
            last_activity_at=state.last_activity_at,
        )
        self._store_mode(scope=scope, decision=decision)

        processed = 0
        learned = 0
        details: dict = {
            "enqueued": enqueued,
            "high_priority": high_priority,
            "batch_size": decision.batch_size,
        }

        try:
            if decision.mode in {"REALTIME", "BACKGROUND", "MAINTENANCE"}:
                processed, learned = self._process_batch(
                    scope=scope,
                    limit=decision.batch_size,
                )

            if decision.mode == "MAINTENANCE":
                details["maintenance"] = self._maintenance(scope=scope)
                self._mark_maintenance(scope=scope)

            details["quality_gate"] = self.quality_gate.refresh(
                scope=scope,
            )

            duration_ms = int((time.perf_counter() - started) * 1000)
            mode_changed = self._last_mode.get(scope) != decision.mode
            now_mono = time.monotonic()
            last_recorded = self._last_cycle_recorded_at.get(scope, 0.0)
            should_record = (
                mode_changed
                or queue_depth > 0
                or processed > 0
                or decision.mode == "MAINTENANCE"
                or now_mono - last_recorded >= 300.0
            )
            cycle_id = None
            if should_record:
                cycle_id = self._record_cycle(
                    scope=scope,
                    mode=decision.mode,
                    reason=decision.reason,
                    queue_depth_before=queue_depth,
                    processed=processed,
                    learned=learned,
                    cloud_used=False,
                    duration_ms=duration_ms,
                    status="success",
                    details=details,
                )
                self._last_cycle_recorded_at[scope] = now_mono

            self._set_worker_status(scope=scope, status="running")

            if mode_changed:
                self.events.emit(
                    "learning.mode.changed",
                    scope=scope,
                    payload={
                        "mode": decision.mode,
                        "reason": decision.reason,
                        "queue_depth": queue_depth,
                    },
                    importance=0.25,
                )
                self._last_mode[scope] = decision.mode

            return {
                "cycle_id": cycle_id,
                "scope": scope,
                "mode": decision.mode,
                "reason": decision.reason,
                "queue_depth_before": queue_depth,
                "processed": processed,
                "learned": learned,
                "cloud_used": False,
                "duration_ms": duration_ms,
                "details": details,
            }
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            cycle_id = self._record_cycle(
                scope=scope,
                mode=decision.mode,
                reason=decision.reason,
                queue_depth_before=queue_depth,
                processed=processed,
                learned=learned,
                cloud_used=False,
                duration_ms=duration_ms,
                status="error",
                details={
                    **details,
                    "error": str(exc)[:500],
                },
            )
            self._set_worker_status(
                scope=scope,
                status="error",
                reason=str(exc)[:300],
            )
            return {
                "cycle_id": cycle_id,
                "scope": scope,
                "mode": decision.mode,
                "reason": decision.reason,
                "status": "error",
                "error": str(exc)[:500],
                "duration_ms": duration_ms,
            }

    def select_mode(
        self,
        *,
        scope: str,
        queue_depth: int,
        high_priority: int,
        last_activity_at: str,
    ) -> LearningModeDecision:
        idle_seconds = self._seconds_since(last_activity_at)
        maintenance_due = self._maintenance_due(scope=scope)

        if idle_seconds <= 45:
            return LearningModeDecision(
                mode="REALTIME",
                reason="user_active",
                batch_size=2,
            )

        if idle_seconds >= 1800 and maintenance_due:
            return LearningModeDecision(
                mode="MAINTENANCE",
                reason="long_idle_and_maintenance_due",
                batch_size=24,
            )

        if queue_depth > 0:
            batch = 12 if queue_depth >= 50 else 8
            if high_priority:
                batch = max(batch, 10)
            return LearningModeDecision(
                mode="BACKGROUND",
                reason="pending_learning_queue",
                batch_size=batch,
            )

        return LearningModeDecision(
            mode="IDLE",
            reason="no_pending_learning_work",
            batch_size=0,
        )

    def status(self, *, scope: str) -> dict:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM continuous_learning_state
                   WHERE scope=?""",
                (scope,),
            ).fetchone()
            queue = conn.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END) AS pending,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed
                   FROM continuous_learning_queue
                   WHERE scope=?""",
                (scope,),
            ).fetchone()

        result = dict(row) if row else {
            "scope": scope,
            "mode": "IDLE",
            "mode_reason": "not_started",
            "worker_status": "stopped",
            "last_cycle_at": None,
            "last_maintenance_at": None,
        }
        if "cursor_json" in result:
            result["cursor"] = json.loads(result.pop("cursor_json") or "{}")
        result["queue"] = {
            "total": int(queue["total"] or 0),
            "pending": int(queue["pending"] or 0),
            "failed": int(queue["failed"] or 0),
        }
        return result

    def recent_cycles(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM continuous_learning_cycles
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["cloud_used"] = bool(item["cloud_used"])
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def patterns(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT
                       p.*,
                       q.lifecycle,
                       q.effective_score,
                       q.decay_factor,
                       q.contradiction_rate,
                       q.age_days,
                       q.reason AS quality_reason,
                       COALESCE(m.weighted_observations, p.observations) AS weighted_observations,
                       COALESCE(m.weighted_successes, p.successes) AS weighted_successes,
                       COALESCE(m.weighted_failures, p.failures) AS weighted_failures,
                       COALESCE(m.evidence_confidence, 0.75) AS evidence_confidence,
                       COALESCE(m.source_types_json, '[]') AS source_types_json
                   FROM learning_patterns p
                   LEFT JOIN learning_pattern_quality q
                     ON q.pattern_id=p.id
                   LEFT JOIN learning_evidence_metrics m
                     ON m.pattern_id=p.id
                   WHERE p.scope=?
                   ORDER BY
                     CASE COALESCE(q.lifecycle, 'candidate')
                       WHEN 'trusted' THEN 0
                       WHEN 'observed' THEN 1
                       WHEN 'candidate' THEN 2
                       ELSE 3
                     END,
                     COALESCE(q.effective_score, p.score) DESC,
                     p.observations DESC,
                     p.id DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["lifecycle"] = item.get("lifecycle") or "candidate"
            item["effective_score"] = float(
                item.get("effective_score")
                if item.get("effective_score") is not None
                else item.get("score", 0.5)
            )
            item["evidence"] = json.loads(item.pop("evidence_json") or "[]")
            item["source_types"] = json.loads(
                item.pop("source_types_json", "[]") or "[]"
            )
            result.append(item)
        return result

    def prompt_block(self, *, scope: str) -> str:
        patterns = [
            item
            for item in self.quality_gate.trusted_patterns(
                scope=scope,
                limit=30,
            )
            if item.get("category") in {
                "logic_strategy_feedback",
                "tool_execution",
                "performance_bottleneck",
            }
        ][:8]

        if not patterns:
            return (
                "Continuous Learning: подтверждённых operational patterns "
                "пока недостаточно. Не придумывай опыт."
            )

        lines = [
            "Continuous Learning: накопленный operational experience.",
            "Это опыт системы, а не факты о мире и не разрешение на действие.",
            "Используй его только как слабую подсказку; текущие evidence, "
            "Permission Gate и Verification имеют приоритет.",
        ]
        for item in patterns:
            lines.append(
                f"- {item['category']}:{item['pattern_key']} "
                f"observations={item['observations']}, "
                f"effective={float(item['effective_score']):.2f}, "
                f"successes={item['successes']}, "
                f"failures={item['failures']}"
            )
        return "\n".join(lines)

    def quality_status(self, *, scope: str) -> dict:
        refresh = self.quality_gate.refresh(scope=scope)
        return {
            **refresh,
            "trusted_patterns": len(
                self.quality_gate.trusted_patterns(
                    scope=scope,
                    limit=500,
                )
            ),
        }

    def strategy_evolution(
        self,
        *,
        scope: str,
        mode: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        self.quality_gate.refresh(scope=scope)
        return self.quality_gate.strategies(
            scope=scope,
            mode=mode,
            include_deprecated=True,
            limit=limit,
        )

    def quality_events(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        return self.quality_gate.recent_events(
            scope=scope,
            limit=limit,
        )

    def queue(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM continuous_learning_queue
                   WHERE scope=?
                   ORDER BY
                     CASE status WHEN 'pending' THEN 0 ELSE 1 END,
                     priority DESC,
                     id ASC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            result.append(item)
        return result

    def _sync_sources(self, *, scope: str) -> int:
        state = self._ensure_state(scope=scope)
        cursors = json.loads(state.get("cursor_json") or "{}")
        total = 0

        sources = (
            ("events", "events", "event_type", 0.45),
            ("performance", "performance_traces", "bottleneck", 0.55),
            ("logic_learning", "logic_learning_events", "outcome", 0.85),
            ("memory_changes", "memory_changes", "action", 0.70),
            ("graph_changes", "graph_changes", "action", 0.60),
            ("execution", "execution_attempts", "status", 0.90),
            ("self_reflection", "self_reflection_runs", "mode", 0.90),
            ("context_budget", "context_budget_reports", "mode", 0.65),
            ("experiment", "experiment_observations", "experiment_id", 0.55),
        )

        for source_type, table, kind_column, default_priority in sources:
            last_id = int(cursors.get(source_type, 0))
            with connect() as conn:
                if table == "events":
                    rows = conn.execute(
                        """SELECT * FROM events
                           WHERE scope=? AND id>? AND event_type NOT LIKE 'learning.%'
                           ORDER BY id ASC LIMIT 200""",
                        (scope, last_id),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        f"""SELECT * FROM {table}
                            WHERE scope=? AND id>?
                            ORDER BY id ASC LIMIT 200""",
                        (scope, last_id),
                    ).fetchall()

            max_id = last_id
            for row in rows:
                item = dict(row)
                source_id = int(item["id"])
                max_id = max(max_id, source_id)
                payload = self._source_payload(
                    source_type=source_type,
                    item=item,
                )
                priority = self._priority_for(
                    source_type=source_type,
                    item=item,
                    default=default_priority,
                )
                kind = str(item.get(kind_column) or source_type)
                if self._enqueue(
                    scope=scope,
                    source_type=source_type,
                    source_id=source_id,
                    kind=kind,
                    priority=priority,
                    payload=payload,
                ):
                    total += 1

            cursors[source_type] = max_id

        with connect() as conn:
            conn.execute(
                """UPDATE continuous_learning_state
                   SET cursor_json=?, updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (
                    json.dumps(cursors, ensure_ascii=False),
                    scope,
                ),
            )
            conn.commit()

        return total

    def _process_batch(self, *, scope: str, limit: int) -> tuple[int, int]:
        if limit <= 0:
            return 0, 0

        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM continuous_learning_queue
                   WHERE scope=? AND status='pending'
                   ORDER BY priority DESC, id ASC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()

        processed = 0
        learned = 0
        for row in rows:
            item = dict(row)
            queue_id = int(item["id"])
            try:
                with connect() as conn:
                    conn.execute(
                        """UPDATE continuous_learning_queue
                           SET status='processing',
                               attempts=attempts+1,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=? AND status='pending'""",
                        (queue_id,),
                    )
                    conn.commit()

                did_learn = self._learn_item(
                    scope=scope,
                    source_type=str(item["source_type"]),
                    kind=str(item["kind"]),
                    payload=json.loads(item["payload_json"] or "{}"),
                    source_id=int(item["source_id"]),
                )
                processed += 1
                if did_learn:
                    learned += 1

                with connect() as conn:
                    conn.execute(
                        """UPDATE continuous_learning_queue
                           SET status='completed',
                               last_error='',
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (queue_id,),
                    )
                    conn.commit()
            except Exception as exc:
                with connect() as conn:
                    conn.execute(
                        """UPDATE continuous_learning_queue
                           SET status=CASE
                                 WHEN attempts>=3 THEN 'failed'
                                 ELSE 'pending'
                               END,
                               last_error=?,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (str(exc)[:500], queue_id),
                    )
                    conn.commit()

        return processed, learned

    def _learn_item(
        self,
        *,
        scope: str,
        source_type: str,
        kind: str,
        payload: dict,
        source_id: int,
    ) -> bool:
        if source_type == "performance":
            key = str(payload.get("bottleneck") or "unknown")
            success = payload.get("budget_status") != "over_budget"
            self._observe_pattern(
                scope=scope,
                category="performance_bottleneck",
                pattern_key=key,
                success=success,
                evidence_weight=0.70,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "total_ms": payload.get("total_ms"),
                    "budget_status": payload.get("budget_status"),
                },
            )
            return True

        if source_type == "logic_learning":
            outcome = str(payload.get("outcome") or kind)
            details = payload.get("details") or {}
            key = str(details.get("strategy_key") or "unknown_strategy")
            self._observe_pattern(
                scope=scope,
                category="logic_strategy_feedback",
                pattern_key=key,
                success=outcome == "success",
                failure=outcome == "failure",
                evidence_weight=1.00,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "outcome": outcome,
                },
            )
            return True

        if source_type == "execution":
            tool_name = str(payload.get("tool_name") or "unknown_tool")
            status = str(payload.get("status") or kind)
            self._observe_pattern(
                scope=scope,
                category="tool_execution",
                pattern_key=tool_name,
                success=status == "success",
                failure=status in {"failed", "stale_or_blocked"},
                evidence_weight=0.95,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "status": status,
                },
            )
            return True

        if source_type == "self_reflection":
            quality = float(payload.get("quality_score") or 0.0)
            weak_spots = payload.get("weak_spots") or []
            for weak_spot in weak_spots[:8]:
                self._observe_pattern(
                    scope=scope,
                    category="self_reflection",
                    pattern_key=str(weak_spot),
                    failure=True,
                    evidence_weight=0.85,
                    evidence={
                        "source_type": source_type,
                        "source_id": source_id,
                        "quality_score": quality,
                        "confidence_score": payload.get("confidence_score"),
                    },
                )
            band = (
                "high_quality" if quality >= 0.80
                else "low_quality" if quality < 0.60
                else "mixed_quality"
            )
            self._observe_pattern(
                scope=scope,
                category="response_quality",
                pattern_key=band,
                success=quality >= 0.80,
                failure=quality < 0.60,
                evidence_weight=0.85,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "quality_score": quality,
                    "correction_signal": bool(payload.get("correction_signal")),
                },
            )
            return True

        if source_type == "context_budget":
            before = int(payload.get("estimated_tokens_before") or 0)
            after = int(payload.get("estimated_tokens_after") or 0)
            trimmed = int(payload.get("trimmed_chars") or 0)
            mode = str(payload.get("mode") or kind or "FAST")
            self._observe_pattern(
                scope=scope,
                category="context_pressure",
                pattern_key=mode,
                success=trimmed == 0,
                failure=trimmed > 0,
                evidence_weight=0.60,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "before": before,
                    "after": after,
                    "trimmed_chars": trimmed,
                },
            )
            return True

        if source_type == "experiment":
            self._observe_pattern(
                scope=scope,
                category="experiment_signal",
                pattern_key=f"experiment:{payload.get('experiment_id') or kind}",
                evidence_weight=0.35,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "baseline_score": payload.get("baseline_score"),
                    "candidate_score": payload.get("candidate_score"),
                    "shadow_only": True,
                },
            )
            return True

        if source_type == "memory_changes":
            self._observe_pattern(
                scope=scope,
                category="memory_change",
                pattern_key=kind,
                evidence_weight=0.55,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "action": kind,
                },
            )
            return True

        if source_type == "graph_changes":
            self._observe_pattern(
                scope=scope,
                category="graph_change",
                pattern_key=kind,
                evidence_weight=0.50,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "action": kind,
                },
            )
            return True

        if source_type == "events":
            event_type = str(payload.get("event_type") or kind)
            self._observe_pattern(
                scope=scope,
                category="event_frequency",
                pattern_key=event_type,
                evidence_weight=0.35,
                evidence={
                    "source_type": source_type,
                    "source_id": source_id,
                    "importance": payload.get("importance"),
                },
            )
            return True

        return False

    def _maintenance(self, *, scope: str) -> dict:
        with connect() as conn:
            queue_recovered = conn.execute(
                """UPDATE continuous_learning_queue
                   SET status='pending',
                       last_error='maintenance_retry',
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=? AND status='processing'""",
                (scope,),
            ).rowcount
            old_completed = conn.execute(
                """DELETE FROM continuous_learning_queue
                   WHERE scope=? AND status='completed'
                     AND datetime(created_at) < datetime('now', '-7 days')""",
                (scope,),
            ).rowcount
            conn.commit()

        return {
            "recovered_processing_items": int(queue_recovered or 0),
            "deleted_completed_queue_items": int(old_completed or 0),
        }

    def _observe_pattern(
        self,
        *,
        scope: str,
        category: str,
        pattern_key: str,
        success: bool = False,
        failure: bool = False,
        evidence_weight: float = 0.5,
        evidence: dict,
    ) -> None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM learning_patterns
                   WHERE scope=? AND category=? AND pattern_key=?""",
                (scope, category, pattern_key),
            ).fetchone()

            if row is None:
                observations = 1
                successes = 1 if success else 0
                failures = 1 if failure else 0
                evidence_list = [evidence]
                score = self._pattern_score(
                    observations=observations,
                    successes=successes,
                    failures=failures,
                )
                conn.execute(
                    """INSERT INTO learning_patterns(
                           scope, category, pattern_key, observations,
                           successes, failures, score, evidence_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        scope,
                        category,
                        pattern_key[:240],
                        observations,
                        successes,
                        failures,
                        score,
                        json.dumps(evidence_list, ensure_ascii=False),
                    ),
                )
            else:
                item = dict(row)
                observations = int(item["observations"]) + 1
                successes = int(item["successes"]) + (1 if success else 0)
                failures = int(item["failures"]) + (1 if failure else 0)
                evidence_list = json.loads(item["evidence_json"] or "[]")
                evidence_list.append(evidence)
                evidence_list = evidence_list[-12:]
                score = self._pattern_score(
                    observations=observations,
                    successes=successes,
                    failures=failures,
                )
                conn.execute(
                    """UPDATE learning_patterns
                       SET observations=?,
                           successes=?,
                           failures=?,
                           score=?,
                           evidence_json=?,
                           last_seen_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        observations,
                        successes,
                        failures,
                        score,
                        json.dumps(evidence_list, ensure_ascii=False),
                        int(item["id"]),
                    ),
                )
            pattern_row = conn.execute(
                """SELECT id FROM learning_patterns
                   WHERE scope=? AND category=? AND pattern_key=?""",
                (scope, category, pattern_key[:240]),
            ).fetchone()
            if pattern_row is not None:
                self._update_evidence_metrics(
                    conn=conn,
                    pattern_id=int(pattern_row["id"]),
                    scope=scope,
                    source_type=str(evidence.get("source_type") or "unknown"),
                    weight=evidence_weight,
                    success=success,
                    failure=failure,
                )
            conn.commit()

    @staticmethod
    def _update_evidence_metrics(
        *,
        conn,
        pattern_id: int,
        scope: str,
        source_type: str,
        weight: float,
        success: bool,
        failure: bool,
    ) -> None:
        weight = max(0.05, min(1.0, float(weight)))
        row = conn.execute(
            """SELECT * FROM learning_evidence_metrics
               WHERE pattern_id=?""",
            (pattern_id,),
        ).fetchone()
        if row is None:
            sources = [source_type]
            weighted_observations = weight
            weighted_successes = weight if success else 0.0
            weighted_failures = weight if failure else 0.0
        else:
            item = dict(row)
            sources = json.loads(item.get("source_types_json") or "[]")
            if source_type not in sources:
                sources.append(source_type)
            weighted_observations = float(item["weighted_observations"]) + weight
            weighted_successes = float(item["weighted_successes"]) + (
                weight if success else 0.0
            )
            weighted_failures = float(item["weighted_failures"]) + (
                weight if failure else 0.0
            )

        diversity_bonus = min(0.12, max(0, len(sources) - 1) * 0.04)
        evidence_confidence = min(
            1.0,
            0.35 + min(0.53, weighted_observations / 10.0) + diversity_bonus,
        )
        conn.execute(
            """INSERT INTO learning_evidence_metrics(
                   pattern_id, scope, weighted_observations,
                   weighted_successes, weighted_failures,
                   evidence_confidence, source_types_json,
                   last_signal_weight, updated_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(pattern_id) DO UPDATE SET
                   weighted_observations=excluded.weighted_observations,
                   weighted_successes=excluded.weighted_successes,
                   weighted_failures=excluded.weighted_failures,
                   evidence_confidence=excluded.evidence_confidence,
                   source_types_json=excluded.source_types_json,
                   last_signal_weight=excluded.last_signal_weight,
                   updated_at=CURRENT_TIMESTAMP""",
            (
                pattern_id,
                scope,
                round(weighted_observations, 4),
                round(weighted_successes, 4),
                round(weighted_failures, 4),
                round(evidence_confidence, 4),
                json.dumps(sources[-8:], ensure_ascii=False),
                weight,
            ),
        )

    def _ensure_state(self, *, scope: str) -> dict:
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO continuous_learning_state(
                       scope, mode, mode_reason, worker_status, cursor_json
                   ) VALUES (?, 'IDLE', 'not_started', 'stopped', '{}')""",
                (scope,),
            )
            row = conn.execute(
                """SELECT * FROM continuous_learning_state
                   WHERE scope=?""",
                (scope,),
            ).fetchone()
            conn.commit()
        return dict(row)

    def _store_mode(
        self,
        *,
        scope: str,
        decision: LearningModeDecision,
    ) -> None:
        self._ensure_state(scope=scope)
        with connect() as conn:
            conn.execute(
                """UPDATE continuous_learning_state
                   SET mode=?,
                       mode_reason=?,
                       last_cycle_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (decision.mode, decision.reason, scope),
            )
            conn.commit()

    def _set_worker_status(
        self,
        *,
        scope: str,
        status: str,
        reason: str = "",
    ) -> None:
        self._ensure_state(scope=scope)
        with connect() as conn:
            conn.execute(
                """UPDATE continuous_learning_state
                   SET worker_status=?,
                       mode_reason=CASE WHEN ?<>'' THEN ? ELSE mode_reason END,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (status, reason, reason, scope),
            )
            conn.commit()

    def _mark_maintenance(self, *, scope: str) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE continuous_learning_state
                   SET last_maintenance_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (scope,),
            )
            conn.commit()

    def _maintenance_due(self, *, scope: str) -> bool:
        state = self._ensure_state(scope=scope)
        value = state.get("last_maintenance_at")
        if not value:
            return True
        return self._seconds_since(str(value)) >= 6 * 3600

    def _queue_stats(self, *, scope: str) -> tuple[int, int]:
        with connect() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*) AS n,
                       SUM(CASE WHEN priority>=0.8 THEN 1 ELSE 0 END) AS high
                   FROM continuous_learning_queue
                   WHERE scope=? AND status='pending'""",
                (scope,),
            ).fetchone()
        return int(row["n"] or 0), int(row["high"] or 0)

    def _enqueue(
        self,
        *,
        scope: str,
        source_type: str,
        source_id: int,
        kind: str,
        priority: float,
        payload: dict,
    ) -> bool:
        with connect() as conn:
            cur = conn.execute(
                """INSERT OR IGNORE INTO continuous_learning_queue(
                       scope, source_type, source_id, kind,
                       priority, payload_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    source_type,
                    source_id,
                    kind[:160],
                    max(0.0, min(1.0, float(priority))),
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()
            return bool(cur.rowcount)

    @staticmethod
    def _source_payload(*, source_type: str, item: dict) -> dict:
        if source_type == "events":
            payload = json.loads(item.get("payload_json") or "{}")
            return {
                "event_type": item.get("event_type"),
                "importance": item.get("importance"),
                "payload": ContinuousLearningEngine._safe_metadata(payload),
            }
        if source_type == "performance":
            return {
                "mode": item.get("mode"),
                "total_ms": item.get("total_ms"),
                "bottleneck": item.get("bottleneck"),
                "budget_status": item.get("budget_status"),
            }
        if source_type == "logic_learning":
            return {
                "outcome": item.get("outcome"),
                "delta": item.get("delta"),
                "details": json.loads(item.get("details_json") or "{}"),
            }
        if source_type == "memory_changes":
            return {
                "action": item.get("action"),
                "reason": item.get("reason"),
                "memory_id": item.get("memory_id"),
            }
        if source_type == "graph_changes":
            return {
                "action": item.get("action"),
                "entity_id": item.get("entity_id"),
                "relation_id": item.get("relation_id"),
            }
        if source_type == "execution":
            return {
                "tool_name": item.get("tool_name"),
                "status": item.get("status"),
            }
        if source_type == "self_reflection":
            return {
                "mode": item.get("mode"),
                "quality_score": item.get("quality_score"),
                "confidence_score": item.get("confidence_score"),
                "error_count": item.get("error_count"),
                "correction_signal": bool(item.get("correction_signal")),
                "weak_spots": json.loads(item.get("weak_spots_json") or "[]"),
            }
        if source_type == "context_budget":
            return {
                "mode": item.get("mode"),
                "token_budget": item.get("token_budget"),
                "estimated_tokens_before": item.get("estimated_tokens_before"),
                "estimated_tokens_after": item.get("estimated_tokens_after"),
                "trimmed_chars": item.get("trimmed_chars"),
            }
        if source_type == "experiment":
            return {
                "experiment_id": item.get("experiment_id"),
                "baseline_score": item.get("baseline_score"),
                "candidate_score": item.get("candidate_score"),
                "details": ContinuousLearningEngine._safe_metadata(
                    json.loads(item.get("details_json") or "{}")
                ),
            }
        return {}

    @staticmethod
    def _safe_metadata(value):
        if isinstance(value, dict):
            result = {}
            for key, item in value.items():
                lowered = str(key).casefold()
                if any(
                    token in lowered
                    for token in (
                        "password",
                        "secret",
                        "token",
                        "api_key",
                        "authorization",
                        "content",
                        "text",
                        "body",
                    )
                ):
                    result[key] = "[REDACTED]"
                else:
                    result[key] = ContinuousLearningEngine._safe_metadata(item)
            return result
        if isinstance(value, list):
            return [
                ContinuousLearningEngine._safe_metadata(item)
                for item in value[:20]
            ]
        if isinstance(value, str):
            return value[:300]
        return value

    @staticmethod
    def _priority_for(
        *,
        source_type: str,
        item: dict,
        default: float,
    ) -> float:
        if source_type == "events":
            return max(default, float(item.get("importance") or 0.0))
        if source_type == "logic_learning":
            return 0.90
        if source_type == "execution":
            status = str(item.get("status") or "")
            return 0.95 if status != "success" else 0.75
        if source_type == "performance":
            return 0.75 if item.get("budget_status") == "over_budget" else default
        if source_type == "self_reflection":
            quality = float(item.get("quality_score") or 0.0)
            correction = bool(item.get("correction_signal"))
            return 0.98 if correction else (0.90 if quality < 0.60 else default)
        if source_type == "context_budget":
            return 0.80 if int(item.get("trimmed_chars") or 0) > 0 else default
        if source_type == "experiment":
            return 0.55
        return default

    @staticmethod
    def _pattern_score(
        *,
        observations: int,
        successes: int,
        failures: int,
    ) -> float:
        if successes or failures:
            return round(
                (successes + 2) / (successes + failures + 4),
                4,
            )
        return round(
            min(0.95, 0.50 + 0.04 * math.log1p(observations)),
            4,
        )

    @staticmethod
    def _seconds_since(value: str | None) -> float:
        if not value:
            return float("inf")
        try:
            parsed = datetime.fromisoformat(str(value))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(
                0.0,
                (datetime.now(timezone.utc) - parsed).total_seconds(),
            )
        except Exception:
            return float("inf")

    @staticmethod
    def _record_cycle(
        *,
        scope: str,
        mode: str,
        reason: str,
        queue_depth_before: int,
        processed: int,
        learned: int,
        cloud_used: bool,
        duration_ms: int,
        status: str,
        details: dict,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO continuous_learning_cycles(
                       scope, mode, reason, queue_depth_before,
                       processed, learned, cloud_used, duration_ms,
                       status, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    mode,
                    reason,
                    queue_depth_before,
                    processed,
                    learned,
                    1 if cloud_used else 0,
                    duration_ms,
                    status,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
