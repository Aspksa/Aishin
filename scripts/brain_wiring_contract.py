from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.engine import AishinEngine


def main() -> int:
    engine = AishinEngine()
    report = engine.wiring_audit.audit(engine)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report.get("status") != "healthy":
        broken = report.get("broken") or []
        raise RuntimeError(
            "Brain Wiring Contract failed: "
            + json.dumps(broken, ensure_ascii=False)
        )
    if report.get("uncovered_modules"):
        raise RuntimeError(
            "Uncovered core modules: "
            + ", ".join(report["uncovered_modules"])
        )
    if report.get("missing_flow_edges"):
        raise RuntimeError(
            "Required real-time flow edges are missing."
        )
    if float(report.get("score") or 0.0) != 100.0:
        raise RuntimeError(
            f"Brain wiring score must be 100%, got {report.get('score')}"
        )

    print(
        "BRAIN WIRING CONTRACT OK: "
        f"{report['checks_passed']}/{report['checks_total']} checks; "
        f"{report['covered_modules']}/{report['core_modules']} core modules"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
