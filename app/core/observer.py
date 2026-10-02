from __future__ import annotations

from dataclasses import dataclass

from .events import EventBus
from .state import StateManager


@dataclass
class Observation:
    severity: str
    code: str
    message: str


class Observer:
    """Passive self-observation layer. It detects conditions but does not act on its own."""

    def __init__(self, state: StateManager, events: EventBus) -> None:
        self.state = state
        self.events = events

    def inspect(self, *, emit_events: bool = False) -> list[Observation]:
        state = self.state.load()
        result: list[Observation] = []

        if state.attention < 0.35:
            result.append(Observation("warning", "low_attention", "Уровень внимания runtime ниже рабочего порога."))

        if state.status != "awake":
            result.append(Observation("info", "not_awake", f"Текущее состояние: {state.status}."))

        if emit_events:
            for item in result:
                self.events.emit(
                    "observer.notice",
                    scope=state.current_scope,
                    payload={
                        "severity": item.severity,
                        "code": item.code,
                        "message": item.message,
                    },
                    importance=0.7 if item.severity == "warning" else 0.3,
                )
        return result
