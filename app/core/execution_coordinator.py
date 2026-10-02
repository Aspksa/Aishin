from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone

from ..db import connect, get_proactive_decision
from .permissions import PermissionGate
from .tools import ToolRegistry


class ExecutionCoordinator:
    """One-shot approvals with stale-state revalidation before tool execution."""

    APPROVAL_TTL_MINUTES = 15

    def __init__(
        self,
        *,
        tools: ToolRegistry,
        permissions: PermissionGate,
    ) -> None:
        self.tools = tools
        self.permissions = permissions

    def issue_approval(
        self,
        decision_id: int,
        *,
        scope: str,
    ) -> dict:
        decision = get_proactive_decision(decision_id, scope)
        if not decision:
            raise ValueError("decision not found in scope")
        if decision["status"] not in {"pending", "approved"}:
            raise ValueError("decision cannot be approved in current status")

        tool_name = str(decision.get("tool_name") or "").strip()
        if not tool_name:
            raise ValueError("informational decision has no executable tool")

        spec = self.tools.SPECS.get(tool_name)
        if spec is None:
            raise ValueError("decision references unknown tool")

        capability = str(decision.get("capability") or spec.capability)
        if capability != spec.capability:
            raise ValueError("decision capability no longer matches tool")

        permission_mode = self.permissions.mode(capability)
        if permission_mode == "deny":
            raise ValueError("tool capability is denied")

        global_mode = self.permissions.mode("execute_planned_action")
        if global_mode == "deny":
            raise ValueError("planned action execution is denied")

        arguments = decision.get("arguments") or {}
        preview = self.tools.invoke(
            tool_name,
            scope=scope,
            arguments=arguments,
            dry_run=True,
            approved=False,
        )
        if preview.get("status") not in {"preview", "success"}:
            raise ValueError("tool preview failed; approval not issued")

        arguments_hash = self._hash_json(arguments)
        preview_hash = self._hash_json(self._stable_preview(preview))
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.APPROVAL_TTL_MINUTES
        )

        with connect() as conn:
            conn.execute(
                """UPDATE execution_approvals
                   SET status='invalidated',
                       invalidated_reason='superseded_by_new_approval'
                   WHERE scope=? AND decision_id=? AND status='active'""",
                (scope, decision_id),
            )
            cur = conn.execute(
                """INSERT INTO execution_approvals(
                       scope, decision_id, tool_name, capability,
                       arguments_hash, preview_hash, permission_mode,
                       status, expires_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)""",
                (
                    scope,
                    decision_id,
                    tool_name,
                    capability,
                    arguments_hash,
                    preview_hash,
                    permission_mode,
                    expires_at.isoformat(),
                ),
            )
            conn.commit()
            approval_id = int(cur.lastrowid)

        return {
            "approval_id": approval_id,
            "decision_id": decision_id,
            "scope": scope,
            "tool": tool_name,
            "capability": capability,
            "permission_mode": permission_mode,
            "status": "active",
            "expires_at": expires_at.isoformat(),
            "one_shot": True,
            "arguments_hash": arguments_hash,
            "preview_hash": preview_hash,
        }

    def execute(
        self,
        decision_id: int,
        *,
        scope: str,
    ) -> dict:
        decision = get_proactive_decision(decision_id, scope)
        if not decision:
            raise ValueError("decision not found in scope")
        if decision["status"] != "approved":
            raise ValueError("decision must be approved before execution")

        approval = self._active_approval(
            decision_id=decision_id,
            scope=scope,
        )
        if approval is None:
            raise ValueError("no active one-shot approval")

        revalidation = self._revalidate(
            decision=decision,
            approval=approval,
            scope=scope,
        )
        if not revalidation["valid"]:
            self._invalidate(
                int(approval["id"]),
                reason=revalidation["reason"],
            )
            attempt_id = self._record_attempt(
                scope=scope,
                decision_id=decision_id,
                approval_id=int(approval["id"]),
                tool_name=str(decision.get("tool_name") or ""),
                status="stale_or_blocked",
                revalidation=revalidation,
                tool_result={},
                rollback={},
            )
            return {
                "status": "stale_or_blocked",
                "attempt_id": attempt_id,
                "approval_id": int(approval["id"]),
                "revalidation": revalidation,
                "tool_result": {},
                "rollback": {},
            }

        tool_name = str(decision.get("tool_name") or "")
        tool_result = self.tools.invoke(
            tool_name,
            scope=scope,
            arguments=decision.get("arguments") or {},
            dry_run=False,
            approved=True,
        )

        rollback = self._rollback_metadata(tool_result)
        success = tool_result.get("status") == "success"

        self._consume(
            int(approval["id"]),
            reason="executed" if success else "tool_failed",
        )
        attempt_id = self._record_attempt(
            scope=scope,
            decision_id=decision_id,
            approval_id=int(approval["id"]),
            tool_name=tool_name,
            status="success" if success else "failed",
            revalidation=revalidation,
            tool_result=tool_result,
            rollback=rollback,
        )

        return {
            "status": "success" if success else "failed",
            "attempt_id": attempt_id,
            "approval_id": int(approval["id"]),
            "revalidation": revalidation,
            "tool_result": tool_result,
            "rollback": rollback,
        }

    def recent_approvals(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM execution_approvals
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_attempts(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM execution_attempts
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["revalidation"] = json.loads(
                item.pop("revalidation_json") or "{}"
            )
            item["tool_result"] = json.loads(
                item.pop("tool_result_json") or "{}"
            )
            item["rollback"] = json.loads(
                item.pop("rollback_json") or "{}"
            )
            result.append(item)
        return result

    def _revalidate(
        self,
        *,
        decision: dict,
        approval: dict,
        scope: str,
    ) -> dict:
        now = datetime.now(timezone.utc)
        try:
            expires_at = datetime.fromisoformat(
                str(approval["expires_at"])
            )
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except Exception:
            return {
                "valid": False,
                "reason": "invalid_approval_expiry",
            }

        if now >= expires_at:
            return {
                "valid": False,
                "reason": "approval_expired",
            }

        tool_name = str(decision.get("tool_name") or "")
        if tool_name != approval["tool_name"]:
            return {
                "valid": False,
                "reason": "tool_changed_after_approval",
            }

        spec = self.tools.SPECS.get(tool_name)
        if spec is None:
            return {
                "valid": False,
                "reason": "tool_no_longer_available",
            }

        capability = str(decision.get("capability") or spec.capability)
        if capability != approval["capability"]:
            return {
                "valid": False,
                "reason": "capability_changed_after_approval",
            }

        permission_mode = self.permissions.mode(capability)
        global_mode = self.permissions.mode("execute_planned_action")
        if permission_mode == "deny":
            return {
                "valid": False,
                "reason": "capability_now_denied",
                "permission_mode": permission_mode,
                "global_mode": global_mode,
            }
        if global_mode == "deny":
            return {
                "valid": False,
                "reason": "planned_execution_now_denied",
                "permission_mode": permission_mode,
                "global_mode": global_mode,
            }

        arguments = decision.get("arguments") or {}
        current_arguments_hash = self._hash_json(arguments)
        if current_arguments_hash != approval["arguments_hash"]:
            return {
                "valid": False,
                "reason": "arguments_changed_after_approval",
            }

        preview = self.tools.invoke(
            tool_name,
            scope=scope,
            arguments=arguments,
            dry_run=True,
            approved=False,
        )
        if preview.get("status") not in {"preview", "success"}:
            return {
                "valid": False,
                "reason": "pre_execution_preview_failed",
                "preview_status": preview.get("status"),
            }

        current_preview_hash = self._hash_json(
            self._stable_preview(preview)
        )
        if current_preview_hash != approval["preview_hash"]:
            return {
                "valid": False,
                "reason": "underlying_state_changed_after_approval",
                "preview_hash_before": approval["preview_hash"],
                "preview_hash_now": current_preview_hash,
            }

        return {
            "valid": True,
            "reason": "revalidated",
            "permission_mode": permission_mode,
            "global_mode": global_mode,
            "arguments_hash": current_arguments_hash,
            "preview_hash": current_preview_hash,
        }

    def _active_approval(
        self,
        *,
        decision_id: int,
        scope: str,
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM execution_approvals
                   WHERE scope=? AND decision_id=? AND status='active'
                   ORDER BY id DESC LIMIT 1""",
                (scope, decision_id),
            ).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _stable_preview(preview: dict) -> dict:
        return {
            "tool": preview.get("tool"),
            "capability": preview.get("capability"),
            "permission": preview.get("permission"),
            "status": preview.get("status"),
            "dry_run": preview.get("dry_run"),
            "output": preview.get("output") or {},
        }

    @staticmethod
    def _hash_json(value: object) -> str:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _rollback_metadata(tool_result: dict) -> dict:
        output = tool_result.get("output") or {}
        rollback = output.get("rollback")
        if isinstance(rollback, dict):
            return rollback
        return {
            "available": False,
            "reason": "tool_did_not_provide_rollback_metadata",
        }

    @staticmethod
    def _invalidate(approval_id: int, *, reason: str) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE execution_approvals
                   SET status='invalidated', invalidated_reason=?
                   WHERE id=? AND status='active'""",
                (reason, approval_id),
            )
            conn.commit()

    @staticmethod
    def _consume(approval_id: int, *, reason: str) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE execution_approvals
                   SET status='consumed',
                       consumed_at=CURRENT_TIMESTAMP,
                       invalidated_reason=?
                   WHERE id=? AND status='active'""",
                (reason, approval_id),
            )
            conn.commit()

    @staticmethod
    def _record_attempt(
        *,
        scope: str,
        decision_id: int,
        approval_id: int,
        tool_name: str,
        status: str,
        revalidation: dict,
        tool_result: dict,
        rollback: dict,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO execution_attempts(
                       scope, decision_id, approval_id, tool_name,
                       status, revalidation_json, tool_result_json,
                       rollback_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    decision_id,
                    approval_id,
                    tool_name,
                    status,
                    json.dumps(revalidation, ensure_ascii=False),
                    json.dumps(tool_result, ensure_ascii=False),
                    json.dumps(rollback, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
