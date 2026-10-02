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
            checks["tools"] = {
                "status": "ok",
                "count": len(tools.json()),
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
