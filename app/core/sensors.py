from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..db import add_sensor_snapshot, list_modules, recent_sensor_snapshots
from .planner import Planner
from .state import StateManager


@dataclass
class SensorReading:
    sensor: str
    status: str
    payload: dict
    importance: float = 0.3

    def to_dict(self) -> dict:
        return asdict(self)


class SensorHub:
    """Read-only sensors for Aishin's local project environment."""

    EXCLUDED_NAMES = {
        ".env",
        ".git",
        ".venv",
        "__pycache__",
        "aishin.db",
    }

    def __init__(self, *, root: Path, planner: Planner) -> None:
        self.root = root.resolve()
        self.planner = planner
        self.state = StateManager()

    def runtime(self, *, scope: str) -> SensorReading:
        state = self.state.load()
        return SensorReading(
            sensor="runtime",
            status="ok",
            payload={
                "status": state.status,
                "activity": state.activity,
                "focus": state.focus,
                "attention": state.attention,
                "scope": scope,
                "heartbeat_at": state.heartbeat_at,
            },
            importance=0.2,
        )

    def modules(self, *, scope: str) -> SensorReading:
        modules = list_modules()
        return SensorReading(
            sensor="modules",
            status="ok",
            payload={
                "count": len(modules),
                "enabled": [
                    item["code"]
                    for item in modules
                    if bool(item.get("enabled"))
                ],
            },
            importance=0.25,
        )

    def planner_sensor(self, *, scope: str) -> SensorReading:
        items = self.planner.open_items(scope=scope)
        notices = self.planner.inspect(scope=scope)
        status = "attention" if any(n.severity == "warning" for n in notices) else "ok"
        return SensorReading(
            sensor="planner",
            status=status,
            payload={
                "active_goals": len(items["goals"]),
                "open_tasks": len(items["tasks"]),
                "notices": [n.__dict__ for n in notices[:10]],
            },
            importance=0.7 if status == "attention" else 0.3,
        )

    def filesystem(self, *, scope: str) -> SensorReading:
        total_files = 0
        total_bytes = 0
        extensions: dict[str, int] = {}

        for path in self.root.rglob("*"):
            try:
                relative = path.relative_to(self.root)
            except ValueError:
                continue

            if any(part in self.EXCLUDED_NAMES for part in relative.parts):
                continue
            if not path.is_file():
                continue

            total_files += 1
            try:
                total_bytes += path.stat().st_size
            except OSError:
                pass

            suffix = path.suffix.lower() or "[no_ext]"
            extensions[suffix] = extensions.get(suffix, 0) + 1

        top_extensions = sorted(
            extensions.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:12]

        return SensorReading(
            sensor="filesystem",
            status="ok",
            payload={
                "files": total_files,
                "bytes": total_bytes,
                "top_extensions": dict(top_extensions),
            },
            importance=0.15,
        )

    def scan(self, *, scope: str, persist: bool = True) -> list[dict]:
        readings = [
            self.runtime(scope=scope),
            self.modules(scope=scope),
            self.planner_sensor(scope=scope),
            self.filesystem(scope=scope),
        ]

        if persist:
            for item in readings:
                add_sensor_snapshot(
                    item.sensor,
                    scope,
                    item.status,
                    item.payload,
                    item.importance,
                )

        return [item.to_dict() for item in readings]

    def history(
        self,
        *,
        scope: str,
        limit: int = 50,
        sensor: str | None = None,
    ) -> list[dict]:
        return recent_sensor_snapshots(scope, limit=limit, sensor=sensor)
