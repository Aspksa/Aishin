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

from app.db import connect
from app.main import app, engine


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
                'id="settings-module"',
                'id="cloud-api-key"',
                'id="brain-links"',
                'data-brain-node="reflection"',
                'data-brain-node="learning-plan"',
                'data-brain-node="experiment"',
                'data-brain-node="learning-check"',
                'data-brain-node="consolidation"',
                'id="reflection-quality"',
                'id="learning-plan-stream"',
                'id="experiment-stream"',
                'id="context-budget-value"',
                'id="development-open"',
                'id="development-score"',
                'id="development-module"',
                'id="development-components"',
                'id="development-chart"',
                'id="development-reasons"',
                'id="dev-count-knowledge"',
                '/static/intelligence.css',
                '/static/intelligence.js',
                '/static/proactive_intelligence.css',
                '/static/proactive_intelligence.js',
                'id="attention-module"',
                'id="proactive-awareness-score"',
                'id="proactive-incidents"',
                'id="proactive-calibration"',
                '/static/evolution.css',
                '/static/evolution.js',
                'id="evolution-module"',
                'id="evolution-score"',
                'id="evolution-capabilities"',
                'id="evolution-variants"',
                'id="evolution-curriculum"',
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

            cloud_settings = client.get("/api/settings/cloudru")
            if cloud_settings.status_code != 200:
                raise RuntimeError(
                    f"/api/settings/cloudru returned HTTP "
                    f"{cloud_settings.status_code}"
                )
            cloud_data = cloud_settings.json()
            if "api_key" in cloud_data or "AISHIN_CLOUDRU_API_KEY" in cloud_data:
                raise RuntimeError("Cloud settings API leaked API key field")

            update_status = client.get("/api/system/update/status")
            if update_status.status_code != 200:
                raise RuntimeError(
                    f"/api/system/update/status returned HTTP "
                    f"{update_status.status_code}"
                )
            if update_status.json().get("mode") not in {"git", "zip"}:
                raise RuntimeError("Updater returned unknown mode")

            checks["cloud_settings_ui"] = {
                "status": "ok",
                "configured": cloud_data.get("configured"),
                "secret_not_exposed": True,
                "update_mode": update_status.json().get("mode"),
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

            reflection_api = client.get(
                "/api/assistant/self-reflection",
                params={"scope": "personal", "limit": 2},
            )
            if reflection_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/self-reflection returned HTTP "
                    f"{reflection_api.status_code}"
                )

            learning_plans_api = client.get(
                "/api/assistant/learning-plans",
                params={"scope": "personal", "limit": 2},
            )
            if learning_plans_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/learning-plans returned HTTP "
                    f"{learning_plans_api.status_code}"
                )

            experiments_api = client.get(
                "/api/assistant/safe-experiments",
                params={"scope": "personal", "limit": 2},
            )
            if experiments_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/safe-experiments returned HTTP "
                    f"{experiments_api.status_code}"
                )
            for item in experiments_api.json():
                if item.get("promotion_allowed") is not False:
                    raise RuntimeError(
                        "Safe experiment must never expose automatic promotion"
                    )

            budget_api = client.get(
                "/api/assistant/context-budget",
                params={"scope": "personal", "limit": 2},
            )
            if budget_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/context-budget returned HTTP "
                    f"{budget_api.status_code}"
                )

            checks["reflective_learning_api"] = {
                "status": "ok",
                "reflection": bool(reflection_api.json().get("summary")),
                "plans": len(learning_plans_api.json()),
                "experiments": len(experiments_api.json()),
                "budget_reports": len(budget_api.json()),
                "automatic_promotion": False,
            }

            development_api = client.get(
                "/api/assistant/development",
                params={"scope": "personal", "days": 30},
            )
            if development_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/development returned HTTP "
                    f"{development_api.status_code}"
                )
            development_data = development_api.json()
            current_development = development_data.get("current") or {}
            if len(current_development.get("components") or {}) != 8:
                raise RuntimeError(
                    "Development API должен возвращать 8 направлений"
                )
            if round(
                sum((current_development.get("weights") or {}).values()), 1
            ) != 100.0:
                raise RuntimeError(
                    "Development API weights должны давать 100%"
                )
            if current_development.get("counters", {}).get(
                "confirmed_hypotheses"
            ) != 0:
                raise RuntimeError(
                    "Нельзя показывать неподтверждённые гипотезы как подтверждённые"
                )
            if "Cloud.ru не добавляет баллы" not in str(
                current_development.get("principle") or ""
            ):
                raise RuntimeError(
                    "Development API должен явно отделять развитие Айшин от Cloud.ru"
                )

            checks["development_metrics_api"] = {
                "status": "ok",
                "score": current_development.get("overall_score"),
                "components": len(current_development.get("components") or {}),
                "history": len(development_data.get("history") or []),
                "cloud_independent": True,
            }

            growth_api = client.get(
                "/api/assistant/growth",
                params={
                    "scope": "personal",
                    "skill_limit": 20,
                    "knowledge_limit": 20,
                    "specialization_limit": 20,
                    "history_limit": 20,
                },
            )
            if growth_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/growth returned HTTP "
                    f"{growth_api.status_code}: {growth_api.text[:300]}"
                )
            growth_data = growth_api.json()
            growth_summary = growth_data.get("summary") or {}
            if growth_summary.get("version") != "aishin-long-term-growth-v1":
                raise RuntimeError(
                    "Long Term Growth вернул несовместимую версию"
                )
            for key in ("skills", "knowledge", "specializations"):
                if not isinstance(growth_data.get(key), list):
                    raise RuntimeError(
                        f"Long Term Growth {key} должен быть списком"
                    )
            if not isinstance(growth_summary.get("principles"), list):
                raise RuntimeError(
                    "Long Term Growth должен объяснять правила честного роста"
                )
            growth_skills = growth_summary.get("skills") or {}
            growth_knowledge = growth_summary.get("knowledge") or {}
            if int(growth_skills.get("mastered") or 0) > int(
                growth_skills.get("total") or 0
            ):
                raise RuntimeError(
                    "Mastered skills не могут превышать total skills"
                )
            if int(growth_knowledge.get("trusted") or 0) > int(
                growth_knowledge.get("total") or 0
            ):
                raise RuntimeError(
                    "Trusted knowledge не может превышать total knowledge"
                )
            schema = state_data.get("state", {}).get("schema")
            checks["long_term_growth"] = {
                "status": "ok",
                "version": growth_summary.get("version"),
                "score": growth_summary.get("overall_score"),
                "skills": len(growth_data.get("skills") or []),
                "knowledge": len(growth_data.get("knowledge") or []),
                "specializations": len(
                    growth_data.get("specializations") or []
                ),
                "history": len(growth_data.get("history") or []),
            }

            intelligence_api = client.get(
                "/api/assistant/intelligence",
                params={
                    "scope": "personal",
                    "history_limit": 20,
                    "route_limit": 20,
                },
            )
            if intelligence_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/intelligence returned HTTP "
                    f"{intelligence_api.status_code}: "
                    f"{intelligence_api.text[:300]}"
                )
            intelligence_data = intelligence_api.json()
            current_intelligence = intelligence_data.get("current") or {}
            dimensions = current_intelligence.get("dimensions") or {}
            if current_intelligence.get("version") != (
                "aishin-cognitive-intelligence-v1"
            ):
                raise RuntimeError(
                    "Cognitive Intelligence вернул несовместимую версию"
                )
            if len(dimensions) != 8:
                raise RuntimeError(
                    "Cognitive Intelligence должен возвращать 8 способностей"
                )
            if round(
                sum(
                    float(item.get("weight") or 0.0)
                    for item in dimensions.values()
                ),
                1,
            ) != 100.0:
                raise RuntimeError(
                    "Веса 8 cognitive dimensions должны давать 100%"
                )
            for key, item in dimensions.items():
                score = float(item.get("score") or 0.0)
                if not 0.0 <= score <= 100.0:
                    raise RuntimeError(
                        f"Cognitive dimension {key} вышел за диапазон 0..100"
                    )
                if not str(item.get("why") or "").strip():
                    raise RuntimeError(
                        f"Cognitive dimension {key} не объясняет свой score"
                    )
            if not any(
                "не IQ" in str(item)
                for item in current_intelligence.get("principles") or []
            ):
                raise RuntimeError(
                    "Cognitive Intelligence должен явно отделяться от IQ"
                )

            safety_route = engine.cognitive_intelligence.route(
                request_id=engine.cognitive_traces.new_request_id(),
                scope="personal",
                query=(
                    "Проверь противоречия и перепроверь данные, "
                    "не делай вывод без подтверждения"
                ),
                intent="verification",
                base_mode="VERIFY",
                base_complexity=0.8,
                metacognition={
                    "status": "needs_verification",
                    "confidence": 0.25,
                },
            )
            if safety_route.adapted_mode != "VERIFY":
                raise RuntimeError(
                    "Adaptive Router не имеет права понижать VERIFY"
                )

            diagnose_route = engine.cognitive_intelligence.route(
                request_id=engine.cognitive_traces.new_request_id(),
                scope="personal",
                query="Диагностируй ошибку запуска системы",
                intent="action",
                base_mode="DIAGNOSE",
                base_complexity=0.8,
                metacognition={
                    "status": "cautious",
                    "confidence": 0.55,
                },
            )
            if diagnose_route.adapted_mode != "DIAGNOSE":
                raise RuntimeError(
                    "Adaptive Router не имеет права понижать DIAGNOSE"
                )

            checks["cognitive_intelligence"] = {
                "status": "ok",
                "score": current_intelligence.get("overall_score"),
                "dimensions": len(dimensions),
                "routes": len(intelligence_data.get("routes") or []),
                "transfer": len(
                    intelligence_data.get("transfer_map") or []
                ),
                "verify_preserved": True,
                "diagnose_preserved": True,
            }

            proactive_task = client.post(
                "/api/assistant/planner/tasks",
                json={
                    "title": "Runtime Smoke — просроченная задача",
                    "description": "Проверка Proactive Intelligence lifecycle",
                    "scope": "personal",
                    "priority": 0.9,
                    "due_at": "2020-01-01T00:00:00+00:00",
                },
            )
            if proactive_task.status_code != 200:
                raise RuntimeError(
                    "Не удалось создать deterministic overdue task для "
                    "Proactive Intelligence smoke"
                )
            proactive_task_id = int(proactive_task.json()["id"])

            proactive_scan_data = engine.proactive_intelligence.evaluate(
                scope="personal",
                trigger="runtime_smoke",
            ).to_dict()
            if not 0.0 <= float(
                proactive_scan_data.get("awareness_score") or 0.0
            ) <= 100.0:
                raise RuntimeError(
                    "Situation Awareness должен оставаться в диапазоне 0..100"
                )

            proactive_api = client.get(
                "/api/assistant/proactive-intelligence",
                params={
                    "scope": "personal",
                    "incident_limit": 100,
                    "signal_limit": 100,
                    "run_limit": 30,
                },
            )
            if proactive_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/proactive-intelligence returned HTTP "
                    f"{proactive_api.status_code}: {proactive_api.text[:300]}"
                )
            proactive_data = proactive_api.json()
            if proactive_data.get("version") != (
                "aishin-proactive-intelligence-v1"
            ):
                raise RuntimeError(
                    "Proactive Intelligence вернул несовместимую версию"
                )
            summary = proactive_data.get("summary") or {}
            threshold = float(summary.get("attention_threshold") or 0.0)
            if not 0.36 <= threshold <= 0.70:
                raise RuntimeError(
                    "Attention threshold вышел за безопасный диапазон"
                )
            if not isinstance(proactive_data.get("incidents"), list):
                raise RuntimeError(
                    "Proactive Intelligence incidents должен быть списком"
                )
            if not isinstance(proactive_data.get("expectations"), list):
                raise RuntimeError(
                    "Proactive Intelligence expectations должен быть списком"
                )
            if not isinstance(proactive_data.get("signals"), list):
                raise RuntimeError(
                    "Proactive Intelligence signals должен быть списком"
                )

            active_incidents = [
                item
                for item in proactive_data.get("incidents") or []
                if item.get("status") == "active"
            ]
            overdue_incident = next(
                (
                    item
                    for item in active_incidents
                    if item.get("subject_type") == "task"
                    and str(item.get("subject_id")) == str(proactive_task_id)
                    and item.get("incident_type") == "task_overdue"
                ),
                None,
            )
            if overdue_incident is None:
                raise RuntimeError(
                    "Proactive Intelligence не обнаружил deterministic overdue task"
                )

            for key in (
                "severity",
                "confidence",
                "impact",
                "urgency",
                "risk_score",
                "attention_score",
            ):
                value = float(overdue_incident.get(key) or 0.0)
                if not 0.0 <= value <= 1.0:
                    raise RuntimeError(
                        f"Proactive incident {key} вышел за диапазон 0..1"
                    )
            if not isinstance(overdue_incident.get("evidence"), list):
                raise RuntimeError(
                    "Proactive incident должен хранить evidence"
                )
            decision_id = overdue_incident.get("decision_id")
            if decision_id:
                decision = next(
                    (
                        item
                        for item in engine.proactive.history(
                            scope="personal",
                            limit=300,
                        )
                        if int(item["id"]) == int(decision_id)
                    ),
                    None,
                )
                if decision and decision.get("tool_name"):
                    raise RuntimeError(
                        "00.00.07 не должен автоматически создавать "
                        "исполняемый tool proposal"
                    )

            proactive_feedback = engine.proactive_intelligence.feedback(
                int(overdue_incident["id"]),
                scope="personal",
                feedback="noisy",
                reason="runtime smoke suppression check",
            )
            feedback_incident = proactive_feedback.get("incident") or {}
            if feedback_incident.get("status") != "snoozed":
                raise RuntimeError(
                    "Noisy feedback должен временно подавлять incident"
                )
            if not feedback_incident.get("snoozed_until"):
                raise RuntimeError(
                    "Noisy feedback должен сохранять snoozed_until"
                )

            engine.proactive_intelligence.evaluate(
                scope="personal",
                trigger="runtime_smoke_rescan",
            )
            incident_after_rescan = engine.proactive_intelligence.incident(
                int(overdue_incident["id"]),
                scope="personal",
            ) or {}
            if incident_after_rescan.get("status") != "snoozed":
                raise RuntimeError(
                    "Suppressed incident не должен немедленно возвращаться active"
                )

            close_proactive_task = client.post(
                f"/api/assistant/planner/tasks/{proactive_task_id}/status",
                json={
                    "scope": "personal",
                    "status": "completed",
                    "blocked_reason": "",
                },
            )
            if close_proactive_task.status_code != 200:
                raise RuntimeError(
                    "Не удалось завершить proactive smoke task"
                )
            engine.proactive_intelligence.evaluate(
                scope="personal",
                trigger="runtime_smoke_cleanup",
            )

            checks["proactive_intelligence"] = {
                "status": "ok",
                "version": proactive_data.get("version"),
                "awareness": summary.get("awareness_score"),
                "incidents": len(proactive_data.get("incidents") or []),
                "signals": len(proactive_data.get("signals") or []),
                "expectations": len(
                    proactive_data.get("expectations") or []
                ),
                "threshold": threshold,
                "feedback_suppression": True,
                "auto_execution": False,
            }

            evolution_scope = "__evolution_smoke__"
            with connect() as conn:
                for table in (
                    "evolution_assignments",
                    "evolution_variants",
                    "evolution_curriculum",
                    "evolution_transfers",
                    "evolution_cycles",
                    "evolution_events",
                    "evolution_capabilities",
                    "evolution_state",
                    "cognitive_intelligence_routes",
                ):
                    conn.execute(
                        f"DELETE FROM {table} WHERE scope=?",
                        (evolution_scope,),
                    )
                conn.execute(
                    """DELETE FROM learning_plans
                       WHERE scope=? AND target_metric LIKE 'evolution:%'""",
                    (evolution_scope,),
                )
                for index in range(12):
                    outcome = 0.54 + (index % 3) * 0.015
                    conn.execute(
                        """INSERT INTO cognitive_intelligence_routes(
                               request_id, scope, task_family, intent,
                               base_mode, adapted_mode, outcome_score,
                               successful, unresolved_count, completed_at
                           ) VALUES (?, ?, 'software', 'analysis',
                                     'FAST', 'FAST', ?, 0, 0,
                                     CURRENT_TIMESTAMP)""",
                        (
                            f"evolution-seed-{index}",
                            evolution_scope,
                            outcome,
                        ),
                    )
                conn.commit()

            first_evolution_cycle = engine.evolution.run_cycle(
                scope=evolution_scope,
                trigger="runtime_smoke_seed",
            )
            if not 0.0 <= float(first_evolution_cycle.evolution_score) <= 100.0:
                raise RuntimeError(
                    "Evolution score должен оставаться в диапазоне 0..100"
                )
            if not 0.0 <= float(first_evolution_cycle.stability_score) <= 100.0:
                raise RuntimeError(
                    "Evolution stability должен оставаться в диапазоне 0..100"
                )
            if not 0.0 <= float(first_evolution_cycle.plasticity_score) <= 100.0:
                raise RuntimeError(
                    "Evolution plasticity должен оставаться в диапазоне 0..100"
                )

            evolution_api = client.get(
                "/api/assistant/evolution",
                params={
                    "scope": evolution_scope,
                    "capability_limit": 40,
                    "variant_limit": 80,
                    "curriculum_limit": 80,
                    "transfer_limit": 80,
                    "cycle_limit": 80,
                },
            )
            if evolution_api.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/evolution returned HTTP "
                    f"{evolution_api.status_code}: "
                    f"{evolution_api.text[:300]}"
                )
            evolution_data = evolution_api.json()
            if evolution_data.get("version") != "aishin-evolution-engine-v1":
                raise RuntimeError(
                    "Evolution Engine вернул несовместимую версию"
                )
            if evolution_data.get("formula_version") != "bounded-meta-learning-v1":
                raise RuntimeError(
                    "Evolution Engine вернул несовместимую формулу"
                )
            if not isinstance(evolution_data.get("capabilities"), list):
                raise RuntimeError(
                    "Evolution capabilities должен быть списком"
                )
            if not isinstance(evolution_data.get("curriculum"), list):
                raise RuntimeError(
                    "Evolution curriculum должен быть списком"
                )
            if not any(
                item.get("family") == "software"
                and int(item.get("sample_count") or 0) >= 12
                for item in evolution_data.get("capabilities") or []
            ):
                raise RuntimeError(
                    "Evolution Engine не построил capability из route outcomes"
                )

            challengers = [
                item
                for item in evolution_data.get("variants") or []
                if item.get("family") == "software"
                and item.get("lifecycle") == "challenger"
            ]
            if not challengers:
                raise RuntimeError(
                    "Evolution Engine не создал challenger для слабой family"
                )
            challenger = challengers[0]
            challenger_id = int(challenger["id"])
            baseline = float(challenger.get("baseline_fitness") or 0.0)

            verify_hint = engine.evolution.routing_hint(
                scope=evolution_scope,
                family="software",
                base_mode="VERIFY",
                request_id="evolution-safety-verify",
                base_complexity=0.9,
            )
            if verify_hint.get("preferred_mode") != "VERIFY":
                raise RuntimeError(
                    "Evolution Engine не имеет права понижать VERIFY"
                )
            diagnose_hint = engine.evolution.routing_hint(
                scope=evolution_scope,
                family="software",
                base_mode="DIAGNOSE",
                request_id="evolution-safety-diagnose",
                base_complexity=0.9,
            )
            if diagnose_hint.get("preferred_mode") != "DIAGNOSE":
                raise RuntimeError(
                    "Evolution Engine не имеет права понижать DIAGNOSE"
                )
            for hint in (verify_hint, diagnose_hint):
                multiplier = float(hint.get("context_multiplier") or 1.0)
                if not 0.90 <= multiplier <= 1.20:
                    raise RuntimeError(
                        "Evolution context policy вышла за safe bounds"
                    )

            with connect() as conn:
                conn.execute(
                    """DELETE FROM evolution_assignments
                       WHERE scope=? AND variant_id=?""",
                    (evolution_scope, challenger_id),
                )
                high_outcome = min(0.98, baseline + 0.18)
                for index in range(10):
                    conn.execute(
                        """INSERT INTO evolution_assignments(
                               request_id, scope, family, variant_id,
                               assignment_type, policy_json,
                               baseline_fitness, outcome_score, successful,
                               unresolved_count, completed_at
                           ) VALUES (?, ?, 'software', ?, 'challenger',
                                     '{}', ?, ?, 1, 0,
                                     CURRENT_TIMESTAMP)""",
                        (
                            f"evolution-promote-{index}",
                            evolution_scope,
                            challenger_id,
                            baseline,
                            high_outcome,
                        ),
                    )
                conn.execute(
                    """UPDATE evolution_variants
                       SET evidence_count=10, wins=10, losses=0,
                           unresolved_total=0, observed_fitness=?
                       WHERE id=?""",
                    (high_outcome, challenger_id),
                )
                conn.commit()

            promote_cycle = engine.evolution.run_cycle(
                scope=evolution_scope,
                trigger="runtime_smoke_promote",
            )
            promoted = engine.evolution.variants(
                scope=evolution_scope,
                lifecycle="champion",
                limit=10,
            )
            champion = next(
                (
                    item for item in promoted
                    if int(item["id"]) == challenger_id
                ),
                None,
            )
            if champion is None or promote_cycle.variants_promoted < 1:
                raise RuntimeError(
                    "Conservative Evolution evidence gate не promoted challenger"
                )

            with connect() as conn:
                for index in range(5):
                    conn.execute(
                        """INSERT INTO evolution_assignments(
                               request_id, scope, family, variant_id,
                               assignment_type, policy_json,
                               baseline_fitness, outcome_score, successful,
                               unresolved_count, completed_at
                           ) VALUES (?, ?, 'software', ?, 'champion',
                                     '{}', ?, 0.28, 0, 1,
                                     CURRENT_TIMESTAMP)""",
                        (
                            f"evolution-regression-{index}",
                            evolution_scope,
                            challenger_id,
                            baseline,
                        ),
                    )
                conn.execute(
                    """UPDATE evolution_variants
                       SET evidence_count=15, losses=losses+5,
                           unresolved_total=unresolved_total+5
                       WHERE id=?""",
                    (challenger_id,),
                )
                conn.commit()

            rollback_cycle = engine.evolution.run_cycle(
                scope=evolution_scope,
                trigger="runtime_smoke_rollback",
            )
            after_rollback = next(
                (
                    item
                    for item in engine.evolution.variants(
                        scope=evolution_scope,
                        limit=100,
                    )
                    if int(item["id"]) == challenger_id
                ),
                {},
            )
            if (
                after_rollback.get("lifecycle") != "rolled_back"
                or rollback_cycle.variants_rolled_back < 1
            ):
                raise RuntimeError(
                    "Evolution Engine не откатил деградировавший champion"
                )

            evolution_state = engine.evolution.state(scope=evolution_scope)
            if int(evolution_state.get("generation") or 0) < 3:
                raise RuntimeError(
                    "Evolution generation не изменилась после promotion/rollback"
                )
            principles = evolution_data.get("principles") or []
            if not any("исходный код" in str(item) for item in principles):
                raise RuntimeError(
                    "Evolution должен явно запрещать self-modifying source code"
                )

            checks["evolution_engine"] = {
                "status": "ok",
                "version": evolution_data.get("version"),
                "generation": evolution_state.get("generation"),
                "score": evolution_state.get("evolution_score"),
                "capabilities": len(
                    evolution_data.get("capabilities") or []
                ),
                "curriculum": len(
                    evolution_data.get("curriculum") or []
                ),
                "challenger_created": True,
                "conservative_promotion": True,
                "verify_preserved": True,
                "diagnose_preserved": True,
                "rollback_verified": True,
                "self_modifying_code": False,
            }

            live_brain = client.get(
                "/api/assistant/live-brain",
                params={
                    "scope": "personal",
                    "event_limit": 20,
                    "graph_limit": 12,
                },
            )
            if live_brain.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/live-brain returned HTTP "
                    f"{live_brain.status_code}: {live_brain.text[:300]}"
                )
            live_brain_data = live_brain.json()
            channels = live_brain_data.get("channels") or []
            if len(channels) != 24:
                raise RuntimeError(
                    "Live Brain должен возвращать ровно 24 когнитивных контура"
                )
            if "скрытой цепочки" not in str(
                live_brain_data.get("trace_policy") or ""
            ):
                raise RuntimeError(
                    "Live Brain должен явно ограничивать безопасную трассу"
                )
            if not isinstance(
                live_brain_data.get("knowledge_graph", {}).get("entities"),
                list,
            ):
                raise RuntimeError(
                    "Live Brain knowledge_graph.entities должен быть списком"
                )

            live_brain_export = client.get(
                "/api/assistant/live-brain/export",
                params={"scope": "personal"},
            )
            if live_brain_export.status_code != 200:
                raise RuntimeError(
                    f"/api/assistant/live-brain/export returned HTTP "
                    f"{live_brain_export.status_code}"
                )
            export_data = live_brain_export.json()
            if export_data.get("format") != "AISHIN_LIVE_BRAIN_EXPORT":
                raise RuntimeError("Live Brain export format несовместим")
            if int(export_data.get("format_version") or 0) != 6:
                raise RuntimeError(
                    "Live Brain export format должен быть version 6"
                )
            if not isinstance(
                live_brain_data.get("cognitive_intelligence"),
                dict,
            ):
                raise RuntimeError(
                    "Live Brain должен включать Cognitive Intelligence"
                )
            if not isinstance(
                live_brain_data.get("proactive_intelligence"),
                dict,
            ):
                raise RuntimeError(
                    "Live Brain должен включать Proactive Intelligence"
                )
            if not isinstance(
                live_brain_data.get("evolution"),
                dict,
            ):
                raise RuntimeError(
                    "Live Brain должен включать Evolution Engine"
                )

            checks["live_brain_runtime"] = {
                "status": "ok",
                "runtime_version": live_brain_data.get("runtime_version"),
                "channels": len(channels),
                "events": len(live_brain_data.get("event_stream") or []),
                "safe_trace": bool(
                    live_brain_data.get("safe_trace", {}).get("policy")
                ),
                "export_version": export_data.get("format_version"),
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

            causal_assessment = __import__(
                "app.core.causal",
                fromlist=["CausalReasoning"],
            ).CausalReasoning().assess(
                "Задержка возникла из-за ошибки сети",
                scope="personal",
                evidence=[
                    {
                        "content": (
                            "Задержка возникла из-за ошибки сети"
                        )
                    }
                ],
                contradictions=[],
            )
            if not causal_assessment.assessment_id:
                raise RuntimeError(
                    "CausalReasoning.assess не сохранил assessment"
                )
            checks["causal_assess_runtime"] = {
                "status": "ok",
                "assessment_id": causal_assessment.assessment_id,
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
