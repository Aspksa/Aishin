from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.engine import AishinEngine
from app.db import init_db
from app.personality import personality


def main() -> int:
    checks: dict[str, object] = {}
    try:
        init_db()
        checks["database"] = "ok"

        checks["personality"] = {
            "status": "ok",
            "name": personality.name,
            "rules": len(personality.profile.get("internal_rules", [])),
        }

        engine = AishinEngine()
        engine.startup()
        snapshot = engine.snapshot()
        checks["runtime"] = {
            "status": "ok",
            "state": snapshot["state"]["status"],
            "scope": snapshot["state"]["current_scope"],
        }
        personal = engine.personal.context(scope=snapshot["state"]["current_scope"])
        checks["personal_core"] = {
            "status": "ok",
            "master_profile_fields": len(personal.master_profile),
            "relationship_memories": len(personal.relationship_memory),
            "timeline_events": len(personal.timeline),
        }
        checks["ai"] = snapshot["ai"]
        checks["permissions"] = snapshot["permissions"]

        print(json.dumps({"status": "ok", "checks": checks}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc), "checks": checks}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
