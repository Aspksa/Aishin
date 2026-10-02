from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ..db import connect


@dataclass
class LearningUpdate:
    applied: bool
    outcome: str
    strategy_id: int | None
    reliability: float | None
    reason: str

    def to_dict(self) -> dict:
        return {
            "applied": self.applied,
            "outcome": self.outcome,
            "strategy_id": self.strategy_id,
            "reliability": self.reliability,
            "reason": self.reason,
        }


class LogicLearning:
    """Learn strategy reliability only from explicit later feedback."""

    POSITIVE_MARKERS = (
        "сработало",
        "получилось",
        "исправлено",
        "решено",
        "заработало",
        "помогло",
        "готово теперь работает",
    )
    NEGATIVE_MARKERS = (
        "не сработало",
        "не помогло",
        "не работает",
        "ошибка осталась",
        "проблема осталась",
        "стало хуже",
    )

    def ingest_feedback(
        self,
        message: str,
        *,
        scope: str,
    ) -> LearningUpdate:
        outcome = self._feedback_outcome(message)
        if outcome == "none":
            return LearningUpdate(
                applied=False,
                outcome="none",
                strategy_id=None,
                reliability=None,
                reason="no_explicit_feedback_signal",
            )

        latest = self._latest_logic_decision(scope=scope)
        if latest is None:
            return LearningUpdate(
                applied=False,
                outcome=outcome,
                strategy_id=None,
                reliability=None,
                reason="no_previous_logic_decision",
            )

        strategy = str(latest.get("selected_strategy") or "").strip()
        mode = str(latest.get("mode") or "FAST")
        if not strategy:
            return LearningUpdate(
                applied=False,
                outcome=outcome,
                strategy_id=None,
                reliability=None,
                reason="previous_decision_has_no_strategy",
            )

        strategy_key = self._strategy_key(mode, strategy)
        strategy_id, successes, failures = self._upsert_strategy(
            scope=scope,
            strategy_key=strategy_key,
            mode=mode,
            strategy=strategy,
        )

        if outcome == "success":
            successes += 1
            delta = 1.0
        else:
            failures += 1
            delta = -1.0

        reliability = self._reliability(successes, failures)
        self._update_strategy(
            strategy_id=strategy_id,
            successes=successes,
            failures=failures,
            reliability=reliability,
            feedback=message,
        )
        self._record_event(
            scope=scope,
            strategy_id=strategy_id,
            feedback=message,
            outcome=outcome,
            delta=delta,
            details={
                "logic_decision_id": latest.get("id"),
                "mode": mode,
                "strategy_key": strategy_key,
            },
        )

        return LearningUpdate(
            applied=True,
            outcome=outcome,
            strategy_id=strategy_id,
            reliability=reliability,
            reason="explicit_user_feedback",
        )

    def recommend(
        self,
        *,
        scope: str,
        mode: str,
        limit: int = 3,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT
                       s.*,
                       COALESCE(q.lifecycle, 'candidate') AS lifecycle,
                       COALESCE(
                         q.effective_reliability,
                         s.reliability
                       ) AS effective_reliability,
                       COALESCE(q.drift_score, 0.0) AS drift_score,
                       q.rank_in_mode,
                       COALESCE(
                         q.reason,
                         'quality_gate_not_refreshed'
                       ) AS quality_reason
                   FROM logic_strategies s
                   LEFT JOIN strategy_quality_state q
                     ON q.strategy_id=s.id
                   WHERE s.scope=? AND s.mode=?
                     AND COALESCE(q.lifecycle, 'candidate')<>'deprecated'
                   ORDER BY
                     CASE COALESCE(q.lifecycle, 'candidate')
                       WHEN 'trusted' THEN 0
                       WHEN 'observed' THEN 1
                       ELSE 2
                     END,
                     COALESCE(
                       q.effective_reliability,
                       s.reliability
                     ) DESC,
                     s.successes DESC,
                     s.id DESC
                   LIMIT ?""",
                (scope, mode, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_events(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM logic_learning_events
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
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

    @staticmethod
    def prompt_block(strategies: list[dict]) -> str:
        if not strategies:
            return "Logic Learning: подтверждённых стратегий для этого режима пока нет."

        lines = [
            "Logic Learning: ранее подтверждённые стратегии.",
            "Используй их как опыт, а не как безусловное правило.",
        ]
        for item in strategies:
            lines.append(
                f"- lifecycle={item.get('lifecycle', 'candidate')}, "
                f"effective={float(item.get('effective_reliability', item.get('reliability', 0.0))):.2f}, "
                f"drift={float(item.get('drift_score', 0.0)):.2f}, "
                f"successes={item.get('successes', 0)}, "
                f"failures={item.get('failures', 0)}: "
                f"{item.get('strategy')}"
            )
        return "\n".join(lines)

    def _latest_logic_decision(self, *, scope: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM logic_decisions
                   WHERE scope=? ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _feedback_outcome(message: str) -> str:
        text = message.casefold()

        if any(marker in text for marker in LogicLearning.NEGATIVE_MARKERS):
            return "failure"
        if any(marker in text for marker in LogicLearning.POSITIVE_MARKERS):
            return "success"
        return "none"

    @staticmethod
    def _strategy_key(mode: str, strategy: str) -> str:
        normalized = " ".join(strategy.casefold().split())
        digest = hashlib.sha256(
            f"{mode}|{normalized}".encode("utf-8")
        ).hexdigest()
        return digest[:32]

    @staticmethod
    def _reliability(successes: int, failures: int) -> float:
        # Beta(2,2) prior prevents one success from becoming certainty.
        return round(
            (successes + 2) / (successes + failures + 4),
            4,
        )

    @staticmethod
    def _upsert_strategy(
        *,
        scope: str,
        strategy_key: str,
        mode: str,
        strategy: str,
    ) -> tuple[int, int, int]:
        with connect() as conn:
            row = conn.execute(
                """SELECT id, successes, failures
                   FROM logic_strategies
                   WHERE scope=? AND strategy_key=?""",
                (scope, strategy_key),
            ).fetchone()

            if row is not None:
                return int(row[0]), int(row[1]), int(row[2])

            cur = conn.execute(
                """INSERT INTO logic_strategies(
                       scope, strategy_key, mode, strategy, last_used_at
                   ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                (scope, strategy_key, mode, strategy),
            )
            conn.commit()
            return int(cur.lastrowid), 0, 0

    @staticmethod
    def _update_strategy(
        *,
        strategy_id: int,
        successes: int,
        failures: int,
        reliability: float,
        feedback: str,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE logic_strategies
                   SET successes=?,
                       failures=?,
                       reliability=?,
                       last_feedback=?,
                       last_used_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    successes,
                    failures,
                    reliability,
                    feedback[:500],
                    strategy_id,
                ),
            )
            conn.commit()

    @staticmethod
    def _record_event(
        *,
        scope: str,
        strategy_id: int,
        feedback: str,
        outcome: str,
        delta: float,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO logic_learning_events(
                       scope, strategy_id, feedback, outcome,
                       delta, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    strategy_id,
                    feedback[:500],
                    outcome,
                    delta,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
