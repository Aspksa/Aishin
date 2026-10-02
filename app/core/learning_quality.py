from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from ..db import connect


class LearningQualityGate:
    """Promote, decay and deprecate learned patterns and strategies."""

    PATTERN_HALF_LIFE_DAYS = 30.0
    STRATEGY_HALF_LIFE_DAYS = 45.0
    MAX_STALE_DAYS = 120.0

    LIFECYCLES = {"candidate", "observed", "trusted", "deprecated"}

    def refresh(self, *, scope: str) -> dict:
        patterns = self._refresh_patterns(scope=scope)
        strategies = self._refresh_strategies(scope=scope)
        return {
            "scope": scope,
            "patterns": patterns,
            "strategies": strategies,
        }

    def trusted_patterns(
        self,
        *,
        scope: str,
        limit: int = 20,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT
                       p.*,
                       q.lifecycle,
                       q.raw_score,
                       q.effective_score,
                       q.decay_factor,
                       q.contradiction_rate,
                       q.age_days,
                       q.reason AS quality_reason
                   FROM learning_patterns p
                   JOIN learning_pattern_quality q ON q.pattern_id=p.id
                   WHERE p.scope=? AND q.lifecycle='trusted'
                   ORDER BY q.effective_score DESC,
                            p.observations DESC,
                            p.id DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(
                item.pop("evidence_json") or "[]"
            )
            result.append(item)
        return result

    def strategies(
        self,
        *,
        scope: str,
        mode: str | None = None,
        include_deprecated: bool = True,
        limit: int = 50,
    ) -> list[dict]:
        where = ["q.scope=?"]
        params: list[object] = [scope]
        if mode:
            where.append("q.mode=?")
            params.append(mode)
        if not include_deprecated:
            where.append("q.lifecycle<>'deprecated'")
        params.append(limit)

        with connect() as conn:
            rows = conn.execute(
                f"""SELECT
                       s.*,
                       q.lifecycle,
                       q.raw_reliability,
                       q.effective_reliability,
                       q.decay_factor,
                       q.drift_score,
                       q.evidence_count,
                       q.rank_in_mode,
                       q.reason AS quality_reason
                   FROM logic_strategies s
                   JOIN strategy_quality_state q ON q.strategy_id=s.id
                   WHERE {' AND '.join(where)}
                   ORDER BY
                       CASE q.lifecycle
                         WHEN 'trusted' THEN 0
                         WHEN 'observed' THEN 1
                         WHEN 'candidate' THEN 2
                         ELSE 3
                       END,
                       q.effective_reliability DESC,
                       s.id DESC
                   LIMIT ?""",
                tuple(params),
            ).fetchall()

        return [dict(row) for row in rows]

    def recent_events(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM learning_quality_events
                   WHERE scope=?
                   ORDER BY id DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(
                item.pop("details_json") or "{}"
            )
            result.append(item)
        return result

    def _refresh_patterns(self, *, scope: str) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM learning_patterns
                   WHERE scope=?""",
                (scope,),
            ).fetchall()

        counts = {name: 0 for name in self.LIFECYCLES}
        changed = 0

        for row in rows:
            item = dict(row)
            observations = int(item["observations"])
            successes = int(item["successes"])
            failures = int(item["failures"])
            raw = float(item["score"])
            age_days = self._age_days(
                str(item.get("last_seen_at") or "")
            )
            decay = self._decay(
                age_days,
                half_life_days=self.PATTERN_HALF_LIFE_DAYS,
            )
            effective = self._decayed_score(raw, decay)

            outcomes = successes + failures
            contradiction_rate = (
                min(successes, failures) / outcomes
                if outcomes > 0
                else 0.0
            )

            lifecycle, reason = self._pattern_lifecycle(
                observations=observations,
                raw_score=raw,
                effective_score=effective,
                contradiction_rate=contradiction_rate,
                age_days=age_days,
            )

            if self._upsert_pattern_quality(
                scope=scope,
                pattern_id=int(item["id"]),
                lifecycle=lifecycle,
                raw_score=raw,
                effective_score=effective,
                decay_factor=decay,
                contradiction_rate=contradiction_rate,
                age_days=age_days,
                reason=reason,
            ):
                changed += 1
            counts[lifecycle] += 1

        return {
            "total": len(rows),
            "changed": changed,
            "lifecycle": counts,
        }

    def _refresh_strategies(self, *, scope: str) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM logic_strategies
                   WHERE scope=?""",
                (scope,),
            ).fetchall()

        counts = {name: 0 for name in self.LIFECYCLES}
        changed = 0
        by_mode: dict[str, list[dict]] = {}

        for row in rows:
            item = dict(row)
            strategy_id = int(item["id"])
            successes = int(item["successes"])
            failures = int(item["failures"])
            evidence_count = successes + failures
            raw = float(item["reliability"])
            age_days = self._age_days(
                str(
                    item.get("last_used_at")
                    or item.get("updated_at")
                    or ""
                )
            )
            decay = self._decay(
                age_days,
                half_life_days=self.STRATEGY_HALF_LIFE_DAYS,
            )
            effective = self._decayed_score(raw, decay)
            drift = self._strategy_drift(
                scope=scope,
                strategy_id=strategy_id,
                historical_failures=failures,
                historical_total=evidence_count,
            )

            lifecycle, reason = self._strategy_lifecycle(
                evidence_count=evidence_count,
                effective_reliability=effective,
                drift_score=drift,
                age_days=age_days,
            )

            quality = {
                "strategy_id": strategy_id,
                "mode": str(item["mode"]),
                "lifecycle": lifecycle,
                "raw_reliability": raw,
                "effective_reliability": effective,
                "decay_factor": decay,
                "drift_score": drift,
                "evidence_count": evidence_count,
                "reason": reason,
            }
            by_mode.setdefault(str(item["mode"]), []).append(quality)
            counts[lifecycle] += 1

        for mode_items in by_mode.values():
            ranked = sorted(
                [
                    item
                    for item in mode_items
                    if item["lifecycle"] != "deprecated"
                ],
                key=lambda item: (
                    item["lifecycle"] != "trusted",
                    -item["effective_reliability"],
                    -item["evidence_count"],
                    item["strategy_id"],
                ),
            )
            ranks = {
                item["strategy_id"]: rank
                for rank, item in enumerate(ranked, start=1)
            }

            for item in mode_items:
                if self._upsert_strategy_quality(
                    scope=scope,
                    rank_in_mode=ranks.get(item["strategy_id"]),
                    **item,
                ):
                    changed += 1

        return {
            "total": len(rows),
            "changed": changed,
            "lifecycle": counts,
        }

    @staticmethod
    def _pattern_lifecycle(
        *,
        observations: int,
        raw_score: float,
        effective_score: float,
        contradiction_rate: float,
        age_days: float,
    ) -> tuple[str, str]:
        if observations < 3:
            return "candidate", "insufficient_observations"

        if age_days >= LearningQualityGate.MAX_STALE_DAYS:
            return "deprecated", "stale_pattern"

        if observations >= 5 and effective_score < 0.40:
            return "deprecated", "persistent_low_effective_score"

        if contradiction_rate > 0.45:
            return "observed", "high_contradiction_rate"

        trust_threshold = 0.62
        if observations >= 5 and effective_score >= trust_threshold:
            return "trusted", "sufficient_repeated_evidence"

        return "observed", "requires_more_confirmation"

    @staticmethod
    def _strategy_lifecycle(
        *,
        evidence_count: int,
        effective_reliability: float,
        drift_score: float,
        age_days: float,
    ) -> tuple[str, str]:
        if evidence_count < 3:
            return "candidate", "insufficient_explicit_feedback"

        if age_days >= LearningQualityGate.MAX_STALE_DAYS:
            return "deprecated", "stale_strategy"

        if evidence_count >= 5 and effective_reliability < 0.40:
            return "deprecated", "persistent_low_reliability"

        if drift_score >= 0.35:
            return "observed", "recent_negative_drift"

        if (
            evidence_count >= 5
            and effective_reliability >= 0.62
            and drift_score < 0.25
        ):
            return "trusted", "stable_positive_feedback"

        return "observed", "not_yet_trusted"

    def _upsert_pattern_quality(
        self,
        *,
        scope: str,
        pattern_id: int,
        lifecycle: str,
        raw_score: float,
        effective_score: float,
        decay_factor: float,
        contradiction_rate: float,
        age_days: float,
        reason: str,
    ) -> bool:
        with connect() as conn:
            old = conn.execute(
                """SELECT * FROM learning_pattern_quality
                   WHERE pattern_id=?""",
                (pattern_id,),
            ).fetchone()

            old_lifecycle = (
                str(old["lifecycle"]) if old is not None else ""
            )
            old_score = (
                float(old["effective_score"])
                if old is not None
                else None
            )
            lifecycle_changed = old_lifecycle != lifecycle

            conn.execute(
                """INSERT INTO learning_pattern_quality(
                       pattern_id, scope, lifecycle, raw_score,
                       effective_score, decay_factor,
                       contradiction_rate, age_days, reason,
                       promoted_at, deprecated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,
                             CASE WHEN ?='trusted'
                                  THEN CURRENT_TIMESTAMP ELSE NULL END,
                             CASE WHEN ?='deprecated'
                                  THEN CURRENT_TIMESTAMP ELSE NULL END)
                   ON CONFLICT(pattern_id) DO UPDATE SET
                       scope=excluded.scope,
                       lifecycle=excluded.lifecycle,
                       raw_score=excluded.raw_score,
                       effective_score=excluded.effective_score,
                       decay_factor=excluded.decay_factor,
                       contradiction_rate=excluded.contradiction_rate,
                       age_days=excluded.age_days,
                       reason=excluded.reason,
                       promoted_at=CASE
                         WHEN learning_pattern_quality.lifecycle<>'trusted'
                              AND excluded.lifecycle='trusted'
                         THEN CURRENT_TIMESTAMP
                         ELSE learning_pattern_quality.promoted_at END,
                       deprecated_at=CASE
                         WHEN excluded.lifecycle='deprecated'
                         THEN COALESCE(
                           learning_pattern_quality.deprecated_at,
                           CURRENT_TIMESTAMP
                         )
                         ELSE NULL END,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    pattern_id,
                    scope,
                    lifecycle,
                    raw_score,
                    effective_score,
                    decay_factor,
                    contradiction_rate,
                    age_days,
                    reason,
                    lifecycle,
                    lifecycle,
                ),
            )

            if lifecycle_changed:
                self._record_event(
                    conn=conn,
                    scope=scope,
                    subject_type="pattern",
                    subject_id=pattern_id,
                    old_lifecycle=old_lifecycle,
                    new_lifecycle=lifecycle,
                    old_score=old_score,
                    new_score=effective_score,
                    reason=reason,
                    details={
                        "decay_factor": decay_factor,
                        "contradiction_rate": contradiction_rate,
                        "age_days": age_days,
                    },
                )
            conn.commit()
            return lifecycle_changed

    def _upsert_strategy_quality(
        self,
        *,
        scope: str,
        strategy_id: int,
        mode: str,
        lifecycle: str,
        raw_reliability: float,
        effective_reliability: float,
        decay_factor: float,
        drift_score: float,
        evidence_count: int,
        rank_in_mode: int | None,
        reason: str,
    ) -> bool:
        with connect() as conn:
            old = conn.execute(
                """SELECT * FROM strategy_quality_state
                   WHERE strategy_id=?""",
                (strategy_id,),
            ).fetchone()

            old_lifecycle = (
                str(old["lifecycle"]) if old is not None else ""
            )
            old_score = (
                float(old["effective_reliability"])
                if old is not None
                else None
            )
            lifecycle_changed = old_lifecycle != lifecycle

            conn.execute(
                """INSERT INTO strategy_quality_state(
                       strategy_id, scope, mode, lifecycle,
                       raw_reliability, effective_reliability,
                       decay_factor, drift_score, evidence_count,
                       rank_in_mode, reason, promoted_at, deprecated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                             CASE WHEN ?='trusted'
                                  THEN CURRENT_TIMESTAMP ELSE NULL END,
                             CASE WHEN ?='deprecated'
                                  THEN CURRENT_TIMESTAMP ELSE NULL END)
                   ON CONFLICT(strategy_id) DO UPDATE SET
                       scope=excluded.scope,
                       mode=excluded.mode,
                       lifecycle=excluded.lifecycle,
                       raw_reliability=excluded.raw_reliability,
                       effective_reliability=excluded.effective_reliability,
                       decay_factor=excluded.decay_factor,
                       drift_score=excluded.drift_score,
                       evidence_count=excluded.evidence_count,
                       rank_in_mode=excluded.rank_in_mode,
                       reason=excluded.reason,
                       promoted_at=CASE
                         WHEN strategy_quality_state.lifecycle<>'trusted'
                              AND excluded.lifecycle='trusted'
                         THEN CURRENT_TIMESTAMP
                         ELSE strategy_quality_state.promoted_at END,
                       deprecated_at=CASE
                         WHEN excluded.lifecycle='deprecated'
                         THEN COALESCE(
                           strategy_quality_state.deprecated_at,
                           CURRENT_TIMESTAMP
                         )
                         ELSE NULL END,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    strategy_id,
                    scope,
                    mode,
                    lifecycle,
                    raw_reliability,
                    effective_reliability,
                    decay_factor,
                    drift_score,
                    evidence_count,
                    rank_in_mode,
                    reason,
                    lifecycle,
                    lifecycle,
                ),
            )

            if lifecycle_changed:
                self._record_event(
                    conn=conn,
                    scope=scope,
                    subject_type="strategy",
                    subject_id=strategy_id,
                    old_lifecycle=old_lifecycle,
                    new_lifecycle=lifecycle,
                    old_score=old_score,
                    new_score=effective_reliability,
                    reason=reason,
                    details={
                        "mode": mode,
                        "rank_in_mode": rank_in_mode,
                        "drift_score": drift_score,
                        "decay_factor": decay_factor,
                        "evidence_count": evidence_count,
                    },
                )
            conn.commit()
            return lifecycle_changed

    def _strategy_drift(
        self,
        *,
        scope: str,
        strategy_id: int,
        historical_failures: int,
        historical_total: int,
    ) -> float:
        with connect() as conn:
            rows = conn.execute(
                """SELECT outcome FROM logic_learning_events
                   WHERE scope=? AND strategy_id=?
                   ORDER BY id DESC LIMIT 8""",
                (scope, strategy_id),
            ).fetchall()

        if len(rows) < 3:
            return 0.0

        recent_failures = sum(
            1 for row in rows if str(row["outcome"]) == "failure"
        )
        recent_rate = recent_failures / len(rows)
        historical_rate = (
            historical_failures / historical_total
            if historical_total > 0
            else 0.0
        )
        return round(
            max(0.0, min(1.0, recent_rate - historical_rate)),
            4,
        )

    @staticmethod
    def _decay(age_days: float, *, half_life_days: float) -> float:
        return round(
            max(
                0.0,
                min(
                    1.0,
                    math.pow(
                        0.5,
                        max(0.0, age_days) / half_life_days,
                    ),
                ),
            ),
            6,
        )

    @staticmethod
    def _decayed_score(raw: float, decay_factor: float) -> float:
        return round(
            max(
                0.0,
                min(
                    1.0,
                    0.5 + (float(raw) - 0.5) * decay_factor,
                ),
            ),
            4,
        )

    @staticmethod
    def _age_days(value: str) -> float:
        if not value:
            return 10_000.0
        try:
            normalized = value.replace(" ", "T")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return max(
                0.0,
                (
                    datetime.now(timezone.utc) - parsed
                ).total_seconds() / 86400.0,
            )
        except Exception:
            return 10_000.0

    @staticmethod
    def _record_event(
        *,
        conn,
        scope: str,
        subject_type: str,
        subject_id: int,
        old_lifecycle: str,
        new_lifecycle: str,
        old_score: float | None,
        new_score: float,
        reason: str,
        details: dict,
    ) -> None:
        conn.execute(
            """INSERT INTO learning_quality_events(
                   scope, subject_type, subject_id,
                   old_lifecycle, new_lifecycle,
                   old_score, new_score, reason, details_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                scope,
                subject_type,
                subject_id,
                old_lifecycle,
                new_lifecycle,
                old_score,
                new_score,
                reason,
                json.dumps(details, ensure_ascii=False),
            ),
        )
