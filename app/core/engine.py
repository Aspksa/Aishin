from __future__ import annotations

from pathlib import Path

from ..ai import AIManager
from ..db import add_message, recent_messages
from ..personality import personality
from .cognition import Cognition
from .context_orchestrator import ContextOrchestrator
from .causal import CausalReasoning
from .consolidation import MemoryConsolidator
from .events import EventBus
from .graph import KnowledgeGraph
from .graph_builder import GraphBuilder
from .memory import MemorySystem
from .logic import LogicEngine
from .metacognition import Metacognition
from .observer import Observer
from .permissions import PermissionGate
from .planner import Planner
from .planner_builder import PlannerBuilder
from .proactive import ProactiveDecisionLoop
from .personal import PersonalAishin
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
        )
        self.observer = Observer(self.state, self.events)
        self.consolidator = MemoryConsolidator(
            ai=self.ai,
            memory=self.memory,
            personal=self.personal,
            events=self.events,
        )
        self.last_cognitive_context: dict = {
            "scope": "personal",
            "query": "",
            "semantic_used": False,
            "memories": [],
        }

    def startup(self) -> None:
        self.permissions.bootstrap()
        self.graph.seed_personal_foundation()
        state = self.state.load()
        state.status = "awake"
        state.activity = "startup"
        state.focus = "system"
        self.state.save(state)
        self.events.emit(
            "aishin.started",
            scope=state.current_scope,
            payload={"status": state.status, "ai": self.ai.health()},
            importance=0.6,
        )

    def snapshot(self) -> dict:
        state = self.state.load()
        personal = self.personal.context(scope=state.current_scope)
        return {
            "identity": personality.public_summary(),
            "state": state.to_dict(),
            "ai": self.ai.health(),
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
            "observations": [o.__dict__ for o in self.observer.inspect()],
            "recent_events": self.events.recent(limit=10),
            "recent_memories": self.memory.recent(
                scope=state.current_scope,
                limit=8,
            ),
            "working_memory": (
                self.last_cognitive_context
                if self.last_cognitive_context.get("scope") == state.current_scope
                else {
                    "scope": state.current_scope,
                    "query": "",
                    "semantic_used": False,
                    "memories": [],
                }
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
        cleaned = message.strip()
        intent = self.cognition.classify(cleaned)

        state = self.state.interaction(intent)
        state.current_scope = scope
        self.state.save(state)

        history = recent_messages(limit=12, scope=scope)

        self.events.emit(
            "input.received",
            scope=scope,
            payload={"intent": intent, "text_preview": cleaned[:240]},
            importance=0.4,
        )

        add_message("user", cleaned, scope=scope)

        consolidation = self.consolidator.consolidate_turn(
            cleaned,
            scope=scope,
        )
        graph_update = self.graph_builder.ingest(cleaned, scope=scope)
        planning_update = self.planner_builder.ingest(cleaned, scope=scope)

        context = self.cognition.build_context(cleaned, scope=scope)
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

        self.last_cognitive_context = {
            "scope": scope,
            "query": cleaned[:500],
            "semantic_used": context.semantic_used,
            "memories": final_memories[:10],
            "metacognition": meta.to_dict(),
            "verification": verification_data,
            "logic": logic_trace.to_dict(),
            "context_orchestrator": context_trace.to_dict(),
            "causal": causal_assessment.to_dict(),
        }
        context.system_prompt += "\n\n" + self.logic.prompt_block(logic_trace)
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

        ai_reply = self.ai.chat(
            system=context.system_prompt,
            messages=model_messages,
        )

        if ai_reply.available:
            reply = ai_reply.text
        else:
            reply = self._fallback_response(
                cleaned,
                intent,
                len(context.recalled_memories),
                consolidation.to_dict(),
            )

        add_message("assistant", reply, scope=scope)

        self.events.emit(
            "response.created",
            scope=scope,
            payload={
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
            },
            importance=0.3,
        )

        state = self.state.load()
        state.activity = "idle"
        state.focus = "waiting"
        self.state.save(state)

        return {
            "reply": reply,
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
            "planner_notices": [
                notice.__dict__
                for notice in self.planner.inspect(scope=scope)
            ],
            "phase": "living-core",
            "llm_connected": ai_reply.available,
            "provider": ai_reply.provider,
            "model": ai_reply.model,
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
