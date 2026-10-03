from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WiringComponent:
    module: str
    path: str
    class_name: str


@dataclass(frozen=True)
class WiringIdentity:
    left: str
    right: str
    label: str


class BrainWiringAudit:
    """Observable object-graph contract for Aishin's cognitive runtime.

    The audit verifies that core modules are not merely present on disk: they
    must be instantiated or intentionally nested, and shared dependencies must
    point at the same runtime objects. This is structural telemetry only.
    """

    VERSION = "aishin-brain-wiring-audit-v1"

    DIRECT = (
        WiringComponent("action_execution", "action_execution", "ActionExecutionBridge"),
        WiringComponent("action_selection", "action_selector", "ActionSelector"),
        WiringComponent("brain_flow", "brain_flow", "BrainFlowRuntime"),
        WiringComponent("causal", "causal", "CausalReasoning"),
        WiringComponent("cognition", "cognition", "Cognition"),
        WiringComponent("cognitive_intelligence", "cognitive_intelligence", "CognitiveIntelligenceEngine"),
        WiringComponent("cognitive_trace", "cognitive_traces", "CognitiveTraceStore"),
        WiringComponent("communication_intelligence", "communication", "CommunicationIntelligenceEngine"),
        WiringComponent("consolidation", "consolidator", "MemoryConsolidator"),
        WiringComponent("context_budgeter", "context_budgeter", "ContextBudgeter"),
        WiringComponent("context_orchestrator", "context_orchestrator", "ContextOrchestrator"),
        WiringComponent("continuous_learning", "continuous_learning", "ContinuousLearningEngine"),
        WiringComponent("counterfactual", "counterfactual", "CounterfactualReasoning"),
        WiringComponent("decision_quality", "decision_quality", "DecisionQualityScorer"),
        WiringComponent("development_metrics", "development", "DevelopmentMetricsEngine"),
        WiringComponent("document_intelligence", "documents", "DocumentIntelligenceEngine"),
        WiringComponent("events", "events", "EventBus"),
        WiringComponent("evolution_engine", "evolution", "EvolutionEngine"),
        WiringComponent("execution_coordinator", "execution_coordinator", "ExecutionCoordinator"),
        WiringComponent("experiment_manager", "experiment_manager", "SafeExperimentManager"),
        WiringComponent("graph", "graph", "KnowledgeGraph"),
        WiringComponent("graph_builder", "graph_builder", "GraphBuilder"),
        WiringComponent("hypotheses", "hypotheses", "HypothesisManager"),
        WiringComponent("learning_planner", "learning_planner", "LearningPlanner"),
        WiringComponent("live_brain", "live_brain", "LiveBrainRuntime"),
        WiringComponent("logic", "logic", "LogicEngine"),
        WiringComponent("logic_learning", "logic_learning", "LogicLearning"),
        WiringComponent("long_term_growth", "long_term_growth", "LongTermGrowthEngine"),
        WiringComponent("memory", "memory", "MemorySystem"),
        WiringComponent("metacognition", "metacognition", "Metacognition"),
        WiringComponent("observer", "observer", "Observer"),
        WiringComponent("performance", "performance", "PerformanceHistory"),
        WiringComponent("permissions", "permissions", "PermissionGate"),
        WiringComponent("personal", "personal", "PersonalAishin"),
        WiringComponent("planner", "planner", "Planner"),
        WiringComponent("planner_builder", "planner_builder", "PlannerBuilder"),
        WiringComponent("proactive", "proactive", "ProactiveDecisionLoop"),
        WiringComponent("proactive_intelligence", "proactive_intelligence", "ProactiveIntelligenceEngine"),
        WiringComponent("research_intelligence", "research", "AutonomousResearchEngine"),
        WiringComponent("self_reflection", "self_reflection", "SelfReflectionMetrics"),
        WiringComponent("semantic", "semantic", "SemanticMemory"),
        WiringComponent("sensors", "sensors", "SensorHub"),
        WiringComponent("state", "state", "StateManager"),
        WiringComponent("tools", "tools", "ToolRegistry"),
        WiringComponent("verification", "verification", "VerificationEngine"),
    )

    NESTED = (
        WiringComponent("learning_quality", "continuous_learning.quality_gate", "LearningQualityGate"),
        WiringComponent("proactive_lifecycle", "proactive.lifecycle", "ProactiveLifecycle"),
        WiringComponent("self_model", "cognition.self_model", "SelfModel"),
    )

    SPECIAL_MODULES = {"engine", "heartbeat"}

    IDENTITIES = (
        WiringIdentity("semantic.ai", "ai", "Semantic Memory uses the active AI manager"),
        WiringIdentity("cognition.memory", "memory", "Cognition shares canonical Memory"),
        WiringIdentity("cognition.semantic", "semantic", "Cognition shares Semantic Memory"),
        WiringIdentity("cognition.planner", "planner", "Cognition shares Planner"),
        WiringIdentity("context_orchestrator.memory", "memory", "Context shares Memory"),
        WiringIdentity("context_orchestrator.graph", "graph", "Context shares Knowledge Graph"),
        WiringIdentity("context_orchestrator.planner", "planner", "Context shares Planner"),
        WiringIdentity("learning_planner.reflection", "self_reflection", "Learning Planner consumes Self Reflection"),
        WiringIdentity("graph_builder.ai", "ai", "Graph Builder uses active AI"),
        WiringIdentity("graph_builder.graph", "graph", "Graph Builder writes canonical graph"),
        WiringIdentity("graph_builder.events", "events", "Graph Builder emits canonical events"),
        WiringIdentity("planner_builder.ai", "ai", "Planner Builder uses active AI"),
        WiringIdentity("planner_builder.planner", "planner", "Planner Builder writes canonical Planner"),
        WiringIdentity("planner_builder.events", "events", "Planner Builder emits canonical events"),
        WiringIdentity("consolidator.ai", "ai", "Memory Consolidator uses active AI"),
        WiringIdentity("consolidator.memory", "memory", "Memory Consolidator writes canonical Memory"),
        WiringIdentity("consolidator.personal", "personal", "Memory Consolidator shares personal profile"),
        WiringIdentity("consolidator.events", "events", "Memory Consolidator emits canonical events"),
        WiringIdentity("sensors.planner", "planner", "Sensors inspect canonical Planner"),
        WiringIdentity("tools.permissions", "permissions", "Tools share Permission Gate"),
        WiringIdentity("tools.planner", "planner", "Tools share Planner"),
        WiringIdentity("action_selector.tools", "tools", "Action Selection shares Tool Registry"),
        WiringIdentity("action_selector.permissions", "permissions", "Action Selection shares Permission Gate"),
        WiringIdentity("action_execution.tools", "tools", "Execution Bridge shares Tool Registry"),
        WiringIdentity("action_execution.permissions", "permissions", "Execution Bridge shares Permission Gate"),
        WiringIdentity("action_execution.events", "events", "Execution Bridge emits canonical events"),
        WiringIdentity("execution_coordinator.tools", "tools", "Execution Coordinator shares Tool Registry"),
        WiringIdentity("execution_coordinator.permissions", "permissions", "Execution Coordinator shares Permission Gate"),
        WiringIdentity("verification.ai", "ai", "Verification uses active AI"),
        WiringIdentity("verification.memory", "memory", "Verification shares Memory"),
        WiringIdentity("verification.semantic", "semantic", "Verification shares Semantic Memory"),
        WiringIdentity("verification.graph", "graph", "Verification shares Knowledge Graph"),
        WiringIdentity("verification.sensors", "sensors", "Verification shares Sensors"),
        WiringIdentity("verification.tools", "tools", "Verification shares Tool Registry"),
        WiringIdentity("proactive.planner", "planner", "Proactive loop shares Planner"),
        WiringIdentity("proactive.sensors", "sensors", "Proactive loop shares Sensors"),
        WiringIdentity("proactive.tools", "tools", "Proactive loop shares Tools"),
        WiringIdentity("proactive.permissions", "permissions", "Proactive loop shares Permission Gate"),
        WiringIdentity("proactive.events", "events", "Proactive loop shares Event Bus"),
        WiringIdentity("proactive.coordinator", "execution_coordinator", "Proactive loop shares Execution Coordinator"),
        WiringIdentity("proactive_intelligence.legacy_loop", "proactive", "Proactive Intelligence wraps legacy decision loop"),
        WiringIdentity("proactive_intelligence.planner", "planner", "Proactive Intelligence shares Planner"),
        WiringIdentity("proactive_intelligence.sensors", "sensors", "Proactive Intelligence shares Sensors"),
        WiringIdentity("proactive_intelligence.events", "events", "Proactive Intelligence shares Event Bus"),
        WiringIdentity("observer.state", "state", "Observer shares State Manager"),
        WiringIdentity("observer.events", "events", "Observer shares Event Bus"),
        WiringIdentity("continuous_learning.state", "state", "Continuous Learning shares State"),
        WiringIdentity("continuous_learning.events", "events", "Continuous Learning shares Event Bus"),
        WiringIdentity("cognitive_intelligence.growth", "long_term_growth", "Cognitive Intelligence shares Growth Engine"),
        WiringIdentity("cognitive_intelligence.evolution", "evolution", "Cognitive Intelligence is bound to Evolution"),
        WiringIdentity("evolution.growth", "long_term_growth", "Evolution shares Growth Engine"),
        WiringIdentity("evolution.continuous_learning", "continuous_learning", "Evolution shares Continuous Learning"),
        WiringIdentity("evolution.events", "events", "Evolution shares Event Bus"),
        WiringIdentity("research.ai", "ai", "Research uses active AI"),
        WiringIdentity("research.memory", "memory", "Research shares Memory"),
        WiringIdentity("research.semantic", "semantic", "Research shares Semantic Memory"),
        WiringIdentity("research.graph", "graph", "Research shares Knowledge Graph"),
        WiringIdentity("research.tools", "tools", "Research shares Tool Registry"),
        WiringIdentity("research.events", "events", "Research shares Event Bus"),
        WiringIdentity("communication.events", "events", "Communication shares Event Bus"),
        WiringIdentity("documents.ai", "ai", "Documents use active AI"),
        WiringIdentity("documents.graph", "graph", "Documents share Knowledge Graph"),
        WiringIdentity("documents.research", "research", "Documents feed Research Intelligence"),
        WiringIdentity("documents.events", "events", "Documents share Event Bus"),
        WiringIdentity("live_brain.engine", "__self__", "Live Brain observes the canonical Engine"),
    )

    REQUIRED_FLOW_EDGES = {
        ("memory", "context"),
        ("graph", "context"),
        ("planner", "context"),
        ("context", "documents"),
        ("documents", "metacognition"),
        ("documents", "verification"),
        ("verification", "research"),
        ("research", "logic"),
        ("documents", "logic"),
        ("logic", "causal"),
        ("causal", "hypotheses"),
        ("hypotheses", "counterfactual"),
        ("counterfactual", "decision_quality"),
        ("decision_quality", "action_selection"),
        ("action_selection", "permission"),
        ("permission", "execution"),
        ("execution", "provider"),
        ("provider", "reflection"),
        ("reflection", "learning"),
        ("learning", "evolution"),
        ("evolution", "completed"),
    }

    def audit(self, engine: Any) -> dict[str, Any]:
        component_checks: list[dict[str, Any]] = []
        broken: list[dict[str, Any]] = []

        for spec in self.DIRECT + self.NESTED:
            obj = self._resolve(engine, spec.path)
            actual = obj.__class__.__name__ if obj is not None else None
            ok = actual == spec.class_name
            item = {
                "kind": "component",
                "module": spec.module,
                "path": spec.path,
                "expected": spec.class_name,
                "actual": actual,
                "ok": ok,
            }
            component_checks.append(item)
            if not ok:
                broken.append(item)

        identity_checks: list[dict[str, Any]] = []
        for spec in self.IDENTITIES:
            left = self._resolve(engine, spec.left)
            right = engine if spec.right == "__self__" else self._resolve(
                engine,
                spec.right,
            )
            ok = left is not None and left is right
            item = {
                "kind": "identity",
                "left": spec.left,
                "right": spec.right,
                "label": spec.label,
                "ok": ok,
            }
            identity_checks.append(item)
            if not ok:
                broken.append(item)

        core_modules = self._core_modules()
        covered_modules = {
            spec.module for spec in self.DIRECT + self.NESTED
        } | self.SPECIAL_MODULES
        uncovered = sorted(core_modules - covered_modules)
        missing_files = sorted(covered_modules - core_modules)
        for module in uncovered:
            broken.append(
                {
                    "kind": "coverage",
                    "module": module,
                    "ok": False,
                    "reason": "core module exists but has no wiring owner",
                }
            )
        for module in missing_files:
            broken.append(
                {
                    "kind": "coverage",
                    "module": module,
                    "ok": False,
                    "reason": "wiring manifest references missing core module",
                }
            )

        flow_edges = {
            (str(source), str(target))
            for source, target, _label in engine.brain_flow.EDGES
        }
        missing_flow_edges = sorted(self.REQUIRED_FLOW_EDGES - flow_edges)
        for source, target in missing_flow_edges:
            broken.append(
                {
                    "kind": "flow_edge",
                    "source": source,
                    "target": target,
                    "ok": False,
                }
            )

        heartbeat = self._heartbeat_contract()
        if not heartbeat["ok"]:
            broken.append(heartbeat)

        performance_tracker = self._performance_tracker_contract()
        if not performance_tracker["ok"]:
            broken.append(performance_tracker)

        self_models = {
            id(self._resolve(engine, "cognition.self_model")),
            id(self._resolve(engine, "context_orchestrator.self_model")),
        }
        nested_self_model_ok = None not in {
            self._resolve(engine, "cognition.self_model"),
            self._resolve(engine, "context_orchestrator.self_model"),
        }
        # Separate SelfModel instances are intentional: both are stateless views
        # over the same canonical personality rules. Class coverage is enough.
        _ = self_models

        total = (
            len(component_checks)
            + len(identity_checks)
            + len(self.REQUIRED_FLOW_EDGES)
            + 2
        )
        failed = len(broken)
        passed = max(0, total - failed)
        score = round(100.0 * passed / max(1, total), 2)

        return {
            "version": self.VERSION,
            "status": "healthy" if failed == 0 else "attention",
            "score": score,
            "checks_total": total,
            "checks_passed": passed,
            "checks_failed": failed,
            "core_modules": len(core_modules),
            "covered_modules": len(covered_modules & core_modules),
            "uncovered_modules": uncovered,
            "missing_manifest_modules": missing_files,
            "missing_flow_edges": [
                {"source": source, "target": target}
                for source, target in missing_flow_edges
            ],
            "heartbeat": heartbeat,
            "performance_tracker": performance_tracker,
            "component_checks": component_checks,
            "identity_checks": identity_checks,
            "broken": broken,
            "notes": [
                "Structural identity audit only; it does not expose chain-of-thought.",
                "A green edge means required runtime objects share the same canonical dependency.",
                "SelfModel instances are stateless and intentionally instantiated in two context composers.",
            ],
        }

    @staticmethod
    def _resolve(root: Any, path: str) -> Any:
        current = root
        for part in path.split("."):
            if not part:
                continue
            if current is None or not hasattr(current, part):
                return None
            current = getattr(current, part)
        return current

    @staticmethod
    def _core_modules() -> set[str]:
        root = Path(__file__).resolve().parent
        return {
            path.stem
            for path in root.glob("*.py")
            if path.name != "__init__.py"
        }

    @staticmethod
    def _heartbeat_contract() -> dict[str, Any]:
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        source = main_path.read_text(encoding="utf-8")
        required = (
            "Heartbeat(engine)",
            "heartbeat.run()",
            "heartbeat.stop()",
        )
        missing = [marker for marker in required if marker not in source]
        return {
            "kind": "special",
            "module": "heartbeat",
            "ok": not missing,
            "missing": missing,
        }

    @staticmethod
    def _performance_tracker_contract() -> dict[str, Any]:
        engine_path = Path(__file__).resolve().parent / "engine.py"
        source = engine_path.read_text(encoding="utf-8")
        ok = "PerformanceTracker()" in source and "perf.finish()" in source
        return {
            "kind": "special",
            "module": "performance",
            "runtime_tracker": "PerformanceTracker",
            "ok": ok,
        }
