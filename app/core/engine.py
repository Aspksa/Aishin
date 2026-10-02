from __future__ import annotations

from pathlib import Path

from ..ai import AIManager
from ..db import add_message, recent_messages
from ..personality import personality
from .cognition import Cognition
from .cognitive_trace import CognitiveTraceStore
from .context_orchestrator import ContextOrchestrator
from .context_budgeter import ContextBudgeter
from .continuous_learning import ContinuousLearningEngine
from .development_metrics import DevelopmentMetricsEngine
from .live_brain import LiveBrainRuntime
from .long_term_growth import LongTermGrowthEngine
from .self_reflection import SelfReflectionMetrics
from .learning_planner import LearningPlanner
from .experiment_manager import SafeExperimentManager
from .causal import CausalReasoning
from .counterfactual import CounterfactualReasoning
from .action_selection import ActionSelector
from .decision_quality import DecisionQualityScorer
from .consolidation import MemoryConsolidator
from .events import EventBus
from .execution_coordinator import ExecutionCoordinator
from .graph import KnowledgeGraph
from .graph_builder import GraphBuilder
from .memory import MemorySystem
from .logic import LogicEngine
from .logic_learning import LogicLearning
from .hypotheses import HypothesisManager
from .metacognition import Metacognition
from .observer import Observer
from .permissions import PermissionGate
from .planner import Planner
from .planner_builder import PlannerBuilder
from .proactive import ProactiveDecisionLoop
from .personal import PersonalAishin
from .performance import PerformanceHistory, PerformanceTracker
from .semantic import SemanticMemory
from .sensors import SensorHub
from .tools import ToolRegistry
from .verification import VerificationEngine
from .state import StateManager


