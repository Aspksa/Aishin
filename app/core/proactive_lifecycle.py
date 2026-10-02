from __future__ import annotations

from ..db import connect, get_proactive_decision, update_proactive_decision


class ProactiveLifecycle:
    """Persistent active/resolved lifecycle for proactive condition fingerprints."""

    def observe(
        self,
        *,
        scope: str,
        fingerprint: str,
        source: str,
    ) -> dict:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM proactive_conditions
                   WHERE scope=? AND fingerprint=?""",
                (scope, fingerprint),
            ).fetchone()

            if row is None:
                conn.execute(
                    """INSERT INTO proactive_conditions(
                           scope, fingerprint, source, active, generation,
                           last_decision_id, disposition
                       ) VALUES (?, ?, ?, 1, 1, NULL, '')""",
                    (scope, fingerprint, source),
                )
                conn.commit()
                return {
                    "active": True,
                    "newly_active": True,
                    "generation": 1,
                    "last_decision_id": None,
                    "suppressed": False,
                }

            item = dict(row)
            if not bool(item["active"]):
                generation = int(item["generation"]) + 1
                conn.execute(
                    """UPDATE proactive_conditions
                       SET source=?,
                           active=1,
                           generation=?,
                           last_decision_id=NULL,
                           disposition='',
                           last_seen_at=CURRENT_TIMESTAMP,
                           resolved_at=NULL,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE scope=? AND fingerprint=?""",
                    (
                        source,
                        generation,
                        scope,
                        fingerprint,
                    ),
                )
                conn.commit()
                return {
                    "active": True,
                    "newly_active": True,
                    "generation": generation,
                    "last_decision_id": None,
                    "suppressed": False,
                }

            conn.execute(
                """UPDATE proactive_conditions
                   SET source=?,
                       last_seen_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=? AND fingerprint=?""",
                (source, scope, fingerprint),
            )
            conn.commit()
            return {
                "active": True,
                "newly_active": False,
                "generation": int(item["generation"]),
                "last_decision_id": item["last_decision_id"],
                "suppressed": item["last_decision_id"] is not None,
            }

    def bind_decision(
        self,
        *,
        scope: str,
        fingerprint: str,
        decision_id: int,
    ) -> None:
        with connect() as conn:
            cur = conn.execute(
                """UPDATE proactive_conditions
                   SET last_decision_id=?,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=? AND fingerprint=? AND active=1""",
                (decision_id, scope, fingerprint),
            )
            if cur.rowcount == 0:
                raise ValueError("active proactive condition not found")
            conn.commit()

    def mark_disposition(
        self,
        *,
        scope: str,
        fingerprint: str,
        disposition: str,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE proactive_conditions
                   SET disposition=?, updated_at=CURRENT_TIMESTAMP
                   WHERE scope=? AND fingerprint=?""",
                (disposition, scope, fingerprint),
            )
            conn.commit()

    def resolve_absent(
        self,
        *,
        scope: str,
        active_fingerprints: set[str],
    ) -> list[int]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proactive_conditions
                   WHERE scope=? AND active=1""",
                (scope,),
            ).fetchall()

        dismissed: list[int] = []
        for row in rows:
            item = dict(row)
            fingerprint = str(item["fingerprint"])
            if fingerprint in active_fingerprints:
                continue

            decision_id = item.get("last_decision_id")
            if decision_id is not None:
                decision = get_proactive_decision(int(decision_id), scope)
                if decision and decision["status"] in {"pending", "approved"}:
                    update_proactive_decision(
                        int(decision_id),
                        scope=scope,
                        status="dismissed",
                        execution={
                            "reason": "underlying_condition_resolved",
                        },
                    )
                    dismissed.append(int(decision_id))

            with connect() as conn:
                conn.execute(
                    """UPDATE proactive_conditions
                       SET active=0,
                           resolved_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE scope=? AND fingerprint=?""",
                    (scope, fingerprint),
                )
                conn.commit()

        return dismissed

    def recent(
        self,
        *,
        scope: str,
        limit: int = 100,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM proactive_conditions
                   WHERE scope=?
                   ORDER BY active DESC, updated_at DESC
                   LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["active"] = bool(item["active"])
            result.append(item)
        return result
