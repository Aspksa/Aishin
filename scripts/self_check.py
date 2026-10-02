from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


_configure_utf8_output()

from app.core.engine import AishinEngine
from app.core.tools import ToolRegistry
from app.db import _merge_graph_data, connect, database_schema_status, init_db
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

        engine = AishinEngine()
        engine.startup()

        ai_diag = engine.ai.diagnostics()
        if ai_diag.get("provider") == "cloud.ru":
            if not (0 <= int(ai_diag.get("max_retries", -1)) <= 4):
                raise RuntimeError("Cloud.ru max_retries вне безопасной границы")
            if float(ai_diag.get("health_ttl_seconds", 0)) < 5:
                raise RuntimeError("Cloud.ru health cache TTL слишком мал")
        checks["cloudru_resilience"] = {
            "status": "ok",
            "diagnostics": ai_diag,
        }

        if engine.verification.should_run(
            intent="conversation",
            status="insufficient_data",
        ):
            raise RuntimeError(
                "Обычный conversation не должен запускать Verification "
                "только из-за insufficient_data"
            )
        if not engine.verification.should_run(
            intent="verification",
            status="cautious",
        ):
            raise RuntimeError("Explicit verification должен запускать Verification")

        checks["verification_trigger_policy"] = {
            "status": "ok",
            "conversation_insufficient": False,
            "explicit_verification": True,
            "action_insufficient": engine.verification.should_run(
                intent="action",
                status="insufficient_data",
            ),
        }

        realtime_mode = engine.continuous_learning.select_mode(
            scope="personal",
            queue_depth=0,
            high_priority=0,
            last_activity_at=__import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
        )
        if realtime_mode.mode != "REALTIME":
            raise RuntimeError("Активный пользователь должен включать REALTIME")

        background_mode = engine.continuous_learning.select_mode(
            scope="personal",
            queue_depth=10,
            high_priority=1,
            last_activity_at="2000-01-01T00:00:00+00:00",
        )
        if background_mode.mode not in {"BACKGROUND", "MAINTENANCE"}:
            raise RuntimeError(
                "Фоновая очередь должна включать BACKGROUND или MAINTENANCE"
            )

        quality = engine.continuous_learning.quality_status(
            scope="personal"
        )
        if set(quality["patterns"]["lifecycle"]) != {
            "candidate", "observed", "trusted", "deprecated"
        }:
            raise RuntimeError("Learning Quality Gate lifecycle неполный")

        checks["learning_quality_gate"] = {
            "status": "ok",
            "pattern_half_life_days": (
                engine.continuous_learning.quality_gate.PATTERN_HALF_LIFE_DAYS
            ),
            "strategy_half_life_days": (
                engine.continuous_learning.quality_gate.STRATEGY_HALF_LIFE_DAYS
            ),
            "quality": quality,
            "strategy_count": len(
                engine.continuous_learning.strategy_evolution(
                    scope="personal",
                    limit=20,
                )
            ),
        }

        checks["continuous_learning"] = {
            "status": "ok",
            "engine": engine.continuous_learning.__class__.__name__,
            "modes": ["REALTIME", "BACKGROUND", "IDLE", "MAINTENANCE"],
            "automatic_mode_selection": True,
            "realtime_test": realtime_mode.to_dict(),
            "background_test": background_mode.to_dict(),
            "runtime_status": engine.continuous_learning.status(
                scope="personal"
            ),
        }

        checks["performance_observability"] = {
            "status": "ok",
            "history_entries": len(
                engine.performance.recent(scope="personal", limit=10)
            ),
            "budgets": __import__(
                "app.core.performance",
                fromlist=["PerformanceTracker"],
            ).PerformanceTracker.DEFAULT_BUDGETS_MS,
        }

        checks["cognitive_trace_isolation"] = {
            "status": "ok",
            "store": engine.cognitive_traces.__class__.__name__,
            "history_entries": len(
                engine.cognitive_traces.recent(scope="personal", limit=10)
            ),
            "global_last_context_removed": not hasattr(
                engine,
                "last_cognitive_context",
            ),
        }
        if not checks["cognitive_trace_isolation"]["global_last_context_removed"]:
            raise RuntimeError("Глобальный last_cognitive_context всё ещё активен")

        checks["personality"] = {
            "status": "ok",
            "name": personality.name,
            "source": personality.source,
            "path": str(personality.path),
            "schema_version": personality.profile["schema"].get("version"),
            "rules": len(personality.profile.get("internal_rules", [])),
        }

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

        merged_graph_data = _merge_graph_data(
            {
                "role": "личная AI-помощница",
                "nested": {"existing": 1},
                "tags": ["a"],
                "keep": "value",
            },
            {
                "nested": {"new": 2},
                "tags": ["a", "b"],
                "keep": "",
                "ignored": None,
            },
        )
        if merged_graph_data != {
            "role": "личная AI-помощница",
            "nested": {"existing": 1, "new": 2},
            "tags": ["a", "b"],
            "keep": "value",
        }:
            raise RuntimeError("Knowledge Graph deep merge policy нарушена")

        with connect() as conn:
            graph_changes_before = int(
                conn.execute(
                    "SELECT COUNT(*) FROM graph_changes WHERE scope='relationship'"
                ).fetchone()[0]
            )
        engine.graph.seed_personal_foundation()
        with connect() as conn:
            graph_changes_after = int(
                conn.execute(
                    "SELECT COUNT(*) FROM graph_changes WHERE scope='relationship'"
                ).fetchone()[0]
            )
        if graph_changes_after != graph_changes_before:
            raise RuntimeError(
                "Идемпотентный Knowledge Graph seed создал ложный audit change"
            )

        graph_shape = engine.graph.search(
            "Айшин",
            scope="relationship",
            limit=5,
        )
        if not graph_shape:
            raise RuntimeError("Knowledge Graph seed Айшин не найден")
        if (
            "canonical_name" not in graph_shape[0]
            or not isinstance(graph_shape[0].get("data"), dict)
        ):
            raise RuntimeError(
                "Knowledge Graph search shape несовместим с Verification"
            )

        checks["graph_merge_audit"] = {
            "status": "ok",
            "deep_merge": True,
            "blank_null_preservation": True,
            "seed_audit_idempotent": True,
            "verification_shape": {
                "canonical_name": True,
                "data_dict": True,
            },
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
        checks["proactive_lifecycle"] = {
            "status": "ok",
            "manager": engine.proactive.lifecycle.__class__.__name__,
            "conditions": len(
                engine.proactive.conditions(scope="personal", limit=20)
            ),
            "dedupe_policy": "one_decision_per_active_condition_generation",
            "acknowledged_status_supported": True,
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
        test_scope = "__selfcheck_reflective_learning__"
        try:
            fitted_system, fitted_messages, budget_report = (
                engine.context_budgeter.fit(
                    request_id="selfcheck-context-budget",
                    scope=test_scope,
                    mode="FAST",
                    system_prompt="system " * 9000,
                    messages=[
                        {"role": "user", "content": "history " * 1200}
                        for _ in range(8)
                    ],
                )
            )
            if (
                budget_report.estimated_tokens_after
                > budget_report.token_budget
            ):
                raise RuntimeError("Context Budgeter не удержал лимит")
            if budget_report.estimated_tokens_after >= (
                budget_report.estimated_tokens_before
            ):
                raise RuntimeError("Context Budgeter не сократил перегрузку")

            reflections = []
            for index in range(3):
                reflections.append(
                    engine.self_reflection.assess(
                        request_id=f"selfcheck-reflection-{index}",
                        scope=test_scope,
                        mode="FAST",
                        user_message=(
                            "Опять ошибка, исправь"
                            if index == 0 else "Проверка качества"
                        ),
                        provider_runtime={
                            "available": index != 1,
                            "error": "test" if index == 1 else None,
                        },
                        metacognition={"confidence": 0.42},
                        verification={
                            "unresolved": ["test"],
                            "consistency": {"conflicts": []},
                        },
                        decision_quality={"overall": 0.50},
                        performance={
                            "total_ms": 100,
                            "budget_status": "within_budget",
                        },
                    )
                )

            summary = engine.self_reflection.summary(
                scope=test_scope,
                limit=10,
            )
            if summary["samples"] != 3:
                raise RuntimeError("Self-Reflection не сохранил тестовые метрики")
            plans = engine.learning_planner.refresh(scope=test_scope)
            if not plans:
                raise RuntimeError("Learning Planner не создал цель из слабых мест")
            experiments = engine.experiment_manager.observe(
                scope=test_scope,
                request_id="selfcheck-experiment-observation",
                reflection=reflections[-1].to_dict(),
                open_plans=plans,
            )
            if not experiments:
                raise RuntimeError("Safe Experiment Manager не создал shadow experiment")
            if any(item.get("promotion_allowed") for item in experiments):
                raise RuntimeError("Safe Experiment не должен автоматически продвигать стратегию")

            checks["reflective_learning"] = {
                "status": "ok",
                "reflection_samples": summary["samples"],
                "learning_plans": len(plans),
                "experiments": len(experiments),
                "context_before": budget_report.estimated_tokens_before,
                "context_after": budget_report.estimated_tokens_after,
                "auto_promotion": False,
            }

            for index in range(6):
                engine.continuous_learning._observe_pattern(
                    scope=test_scope,
                    category="selfcheck_weighted",
                    pattern_key="weak_telemetry",
                    success=True,
                    evidence_weight=0.35,
                    evidence={
                        "source_type": "events",
                        "source_id": 1000 + index,
                    },
                )
                engine.continuous_learning._observe_pattern(
                    scope=test_scope,
                    category="selfcheck_weighted",
                    pattern_key="strong_feedback",
                    success=True,
                    evidence_weight=1.0,
                    evidence={
                        "source_type": "logic_learning",
                        "source_id": 2000 + index,
                    },
                )

            weighted_quality = (
                engine.continuous_learning.quality_gate.refresh(
                    scope=test_scope
                )
            )
            weighted_patterns = engine.continuous_learning.patterns(
                scope=test_scope,
                limit=20,
            )
            by_key = {
                item["pattern_key"]: item
                for item in weighted_patterns
                if item["category"] == "selfcheck_weighted"
            }
            weak_pattern = by_key.get("weak_telemetry")
            strong_pattern = by_key.get("strong_feedback")
            if not weak_pattern or not strong_pattern:
                raise RuntimeError(
                    "Weighted Learning Evidence не сохранил тестовые паттерны"
                )
            if weak_pattern.get("lifecycle") == "trusted":
                raise RuntimeError(
                    "Слабая телеметрия не должна становиться trusted "
                    "только из-за количества повторов"
                )
            if strong_pattern.get("lifecycle") != "trusted":
                raise RuntimeError(
                    "Повторная сильная evidence не достигла trusted"
                )
            if float(strong_pattern.get("weighted_observations", 0)) <= float(
                weak_pattern.get("weighted_observations", 0)
            ):
                raise RuntimeError(
                    "Weighted observations не различают силу evidence"
                )

            checks["weighted_learning_evidence"] = {
                "status": "ok",
                "weak_lifecycle": weak_pattern.get("lifecycle"),
                "weak_weighted": weak_pattern.get("weighted_observations"),
                "strong_lifecycle": strong_pattern.get("lifecycle"),
                "strong_weighted": strong_pattern.get("weighted_observations"),
                "quality": weighted_quality,
                "shadow_self_confirmation": False,
            }

            development = engine.development.current(
                scope=test_scope,
                persist=True,
            )
            if round(sum(development["weights"].values()), 1) != 100.0:
                raise RuntimeError(
                    "Development Metrics weights должны давать ровно 100%"
                )
            if development["formula_version"] != "aishin-development-v1":
                raise RuntimeError("Development Metrics formula version mismatch")
            if development["counters"].get("confirmed_hypotheses") != 0:
                raise RuntimeError(
                    "Нельзя считать гипотезу подтверждённой без отдельного evidence"
                )
            if not (0.0 <= float(development["overall_score"]) <= 100.0):
                raise RuntimeError("Development Metrics вышел за диапазон 0..100")
            if len(development["components"]) != 8:
                raise RuntimeError("Development Metrics должен иметь 8 направлений")
            development_history = engine.development.history(
                scope=test_scope,
                days=30,
            )
            if not development_history:
                raise RuntimeError("Development Metrics не сохранил историю")

            checks["development_metrics"] = {
                "status": "ok",
                "formula": development["formula_version"],
                "overall_score": development["overall_score"],
                "components": len(development["components"]),
                "weight_total": sum(development["weights"].values()),
                "confirmed_hypotheses_are_evidence_only": True,
                "cloud_provider_contributes_score": False,
                "history_entries": len(development_history),
            }
        finally:
            with connect() as conn:
                conn.execute(
                    """DELETE FROM experiment_observations
                       WHERE scope=?""",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM safe_experiments WHERE scope=?",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM learning_plan_events WHERE scope=?",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM learning_plans WHERE scope=?",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM self_reflection_runs WHERE scope=?",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM context_budget_reports WHERE scope=?",
                    (test_scope,),
                )
                conn.execute(
                    """DELETE FROM learning_pattern_quality
                       WHERE pattern_id IN (
                           SELECT id FROM learning_patterns WHERE scope=?
                       )""",
                    (test_scope,),
                )
                conn.execute(
                    """DELETE FROM learning_evidence_metrics
                       WHERE pattern_id IN (
                           SELECT id FROM learning_patterns WHERE scope=?
                       )""",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM learning_patterns WHERE scope=?",
                    (test_scope,),
                )
                conn.execute(
                    "DELETE FROM development_snapshots WHERE scope=?",
                    (test_scope,),
                )
                conn.commit()

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
        checks["action_selection"] = {
            "status": "ok",
            "engine": engine.action_selector.__class__.__name__,
            "history_entries": len(
                engine.action_selector.recent(scope="personal", limit=10)
            ),
            "execution_policy": "selection_never_executes_tools",
        }
        checks["execution_coordinator"] = {
            "status": "ok",
            "engine": engine.execution_coordinator.__class__.__name__,
            "approval_ttl_minutes": engine.execution_coordinator.APPROVAL_TTL_MINUTES,
            "approvals": len(
                engine.execution_coordinator.recent_approvals(scope="personal", limit=10)
            ),
            "attempts": len(
                engine.execution_coordinator.recent_attempts(scope="personal", limit=10)
            ),
            "policy": "one_shot_revalidate_before_execute",
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
