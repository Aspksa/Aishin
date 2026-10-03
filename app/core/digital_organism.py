from __future__ import annotations

import hashlib
import json
import math
import uuid
from datetime import datetime, timezone
from typing import Any

from ..db import connect
from ..personality import personality


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


class DigitalOrganismFoundation:
    """Persistent technical continuity for Aishin as a digital organism.

    This layer models continuity, inner time, autobiography and development.
    It does not claim biological life or subjective consciousness.
    """

    VERSION = "aishin-digital-organism-foundation-v1"
    DEVELOPMENT_FORMULA_VERSION = "aishin-developmental-state-v1"

    STAGES: dict[str, dict[str, Any]] = {
        "D0": {
            "name": "Genesis",
            "next": "D1",
            "min_age_days_for_exit": 30.0,
            "exit_criteria": (
                "identity_persistence_verified",
                "memory_recovery_verified",
                "critical_security_tests_passed",
                "basic_autobiography_operational",
            ),
        },
        "D1": {
            "name": "Adaptation",
            "next": "D2",
            "min_age_days_for_exit": 90.0,
            "exit_criteria": (
                "stable_context_tracking",
                "measurable_error_reduction",
                "reliable_task_follow_through",
            ),
        },
        "D2": {
            "name": "Formation",
            "next": "D3",
            "min_age_days_for_exit": 180.0,
            "exit_criteria": (
                "specialized_skills_have_benchmarks",
                "cross_modal_context_linking_verified",
                "strategy_memory_operational",
            ),
        },
        "D3": {
            "name": "Expansion",
            "next": "D4",
            "min_age_days_for_exit": 365.0,
            "exit_criteria": (
                "at_least_one_generated_module_survived_full_validation",
                "automatic_rollback_verified",
                "growth_governor_effective",
            ),
        },
        "D4": {
            "name": "Maturity",
            "next": "D5",
            "min_age_days_for_exit": 730.0,
            "exit_criteria": (
                "long_term_benchmark_stability",
                "low_regression_rate",
                "high_recovery_reliability",
                "consistent_identity_across_generations",
            ),
        },
        "D5": {
            "name": "Deep Maturity",
            "next": "D6",
            "min_age_days_for_exit": 1825.0,
            "exit_criteria": (
                "multi_year_memory_integrity",
                "cross_domain_skill_transfer_verified",
                "architecture_changes_are_measurably_beneficial",
            ),
        },
        "D6": {
            "name": "Long Horizon",
            "next": None,
            "min_age_days_for_exit": None,
            "exit_criteria": ("open_ended_stage",),
        },
    }

    MANIFEST_TABLES = (
        "runtime_state",
        "organism_now",
        "messages",
        "memories",
        "master_profile",
        "relationship_memory",
        "personal_timeline",
        "knowledge_claims",
        "canonical_facts",
        "organism_identity_state",
        "organism_autobiography",
        "organism_stage_evidence",
        "organism_development_snapshots",
    )

    def __init__(
        self,
        *,
        events: Any | None = None,
        state: Any | None = None,
        scopes: tuple[str, ...] = ("personal", "project:aishin"),
    ) -> None:
        self.events = events
        self.state = state
        self.scopes = tuple(scopes)
        self.boot_session_id = ""

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def startup(self) -> dict:
        self.boot_session_id = uuid.uuid4().hex
        created = self._ensure_identity_state()
        if created:
            self.record_episode(
                episode_type="first_boot",
                participants=["Айшин"],
                context={
                    "basis": created["first_boot_basis"],
                    "confidence": created["first_boot_confidence"],
                },
                what_happened=(
                    "Зафиксирован первый технически подтверждаемый момент "
                    "непрерывной истории Айшин."
                ),
                what_changed="Создано критическое persistent development state.",
                lesson=(
                    "Дата основана на сохранённых данных; если она backfilled, "
                    "это не утверждение точного исторического запуска."
                ),
                importance=1.0,
                confidence=float(created["first_boot_confidence"]),
            )

        validation = self.inspect_continuity()
        self._record_validation(validation)
        self._open_session(validation)

        continuity_status = str(validation["status"])
        self._set_continuity_status(continuity_status)

        self.update_now(
            active_scope="personal",
            focus="system",
            active_task="startup",
            expected_next_action="runtime_ready",
        )

        if continuity_status == "verified_clean_continuity":
            self.record_stage_evidence(
                criterion_key="identity_persistence_verified",
                status="passed",
                source_type="continuous_self",
                source_ref=str(validation.get("latest_snapshot_id") or ""),
                confidence=1.0,
                evidence={
                    "chain_valid": validation.get("chain_valid"),
                    "identity_valid": validation.get("identity_valid"),
                    "manifest_valid": validation.get("manifest_valid"),
                },
            )

        self.record_episode(
            episode_type="runtime_start",
            participants=["Айшин"],
            context={
                "boot_session_id": self.boot_session_id,
                "continuity_status": continuity_status,
            },
            what_happened="Запущена новая runtime-сессия Айшин.",
            what_changed=(
                "Подтверждена или оценена непрерывность предыдущего состояния."
            ),
            lesson="Непрерывность оценивается по hash-chain и persisted manifest.",
            importance=0.45,
            confidence=1.0 if validation["chain_valid"] else 0.45,
        )

        self.record_stage_evidence(
            criterion_key="basic_autobiography_operational",
            status="passed",
            source_type="digital_organism",
            source_ref=self.VERSION,
            confidence=1.0,
            evidence={"autobiography": True},
        )
        development = self.refresh_development(
            persist_snapshot=True,
            allow_transition=True,
        )
        snapshot = self.create_snapshot(snapshot_type="startup")

        self._emit(
            "digital_organism.started",
            payload={
                "boot_session_id": self.boot_session_id,
                "continuity_status": continuity_status,
                "stage": development["current_stage"],
                "first_boot_timestamp": development["first_boot_timestamp"],
                "snapshot_id": snapshot["id"],
            },
            importance=0.65,
        )
        return self.dashboard()

    def shutdown(self, *, reason: str = "normal") -> dict:
        now = _iso_now()
        if self.state is not None:
            state = self.state.load()
            state.status = "sleeping"
            state.activity = "shutdown"
            state.focus = "system"
            state.last_activity_at = now
            self.state.save(state)

        self.update_now(
            focus="offline",
            active_task="shutdown",
            expected_next_action="next_startup_validation",
        )
        self.record_episode(
            episode_type="runtime_shutdown",
            participants=["Айшин"],
            context={
                "boot_session_id": self.boot_session_id,
                "reason": reason,
            },
            what_happened="Runtime-сессия Айшин завершена.",
            what_changed="Состояние подготовлено к continuity snapshot.",
            lesson="Следующий запуск должен проверить shutdown manifest.",
            importance=0.4,
            confidence=1.0,
        )
        self.refresh_development(
            persist_snapshot=True,
            allow_transition=True,
        )
        self._set_continuity_status("sealed_shutdown")
        self._close_session(reason=reason)
        snapshot = self.create_snapshot(snapshot_type="shutdown")
        self._emit(
            "digital_organism.shutdown",
            payload={
                "boot_session_id": self.boot_session_id,
                "snapshot_id": snapshot["id"],
                "state_hash": snapshot["state_hash"],
            },
            importance=0.55,
        )
        return snapshot

    # ------------------------------------------------------------------
    # AISHIN_NOW and inner time
    # ------------------------------------------------------------------

    def observe_interaction(self, *, scope: str, focus: str) -> dict:
        return self.update_now(
            active_scope=(scope or "personal").strip() or "personal",
            focus=focus,
            active_task="conversation",
            expected_next_action="respond",
            interaction=True,
        )

    def update_now(
        self,
        *,
        active_scope: str | None = None,
        user_context: dict | None = None,
        environment_context: dict | None = None,
        current_screen: str | None = None,
        current_project: str | None = None,
        focus: str | None = None,
        active_task: str | None = None,
        expected_next_action: str | None = None,
        interaction: bool = False,
    ) -> dict:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM organism_now WHERE id=1"
            ).fetchone()
            if not row:
                conn.execute(
                    """INSERT INTO organism_now(id, timestamp)
                       VALUES (1, CURRENT_TIMESTAMP)"""
                )
                row = conn.execute(
                    "SELECT * FROM organism_now WHERE id=1"
                ).fetchone()
            current = dict(row)

            scope = (
                str(active_scope).strip()
                if active_scope is not None
                else str(current.get("active_scope") or "personal")
            ) or "personal"
            project = current_project
            if project is None and scope.startswith("project:"):
                project = scope.split(":", 1)[1]

            merged_user = self._json(
                current.get("user_context_json"),
                {},
            )
            if user_context:
                merged_user.update(user_context)
            merged_env = self._json(
                current.get("environment_context_json"),
                {},
            )
            if environment_context:
                merged_env.update(environment_context)

            ts = _iso_now()
            conn.execute(
                """UPDATE organism_now
                   SET timestamp=?,
                       active_scope=?,
                       user_context_json=?,
                       environment_context_json=?,
                       current_screen=?,
                       current_project=?,
                       focus=?,
                       active_task=?,
                       expected_next_action=?,
                       last_interaction_at=CASE
                         WHEN ?=1 THEN ?
                         ELSE last_interaction_at END,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=1""",
                (
                    ts,
                    scope,
                    json.dumps(merged_user, ensure_ascii=False),
                    json.dumps(merged_env, ensure_ascii=False),
                    (
                        str(current_screen)
                        if current_screen is not None
                        else str(current.get("current_screen") or "")
                    ),
                    (
                        str(project)
                        if project is not None
                        else str(current.get("current_project") or "")
                    ),
                    (
                        str(focus)
                        if focus is not None
                        else str(current.get("focus") or "waiting")
                    ),
                    (
                        str(active_task)
                        if active_task is not None
                        else str(current.get("active_task") or "")
                    ),
                    (
                        str(expected_next_action)
                        if expected_next_action is not None
                        else str(current.get("expected_next_action") or "")
                    ),
                    1 if interaction else 0,
                    ts,
                ),
            )
            conn.commit()
        return self.now(scope=scope)

    def now(self, *, scope: str | None = None) -> dict:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM organism_now WHERE id=1"
            ).fetchone()
            current = dict(row) if row else {}
            effective_scope = (
                (scope or current.get("active_scope") or "personal").strip()
                or "personal"
            )
            event = conn.execute(
                """SELECT id, event_type, importance, created_at
                   FROM events
                   WHERE scope=?
                   ORDER BY id DESC LIMIT 1""",
                (effective_scope,),
            ).fetchone()

        runtime = self.state.load().to_dict() if self.state is not None else {}
        return {
            "timestamp": _iso_now(),
            "user_context": self._json(
                current.get("user_context_json"),
                {},
            ),
            "environment_context": self._json(
                current.get("environment_context_json"),
                {},
            ),
            "current_screen": str(current.get("current_screen") or ""),
            "current_project": str(
                current.get("current_project")
                or (
                    effective_scope.split(":", 1)[1]
                    if effective_scope.startswith("project:")
                    else ""
                )
            ),
            "current_scope": effective_scope,
            "last_event": dict(event) if event else None,
            "focus": str(runtime.get("focus") or current.get("focus") or "waiting"),
            "active_task": str(current.get("active_task") or ""),
            "expected_next_action": str(
                current.get("expected_next_action") or ""
            ),
            "last_interaction_at": current.get("last_interaction_at"),
            "last_important_event_at": current.get("last_important_event_at"),
        }

    def inner_time(self, *, scope: str = "personal") -> dict:
        identity = self._identity_state()
        first_boot = self._parse_time(identity.get("first_boot_timestamp"))
        now = _utc_now()
        current = self.now(scope=scope)

        with connect() as conn:
            latest_skill = conn.execute(
                """SELECT MAX(COALESCE(last_evidence_at, updated_at))
                   FROM growth_skills WHERE scope=?""",
                (scope,),
            ).fetchone()[0]
            memory_bounds = conn.execute(
                """SELECT MIN(created_at), MAX(updated_at)
                   FROM memories WHERE scope=?""",
                (scope,),
            ).fetchone()
            capability_bounds = conn.execute(
                """SELECT MIN(first_seen_at), MAX(COALESCE(last_evidence_at, updated_at))
                   FROM growth_skills WHERE scope=?""",
                (scope,),
            ).fetchone()
            next_due = conn.execute(
                """SELECT MIN(due_at)
                   FROM (
                       SELECT due_at FROM tasks
                       WHERE scope=? AND status IN ('open','active')
                         AND due_at IS NOT NULL
                       UNION ALL
                       SELECT due_at FROM goals
                       WHERE scope=? AND status='active'
                         AND due_at IS NOT NULL
                   )""",
                (scope, scope),
            ).fetchone()[0]

        return {
            "name": "AISHIN_INNER_TIME",
            "time_since_first_boot": self._elapsed(first_boot, now),
            "time_since_last_interaction": self._elapsed(
                self._parse_time(current.get("last_interaction_at")),
                now,
            ),
            "time_since_skill_use": self._elapsed(
                self._parse_time(latest_skill),
                now,
            ),
            "time_since_important_event": self._elapsed(
                self._parse_time(current.get("last_important_event_at")),
                now,
            ),
            "age_of_memory": {
                "oldest": self._elapsed(
                    self._parse_time(memory_bounds[0]),
                    now,
                ),
                "newest": self._elapsed(
                    self._parse_time(memory_bounds[1]),
                    now,
                ),
            },
            "age_of_capability": {
                "oldest": self._elapsed(
                    self._parse_time(capability_bounds[0]),
                    now,
                ),
                "most_recent_use": self._elapsed(
                    self._parse_time(capability_bounds[1]),
                    now,
                ),
            },
            "time_to_expected_event": self._until(
                self._parse_time(next_due),
                now,
            ),
        }

    # ------------------------------------------------------------------
    # Autobiography
    # ------------------------------------------------------------------

    def record_episode(
        self,
        *,
        episode_type: str,
        participants: list[str],
        context: dict,
        what_happened: str,
        what_changed: str = "",
        lesson: str = "",
        importance: float = 0.5,
        confidence: float = 1.0,
        linked_memories: list[int] | None = None,
        source_event_id: int | None = None,
    ) -> int:
        importance = self._clamp(importance)
        confidence = self._clamp(confidence)
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO organism_autobiography(
                       episode_type, timestamp, participants_json,
                       context_json, what_happened, what_changed,
                       lesson, importance, confidence,
                       linked_memories_json, source_event_id,
                       boot_session_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    episode_type[:120],
                    _iso_now(),
                    json.dumps(participants, ensure_ascii=False),
                    json.dumps(context, ensure_ascii=False),
                    what_happened[:4000],
                    what_changed[:3000],
                    lesson[:3000],
                    importance,
                    confidence,
                    json.dumps(linked_memories or []),
                    source_event_id,
                    self.boot_session_id,
                ),
            )
            episode_id = int(cur.lastrowid)
            if importance >= 0.8:
                conn.execute(
                    """UPDATE organism_now
                       SET last_important_event_at=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=1""",
                    (_iso_now(),),
                )
            conn.commit()
        return episode_id

    def autobiography(
        self,
        *,
        limit: int = 100,
        episode_type: str | None = None,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with connect() as conn:
            if episode_type:
                rows = conn.execute(
                    """SELECT * FROM organism_autobiography
                       WHERE episode_type=?
                       ORDER BY id DESC LIMIT ?""",
                    (episode_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM organism_autobiography
                       ORDER BY id DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["participants"] = self._json(
                item.pop("participants_json"),
                [],
            )
            item["context"] = self._json(item.pop("context_json"), {})
            item["linked_memories"] = self._json(
                item.pop("linked_memories_json"),
                [],
            )
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # Developmental state
    # ------------------------------------------------------------------

    def record_stage_evidence(
        self,
        *,
        criterion_key: str,
        status: str,
        source_type: str,
        source_ref: str,
        confidence: float,
        evidence: dict,
        expires_at: str | None = None,
    ) -> dict:
        status = status.strip().casefold()
        if status not in {"passed", "failed", "unknown"}:
            raise ValueError("status must be passed, failed or unknown")
        with connect() as conn:
            conn.execute(
                """INSERT INTO organism_stage_evidence(
                       criterion_key, status, source_type, source_ref,
                       evidence_json, confidence, observed_at,
                       expires_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?,
                             CURRENT_TIMESTAMP)
                   ON CONFLICT(criterion_key)
                   DO UPDATE SET
                       status=excluded.status,
                       source_type=excluded.source_type,
                       source_ref=excluded.source_ref,
                       evidence_json=excluded.evidence_json,
                       confidence=excluded.confidence,
                       observed_at=CURRENT_TIMESTAMP,
                       expires_at=excluded.expires_at,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    criterion_key,
                    status,
                    source_type[:120],
                    source_ref[:700],
                    json.dumps(evidence, ensure_ascii=False),
                    self._clamp(confidence),
                    expires_at,
                ),
            )
            conn.commit()
        return self.stage_evidence(criterion_key)

    def stage_evidence(self, criterion_key: str | None = None) -> Any:
        with connect() as conn:
            if criterion_key:
                row = conn.execute(
                    """SELECT * FROM organism_stage_evidence
                       WHERE criterion_key=?""",
                    (criterion_key,),
                ).fetchone()
                return self._decode_evidence(dict(row)) if row else None
            rows = conn.execute(
                """SELECT * FROM organism_stage_evidence
                   ORDER BY criterion_key"""
            ).fetchall()
        return [self._decode_evidence(dict(row)) for row in rows]

    def refresh_development(
        self,
        *,
        persist_snapshot: bool,
        allow_transition: bool,
    ) -> dict:
        identity = self._identity_state()
        first_boot = self._parse_time(identity["first_boot_timestamp"])
        age_days = (
            max(0.0, (_utc_now() - first_boot).total_seconds() / 86400.0)
            if first_boot is not None
            else 0.0
        )

        evidence = self._development_evidence()
        experience_score = float(
            evidence["autobiography_episodes"]
            + evidence["completed_tasks"]
            + evidence["confirmed_hypotheses"]
            + evidence["confirmed_corrections"]
            + evidence["trusted_strategies"]
            + evidence["mastered_skills"]
        )
        competence_samples = [
            float(value)
            for value in evidence["competence_samples"]
            if value is not None
        ]
        competence_score = (
            sum(competence_samples) / len(competence_samples)
            if competence_samples
            else 0.0
        )

        current_stage = str(identity.get("current_stage") or "D0")
        eligibility = self._stage_eligibility(
            stage=current_stage,
            age_days=age_days,
        )

        if allow_transition and eligibility.get("eligible"):
            next_stage = eligibility.get("next_stage")
            if next_stage:
                self._advance_stage(
                    old_stage=current_stage,
                    new_stage=str(next_stage),
                    eligibility=eligibility,
                )
                identity = self._identity_state()
                current_stage = str(identity["current_stage"])
                eligibility = self._stage_eligibility(
                    stage=current_stage,
                    age_days=age_days,
                )

        maturity_profile = {
            "chronological_age_days": round(age_days, 4),
            "experience": {
                "score": round(experience_score, 2),
                "formula": (
                    "sum(autobiography_episodes, completed_tasks, "
                    "confirmed_hypotheses, confirmed_corrections, "
                    "trusted_strategies, mastered_skills)"
                ),
                "quality_gate": (
                    "Only confirmed/trusted/mastered outcome classes "
                    "count in quality-sensitive categories."
                ),
            },
            "competence": {
                "score": round(competence_score, 2),
                "formula": (
                    "arithmetic mean of latest persisted Development Metrics, "
                    "Long-Term Growth and Cognitive Intelligence scores "
                    "across runtime scopes"
                ),
                "samples": competence_samples,
            },
            "architecture_generation": int(
                identity.get("architecture_generation") or 1
            ),
            "stage": current_stage,
        }

        with connect() as conn:
            conn.execute(
                """UPDATE organism_identity_state
                   SET experience_age_score=?,
                       competence_age_score=?,
                       current_maturity_profile_json=?,
                       stage_eligibility_json=?,
                       last_development_refresh_at=?,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=1""",
                (
                    round(experience_score, 4),
                    round(competence_score, 4),
                    json.dumps(maturity_profile, ensure_ascii=False),
                    json.dumps(eligibility, ensure_ascii=False),
                    _iso_now(),
                ),
            )
            if persist_snapshot:
                conn.execute(
                    """INSERT INTO organism_development_snapshots(
                           formula_version, first_boot_timestamp,
                           chronological_age_days, current_stage,
                           experience_age_score, competence_age_score,
                           architecture_generation, completed_growth_cycles,
                           maturity_profile_json, evidence_json,
                           stage_eligibility_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.DEVELOPMENT_FORMULA_VERSION,
                        identity["first_boot_timestamp"],
                        round(age_days, 6),
                        current_stage,
                        round(experience_score, 4),
                        round(competence_score, 4),
                        int(identity.get("architecture_generation") or 1),
                        int(identity.get("completed_growth_cycles") or 0),
                        json.dumps(maturity_profile, ensure_ascii=False),
                        json.dumps(evidence, ensure_ascii=False),
                        json.dumps(eligibility, ensure_ascii=False),
                    ),
                )
            conn.commit()

        return self.development_state()

    def development_state(self) -> dict:
        state = self._identity_state()
        first_boot = self._parse_time(state["first_boot_timestamp"])
        age_days = (
            max(0.0, (_utc_now() - first_boot).total_seconds() / 86400.0)
            if first_boot is not None
            else 0.0
        )
        return {
            "name": "AISHIN_DEVELOPMENT_STATE",
            "formula_version": self.DEVELOPMENT_FORMULA_VERSION,
            "first_boot_timestamp": state["first_boot_timestamp"],
            "first_boot_basis": state["first_boot_basis"],
            "first_boot_confidence": float(
                state["first_boot_confidence"]
            ),
            "chronological_age_days": round(age_days, 6),
            "current_stage": state["current_stage"],
            "current_stage_name": self.STAGES.get(
                str(state["current_stage"]),
                {},
            ).get("name", "Unknown"),
            "experience_age_score": float(state["experience_age_score"]),
            "competence_age_score": float(state["competence_age_score"]),
            "architecture_generation": int(
                state["architecture_generation"]
            ),
            "completed_growth_cycles": int(
                state["completed_growth_cycles"]
            ),
            "active_growth_goals": self._json(
                state["active_growth_goals_json"],
                [],
            ),
            "growth_plateaus": self._json(
                state["growth_plateaus_json"],
                [],
            ),
            "recent_breakthroughs": self._json(
                state["recent_breakthroughs_json"],
                [],
            ),
            "current_maturity_profile": self._json(
                state["current_maturity_profile_json"],
                {},
            ),
            "stage_eligibility": self._json(
                state["stage_eligibility_json"],
                {},
            ),
            "continuity_status": state["continuity_status"],
            "identity_anchor_hash": state["identity_anchor_hash"],
            "last_development_refresh_at": (
                state["last_development_refresh_at"]
            ),
        }

    def development_history(self, *, limit: int = 90) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM organism_development_snapshots
                   ORDER BY id DESC LIMIT ?""",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["maturity_profile"] = self._json(
                item.pop("maturity_profile_json"),
                {},
            )
            item["evidence"] = self._json(item.pop("evidence_json"), {})
            item["stage_eligibility"] = self._json(
                item.pop("stage_eligibility_json"),
                {},
            )
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # Continuous self
    # ------------------------------------------------------------------

    def create_snapshot(self, *, snapshot_type: str) -> dict:
        manifest = self._critical_manifest()
        identity_hash = self._identity_hash()
        previous_hash = ""
        with connect() as conn:
            previous = conn.execute(
                """SELECT state_hash FROM organism_continuity_snapshots
                   ORDER BY id DESC LIMIT 1"""
            ).fetchone()
            if previous:
                previous_hash = str(previous["state_hash"])

        payload = {
            "version": self.VERSION,
            "snapshot_type": snapshot_type,
            "created_at": _iso_now(),
            "boot_session_id": self.boot_session_id,
            "development_state": self.development_state(),
            "aishin_now": self.now(),
            "identity_hash": identity_hash,
            "manifest": manifest,
        }
        state_hash = self._snapshot_hash(
            previous_state_hash=previous_hash,
            snapshot_type=snapshot_type,
            payload=payload,
        )
        manifest_hash = self._sha_json(manifest)

        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO organism_continuity_snapshots(
                       boot_session_id, snapshot_type,
                       previous_state_hash, state_hash,
                       identity_hash, data_manifest_hash,
                       payload_json, chain_status
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'recorded')""",
                (
                    self.boot_session_id,
                    snapshot_type,
                    previous_hash,
                    state_hash,
                    identity_hash,
                    manifest_hash,
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
            snapshot_id = int(cur.lastrowid)
            conn.commit()
        return {
            "id": snapshot_id,
            "snapshot_type": snapshot_type,
            "previous_state_hash": previous_hash,
            "state_hash": state_hash,
            "identity_hash": identity_hash,
            "data_manifest_hash": manifest_hash,
        }

    def inspect_continuity(self) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM organism_continuity_snapshots
                   ORDER BY id ASC"""
            ).fetchall()

        if not rows:
            return {
                "name": "AISHIN_CONTINUOUS_SELF",
                "status": "genesis",
                "chain_valid": True,
                "identity_valid": True,
                "manifest_valid": None,
                "latest_snapshot_id": None,
                "latest_snapshot_type": None,
                "snapshot_count": 0,
                "current_identity_hash": self._identity_hash(),
                "current_manifest_hash": self._sha_json(
                    self._critical_manifest()
                ),
            }

        expected_previous = ""
        chain_valid = True
        chain_error: dict | None = None
        for row in rows:
            item = dict(row)
            payload = self._json(item["payload_json"], {})
            computed = self._snapshot_hash(
                previous_state_hash=str(item["previous_state_hash"]),
                snapshot_type=str(item["snapshot_type"]),
                payload=payload,
            )
            if str(item["previous_state_hash"]) != expected_previous:
                chain_valid = False
                chain_error = {
                    "snapshot_id": int(item["id"]),
                    "reason": "previous_state_hash_mismatch",
                }
                break
            if computed != str(item["state_hash"]):
                chain_valid = False
                chain_error = {
                    "snapshot_id": int(item["id"]),
                    "reason": "state_hash_mismatch",
                }
                break
            expected_previous = str(item["state_hash"])

        latest = dict(rows[-1])
        current_identity_hash = self._identity_hash()
        identity_valid = (
            current_identity_hash == str(latest["identity_hash"])
        )
        current_manifest_hash = self._sha_json(self._critical_manifest())
        manifest_valid: bool | None = None
        if str(latest["snapshot_type"]) == "shutdown":
            manifest_valid = (
                current_manifest_hash
                == str(latest["data_manifest_hash"])
            )

        if not chain_valid:
            status = "chain_broken"
        elif not identity_valid:
            status = "identity_changed_requires_review"
        elif manifest_valid is False:
            status = "state_mismatch_after_clean_shutdown"
        elif manifest_valid is True:
            status = "verified_clean_continuity"
        else:
            status = "unclean_gap"

        return {
            "name": "AISHIN_CONTINUOUS_SELF",
            "status": status,
            "chain_valid": chain_valid,
            "identity_valid": identity_valid,
            "manifest_valid": manifest_valid,
            "latest_snapshot_id": int(latest["id"]),
            "latest_snapshot_type": latest["snapshot_type"],
            "latest_state_hash": latest["state_hash"],
            "previous_state_hash": latest["previous_state_hash"],
            "snapshot_count": len(rows),
            "current_identity_hash": current_identity_hash,
            "current_manifest_hash": current_manifest_hash,
            "chain_error": chain_error,
            "external_trust_root": False,
            "integrity_model": (
                "SHA-256 hash chain + identity hash + persisted data manifest"
            ),
        }

    def continuity_summary(self) -> dict:
        identity = self._identity_state()
        with connect() as conn:
            latest_snapshot = conn.execute(
                """SELECT id, snapshot_type, previous_state_hash, state_hash,
                          identity_hash, data_manifest_hash, created_at
                   FROM organism_continuity_snapshots
                   ORDER BY id DESC LIMIT 1"""
            ).fetchone()
            snapshot_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM organism_continuity_snapshots"
                ).fetchone()[0]
            )
            latest_validation = conn.execute(
                """SELECT id, status, chain_valid, identity_valid,
                          manifest_valid, created_at
                   FROM organism_continuity_validations
                   ORDER BY id DESC LIMIT 1"""
            ).fetchone()
        validation = dict(latest_validation) if latest_validation else None
        if validation:
            validation["chain_valid"] = bool(validation["chain_valid"])
            validation["identity_valid"] = bool(validation["identity_valid"])
            validation["manifest_valid"] = (
                None
                if validation["manifest_valid"] is None
                else bool(validation["manifest_valid"])
            )
        return {
            "name": "AISHIN_CONTINUOUS_SELF",
            "status": str(identity.get("continuity_status") or "genesis"),
            "snapshot_count": snapshot_count,
            "latest_snapshot": (
                dict(latest_snapshot) if latest_snapshot else None
            ),
            "latest_validation": validation,
            "external_trust_root": False,
            "integrity_model": (
                "SHA-256 hash chain + identity hash + persisted data manifest"
            ),
            "validation_mode": (
                "full manifest validation on startup or explicit inspection; "
                "summary reads do not rehash the database"
            ),
        }

    def continuity_history(
        self,
        *,
        snapshot_limit: int = 50,
        validation_limit: int = 50,
    ) -> dict:
        with connect() as conn:
            snapshots = [
                dict(row)
                for row in conn.execute(
                    """SELECT id, boot_session_id, snapshot_type,
                              previous_state_hash, state_hash,
                              identity_hash, data_manifest_hash,
                              chain_status, created_at
                       FROM organism_continuity_snapshots
                       ORDER BY id DESC LIMIT ?""",
                    (max(1, min(int(snapshot_limit), 500)),),
                ).fetchall()
            ]
            validations = []
            for row in conn.execute(
                """SELECT * FROM organism_continuity_validations
                   ORDER BY id DESC LIMIT ?""",
                (max(1, min(int(validation_limit), 500)),),
            ).fetchall():
                item = dict(row)
                item["chain_valid"] = bool(item["chain_valid"])
                item["identity_valid"] = bool(item["identity_valid"])
                item["manifest_valid"] = (
                    None
                    if item["manifest_valid"] is None
                    else bool(item["manifest_valid"])
                )
                item["details"] = self._json(
                    item.pop("details_json"),
                    {},
                )
                validations.append(item)
        return {
            "current": self.inspect_continuity(),
            "snapshots": snapshots,
            "validations": validations,
        }

    @classmethod
    def verify_snapshot_record(cls, record: dict) -> bool:
        payload = cls._json(record.get("payload_json"), {})
        return cls._snapshot_hash(
            previous_state_hash=str(
                record.get("previous_state_hash") or ""
            ),
            snapshot_type=str(record.get("snapshot_type") or ""),
            payload=payload,
        ) == str(record.get("state_hash") or "")

    # ------------------------------------------------------------------
    # Public dashboard / prompt
    # ------------------------------------------------------------------

    def dashboard(self, *, scope: str = "personal") -> dict:
        with connect() as conn:
            autobiography_total = int(
                conn.execute(
                    "SELECT COUNT(*) FROM organism_autobiography"
                ).fetchone()[0]
            )
            runtime_sessions = int(
                conn.execute(
                    "SELECT COUNT(*) FROM organism_runtime_sessions"
                ).fetchone()[0]
            )
        return {
            "version": self.VERSION,
            "scientific_boundary": (
                "Persistent technical digital personality state; "
                "no claim of biological life or subjective consciousness."
            ),
            "now": self.now(scope=scope),
            "inner_time": self.inner_time(scope=scope),
            "development_state": self.development_state(),
            "continuity": self.continuity_summary(),
            "autobiography": {
                "total": autobiography_total,
                "recent": self.autobiography(limit=12),
            },
            "runtime_sessions": runtime_sessions,
        }

    def prompt_block(self, *, scope: str = "personal") -> str:
        development = self.development_state()
        continuity = self.continuity_summary()
        now = self.now(scope=scope)
        return (
            "AISHIN_DIGITAL_ORGANISM technical state.\n"
            f"- development_stage: {development['current_stage']} "
            f"({development['current_stage_name']})\n"
            f"- chronological_age_days: "
            f"{development['chronological_age_days']:.3f}\n"
            f"- continuity_status: {continuity['status']}\n"
            f"- current_scope: {now['current_scope']}\n"
            f"- focus: {now['focus']}\n"
            "This is an engineering continuity model. Do not claim biological "
            "life, subjective consciousness, or feelings from these fields."
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_identity_state(self) -> dict | None:
        with connect() as conn:
            existing = conn.execute(
                "SELECT * FROM organism_identity_state WHERE id=1"
            ).fetchone()
        if existing:
            self._ensure_now_row()
            return None

        first_boot, basis, confidence = self._infer_first_boot()
        identity_hash = self._identity_hash()
        with connect() as conn:
            conn.execute(
                """INSERT INTO organism_identity_state(
                       id, first_boot_timestamp, first_boot_basis,
                       first_boot_confidence, architecture_generation,
                       current_stage, stage_entered_at,
                       continuity_status, identity_anchor_hash
                   ) VALUES (1, ?, ?, ?, 1, 'D0', ?, 'genesis', ?)""",
                (
                    first_boot,
                    basis,
                    confidence,
                    first_boot,
                    identity_hash,
                ),
            )
            conn.execute(
                """INSERT OR IGNORE INTO organism_now(
                       id, timestamp, active_scope, focus
                   ) VALUES (1, ?, 'personal', 'waiting')""",
                (_iso_now(),),
            )
            conn.commit()
        return {
            "first_boot_timestamp": first_boot,
            "first_boot_basis": basis,
            "first_boot_confidence": confidence,
        }

    def _ensure_now_row(self) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO organism_now(
                       id, timestamp, active_scope, focus
                   ) VALUES (1, ?, 'personal', 'waiting')""",
                (_iso_now(),),
            )
            conn.commit()

    def _infer_first_boot(self) -> tuple[str, str, float]:
        sources = (
            ("events", "created_at"),
            ("memories", "created_at"),
            ("messages", "created_at"),
            ("personal_timeline", "occurred_at"),
        )
        candidates: list[tuple[datetime, str]] = []
        with connect() as conn:
            for table, column in sources:
                value = conn.execute(
                    f"SELECT MIN({column}) FROM {table}"
                ).fetchone()[0]
                parsed = self._parse_time(value)
                if parsed is not None:
                    candidates.append((parsed, table))
            migration = conn.execute(
                "SELECT MIN(applied_at) FROM schema_migrations"
            ).fetchone()[0]
        parsed_migration = self._parse_time(migration)
        if candidates:
            dt, table = min(candidates, key=lambda item: item[0])
            return (
                dt.isoformat(),
                f"backfilled_from_earliest_persisted_{table}",
                0.85,
            )
        if parsed_migration is not None:
            return (
                parsed_migration.isoformat(),
                "initial_schema_bootstrap",
                0.75,
            )
        return (_iso_now(), "fresh_install_first_boot", 1.0)

    def _development_evidence(self) -> dict:
        scopes = self.scopes
        placeholders = ",".join("?" for _ in scopes)
        with connect() as conn:
            episodes = int(
                conn.execute(
                    """SELECT COUNT(*) FROM organism_autobiography
                       WHERE importance>=0.5"""
                ).fetchone()[0]
            )
            completed_tasks = int(
                conn.execute(
                    f"""SELECT COUNT(*) FROM tasks
                        WHERE scope IN ({placeholders})
                          AND status IN ('completed','done','closed')""",
                    scopes,
                ).fetchone()[0]
            )
            confirmed_hypotheses = int(
                conn.execute(
                    f"""SELECT COUNT(*) FROM hypothesis_registry
                        WHERE scope IN ({placeholders})
                          AND state='confirmed'""",
                    scopes,
                ).fetchone()[0]
            )
            confirmed_corrections = int(
                conn.execute(
                    f"""SELECT COUNT(*) FROM knowledge_learning_events
                        WHERE scope IN ({placeholders})
                          AND event_type='correction_confirmed'""",
                    scopes,
                ).fetchone()[0]
            )
            trusted_strategies = int(
                conn.execute(
                    f"""SELECT COUNT(*) FROM strategy_quality_state
                        WHERE scope IN ({placeholders})
                          AND lifecycle='trusted'""",
                    scopes,
                ).fetchone()[0]
            )
            mastered_skills = int(
                conn.execute(
                    f"""SELECT COUNT(*) FROM growth_skills
                        WHERE scope IN ({placeholders})
                          AND lifecycle='mastered'""",
                    scopes,
                ).fetchone()[0]
            )

            competence_samples: list[float] = []
            for scope in scopes:
                for table in (
                    "development_snapshots",
                    "long_term_growth_snapshots",
                    "cognitive_intelligence_snapshots",
                ):
                    row = conn.execute(
                        f"""SELECT overall_score FROM {table}
                            WHERE scope=?
                            ORDER BY id DESC LIMIT 1""",
                        (scope,),
                    ).fetchone()
                    if row is not None:
                        competence_samples.append(
                            float(row["overall_score"] or 0.0)
                        )

        return {
            "autobiography_episodes": episodes,
            "completed_tasks": completed_tasks,
            "confirmed_hypotheses": confirmed_hypotheses,
            "confirmed_corrections": confirmed_corrections,
            "trusted_strategies": trusted_strategies,
            "mastered_skills": mastered_skills,
            "competence_samples": competence_samples,
        }

    def _stage_eligibility(
        self,
        *,
        stage: str,
        age_days: float,
    ) -> dict:
        definition = self.STAGES.get(stage, self.STAGES["D0"])
        criteria = list(definition["exit_criteria"])
        evidence_rows = {
            item["criterion_key"]: item
            for item in self.stage_evidence()
        }
        criteria_state = []
        all_passed = True
        now = _utc_now()
        for key in criteria:
            row = evidence_rows.get(key)
            expires_at = (
                self._parse_time(row.get("expires_at"))
                if row else None
            )
            expired = bool(expires_at and expires_at <= now)
            passed = bool(
                row
                and row.get("status") == "passed"
                and not expired
            )
            all_passed = all_passed and passed
            criteria_state.append(
                {
                    "criterion": key,
                    "status": row.get("status") if row else "unknown",
                    "passed": passed,
                    "expired": expired,
                    "expires_at": row.get("expires_at") if row else None,
                    "source_type": row.get("source_type") if row else "",
                    "source_ref": row.get("source_ref") if row else "",
                    "confidence": (
                        float(row.get("confidence") or 0.0)
                        if row else 0.0
                    ),
                }
            )

        min_age = definition.get("min_age_days_for_exit")
        time_met = True if min_age is None else age_days >= float(min_age)
        next_stage = definition.get("next")
        eligible = bool(next_stage and time_met and all_passed)
        return {
            "current_stage": stage,
            "current_stage_name": definition["name"],
            "next_stage": next_stage,
            "minimum_age_days": min_age,
            "age_days": round(age_days, 6),
            "time_requirement_met": time_met,
            "criteria": criteria_state,
            "all_exit_criteria_passed": all_passed,
            "eligible": eligible,
            "rule": (
                "time AND explicit exit-criteria evidence; "
                "calendar time alone is insufficient"
            ),
        }

    def _advance_stage(
        self,
        *,
        old_stage: str,
        new_stage: str,
        eligibility: dict,
    ) -> None:
        now = _iso_now()
        with connect() as conn:
            conn.execute(
                """UPDATE organism_identity_state
                   SET current_stage=?,
                       stage_entered_at=?,
                       completed_growth_cycles=completed_growth_cycles+1,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=1 AND current_stage=?""",
                (new_stage, now, old_stage),
            )
            conn.commit()
        self.record_episode(
            episode_type="development_stage_transition",
            participants=["Айшин"],
            context={
                "from_stage": old_stage,
                "to_stage": new_stage,
                "eligibility": eligibility,
            },
            what_happened=(
                f"Подтверждён переход развития {old_stage} → {new_stage}."
            ),
            what_changed="Обновлена стадия AISHIN_DEVELOPMENT_STATE.",
            lesson=(
                "Переход выполнен только после минимального времени и "
                "подтверждённых exit criteria."
            ),
            importance=1.0,
            confidence=1.0,
        )
        self._emit(
            "digital_organism.stage_changed",
            payload={"from": old_stage, "to": new_stage},
            importance=0.9,
        )

    def _record_validation(self, validation: dict) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO organism_continuity_validations(
                       boot_session_id, latest_snapshot_id, status,
                       chain_valid, identity_valid, manifest_valid,
                       details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    self.boot_session_id,
                    validation.get("latest_snapshot_id"),
                    validation["status"],
                    1 if validation["chain_valid"] else 0,
                    1 if validation["identity_valid"] else 0,
                    (
                        None
                        if validation["manifest_valid"] is None
                        else 1 if validation["manifest_valid"] else 0
                    ),
                    json.dumps(validation, ensure_ascii=False),
                ),
            )
            conn.commit()

    def _open_session(self, validation: dict) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO organism_runtime_sessions(
                       boot_session_id, started_at,
                       startup_validation_status, continuity_status
                   ) VALUES (?, ?, ?, ?)""",
                (
                    self.boot_session_id,
                    _iso_now(),
                    validation["status"],
                    validation["status"],
                ),
            )
            conn.commit()

    def _close_session(self, *, reason: str) -> None:
        if not self.boot_session_id:
            return
        with connect() as conn:
            conn.execute(
                """UPDATE organism_runtime_sessions
                   SET ended_at=?, shutdown_reason=?,
                       continuity_status='sealed_shutdown',
                       updated_at=CURRENT_TIMESTAMP
                   WHERE boot_session_id=?""",
                (_iso_now(), reason[:500], self.boot_session_id),
            )
            conn.commit()

    def _set_continuity_status(self, status: str) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE organism_identity_state
                   SET continuity_status=?, updated_at=CURRENT_TIMESTAMP
                   WHERE id=1""",
                (status,),
            )
            conn.commit()

    def _critical_manifest(self) -> dict:
        tables = {
            table: self._table_digest(table)
            for table in self.MANIFEST_TABLES
        }
        with connect() as conn:
            schema_version = int(
                conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
                ).fetchone()[0]
            )
        return {
            "schema_version": schema_version,
            "identity_hash": self._identity_hash(),
            "tables": tables,
        }

    def _table_digest(self, table: str) -> dict:
        with connect() as conn:
            columns = [
                str(row["name"])
                for row in conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
            ]
            if not columns:
                return {"count": 0, "sha256": self._sha_text("")}
            info = conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
            pk_columns = [
                str(row["name"])
                for row in info
                if int(row["pk"] or 0) > 0
            ]
            order_by = ", ".join(pk_columns or columns[:1])
            rows = conn.execute(
                f"SELECT * FROM {table} ORDER BY {order_by}"
            ).fetchall()

        digest = hashlib.sha256()
        for row in rows:
            encoded = json.dumps(
                dict(row),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
            digest.update(encoded)
            digest.update(b"\n")
        return {
            "count": len(rows),
            "sha256": digest.hexdigest(),
        }

    def _identity_hash(self) -> str:
        return self._sha_json(personality.profile)

    @classmethod
    def _snapshot_hash(
        cls,
        *,
        previous_state_hash: str,
        snapshot_type: str,
        payload: dict,
    ) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        raw = (
            str(previous_state_hash)
            + "\n"
            + str(snapshot_type)
            + "\n"
            + canonical
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _identity_state(self) -> dict:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM organism_identity_state WHERE id=1"
            ).fetchone()
        if not row:
            created = self._ensure_identity_state()
            if created is None:
                raise RuntimeError("Digital organism identity state unavailable")
            with connect() as conn:
                row = conn.execute(
                    "SELECT * FROM organism_identity_state WHERE id=1"
                ).fetchone()
        return dict(row)

    @classmethod
    def _decode_evidence(cls, item: dict) -> dict:
        item["evidence"] = cls._json(item.pop("evidence_json"), {})
        return item

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

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
                parsed = datetime.strptime(
                    text[:19],
                    "%Y-%m-%d %H:%M:%S",
                )
            except ValueError:
                return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _elapsed(start: datetime | None, end: datetime) -> dict | None:
        if start is None:
            return None
        seconds = max(0.0, (end - start).total_seconds())
        return {
            "seconds": round(seconds, 3),
            "hours": round(seconds / 3600.0, 6),
            "days": round(seconds / 86400.0, 6),
            "since": start.isoformat(),
        }

    @staticmethod
    def _until(target: datetime | None, now: datetime) -> dict | None:
        if target is None:
            return None
        seconds = (target - now).total_seconds()
        return {
            "seconds": round(seconds, 3),
            "days": round(seconds / 86400.0, 6),
            "target": target.isoformat(),
            "overdue": seconds < 0,
        }

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _sha_json(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _sha_text(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _emit(
        self,
        event_type: str,
        *,
        payload: dict,
        importance: float,
    ) -> None:
        if self.events is not None:
            self.events.emit(
                event_type,
                scope="personal",
                payload=payload,
                importance=importance,
            )
