from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ..db import get_runtime_state, set_runtime_state


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AishinState:
    """Persistent runtime state for continuity and interface behavior."""

    status: str = "awake"
    mood: str = "calm"
    focus: str = "waiting"
    activity: str = "idle"
    attention: float = 1.0
    interaction_count: int = 0
    last_seen_at: str = ""
    last_activity_at: str = ""
    heartbeat_at: str = ""
    current_scope: str = "personal"

    def normalize(self) -> "AishinState":
        self.attention = max(0.0, min(1.0, float(self.attention)))
        self.interaction_count = max(0, int(self.interaction_count))
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StateManager:
    KEY = "aishin_runtime_state"

    def load(self) -> AishinState:
        raw = get_runtime_state(self.KEY)
        if not raw:
            now = utc_now()
            state = AishinState(
                last_seen_at=now,
                last_activity_at=now,
                heartbeat_at=now,
            )
            self.save(state)
            return state

        allowed = AishinState.__dataclass_fields__.keys()
        state = AishinState(**{k: raw[k] for k in raw if k in allowed})
        return state.normalize()

    def save(self, state: AishinState) -> None:
        set_runtime_state(self.KEY, state.normalize().to_dict())

    def touch(self, *, activity: str, focus: str | None = None) -> AishinState:
        state = self.load()
        state.status = "awake"
        state.activity = activity
        if focus is not None:
            state.focus = focus
        state.last_activity_at = utc_now()
        self.save(state)
        return state

    def heartbeat(self) -> AishinState:
        state = self.load()
        state.heartbeat_at = utc_now()
        self.save(state)
        return state

    def interaction(self, focus: str) -> AishinState:
        state = self.load()
        state.status = "awake"
        state.activity = "conversation"
        state.focus = focus
        state.interaction_count += 1
        now = utc_now()
        state.last_seen_at = now
        state.last_activity_at = now
        self.save(state)
        return state
