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

from fastapi.testclient import TestClient

from app.main import app


def main() -> int:
    checks: dict[str, object] = {}

    try:
        with TestClient(app) as client:
            home = client.get("/")
            if home.status_code != 200:
                raise RuntimeError(
                    f"/ returned HTTP {home.status_code}: {home.text[:300]}"
                )
            required_ui = (
                'id="chat-form"',
                'id="messages"',
                'id="simple-mode"',
                'id="simple-learning"',
                'class="technical-brain"',
                'id="brain-flow"',
                'id="pending-decisions"',
            )
            missing_ui = [
                marker for marker in required_ui
                if marker not in home.text
            ]
            if missing_ui:
                raise RuntimeError(
                    f"Новая UI-компоновка неполная: {missing_ui}"
                )
            checks["ui_layout"] = {
                "status": "ok",
                "chat_first": True,
                "technical_brain_collapsed": True,
            }

            health = client.get("/health")
            if health.status_code != 200:
                raise RuntimeError(
                    f"/health returned HTTP {health.status_code}: {health.text[:300]}"
                )
            health_data = health.json()
            checks["health"] = health_data

            state = client.get("/api/assistant/state")
            if state.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/state returned HTTP {state.status_code}: "
                    f"{state.text[:300]}"
                )
            state_data = state.json()
            checks["state"] = {
                "identity": state_data.get("identity", {}).get("name"),
                "runtime_status": state_data.get("state", {}).get("status"),
                "profile_source": state_data.get("identity", {}).get(
                    "profile_source"
                ),
                "schema_present": bool(state_data.get("state")),
            }

            tools = client.get("/api/assistant/tools")
            if tools.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/tools returned HTTP {tools.status_code}"
                )
            tools_catalog = client.get("/api/assistant/tools")
            if tools_catalog.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/tools returned HTTP {tools_catalog.status_code}"
                )
            tool_names = {
                item.get("name")
                for item in tools_catalog.json()
            }
            if "project.rollback_write" not in tool_names:
                raise RuntimeError("Rollback tool отсутствует в Tool Registry")

            rollback_missing = client.post(
                "/api/assistant/execution/attempts/999999999/rollback",
                json={"scope": "personal", "approved": False},
            )
            if rollback_missing.status_code not in {400, 403}:
                raise RuntimeError(
                    "Rollback API должен отклонять неизвестный или нелокальный вызов"
                )
            checks["atomic_write_rollback"] = {
                "status": "ok",
                "rollback_tool_present": True,
                "rollback_api_present": True,
            }

            checks["tools"] = {
                "status": "ok",
                "count": len(tools.json()),
            }

            proactive_conditions = client.get(
                "/api/assistant/proactive/conditions",
                params={"scope": "personal", "limit": 1},
            )
            if proactive_conditions.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/proactive/conditions returned HTTP "
                    f"{proactive_conditions.status_code}"
                )
            checks["proactive_conditions"] = {
                "status": "ok",
                "history_entries": len(proactive_conditions.json()),
            }

            graph_search = client.get(
                "/api/assistant/graph/search",
                params={
                    "scope": "relationship",
                    "query": "Айшин",
                    "limit": 5,
                },
            )
            if graph_search.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/graph/search returned HTTP "
                    f"{graph_search.status_code}"
                )
            graph_items = graph_search.json()
            if not graph_items:
                raise RuntimeError("Knowledge Graph seed Айшин не найден")
            if (
                "canonical_name" not in graph_items[0]
                or not isinstance(graph_items[0].get("data"), dict)
            ):
                raise RuntimeError(
                    "Knowledge Graph search shape несовместим с Verification"
                )
            checks["knowledge_graph_shape"] = {
                "status": "ok",
                "matches": len(graph_items),
            }

            learning_status = client.get(
                "/api/assistant/continuous-learning/status",
                params={"scope": "personal"},
            )
            if learning_status.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/continuous-learning/status returned HTTP "
                    f"{learning_status.status_code}"
                )
            learning_data = learning_status.json()
            if learning_data.get("mode") not in {
                "REALTIME", "BACKGROUND", "IDLE", "MAINTENANCE"
            }:
                raise RuntimeError("Continuous Learning вернул неизвестный mode")

            learning_cycles = client.get(
                "/api/assistant/continuous-learning/cycles",
                params={"scope": "personal", "limit": 2},
            )
            if learning_cycles.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/continuous-learning/cycles returned HTTP "
                    f"{learning_cycles.status_code}"
                )

            learning_patterns = client.get(
                "/api/assistant/continuous-learning/patterns",
                params={"scope": "personal", "limit": 2},
            )
            if learning_patterns.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/continuous-learning/patterns returned HTTP "
                    f"{learning_patterns.status_code}"
                )

            checks["continuous_learning"] = {
                "status": "ok",
                "mode": learning_data.get("mode"),
                "worker_status": learning_data.get("worker_status"),
                "cycles": len(learning_cycles.json()),
                "patterns": len(learning_patterns.json()),
            }

            learning_quality = client.get(
                "/api/assistant/continuous-learning/quality",
                params={"scope": "personal"},
            )
            if learning_quality.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/continuous-learning/quality returned HTTP "
                    f"{learning_quality.status_code}"
                )

            strategy_evolution = client.get(
                "/api/assistant/continuous-learning/strategies",
                params={"scope": "personal", "limit": 3},
            )
            if strategy_evolution.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/continuous-learning/strategies returned HTTP "
                    f"{strategy_evolution.status_code}"
                )

            checks["learning_quality"] = {
                "status": "ok",
                "quality": learning_quality.json(),
                "strategies": len(strategy_evolution.json()),
            }

            performance = client.get(
                "/api/assistant/performance",
                params={"scope": "personal", "limit": 1},
            )
            if performance.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/performance returned HTTP "
                    f"{performance.status_code}"
                )
            checks["performance"] = {
                "status": "ok",
                "history_entries": len(performance.json()),
            }

            cognitive_traces = client.get(
                "/api/assistant/cognitive-traces",
                params={"scope": "personal", "limit": 1},
            )
            if cognitive_traces.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/cognitive-traces returned HTTP "
                    f"{cognitive_traces.status_code}"
                )
            checks["cognitive_traces"] = {
                "status": "ok",
                "history_entries": len(cognitive_traces.json()),
            }

            ai_diagnostics = client.get("/api/assistant/ai-diagnostics")
            if ai_diagnostics.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/ai-diagnostics returned HTTP "
                    f"{ai_diagnostics.status_code}"
                )
            checks["ai_resilience"] = ai_diagnostics.json()

            execution_approvals = client.get(
                "/api/assistant/execution/approvals",
                params={"scope": "personal", "limit": 1},
            )
            if execution_approvals.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/execution/approvals returned HTTP "
                    f"{execution_approvals.status_code}"
                )
            checks["execution_approvals"] = {
                "status": "ok",
                "history_entries": len(execution_approvals.json()),
            }

            execution_attempts = client.get(
                "/api/assistant/execution/attempts",
                params={"scope": "personal", "limit": 1},
            )
            if execution_attempts.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/execution/attempts returned HTTP "
                    f"{execution_attempts.status_code}"
                )
            checks["execution_attempts"] = {
                "status": "ok",
                "history_entries": len(execution_attempts.json()),
            }

            action_selection = client.get(
                "/api/assistant/action-selection",
                params={"scope": "personal", "limit": 1},
            )
            if action_selection.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/action-selection returned HTTP "
                    f"{action_selection.status_code}"
                )
            checks["action_selection"] = {
                "status": "ok",
                "history_entries": len(action_selection.json()),
            }

            counterfactual = client.get(
                "/api/assistant/counterfactual",
                params={"scope": "personal", "limit": 1},
            )
            if counterfactual.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/counterfactual returned HTTP "
                    f"{counterfactual.status_code}"
                )
            checks["counterfactual"] = {
                "status": "ok",
                "history_entries": len(counterfactual.json()),
            }

            decision_quality = client.get(
                "/api/assistant/decision-quality",
                params={"scope": "personal", "limit": 1},
            )
            if decision_quality.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/decision-quality returned HTTP "
                    f"{decision_quality.status_code}"
                )
            checks["decision_quality"] = {
                "status": "ok",
                "history_entries": len(decision_quality.json()),
            }

            hypotheses = client.get(
                "/api/assistant/hypotheses",
                params={"scope": "personal", "limit": 1},
            )
            if hypotheses.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/hypotheses returned HTTP {hypotheses.status_code}"
                )
            checks["hypotheses"] = {
                "status": "ok",
                "history_entries": len(hypotheses.json()),
            }

            logic_learning = client.get(
                "/api/assistant/logic-learning",
                params={"scope": "personal", "limit": 1},
            )
            if logic_learning.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/logic-learning returned HTTP "
                    f"{logic_learning.status_code}"
                )
            checks["logic_learning"] = {
                "status": "ok",
                "events": len(logic_learning.json()),
            }

            context_traces = client.get(
                "/api/assistant/context-traces",
                params={"scope": "personal", "limit": 1},
            )
            if context_traces.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/context-traces returned HTTP "
                    f"{context_traces.status_code}"
                )
            checks["context_orchestrator"] = {
                "status": "ok",
                "history_entries": len(context_traces.json()),
            }

            causal = client.get(
                "/api/assistant/causal",
                params={"scope": "personal", "limit": 1},
            )
            if causal.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/causal returned HTTP {causal.status_code}"
                )
            checks["causal"] = {
                "status": "ok",
                "history_entries": len(causal.json()),
            }

            logic = client.get(
                "/api/assistant/logic",
                params={"scope": "personal", "limit": 1},
            )
            if logic.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/logic returned HTTP {logic.status_code}"
                )
            checks["logic"] = {
                "status": "ok",
                "history_entries": len(logic.json()),
            }

            verification = client.get(
                "/api/assistant/verification",
                params={"scope": "personal", "limit": 1},
            )
            if verification.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/verification returned HTTP "
                    f"{verification.status_code}"
                )
            checks["verification"] = {
                "status": "ok",
                "history_entries": len(verification.json()),
            }

        print(
            json.dumps(
                {"status": "ok", "checks": checks},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": str(exc),
                    "checks": checks,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
