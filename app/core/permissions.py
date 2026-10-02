from __future__ import annotations

from ..db import get_permission, set_permission


class PermissionGate:
    """Central guardrail for future autonomous actions.

    Modes:
    - allow: may execute locally without an extra prompt
    - ask: requires user approval
    - deny: execution is blocked
    """

    SAFE_DEFAULTS = {
        "read_local_context": "allow",
        "write_memory": "allow",
        "write_runtime_state": "allow",
        "external_network": "ask",
        "send_message": "ask",
        "modify_files": "ask",
        "delete_data": "deny",
        "install_software": "ask",
        "system_command": "ask",
    }

    def bootstrap(self) -> None:
        for capability, mode in self.SAFE_DEFAULTS.items():
            if get_permission(capability) == "ask" and mode != "ask":
                set_permission(capability, mode)

    def mode(self, capability: str) -> str:
        return get_permission(capability)

    def set(self, capability: str, mode: str) -> None:
        set_permission(capability, mode)

    def allowed(self, capability: str) -> bool:
        return self.mode(capability) == "allow"
