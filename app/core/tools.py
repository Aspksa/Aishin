from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..db import add_tool_action, recent_tool_actions
from .permissions import PermissionGate
from .planner import Planner


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    capability: str
    destructive: bool = False


class ToolRegistry:
    """Permission-gated tools. Every invocation is audited."""

    FORBIDDEN_NAMES = {
        ".env",
        ".git",
        ".venv",
        "aishin.db",
    }

    SPECS = {
        "planner.create_task": ToolSpec(
            "planner.create_task",
            "Создать внутреннюю задачу Айшин.",
            "manage_internal_plans",
        ),
        "planner.set_task_status": ToolSpec(
            "planner.set_task_status",
            "Изменить статус внутренней задачи.",
            "manage_internal_plans",
        ),
        "project.read_text": ToolSpec(
            "project.read_text",
            "Прочитать текстовый файл внутри проекта.",
            "read_local_context",
        ),
        "project.write_text": ToolSpec(
            "project.write_text",
            "Записать текстовый файл внутри проекта.",
            "modify_files",
        ),
    }

    def __init__(
        self,
        *,
        root: Path,
        permissions: PermissionGate,
        planner: Planner,
    ) -> None:
        self.root = root.resolve()
        self.permissions = permissions
        self.planner = planner

    def catalog(self) -> list[dict]:
        return [asdict(spec) for spec in self.SPECS.values()]

    def invoke(
        self,
        name: str,
        *,
        scope: str,
        arguments: dict,
        dry_run: bool = True,
    ) -> dict:
        spec = self.SPECS.get(name)
        if spec is None:
            return self._audit(
                name,
                scope,
                "unknown",
                "deny",
                "unknown_tool",
                dry_run,
                arguments,
                {"error": "Неизвестный инструмент"},
            )

        mode = self.permissions.mode(spec.capability)

        if mode == "deny":
            return self._audit(
                name,
                scope,
                spec.capability,
                mode,
                "denied",
                dry_run,
                arguments,
                {"error": "Действие запрещено permission gate"},
            )

        if mode == "ask" and not dry_run:
            return self._audit(
                name,
                scope,
                spec.capability,
                mode,
                "approval_required",
                dry_run,
                arguments,
                {"error": "Требуется явное разрешение Господина"},
            )

        try:
            output = self._dispatch(
                name,
                scope=scope,
                arguments=arguments,
                dry_run=dry_run,
            )
            status = "preview" if dry_run else "success"
        except Exception as exc:
            output = {"error": str(exc)}
            status = "error"

        return self._audit(
            name,
            scope,
            spec.capability,
            mode,
            status,
            dry_run,
            arguments,
            output,
        )

    def _dispatch(
        self,
        name: str,
        *,
        scope: str,
        arguments: dict,
        dry_run: bool,
    ) -> dict:
        if name == "planner.create_task":
            title = str(arguments.get("title") or "").strip()
            if not title:
                raise ValueError("Название задачи пустое")
            payload = {
                "title": title,
                "description": str(arguments.get("description") or "").strip(),
                "priority": max(
                    0.0,
                    min(1.0, float(arguments.get("priority", 0.5))),
                ),
                "goal_id": arguments.get("goal_id"),
                "due_at": arguments.get("due_at"),
            }
            if dry_run:
                return {"would_create": payload}
            task_id = self.planner.create_task(
                scope=scope,
                title=payload["title"],
                description=payload["description"],
                priority=payload["priority"],
                goal_id=payload["goal_id"],
                due_at=payload["due_at"],
                source="tool_registry",
                evidence="tool_registry",
            )
            return {"task_id": task_id}

        if name == "planner.set_task_status":
            task_id = int(arguments["task_id"])
            status = str(arguments["status"])
            blocked_reason = str(arguments.get("blocked_reason") or "")
            if dry_run:
                return {
                    "would_update": {
                        "task_id": task_id,
                        "status": status,
                        "blocked_reason": blocked_reason,
                    }
                }
            self.planner.set_task_status(
                task_id,
                status,
                scope=scope,
                blocked_reason=blocked_reason,
            )
            return {"task_id": task_id, "status": status}

        if name == "project.read_text":
            path = self._safe_path(str(arguments.get("path") or ""))
            if dry_run:
                return {
                    "would_read": str(path.relative_to(self.root)),
                    "exists": path.is_file(),
                }
            if not path.is_file():
                raise FileNotFoundError("Файл не найден")
            if path.stat().st_size > 1_000_000:
                raise ValueError("Файл слишком большой для текстового инструмента")
            return {
                "path": str(path.relative_to(self.root)),
                "content": path.read_text(encoding="utf-8"),
            }

        if name == "project.write_text":
            path = self._safe_path(str(arguments.get("path") or ""))
            content = str(arguments.get("content") or "")
            if len(content.encode("utf-8")) > 1_000_000:
                raise ValueError("Содержимое слишком большое")
            if dry_run:
                return {
                    "would_write": str(path.relative_to(self.root)),
                    "bytes": len(content.encode("utf-8")),
                }
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {
                "path": str(path.relative_to(self.root)),
                "bytes": len(content.encode("utf-8")),
            }

        raise ValueError("Инструмент не реализован")

    def _safe_path(self, raw: str) -> Path:
        if not raw.strip():
            raise ValueError("Путь пустой")
        candidate = (self.root / raw).resolve()
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Выход за пределы проекта запрещён") from exc

        if any(part in self.FORBIDDEN_NAMES for part in relative.parts):
            raise ValueError("Доступ к защищённому пути запрещён")
        return candidate

    def _audit(
        self,
        name: str,
        scope: str,
        capability: str,
        permission_mode: str,
        status: str,
        dry_run: bool,
        input_data: dict,
        output_data: dict,
    ) -> dict:
        action_id = add_tool_action(
            name,
            scope,
            capability,
            permission_mode,
            status,
            dry_run,
            input_data,
            output_data,
        )
        return {
            "action_id": action_id,
            "tool": name,
            "capability": capability,
            "permission": permission_mode,
            "status": status,
            "dry_run": dry_run,
            "output": output_data,
        }

    def history(self, *, scope: str, limit: int = 50) -> list[dict]:
        return recent_tool_actions(scope, limit=limit)
