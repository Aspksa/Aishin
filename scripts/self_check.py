from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_output()

from app.core.engine import AishinEngine
from app.db import connect, database_schema_status, init_db
from app.personality import personality


def main() -> int:
    checks: dict[str, object] = {}
    try:
        init_db()
        schema = database_schema_status()
        if not schema["up_to_date"]:
            raise RuntimeError(
                f"Схема БД устарела: {schema['current_version']} "
                f"из {schema['latest_version']}"
            )

        with connect() as conn:
            foreign_keys = int(
                conn.execute("PRAGMA foreign_keys").fetchone()[0]
            )
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]

        if foreign_keys != 1:
            raise RuntimeError("SQLite foreign_keys отключён")
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check: {integrity}")

        checks["database"] = {
            "status": "ok",
            "schema": schema,
            "foreign_keys": True,
            "integrity": integrity,
        }

        if personality.source != "canonical":
            raise RuntimeError(
                "Айшин запущена не из канонического профиля личности"
            )

        checks["personality"] = {
            "status": "ok",
            "name": personality.name,
            "source": personality.source,
            "path": str(personality.path),
            "schema_version": personality.profile["schema"].get("version"),
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
        checks["memory_consolidation"] = {
            "status": "ok",
            "consolidator": engine.consolidator.__class__.__name__,
            "audit_entries": len(engine.memory.recent_changes(limit=10)),
        }
        checks["semantic_memory"] = {
            "status": "ok",
            "health": engine.semantic.health(),
        }
        checks["knowledge_graph"] = {
            "status": "ok",
            "personal": engine.graph.stats(scope="personal"),
            "relationship": engine.graph.stats(scope="relationship"),
        }
        checks["planner"] = {
            "status": "ok",
            "open_items": engine.planner.open_items(scope="personal"),
            "notices": [
                notice.__dict__
                for notice in engine.planner.inspect(scope="personal")
            ],
        }
        checks["sensors_tools"] = {
            "status": "ok",
            "sensors": engine.sensors.scan(scope="personal", persist=False),
            "tools": engine.tools.catalog(),
        }
        checks["proactive_loop"] = {
            "status": "ok",
            "engine": engine.proactive.__class__.__name__,
            "pending": engine.proactive.pending(scope="personal", limit=20),
        }
        checks["metacognition"] = {
            "status": "ok",
            "engine": engine.metacognition.__class__.__name__,
            "history_entries": len(
                engine.metacognition.recent(scope="personal", limit=10)
            ),
        }
        checks["verification_engine"] = {
            "status": "ok",
            "engine": engine.verification.__class__.__name__,
            "history_entries": len(
                engine.verification.recent(scope="personal", limit=10)
            ),
        }
        checks["logic_engine"] = {
            "status": "ok",
            "engine": engine.logic.__class__.__name__,
            "history_entries": len(
                engine.logic.recent(scope="personal", limit=10)
            ),
            "modes": ["FAST", "DEEP", "VERIFY", "PLAN", "DIAGNOSE"],
        }
        fast_budget = engine.context_orchestrator.budget_for("FAST")
        verify_budget = engine.context_orchestrator.budget_for("VERIFY")
        if fast_budget.memories >= verify_budget.memories:
            raise RuntimeError("Context budget FAST должен быть меньше VERIFY")
        checks["context_orchestrator"] = {
            "status": "ok",
            "engine": engine.context_orchestrator.__class__.__name__,
            "fast": fast_budget.__dict__,
            "verify": verify_budget.__dict__,
            "history_entries": len(
                engine.context_orchestrator.recent(scope="personal", limit=10)
            ),
        }
        checks["causal_reasoning"] = {
            "status": "ok",
            "engine": engine.causal.__class__.__name__,
            "history_entries": len(
                engine.causal.recent(scope="personal", limit=10)
            ),
        }
        checks["hypothesis_manager"] = {
            "status": "ok",
            "engine": engine.hypotheses.__class__.__name__,
            "history_entries": len(
                engine.hypotheses.recent(scope="personal", limit=10)
            ),
            "active_modes": ["VERIFY", "DIAGNOSE"],
        }
        checks["logic_learning"] = {
            "status": "ok",
            "engine": engine.logic_learning.__class__.__name__,
            "events": len(
                engine.logic_learning.recent_events(scope="personal", limit=10)
            ),
            "feedback_policy": "explicit_success_or_failure_only",
        }
        checks["counterfactual_reasoning"] = {
            "status": "ok",
            "engine": engine.counterfactual.__class__.__name__,
            "history_entries": len(
                engine.counterfactual.recent(scope="personal", limit=10)
            ),
            "active_modes": ["DEEP", "PLAN", "VERIFY", "DIAGNOSE"],
        }
        checks["decision_quality"] = {
            "status": "ok",
            "engine": engine.decision_quality.__class__.__name__,
            "history_entries": len(
                engine.decision_quality.recent(scope="personal", limit=10)
            ),
            "meaning": "quality_of_evidence_not_truth",
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
