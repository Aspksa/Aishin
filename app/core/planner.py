from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..db import (
    add_task_dependency,
    create_goal,
    create_task,
    get_goal,
    get_task,
    list_goals,
    list_tasks,
    log_planner_change,
    planner_open_items,
    recent_planner_changes,
    task_dependencies,
    update_goal_status,
    update_task_status,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class PlannerNotice:
    severity: str
    code: str
    message: str
    task_id: int | None = None
    goal_id: int | None = None


class Planner:
    """Persistent goals/tasks layer. It plans and notices; it does not execute external actions."""

    def create_goal(
        self,
        *,
        scope: str,
        title: str,
        description: str = "",
        priority: float = 0.5,
        source: str = "explicit_user",
        evidence: str = "",
        due_at: str | None = None,
    ) -> int:
        priority = max(0.0, min(1.0, float(priority)))
        goal_id = create_goal(
            scope,
            title.strip(),
            description.strip(),
            priority,
            source,
            evidence.strip(),
            due_at,
        )
        log_planner_change(
            scope,
            "goal_created",
            goal_id=goal_id,
            details={"title": title.strip(), "priority": priority, "due_at": due_at},
        )
        return goal_id

    def create_task(
        self,
        *,
        scope: str,
        title: str,
        description: str = "",
        goal_id: int | None = None,
        priority: float = 0.5,
        source: str = "explicit_user",
        evidence: str = "",
        due_at: str | None = None,
    ) -> int:
        priority = max(0.0, min(1.0, float(priority)))
        if goal_id is not None and not get_goal(goal_id, scope):
            raise ValueError("goal not found in scope")
        task_id = create_task(
            scope,
            title.strip(),
            description.strip(),
            goal_id,
            priority,
            source,
            evidence.strip(),
            due_at,
        )
        log_planner_change(
            scope,
            "task_created",
            goal_id=goal_id,
            task_id=task_id,
            details={"title": title.strip(), "priority": priority, "due_at": due_at},
        )
        return task_id

    def add_dependency(self, *, scope: str, task_id: int, depends_on_task_id: int) -> int:
        if not get_task(task_id, scope) or not get_task(depends_on_task_id, scope):
            raise ValueError("both tasks must exist in the same scope")
        if self._would_create_cycle(
            scope=scope,
            task_id=task_id,
            depends_on_task_id=depends_on_task_id,
        ):
            raise ValueError("dependency would create a cycle")
        dependency_id = add_task_dependency(scope, task_id, depends_on_task_id)
        log_planner_change(
            scope,
            "dependency_added",
            task_id=task_id,
            details={"depends_on_task_id": depends_on_task_id},
        )
        return dependency_id

    def goals(self, *, scope: str, status: str | None = None, limit: int = 100) -> list[dict]:
        return list_goals(scope, status=status, limit=limit)

    def tasks(self, *, scope: str, status: str | None = None, limit: int = 200) -> list[dict]:
        return list_tasks(scope, status=status, limit=limit)

    def set_goal_status(self, goal_id: int, status: str, *, scope: str) -> None:
        update_goal_status(goal_id, status, scope)
        log_planner_change(scope, "goal_status_changed", goal_id=goal_id, details={"status": status})

    def set_task_status(
        self,
        task_id: int,
        status: str,
        *,
        scope: str,
        blocked_reason: str = "",
    ) -> None:
        update_task_status(task_id, status, scope, blocked_reason)
        log_planner_change(
            scope,
            "task_status_changed",
            task_id=task_id,
            details={"status": status, "blocked_reason": blocked_reason},
        )

    def dependencies(self, task_id: int, *, scope: str) -> list[dict]:
        return task_dependencies(task_id, scope)

    def _would_create_cycle(
        self,
        *,
        scope: str,
        task_id: int,
        depends_on_task_id: int,
    ) -> bool:
        target = int(task_id)
        stack = [int(depends_on_task_id)]
        visited: set[int] = set()

        while stack:
            current = stack.pop()
            if current == target:
                return True
            if current in visited:
                continue
            visited.add(current)
            for dep in task_dependencies(current, scope):
                stack.append(int(dep["depends_on_task_id"]))
        return False

    def open_items(self, *, scope: str) -> dict:
        return planner_open_items(scope)

    def changes(self, *, scope: str, limit: int = 30) -> list[dict]:
        return recent_planner_changes(scope, limit=limit)

    def inspect(self, *, scope: str) -> list[PlannerNotice]:
        notices: list[PlannerNotice] = []
        now = utc_now()
        items = self.open_items(scope=scope)

        for task in items["tasks"]:
            if task["status"] == "blocked":
                notices.append(
                    PlannerNotice(
                        severity="warning",
                        code="task_blocked",
                        message=f"Задача «{task['title']}» заблокирована: {task.get('blocked_reason') or 'причина не указана'}.",
                        task_id=int(task["id"]),
                        goal_id=task.get("goal_id"),
                    )
                )

            due_at = task.get("due_at")
            if due_at:
                try:
                    due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                    if due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    if due < now and task["status"] not in {"completed", "cancelled"}:
                        notices.append(
                            PlannerNotice(
                                severity="warning",
                                code="task_overdue",
                                message=f"Срок задачи «{task['title']}» уже прошёл.",
                                task_id=int(task["id"]),
                                goal_id=task.get("goal_id"),
                            )
                        )
                except ValueError:
                    notices.append(
                        PlannerNotice(
                            severity="info",
                            code="invalid_due_at",
                            message=f"У задачи «{task['title']}» некорректный срок.",
                            task_id=int(task["id"]),
                            goal_id=task.get("goal_id"),
                        )
                    )

            dependencies = self.dependencies(int(task["id"]), scope=scope)
            unfinished = [
                dep for dep in dependencies
                if dep["depends_on_status"] not in {"completed", "cancelled"}
            ]
            if unfinished and task["status"] in {"open", "in_progress"}:
                names = ", ".join(dep["depends_on_title"] for dep in unfinished[:3])
                notices.append(
                    PlannerNotice(
                        severity="info",
                        code="waiting_dependencies",
                        message=f"Задача «{task['title']}» ждёт завершения: {names}.",
                        task_id=int(task["id"]),
                        goal_id=task.get("goal_id"),
                    )
                )

        active_goals = items["goals"]
        task_goal_ids = {task.get("goal_id") for task in items["tasks"] if task.get("goal_id") is not None}
        for goal in active_goals:
            if int(goal["id"]) not in task_goal_ids:
                notices.append(
                    PlannerNotice(
                        severity="info",
                        code="goal_without_tasks",
                        message=f"У цели «{goal['title']}» пока нет открытых задач.",
                        goal_id=int(goal["id"]),
                    )
                )

        return notices


    def prompt_block(self, *, scope: str) -> str:
        items = self.open_items(scope=scope)
        notices = self.inspect(scope=scope)

        lines = [
            "Внутренний планировщик Айшин.",
            "Не утверждай, что задача выполнена, пока её статус явно не completed.",
            "Не выполняй внешние действия без соответствующего разрешения.",
        ]

        if items["goals"]:
            lines.append("Активные цели:")
            for goal in items["goals"][:8]:
                lines.append(
                    f"- #{goal['id']} {goal['title']} "
                    f"(priority={float(goal['priority']):.2f}, status={goal['status']})"
                )

        if items["tasks"]:
            lines.append("Открытые задачи:")
            for task in items["tasks"][:12]:
                due = f", due={task['due_at']}" if task.get("due_at") else ""
                lines.append(
                    f"- #{task['id']} {task['title']} "
                    f"(priority={float(task['priority']):.2f}, status={task['status']}{due})"
                )

        if notices:
            lines.append("Требует внимания:")
            for notice in notices[:8]:
                lines.append(f"- [{notice.severity}] {notice.message}")

        return "\n".join(lines)
