from __future__ import annotations

from typing import Any

from ..db import add_event, recent_events


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

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        return recent_events(limit=limit)
