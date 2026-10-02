from __future__ import annotations

import json
from uuid import uuid4

from ..db import connect


class CognitiveTraceStore:
    """Persistent per-request cognitive traces.

    Each request owns a unique trace row; no process-global mutable working
    context is required to render the latest completed state.
    """

    @staticmethod
    def new_request_id() -> str:
        return uuid4().hex

    def record(
        self,
        *,
        request_id: str,
        scope: str,
        query: str,
        trace: dict,
        provider: dict,
        status: str = "completed",
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO cognitive_request_traces(
                       request_id, scope, query, status,
                       trace_json, provider_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    request_id,
                    scope,
                    query[:1200],
                    status,
                    json.dumps(trace, ensure_ascii=False),
                    json.dumps(provider, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def latest(self, *, scope: str) -> dict:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM cognitive_request_traces
                   WHERE scope=?
                   ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()

        if row is None:
            return {
                "request_id": "",
                "scope": scope,
                "query": "",
                "semantic_used": False,
                "memories": [],
            }

        item = dict(row)
        trace = json.loads(item.pop("trace_json") or "{}")
        provider = json.loads(item.pop("provider_json") or "{}")
        return {
            **trace,
            "request_id": item["request_id"],
            "trace_status": item["status"],
            "provider_runtime": provider,
            "trace_id": item["id"],
            "trace_created_at": item["created_at"],
        }

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM cognitive_request_traces
                   WHERE scope=?
                   ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["trace"] = json.loads(item.pop("trace_json") or "{}")
            item["provider"] = json.loads(item.pop("provider_json") or "{}")
            result.append(item)
        return result