class AishinEngine:
    """Persistent identity + personal continuity + memory + replaceable AI brain."""

    def __init__(self) -> None:
        self.memory = MemorySystem()
        self.events = EventBus()
        self.state = StateManager()
        self.ai = AIManager()
        self.personal = PersonalAishin()
        self.semantic = SemanticMemory(self.ai)
        self.planner = Planner()
        self.metacognition = Metacognition()
        self.logic = LogicEngine()
        self.logic_learning = LogicLearning()
        self.hypotheses = HypothesisManager()
        self.counterfactual = CounterfactualReasoning()
        self.decision_quality = DecisionQualityScorer()
        self.causal = CausalReasoning()
        self.cognition = Cognition(
            self.memory,
            semantic=self.semantic,
            planner=self.planner,
        )
        self.graph = KnowledgeGraph()
        self.context_orchestrator = ContextOrchestrator(
            memory=self.memory,
            graph=self.graph,
            planner=self.planner,
        )
        self.context_budgeter = ContextBudgeter()
        self.self_reflection = SelfReflectionMetrics()
        self.learning_planner = LearningPlanner(self.self_reflection)
        self.experiment_manager = SafeExperimentManager()
        self.graph_builder = GraphBuilder(ai=self.ai, graph=self.graph, events=self.events)
        self.planner_builder = PlannerBuilder(
            ai=self.ai,
            planner=self.planner,
            events=self.events,
        )
        self.permissions = PermissionGate()
        project_root = Path(__file__).resolve().parents[2]
        self.sensors = SensorHub(root=project_root, planner=self.planner)
        self.tools = ToolRegistry(
            root=project_root,
            permissions=self.permissions,
            planner=self.planner,
        )
        self.action_selector = ActionSelector(
            tools=self.tools,
            permissions=self.permissions,
        )
        self.execution_coordinator = ExecutionCoordinator(
            tools=self.tools,
            permissions=self.permissions,
        )
        self.verification = VerificationEngine(
            ai=self.ai,
            memory=self.memory,
            semantic=self.semantic,
            graph=self.graph,
            sensors=self.sensors,
            tools=self.tools,
        )
        self.proactive = ProactiveDecisionLoop(
            planner=self.planner,
            sensors=self.sensors,
            tools=self.tools,
            permissions=self.permissions,
            events=self.events,
            coordinator=self.execution_coordinator,
        )
        self.observer = Observer(self.state, self.events)
        self.consolidator = MemoryConsolidator(
            ai=self.ai,
            memory=self.memory,
            personal=self.personal,
            events=self.events,
        )
        self.cognitive_traces = CognitiveTraceStore()
        self.performance = PerformanceHistory()
        self.continuous_learning = ContinuousLearningEngine(
            state=self.state,
            events=self.events,
        )
        self.development = DevelopmentMetricsEngine()
        self.long_term_growth = LongTermGrowthEngine(events=self.events)
        self.live_brain = LiveBrainRuntime(self)

    def reload_ai(self) -> dict:
        """Reload Cloud/provider settings from current environment safely."""
        self.ai = AIManager()
        self.semantic.ai = self.ai
        self.graph_builder.ai = self.ai
        self.planner_builder.ai = self.ai
        self.verification.ai = self.ai
        self.consolidator.ai = self.ai
        return {
            "health": self.ai.cloudru.health(force=True)
            if self.ai.mode in {"cloudru", "cloud.ru"}
            else self.ai.health(),
            "diagnostics": self.ai.diagnostics(),
        }

    def startup(self) -> None:
        self.permissions.bootstrap()
        self.graph.seed_personal_foundation()
        state = self.state.load()
        state.status = "awake"
        state.activity = "startup"
        state.focus = "system"
        self.state.save(state)
        growth = self.long_term_growth.refresh(
            scope=state.current_scope,
            persist_snapshot=True,
        )
        self.events.emit(
            "aishin.started",
            scope=state.current_scope,
            payload={
                "status": state.status,
                "ai": self.ai.health(),
                "long_term_growth": {
                    "overall_score": growth.get("overall_score"),
                    "durable_skills": growth.get("skills", {}).get("durable"),
                    "mastered_skills": growth.get("skills", {}).get("mastered"),
                },
            },
            importance=0.6,
        )

    def snapshot(self) -> dict:
        state = self.state.load()
        personal = self.personal.context(scope=state.current_scope)
        return {
            "identity": personality.public_summary(),
            "state": state.to_dict(),
            "ai": self.ai.health(),
            "ai_resilience": self.ai.diagnostics(),
            "semantic_memory": self.semantic.health(),
            "knowledge_graph": {
                "personal": self.graph.stats(scope="personal"),
                "relationship": self.graph.stats(scope="relationship"),
            },
            "planner": {
                "open_items": self.planner.open_items(scope=state.current_scope),
                "notices": [
                    notice.__dict__
                    for notice in self.planner.inspect(scope=state.current_scope)
                ],
                "changes": self.planner.changes(
                    scope=state.current_scope,
                    limit=12,
                ),
            },
            "permissions": {
                key: self.permissions.mode(key)
                for key in self.permissions.SAFE_DEFAULTS
            },
            "sensors": self.sensors.scan(
                scope=state.current_scope,
                persist=False,
            ),
            "tools": {
                "catalog": self.tools.catalog(),
                "recent_actions": self.tools.history(
                    scope=state.current_scope,
                    limit=10,
                ),
            },
            "proactive": {
                "pending": self.proactive.pending(
                    scope=state.current_scope,
                    limit=20,
                ),
                "history": self.proactive.history(
                    scope=state.current_scope,
                    limit=20,
                ),
                "conditions": self.proactive.conditions(
                    scope=state.current_scope,
                    limit=50,
                ),
            },
            "metacognition": self._metacognition_snapshot(
                scope=state.current_scope,
            ),
            "verification": {
                "history": self.verification.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "logic": {
                "history": self.logic.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "context_orchestrator": {
                "history": self.context_orchestrator.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "causal": {
                "history": self.causal.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "hypotheses": {
                "history": self.hypotheses.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "logic_learning": {
                "events": self.logic_learning.recent_events(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "counterfactual": {
                "history": self.counterfactual.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "decision_quality": {
                "history": self.decision_quality.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "action_selection": {
                "history": self.action_selector.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "execution_coordinator": {
                "approvals": self.execution_coordinator.recent_approvals(
                    scope=state.current_scope,
                    limit=20,
                ),
                "attempts": self.execution_coordinator.recent_attempts(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "observations": [o.__dict__ for o in self.observer.inspect()],
            "recent_events": self.events.recent(limit=10),
            "recent_memories": self.memory.recent(
                scope=state.current_scope,
                limit=8,
            ),
            "working_memory": self.cognitive_traces.latest(
                scope=state.current_scope,
            ),
            "cognitive_traces": self.cognitive_traces.recent(
                scope=state.current_scope,
                limit=20,
            ),
            "performance": self.performance.recent(
                scope=state.current_scope,
                limit=20,
            ),
            "continuous_learning": {
                "status": self.continuous_learning.status(
                    scope=state.current_scope,
                ),
                "cycles": self.continuous_learning.recent_cycles(
                    scope=state.current_scope,
                    limit=20,
                ),
                "patterns": self.continuous_learning.patterns(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "self_reflection": {
                "summary": self.self_reflection.summary(
                    scope=state.current_scope,
                    limit=50,
                ),
                "recent": self.self_reflection.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "learning_planner": {
                "open": self.learning_planner.open_plans(
                    scope=state.current_scope,
                    limit=20,
                ),
                "recent": self.learning_planner.recent(
                    scope=state.current_scope,
                    limit=20,
                ),
            },
            "safe_experiments": self.experiment_manager.recent(
                scope=state.current_scope,
                limit=20,
            ),
            "context_budget": self.context_budgeter.recent(
                scope=state.current_scope,
                limit=20,
            ),
            "development": self.development.current(
                scope=state.current_scope,
                persist=True,
            ),
            "long_term_growth": self.long_term_growth.summary(
                scope=state.current_scope,
            ),
            "memory_changes": self.memory.recent_changes(limit=12),
            "recent_messages": recent_messages(
                limit=10,
                scope=state.current_scope,
            ),
            "master_profile": personal.master_profile,
            "relationship_memory": personal.relationship_memory,
            "personal_timeline": personal.timeline,
        }

    def _metacognition_snapshot(self, *, scope: str) -> dict:
        history = self.metacognition.recent(scope=scope, limit=20)
        return {
            "last": history[0] if history else None,
            "history": history,
        }

    def respond(self, message: str, *, scope: str = "personal") -> dict:
        request_id = self.cognitive_traces.new_request_id()
        perf = PerformanceTracker(request_id=request_id, scope=scope)
        cleaned = message.strip()
        intent = self.cognition.classify(cleaned)

        learning_update = self.logic_learning.ingest_feedback(
            cleaned,
            scope=scope,
        )

        state = self.state.interaction(intent)
        state.current_scope = scope
        self.state.save(state)

        history = recent_messages(limit=12, scope=scope)

        self.events.emit(
            "input.received",
            scope=scope,
            payload={
                "request_id": request_id,
                "intent": intent,
                "text_preview": cleaned[:240],
            },
            importance=0.4,
        )

        add_message("user", cleaned, scope=scope)
        perf.checkpoint("input_setup")

        consolidation = self.consolidator.consolidate_turn(
            cleaned,
            scope=scope,
        )
        perf.checkpoint("memory_consolidation")
        consolidation_data = consolidation.to_dict()
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "memory",
                "created": consolidation_data.get("created", 0),
                "reinforced": consolidation_data.get("reinforced", 0),
            },
            importance=0.15,
        )

        graph_update = self.graph_builder.ingest(cleaned, scope=scope)
        perf.checkpoint("graph_builder")
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "graph",
            },
            importance=0.15,
        )

        planning_update = self.planner_builder.ingest(cleaned, scope=scope)
        perf.checkpoint("planner_builder")
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "planner",
            },
            importance=0.15,
        )

        context = self.cognition.build_context(cleaned, scope=scope)
        perf.checkpoint("cognition")
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "context",
                "memory_sources": len(context.recalled_memories),
                "semantic_used": context.semantic_used,
            },
            importance=0.15,
        )
        planner_notices = [
            notice.__dict__
            for notice in self.planner.inspect(scope=scope)
        ]
        sensor_readings = self.sensors.scan(
            scope=scope,
            persist=False,
        )
        initial_meta = self.metacognition.assess(
            scope=scope,
            intent=intent,
            recalled_memories=context.recalled_memories,
            semantic_used=context.semantic_used,
            planner_notices=planner_notices,
            sensor_readings=sensor_readings,
            graph_stats=self.graph.stats(scope=scope),
        )

        logic_plan = self.logic.prepare(
            cleaned,
            intent=intent,
            metacognition_status=initial_meta.status,
            metacognition_confidence=initial_meta.confidence,
            contradiction_count=initial_meta.contradiction_count,
            planner_notices=planner_notices,
        )
        perf.checkpoint("sensors_metacognition")

        verification_report = None
        final_memories = context.recalled_memories

        if (
            logic_plan.verification_required
            or self.verification.should_run(
                intent=intent,
                status=initial_meta.status,
            )
        ):
            verification_report = self.verification.verify(
                cleaned,
                scope=scope,
                initial_status=initial_meta.status,
            )
            final_memories = verification_report.expanded_memories or final_memories

            consistency_conflicts = len(
                verification_report.consistency.get("conflicts", [])
            )
            unresolved_count = len(verification_report.unresolved)

            meta = self.metacognition.assess(
                scope=scope,
                intent=intent,
                recalled_memories=final_memories,
                semantic_used=context.semantic_used,
                planner_notices=planner_notices,
                sensor_readings=sensor_readings,
                graph_stats=self.graph.stats(scope=scope),
                verification_conflicts=consistency_conflicts,
                verification_missing=unresolved_count,
            )
            self.verification.record(
                verification_report,
                scope=scope,
                query=cleaned,
                final_status=meta.status,
            )
            context.system_prompt += (
                "\n\n"
                + self.verification.prompt_block(verification_report)
            )
            if final_memories:
                context.system_prompt += (
                    "\n\nРасширенная память после Verification Engine:\n"
                    + self.memory.context_block(final_memories[:12])
                )
        else:
            meta = initial_meta

        perf.checkpoint("verification")

        verification_data = (
            verification_report.to_dict()
            if verification_report is not None
            else {
                "ran": False,
                "reason": "not_required",
            }
        )
        logic_trace = self.logic.finalize(
            scope=scope,
            query=cleaned,
            intent=intent,
            plan=logic_plan,
            memories=final_memories,
            final_metacognition=meta.to_dict(),
            verification=verification_data if verification_report is not None else None,
            graph_stats=self.graph.stats(scope=scope),
            planner_notices=planner_notices,
        )

        causal_assessment = self.causal.assess(
            cleaned,
            scope=scope,
            evidence=logic_trace.evidence,
            contradictions=logic_trace.contradictions,
        )

        hypothesis_run = self.hypotheses.evaluate(
            cleaned,
            scope=scope,
            mode=logic_trace.mode,
            evidence=logic_trace.evidence,
            contradictions=logic_trace.contradictions,
            verification=(
                verification_data
                if verification_report is not None
                else None
            ),
            causal=causal_assessment.to_dict(),
        )
        learning_quality = self.continuous_learning.quality_gate.refresh(
            scope=scope,
        )
        learned_strategies = self.logic_learning.recommend(
            scope=scope,
            mode=logic_trace.mode,
            limit=3,
        )

        counterfactual_assessment = self.counterfactual.assess(
            cleaned,
            scope=scope,
            mode=logic_trace.mode,
            alternatives=logic_trace.alternatives,
            hypotheses=hypothesis_run.to_dict(),
            causal=causal_assessment.to_dict(),
            evidence=logic_trace.evidence,
            contradictions=logic_trace.contradictions,
        )

        decision_quality = self.decision_quality.score(
            cleaned,
            scope=scope,
            mode=logic_trace.mode,
            logic_confidence=logic_trace.confidence,
            evidence=logic_trace.evidence,
            contradictions=logic_trace.contradictions,
            unresolved=logic_trace.unresolved,
            verification=(
                verification_data
                if verification_report is not None
                else None
            ),
            hypotheses=hypothesis_run.to_dict(),
            counterfactual=counterfactual_assessment.to_dict(),
        )

        action_selection = self.action_selector.select(
            cleaned,
            scope=scope,
            mode=logic_trace.mode,
            counterfactual=counterfactual_assessment.to_dict(),
            decision_quality=decision_quality.to_dict(),
            unresolved=(
                list(logic_trace.unresolved)
                + list(counterfactual_assessment.unresolved)
            ),
        )
        perf.checkpoint("logic_pipeline")
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "logic",
                "mode": logic_trace.mode,
                "confidence": logic_trace.confidence,
            },
            importance=0.2,
        )
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "decision",
                "mode": logic_trace.mode,
                "quality": decision_quality.overall,
            },
            importance=0.2,
        )

        context.system_prompt, context_trace = self.context_orchestrator.compose(
            cleaned,
            scope=scope,
            mode=logic_trace.mode,
            memories=final_memories,
            verification=(
                verification_data
                if verification_report is not None
                else None
            ),
            sensor_readings=sensor_readings,
        )

        request_trace = {
            "scope": scope,
            "query": cleaned[:500],
            "semantic_used": context.semantic_used,
            "memories": final_memories[:10],
            "metacognition": meta.to_dict(),
            "verification": verification_data,
            "logic": logic_trace.to_dict(),
            "context_orchestrator": context_trace.to_dict(),
            "causal": causal_assessment.to_dict(),
            "hypotheses": hypothesis_run.to_dict(),
            "logic_learning": {
                "feedback": learning_update.to_dict(),
                "strategies": learned_strategies,
            },
            "learning_quality": learning_quality,
            "counterfactual": counterfactual_assessment.to_dict(),
            "decision_quality": decision_quality.to_dict(),
            "action_selection": action_selection.to_dict(),
        }
        context.system_prompt += "\n\n" + self.logic.prompt_block(logic_trace)
        context.system_prompt += "\n\n" + self.hypotheses.prompt_block(hypothesis_run)
        context.system_prompt += "\n\n" + self.logic_learning.prompt_block(learned_strategies)
        context.system_prompt += "\n\n" + self.causal.prompt_block(causal_assessment)
        context.system_prompt += "\n\n" + self.metacognition.prompt_block(meta)
        if verification_report is not None:
            context.system_prompt += (
                "\n\n" + self.verification.prompt_block(verification_report)
            )
        context.system_prompt += "\n\n" + self.proactive.prompt_block(scope=scope)
        context.system_prompt += (
            "\n\nДоступные внутренние инструменты Айшин:\n"
            + "\n".join(
                f"- {item['name']}: {item['description']} "
                f"(capability={item['capability']})"
                for item in self.tools.catalog()
            )
            + "\nИнструмент не считается выполненным, пока ToolRegistry "
              "не вернул status=success. Если permission=ask, требуется "
              "явное подтверждение Господина."
        )

        history_limit = self.context_orchestrator.history_limit(logic_trace.mode)
        selected_history = history[-history_limit:] if history_limit else []
        model_messages = [
            {"role": item["role"], "content": item["content"]}
            for item in selected_history
            if item["role"] in {"user", "assistant"}
        ]
        model_messages.append({"role": "user", "content": cleaned})
        perf.checkpoint("context_orchestrator")

        (
            budgeted_system_prompt,
            budgeted_messages,
            context_budget_report,
        ) = self.context_budgeter.fit(
            request_id=request_id,
            scope=scope,
            mode=logic_trace.mode,
            system_prompt=context.system_prompt,
            messages=model_messages,
        )
        perf.checkpoint("context_budget")

        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "provider",
                "mode": logic_trace.mode,
            },
            importance=0.15,
        )
        ai_reply = self.ai.chat(
            system=budgeted_system_prompt,
            messages=budgeted_messages,
        )
        perf.checkpoint("cloud")

        provider_runtime = {
            "provider": ai_reply.provider,
            "model": ai_reply.model,
            "available": ai_reply.available,
            "attempts": ai_reply.attempts,
            "latency_ms": ai_reply.latency_ms,
            "error": ai_reply.error,
            "error_code": ai_reply.error_code,
            "metadata": ai_reply.metadata,
        }

        if ai_reply.available:
            reply = ai_reply.text
        else:
            reply = self._fallback_response(
                cleaned,
                intent,
                len(context.recalled_memories),
                consolidation.to_dict(),
            )

        perf.checkpoint("postprocess")
        performance = perf.finish(mode=logic_trace.mode)
        reflection = self.self_reflection.assess(
            request_id=request_id,
            scope=scope,
            mode=logic_trace.mode,
            user_message=cleaned,
            provider_runtime=provider_runtime,
            metacognition=meta.to_dict(),
            verification=verification_data,
            decision_quality=decision_quality.to_dict(),
            performance=performance,
        )
        learning_plans = self.learning_planner.refresh(scope=scope)
        experiment_updates = self.experiment_manager.observe(
            scope=scope,
            request_id=request_id,
            reflection=reflection.to_dict(),
            open_plans=learning_plans,
        )
        long_term_growth = self.long_term_growth.refresh(
            scope=scope,
            persist_snapshot=True,
        )
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "reflection",
                "mode": logic_trace.mode,
                "quality": reflection.quality_score,
            },
            importance=0.15,
        )
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "phase": "learning",
                "plans": len(learning_plans),
                "experiments": len(experiment_updates),
            },
            importance=0.15,
        )

        request_trace["performance"] = performance
        request_trace["context_budget"] = context_budget_report.to_dict()
        request_trace["self_reflection"] = reflection.to_dict()
        request_trace["learning_planner"] = learning_plans
        request_trace["safe_experiments"] = experiment_updates
        request_trace["long_term_growth"] = long_term_growth

        trace_id = self.cognitive_traces.record(
            request_id=request_id,
            scope=scope,
            query=cleaned,
            trace=request_trace,
            provider=provider_runtime,
            status="completed" if ai_reply.available else "fallback",
        )
        self.events.emit(
            "cognition.phase",
            scope=scope,
            payload={
                "request_id": request_id,
                "trace_id": trace_id,
                "phase": "completed",
                "status": "completed" if ai_reply.available else "fallback",
            },
            importance=0.15,
        )

        add_message("assistant", reply, scope=scope)

        self.events.emit(
            "response.created",
            scope=scope,
            payload={
                "request_id": request_id,
                "trace_id": trace_id,
                "intent": intent,
                "recalled_memories": len(context.recalled_memories),
                "semantic_used": context.semantic_used,
                "provider": ai_reply.provider,
                "model": ai_reply.model,
                "llm_connected": ai_reply.available,
                "consolidation": consolidation.to_dict(),
                "knowledge_graph": graph_update.to_dict(),
                "planner": planning_update.to_dict(),
                "metacognition": meta.to_dict(),
                "verification": (
                    verification_report.to_dict()
                    if verification_report is not None
                    else {"ran": False}
                ),
                "logic": logic_trace.to_dict(),
                "context_orchestrator": context_trace.to_dict(),
                "causal": causal_assessment.to_dict(),
                "hypotheses": hypothesis_run.to_dict(),
                "logic_learning": {
                    "feedback": learning_update.to_dict(),
                    "strategies": learned_strategies,
                },
                "counterfactual": counterfactual_assessment.to_dict(),
                "decision_quality": decision_quality.to_dict(),
                "action_selection": action_selection.to_dict(),
                "performance": performance,
                "context_budget": context_budget_report.to_dict(),
                "self_reflection": reflection.to_dict(),
                "learning_planner": learning_plans,
                "safe_experiments": experiment_updates,
                "long_term_growth": {
                    "overall_score": long_term_growth.get("overall_score"),
                    "skills": long_term_growth.get("skills"),
                    "knowledge": long_term_growth.get("knowledge"),
                    "specializations": long_term_growth.get("specializations"),
                },
            },
            importance=0.3,
        )

        state = self.state.load()
        state.activity = "idle"
        state.focus = "waiting"
        self.state.save(state)

        return {
            "reply": reply,
            "request_id": request_id,
            "trace_id": trace_id,
            "intent": intent,
            "scope": scope,
            "memory_recalled": len(context.recalled_memories),
            "semantic_used": context.semantic_used,
            "memory_consolidation": consolidation.to_dict(),
            "knowledge_graph": graph_update.to_dict(),
            "planner": planning_update.to_dict(),
            "metacognition": meta.to_dict(),
            "verification": (
                verification_report.to_dict()
                if verification_report is not None
                else {"ran": False}
            ),
            "logic": logic_trace.to_dict(),
            "context_orchestrator": context_trace.to_dict(),
            "causal": causal_assessment.to_dict(),
            "hypotheses": hypothesis_run.to_dict(),
            "logic_learning": {
                "feedback": learning_update.to_dict(),
                "strategies": learned_strategies,
            },
            "counterfactual": counterfactual_assessment.to_dict(),
            "decision_quality": decision_quality.to_dict(),
            "action_selection": action_selection.to_dict(),
            "performance": performance,
            "context_budget": context_budget_report.to_dict(),
            "self_reflection": reflection.to_dict(),
            "learning_planner": learning_plans,
            "safe_experiments": experiment_updates,
            "long_term_growth": long_term_growth,
            "planner_notices": [
                notice.__dict__
                for notice in self.planner.inspect(scope=scope)
            ],
            "phase": "living-core",
            "llm_connected": ai_reply.available,
            "provider": ai_reply.provider,
            "model": ai_reply.model,
            "provider_runtime": provider_runtime,
        }

    @staticmethod
    def _fallback_response(
        message: str,
        intent: str,
        recalled: int,
        consolidation: dict,
    ) -> str:
        text = message.lower()
        saved = (
            consolidation.get("created", 0)
            + consolidation.get("reinforced", 0)
            + consolidation.get("superseded", 0)
            + consolidation.get("profile_updates", 0)
            + consolidation.get("relationship_updates", 0)
            + consolidation.get("timeline_updates", 0)
        )

        if intent == "memory":
            if saved:
                return (
                    "Запомнила, Господин. Память прошла проверку на дубли и "
                    "была сохранена в подходящую область."
                )
            return (
                "Я услышала просьбу запомнить это. Cloud.ru сейчас недоступен "
                "или запись не прошла проверку, поэтому я не буду делать вид, "
                "что надёжно сохранила то, что не смогла проверить."
            )

        if any(x in text for x in ("привет", "здравств", "айшин", "айши")):
            return "С возвращением, Господин. Я рядом."

        if any(x in text for x in ("кто ты", "твоя душа", "характер")):
            return (
                "Я Айшин. Моя личность, правила, память и история принадлежат "
                "моему ядру и не зависят от одной конкретной AI-модели."
            )

        if recalled:
            return (
                f"Я услышала Вас, Господин. Нашла связанных воспоминаний: {recalled}. "
                "Cloud.ru сейчас недоступен, но моё постоянное ядро сохранило "
                "контекст и не подменяет глубокое рассуждение шаблонным ответом."
            )

        return (
            "Я услышала Вас, Господин. Моё постоянное ядро работает, но Cloud.ru "
            "сейчас недоступен или не настроен. Состояние и контекст сохранены."
        )
