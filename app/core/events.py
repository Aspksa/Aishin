from __future__ import annotations

from typing import Any

from ..db import add_event, connect, recent_events


class EventBus:
    """Persistent event journal used as Aishin's observable event stream."""

    def emit(
        self,
        event_type: str,
        *,
        scope: str = "personal",
        payload: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> int:
        return add_event(
            event_type=event_type,
            scope=scope,
            payload=payload or {},
            importance=importance,
        )

    def recent(
        self,
        limit: int = 30,
        *,
        scope: str | None = None,
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        if scope is None:
            return recent_events(limit=limit)
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM events
                   WHERE scope=?
                   ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result: list[dict[str, Any]] = []
        import json
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
            result.append(item)
        return result

    def stats(self, *, scope: str) -> dict[str, Any]:
        with connect() as conn:
            row = conn.execute(
                """SELECT
                       COUNT(*) AS total,
                       SUM(
                           CASE
                               WHEN datetime(created_at) >= datetime('now', '-5 minutes')
                               THEN 1 ELSE 0
                           END
                       ) AS events_5m,
                       SUM(
                           CASE
                               WHEN datetime(created_at) >= datetime('now', '-1 hour')
                               THEN 1 ELSE 0
                           END
                       ) AS events_1h,
                       SUM(
                           CASE
                               WHEN datetime(created_at) >= datetime('now', '-1 hour')
                                AND importance >= 0.8
                               THEN 1 ELSE 0
                           END
                       ) AS attention_events_1h,
                       AVG(importance) AS average_importance
                   FROM events
                   WHERE scope=?""",
                (scope,),
            ).fetchone()
        return {
            "scope": scope,
            "total": int(row["total"] or 0),
            "events_5m": int(row["events_5m"] or 0),
            "events_1h": int(row["events_1h"] or 0),
            "attention_events_1h": int(row["attention_events_1h"] or 0),
            "average_importance": round(
                float(row["average_importance"] or 0.0),
                4,
            ),
        }
