from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile

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

    MISSING_SHA256 = "__missing__"

    FORBIDDEN_NAMES = {
        ".env",
        ".git",
        ".venv",
        "aishin.db",
        ".aishin_backups",
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
            "Атомарно записать текстовый файл внутри проекта.",
            "modify_files",
        ),
        "project.rollback_write": ToolSpec(
            "project.rollback_write",
            "Откатить ранее выполненную запись файла по проверенным rollback metadata.",
            "modify_files",
            destructive=True,
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
        self.backup_root = (self.root / ".aishin_backups").resolve()

    def catalog(self) -> list[dict]:
        return [asdict(spec) for spec in self.SPECS.values()]

    def invoke(
        self,
        name: str,
        *,
        scope: str,
        arguments: dict,
        dry_run: bool = True,
        approved: bool = False,
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

        requires_approval = mode == "ask" or spec.destructive
        if requires_approval and not dry_run and not approved:
            return self._audit(
                name,
                scope,
                spec.capability,
                mode,
                "approval_required",
                dry_run,
                {**arguments, "_approved": False},
                {"error": "Требуется новое явное разрешение Господина"},
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
            {**arguments, "_approved": approved},
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
                "sha256": self._sha256_file(path),
            }

        if name == "project.write_text":
            return self._write_text(arguments, dry_run=dry_run)

        if name == "project.rollback_write":
            return self._rollback_write(arguments, dry_run=dry_run)

        raise ValueError("Инструмент не реализован")

    def _write_text(self, arguments: dict, *, dry_run: bool) -> dict:
        path = self._safe_path(str(arguments.get("path") or ""))
        content = str(arguments.get("content") or "")
        encoded = content.encode("utf-8")
        if len(encoded) > 1_000_000:
            raise ValueError("Содержимое слишком большое")

        existed = path.is_file()
        before = path.read_bytes() if existed else b""
        before_sha256 = self._sha256_bytes(before) if existed else None
        before_bytes = len(before)

        expected_sha256 = arguments.get(
            "_expected_sha256",
            arguments.get("expected_sha256"),
        )
        self._validate_expected_state(
            existed=existed,
            current_sha256=before_sha256,
            expected_sha256=expected_sha256,
        )

        if dry_run:
            return {
                "would_write": str(path.relative_to(self.root)),
                "bytes": len(encoded),
                "existing_file": existed,
                "existing_bytes": before_bytes,
                "existing_sha256": before_sha256,
                "expected_sha256": expected_sha256,
                "precondition_match": True,
                "atomic_replace": True,
            }

        rollback: dict
        if existed:
            stamp = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%S%fZ"
            )
            backup = (
                self.backup_root
                / stamp
                / path.relative_to(self.root)
            )
            self._atomic_write_bytes(backup, before)
            backup_sha256 = self._sha256_file(backup)
            if backup_sha256 != before_sha256:
                raise IOError("Проверка целостности backup не пройдена")
            rollback = {
                "available": True,
                "kind": "restore_backup",
                "target": str(path.relative_to(self.root)),
                "backup_path": str(backup.relative_to(self.root)),
                "before_sha256": before_sha256,
                "backup_sha256": backup_sha256,
            }
        else:
            rollback = {
                "available": True,
                "kind": "remove_created_file",
                "target": str(path.relative_to(self.root)),
                "before_sha256": self.MISSING_SHA256,
                "requires_fresh_approval": True,
            }

        self._atomic_write_bytes(path, encoded)
        after_sha256 = self._sha256_file(path)
        expected_after = self._sha256_bytes(encoded)
        if after_sha256 != expected_after:
            raise IOError("Проверка SHA-256 после atomic write не пройдена")

        rollback["after_sha256"] = after_sha256
        return {
            "path": str(path.relative_to(self.root)),
            "bytes": len(encoded),
            "sha256": after_sha256,
            "atomic": True,
            "rollback": rollback,
        }

    def _rollback_write(self, arguments: dict, *, dry_run: bool) -> dict:
        kind = str(arguments.get("kind") or "").strip()
        target = self._safe_path(str(arguments.get("target") or ""))
        after_sha256 = str(arguments.get("after_sha256") or "").strip()

        if not after_sha256:
            raise ValueError("Rollback metadata не содержит after_sha256")

        current_exists = target.is_file()
        current_sha256 = (
            self._sha256_file(target)
            if current_exists
            else self.MISSING_SHA256
        )
        if current_sha256 != after_sha256:
            raise ValueError(
                "Целевой файл изменился после исходной операции; "
                "автоматический rollback запрещён"
            )

        if kind == "restore_backup":
            backup = self._safe_backup_path(
                str(arguments.get("backup_path") or "")
            )
            if not backup.is_file():
                raise FileNotFoundError("Backup для rollback не найден")

            expected_backup_sha = str(
                arguments.get("backup_sha256")
                or arguments.get("before_sha256")
                or ""
            ).strip()
            if not expected_backup_sha:
                raise ValueError("Rollback metadata не содержит backup SHA-256")

            actual_backup_sha = self._sha256_file(backup)
            if actual_backup_sha != expected_backup_sha:
                raise ValueError("Целостность rollback backup нарушена")

            if dry_run:
                return {
                    "would_restore": str(target.relative_to(self.root)),
                    "backup_path": str(backup.relative_to(self.root)),
                    "current_sha256": current_sha256,
                    "restore_sha256": actual_backup_sha,
                    "integrity_ok": True,
                    "atomic_replace": True,
                }

            data = backup.read_bytes()
            self._atomic_write_bytes(target, data)
            restored_sha = self._sha256_file(target)
            if restored_sha != actual_backup_sha:
                raise IOError("Проверка восстановленного файла не пройдена")

            return {
                "rollback": "restored_backup",
                "path": str(target.relative_to(self.root)),
                "sha256": restored_sha,
                "backup_sha256": actual_backup_sha,
                "atomic": True,
            }

        if kind == "remove_created_file":
            before_sha256 = str(
                arguments.get("before_sha256") or ""
            ).strip()
            if before_sha256 not in {"", self.MISSING_SHA256}:
                raise ValueError(
                    "Некорректные rollback metadata для созданного файла"
                )

            if dry_run:
                return {
                    "would_remove": str(target.relative_to(self.root)),
                    "current_sha256": current_sha256,
                    "precondition_match": True,
                }

            target.unlink()
            self._fsync_directory(target.parent)
            return {
                "rollback": "removed_created_file",
                "path": str(target.relative_to(self.root)),
                "previous_sha256": current_sha256,
                "exists_after": target.exists(),
            }

        raise ValueError("Неизвестный вид rollback")

    def _validate_expected_state(
        self,
        *,
        existed: bool,
        current_sha256: str | None,
        expected_sha256,
    ) -> None:
        if expected_sha256 is None:
            return

        expected = str(expected_sha256).strip()
        if expected == self.MISSING_SHA256:
            if existed:
                raise ValueError(
                    "Файл появился после проверки; atomic write отменён"
                )
            return

        if not existed:
            raise ValueError(
                "Файл исчез после проверки; atomic write отменён"
            )
        if current_sha256 != expected:
            raise ValueError(
                "SHA-256 файла изменился после проверки; atomic write отменён"
            )

    def _atomic_write_bytes(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".aishin-tmp",
            dir=str(path.parent),
        )
        temp_path = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(path.parent)
        except Exception:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        if os.name == "nt":
            return
        flags = getattr(os, "O_RDONLY", 0)
        directory_flag = getattr(os, "O_DIRECTORY", 0)
        fd = None
        try:
            fd = os.open(str(path), flags | directory_flag)
            os.fsync(fd)
        except OSError:
            return
        finally:
            if fd is not None:
                os.close(fd)

    def _safe_path(self, raw: str) -> Path:
        if not raw.strip():
            raise ValueError("Путь пустой")
        candidate = (self.root / raw).resolve()
        try:
            relative = candidate.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Выход за пределы проекта запрещён") from exc

        lowered_parts = [part.casefold() for part in relative.parts]
        if any(
            part.casefold() in self.FORBIDDEN_NAMES
            for part in relative.parts
        ):
            raise ValueError("Доступ к защищённому пути запрещён")
        if any(part.startswith(".env") for part in lowered_parts):
            raise ValueError("Доступ к env-файлам запрещён")
        if candidate.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}:
            raise ValueError("Доступ к файлам ключей запрещён")
        return candidate

    def _safe_backup_path(self, raw: str) -> Path:
        if not raw.strip():
            raise ValueError("Путь backup пустой")
        candidate = (self.root / raw).resolve()
        try:
            candidate.relative_to(self.backup_root)
        except ValueError as exc:
            raise ValueError(
                "Rollback backup должен находиться в .aishin_backups"
            ) from exc
        return candidate

    @staticmethod
    def _sha256_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def _sha256_file(cls, path: Path) -> str:
        return cls._sha256_bytes(path.read_bytes())

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
        safe_input = self._sanitize_audit_payload(input_data)
        safe_output = self._sanitize_audit_payload(output_data)
        action_id = add_tool_action(
            name,
            scope,
            capability,
            permission_mode,
            status,
            dry_run,
            safe_input,
            safe_output,
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

    @staticmethod
    def _sanitize_audit_payload(payload: dict) -> dict:
        result: dict = {}
        for key, value in payload.items():
            lowered = str(key).casefold()
            if lowered in {"content", "text", "body"}:
                if isinstance(value, str):
                    result[f"{key}_bytes"] = len(value.encode("utf-8"))
                else:
                    result[f"{key}_redacted"] = True
                continue
            if any(
                token in lowered
                for token in (
                    "password",
                    "secret",
                    "token",
                    "api_key",
                    "authorization",
                )
            ):
                result[key] = "[REDACTED]"
                continue
            result[key] = value
        return result

    def history(self, *, scope: str, limit: int = 50) -> list[dict]:
        return recent_tool_actions(scope, limit=limit)
