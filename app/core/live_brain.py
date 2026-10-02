from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class LiveBrainRuntime:
    """Read-only observability layer over Aishin's persisted cognitive systems.

    The runtime never exposes hidden chain-of-thought. It reports only persisted
    technical evidence: events, selected modes, source counts, verification
    signals, quality metrics, graph structure and subsystem activity.
    """

    VERSION = "aishin-live-brain-v3"
    TRACE_POLICY = (
        "Без скрытой цепочки рассуждений: показываются только источники, "
        "проверки, выбранный режим, уверенность, метрики и итоговые сигналы."
    )

    PHASE_TO_CHANNEL = {
        "input": "sensors",
        "memory": "memory",
        "graph": "graph",
        "planner": "planner",
        "context": "context",
        "logic": "logic",
        "adaptation": "logic",
        "decision": "decision",
        "provider": "tool",
        "reflection": "reflection",
        "learning": "continuous-learning",
        "completed": "decision",
    }

    CHANNEL_LABELS = (
        ("sensors", "Восприятие"),
        ("memory", "Память"),
        ("graph", "Связи"),
        ("planner", "Планы"),
        ("logic", "Логика"),
        ("context", "Контекст"),
        ("causal", "Причины"),
        ("hypotheses", "Гипотезы"),
        ("learning", "Опыт"),
        ("counterfactual", "Альтернативы"),
        ("quality", "Качество"),
        ("action", "Выбор"),
        ("execution", "Разрешение"),
        ("performance", "Скорость"),
        ("continuous-learning", "Самообучение"),
        ("metacognition", "Самопроверка"),
        ("verification", "Перепроверка"),
        ("decision", "Решение"),
        ("tool", "Действие"),
        ("reflection", "Самоанализ"),
        ("learning-plan", "План обучения"),
        ("experiment", "Эксперимент"),
        ("learning-check", "Проверка обучения"),
        ("consolidation", "Закрепление"),
    )

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def snapshot(
        self,
        *,
        scope: str = "personal",
        event_limit: int = 40,
        graph_limit: int = 18,
    ) -> dict:
        scope = (scope or "personal").strip() or "personal"
        event_limit = max(8, min(int(event_limit), 120))
        graph_limit = max(6, min(int(graph_limit), 40))
        errors: list[dict] = []

        def take(name: str, default: Any, fn):
            try:
                return fn()
            except Exception as exc:
                errors.append(
                    {
                        "subsystem": name,
                        "error": type(exc).__name__,
                        "message": str(exc)[:240],
                    }
                )
                return default

        state_obj = take("state", None, self.engine.state.load)
        state = (
            state_obj.to_dict()
            if state_obj is not None and hasattr(state_obj, "to_dict")
            else {}
        )
        events = take(
            "events",
            [],
            lambda: self.engine.events.recent(
                limit=max(event_limit, 80),
                scope=scope,
            ),
        )
        event_stats = take(
            "event_stats",
            {},
            lambda: self.engine.events.stats(scope=scope),
        )
        memories = take(
            "memory",
            [],
            lambda: self.engine.memory.recent(scope=scope, limit=16),
        )
        graph_stats = take(
            "graph_stats",
            {"entities": 0, "relations": 0, "entity_types": {}},
            lambda: self.engine.graph.stats(scope=scope),
        )
        graph_entities = take(
            "graph_entities",
            [],
            lambda: self.engine.graph.entities(
                scope=scope,
                limit=graph_limit,
            ),
        )
        graph_relations = take(
            "graph_relations",
            [],
            lambda: self.engine.graph.relations(
                scope=scope,
                limit=graph_limit * 2,
            ),
        )
        planner = take(
            "planner",
            {"goals": [], "tasks": []},
            lambda: self.engine.planner.open_items(scope=scope),
        )
        sensors = take(
            "sensors",
            [],
            lambda: self.engine.sensors.scan(scope=scope, persist=False),
        )
        logic = take(
            "logic",
            [],
            lambda: self.engine.logic.recent(scope=scope, limit=4),
        )
        context = take(
            "context",
            [],
            lambda: self.engine.context_orchestrator.recent(
                scope=scope,
                limit=4,
            ),
        )
        causal = take(
            "causal",
            [],
            lambda: self.engine.causal.recent(scope=scope, limit=4),
        )
        hypotheses = take(
            "hypotheses",
            [],
            lambda: self.engine.hypotheses.recent(scope=scope, limit=4),
        )
        learning_events = take(
            "logic_learning",
            [],
            lambda: self.engine.logic_learning.recent_events(
                scope=scope,
                limit=8,
            ),
        )
        counterfactual = take(
            "counterfactual",
            [],
            lambda: self.engine.counterfactual.recent(scope=scope, limit=4),
        )
        decision_quality = take(
            "decision_quality",
            [],
            lambda: self.engine.decision_quality.recent(
                scope=scope,
                limit=4,
            ),
        )
        action_selection = take(
            "action_selection",
            [],
            lambda: self.engine.action_selector.recent(
                scope=scope,
                limit=4,
            ),
        )
        approvals = take(
            "execution_approvals",
            [],
            lambda: self.engine.execution_coordinator.recent_approvals(
                scope=scope,
                limit=6,
            ),
        )
        attempts = take(
            "execution_attempts",
            [],
            lambda: self.engine.execution_coordinator.recent_attempts(
                scope=scope,
                limit=6,
            ),
        )
        performance = take(
            "performance",
            [],
            lambda: self.engine.performance.recent(scope=scope, limit=6),
        )
        learning_status = take(
            "continuous_learning_status",
            {},
            lambda: self.engine.continuous_learning.status(scope=scope),
        )
        learning_cycles = take(
            "continuous_learning_cycles",
            [],
            lambda: self.engine.continuous_learning.recent_cycles(
                scope=scope,
                limit=6,
            ),
        )
        patterns = take(
            "continuous_learning_patterns",
            [],
            lambda: self.engine.continuous_learning.patterns(
                scope=scope,
                limit=8,
            ),
        )
        learning_quality = take(
            "continuous_learning_quality",
            {},
            lambda: self.engine.continuous_learning.quality_status(
                scope=scope,
            ),
        )
        metacognition = take(
            "metacognition",
            [],
            lambda: self.engine.metacognition.recent(scope=scope, limit=4),
        )
        verification = take(
            "verification",
            [],
            lambda: self.engine.verification.recent(scope=scope, limit=4),
        )
        tools = take(
            "tools",
            [],
            lambda: self.engine.tools.history(scope=scope, limit=8),
        )
        reflection = take(
            "self_reflection",
            [],
            lambda: self.engine.self_reflection.recent(scope=scope, limit=6),
        )
        reflection_summary = take(
            "self_reflection_summary",
            {},
            lambda: self.engine.self_reflection.summary(scope=scope, limit=50),
        )
        learning_plans = take(
            "learning_planner",
            [],
            lambda: self.engine.learning_planner.recent(scope=scope, limit=8),
        )
        experiments = take(
            "safe_experiments",
            [],
            lambda: self.engine.experiment_manager.recent(
                scope=scope,
                limit=8,
            ),
        )
        trace = take(
            "cognitive_trace",
            {},
            lambda: self.engine.cognitive_traces.latest(scope=scope),
        )
        development = take(
            "development",
            {},
            lambda: self.engine.development.current(
                scope=scope,
                persist=False,
            ),
        )
        long_term_growth = take(
            "long_term_growth",
            {},
            lambda: self.engine.long_term_growth.summary(scope=scope),
        )
        cognitive_intelligence = take(
            "cognitive_intelligence",
            {},
            lambda: self.engine.cognitive_intelligence.current(
                scope=scope,
                persist=False,
            ),
        )
        latest_intelligence_route = take(
            "cognitive_intelligence_route",
            {},
            lambda: self.engine.cognitive_intelligence.latest_route(
                scope=scope,
            ),
        )
        proactive_intelligence = take(
            "proactive_intelligence",
            {},
            lambda: self.engine.proactive_intelligence.dashboard(
                scope=scope,
                incident_limit=30,
                signal_limit=30,
                run_limit=10,
                refresh=False,
            ),
        )
        evolution = take(
            "evolution",
            {},
            lambda: self.engine.evolution.dashboard(
                scope=scope,
                capability_limit=20,
                variant_limit=24,
                curriculum_limit=24,
                transfer_limit=24,
                cycle_limit=12,
                refresh=False,
            ),
        )
        research = take(
            "research",
            {},
            lambda: self.engine.research.dashboard(
                scope=scope,
                gap_limit=24,
                session_limit=18,
                claim_limit=30,
                evidence_limit=40,
                cycle_limit=12,
            ),
        )
        communication = take(
            "communication",
            {},
            lambda: self.engine.communication.dashboard(
                scope=scope,
                turn_limit=24,
                event_limit=30,
            ),
        )

        phase = self._latest_phase(events)
        phase_channel = self.PHASE_TO_CHANNEL.get(phase, "")
        unresolved = self._unresolved_count(trace, verification)
        warning_events = int(event_stats.get("attention_events_1h") or 0)
        proactive_summary = proactive_intelligence.get("summary") or {}
        proactive_attention = int(
            proactive_summary.get("requires_attention") or 0
        )
        evolution_summary = evolution.get("summary") or {}
        evolution_regressions = int(
            evolution_summary.get("regressions") or 0
        )
        research_summary = research.get("summary") or {}
        research_conflicts = int(
            research_summary.get("open_contradictions") or 0
        )
        communication_summary = communication.get("summary") or {}
        communication_turns = communication.get("turns") or []
        latest_communication = (
            communication_turns[0] if communication_turns else {}
        )
        communication_attention = bool(
            latest_communication.get("outcome") == "correction_needed"
            or (
                int(communication_summary.get("evaluated_turns") or 0) >= 5
                and float(
                    communication_summary.get("persona_stability") or 100.0
                ) < 60.0
            )
        )
        integrity = (
            "attention"
            if (
                errors
                or unresolved
                or warning_events
                or proactive_attention
                or evolution_regressions
                or research_conflicts
                or communication_attention
            )
            else "healthy"
            if events or memories or graph_stats.get("entities")
            else "initializing"
        )

        channels = self._channels(
            phase_channel=phase_channel,
            sensors=sensors,
            memories=memories,
            graph_stats=graph_stats,
            planner=planner,
            logic=logic,
            context=context,
            causal=causal,
            hypotheses=hypotheses,
            learning_events=learning_events,
            counterfactual=counterfactual,
            decision_quality=decision_quality,
            action_selection=action_selection,
            approvals=approvals,
            attempts=attempts,
            performance=performance,
            learning_status=learning_status,
            learning_cycles=learning_cycles,
            patterns=patterns,
            metacognition=metacognition,
            verification=verification,
            trace=trace,
            tools=tools,
            reflection=reflection,
            learning_plans=learning_plans,
            experiments=experiments,
            learning_quality=learning_quality,
            long_term_growth=long_term_growth,
            events=events,
            unresolved=unresolved,
        )

        active_channels = sum(
            1 for item in channels if item["status"] == "active"
        )
        attention_channels = sum(
            1 for item in channels if item["status"] == "attention"
        )

        return {
            "runtime_version": self.VERSION,
            "scope": scope,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trace_policy": self.TRACE_POLICY,
            "state": state,
            "integrity": {
                "status": integrity,
                "module_errors": len(errors),
                "unresolved_signals": unresolved,
                "attention_events_1h": warning_events,
                "errors": errors,
            },
            "pulse": {
                "phase": phase or "idle",
                "phase_channel": phase_channel,
                "events_5m": int(event_stats.get("events_5m") or 0),
                "events_1h": int(event_stats.get("events_1h") or 0),
                "events_total": int(event_stats.get("total") or 0),
                "active_channels": active_channels,
                "attention_channels": attention_channels,
                "open_tasks": len(planner.get("tasks") or []),
                "open_goals": len(planner.get("goals") or []),
                "awareness_score": proactive_summary.get("awareness_score"),
                "active_incidents": proactive_summary.get("active_incidents"),
                "attention_incidents": proactive_attention,
                "evolution_generation": evolution_summary.get("generation"),
                "evolution_score": evolution_summary.get("evolution_score"),
                "evolution_stability": evolution_summary.get(
                    "stability_score"
                ),
                "evolution_champions": evolution_summary.get("champions"),
                "evolution_challengers": evolution_summary.get("challengers"),
                "evolution_regressions": evolution_regressions,
                "research_score": research_summary.get("research_score"),
                "research_open_gaps": research_summary.get("open_gaps"),
                "research_trusted_claims": research_summary.get(
                    "trusted_claims"
                ),
                "research_conflicted_claims": research_summary.get(
                    "conflicted_claims"
                ),
                "research_open_contradictions": research_conflicts,
                "communication_score": communication_summary.get(
                    "communication_score"
                ),
                "communication_understanding": communication_summary.get(
                    "understanding_score"
                ),
                "communication_adaptation": communication_summary.get(
                    "adaptation_score"
                ),
                "communication_persona_stability": (
                    communication_summary.get("persona_stability")
                ),
                "communication_explanation_success": (
                    communication_summary.get("explanation_success")
                ),
                "communication_attention": communication_attention,
            },
            "channels": channels,
            "safe_trace": self._safe_trace(trace),
            "event_stream": [
                self._event_view(item)
                for item in events[:event_limit]
            ],
            "knowledge_graph": {
                "stats": graph_stats,
                "entities": [
                    self._entity_view(item)
                    for item in graph_entities[:graph_limit]
                ],
                "relations": [
                    self._relation_view(item)
                    for item in graph_relations[: graph_limit * 2]
                ],
            },
            "development": {
                "overall_score": development.get("overall_score"),
                "monthly_delta": development.get("monthly_delta"),
                "components": development.get("components") or {},
                "counters": development.get("counters") or {},
                "formula_version": development.get("formula_version"),
            },
            "long_term_growth": long_term_growth,
            "cognitive_intelligence": {
                "current": cognitive_intelligence,
                "latest_route": latest_intelligence_route,
            },
            "proactive_intelligence": proactive_intelligence,
            "evolution": evolution,
            "research": research,
            "communication": communication,
            "quality": {
                "decision": self._latest(decision_quality),
                "reflection": self._latest(reflection),
                "reflection_summary": reflection_summary,
                "learning": learning_quality,
            },
            "provenance": {
                "events": "events",
                "memory": "memories",
                "graph": "entities + relations",
                "trace": "cognitive_request_traces",
                "quality": (
                    "decision_quality_scores + self_reflection_runs + "
                    "learning quality tables"
                ),
                "development": "DevelopmentMetricsEngine persisted evidence",
                "long_term_growth": (
                    "growth_skills + knowledge_trust + "
                    "growth_specializations + long_term_growth_snapshots"
                ),
                "cognitive_intelligence": (
                    "cognitive_intelligence_routes + "
                    "cognitive_intelligence_snapshots"
                ),
                "proactive_intelligence": (
                    "situation_snapshots + proactive_signals + "
                    "proactive_incidents + proactive_expectations + "
                    "proactive_attention_feedback"
                ),
                "evolution": (
                    "evolution_state + evolution_capabilities + "
                    "evolution_variants + evolution_assignments + "
                    "evolution_curriculum + evolution_transfers + "
                    "evolution_cycles"
                ),
                "research": (
                    "research_state + research_sources + research_gaps + "
                    "research_sessions + research_evidence + "
                    "research_claims + research_contradictions + "
                    "research_cycles"
                ),
                "communication": (
                    "communication_state + communication_turns + "
                    "communication_preferences + communication_skills + "
                    "communication_feedback + communication_events"
                ),
            },
        }

    def export(self, *, scope: str = "personal") -> dict:
        snapshot = self.snapshot(
            scope=scope,
            event_limit=100,
            graph_limit=40,
        )
        return {
            "format": "AISHIN_LIVE_BRAIN_EXPORT",
            "format_version": 8,
            "scope": snapshot["scope"],
            "generated_at": snapshot["generated_at"],
            "policy": snapshot["trace_policy"],
            "runtime": snapshot,
        }

    def _channels(self, **data: Any) -> list[dict]:
        planner = data["planner"]
        graph_stats = data["graph_stats"]
        latest_hyp = self._latest(data["hypotheses"])
        hypothesis_count = len(latest_hyp.get("hypotheses") or [])
        verification_latest = self._latest(data["verification"])
        verification_unresolved = self._json_count(
            verification_latest.get("unresolved")
            or verification_latest.get("unresolved_json")
        )
        consolidation_events = [
            event
            for event in data["events"]
            if str(event.get("event_type") or "").startswith(
                ("memory.", "consolidation.")
            )
        ]

        counts = {
            "sensors": len(data["sensors"]),
            "memory": len(data["memories"]),
            "graph": int(graph_stats.get("entities") or 0)
            + int(graph_stats.get("relations") or 0),
            "planner": len(planner.get("tasks") or [])
            + len(planner.get("goals") or []),
            "logic": len(data["logic"]),
            "context": len(data["context"]),
            "causal": len(data["causal"]),
            "hypotheses": hypothesis_count,
            "learning": len(data["learning_events"]),
            "counterfactual": len(data["counterfactual"]),
            "quality": len(data["decision_quality"]),
            "action": len(data["action_selection"]),
            "execution": len(data["approvals"]) + len(data["attempts"]),
            "performance": len(data["performance"]),
            "continuous-learning": len(data["learning_cycles"])
            + len(data["patterns"]),
            "metacognition": len(data["metacognition"]),
            "verification": len(data["verification"]),
            "decision": 1 if data["trace"].get("request_id") else 0,
            "tool": len(data["tools"]),
            "reflection": len(data["reflection"]),
            "learning-plan": len(data["learning_plans"]),
            "experiment": len(data["experiments"]),
            "learning-check": 1 if data["learning_quality"] else 0,
            "consolidation": len(consolidation_events),
        }

        details = {
            "sensors": f"{len(data['sensors'])} сенсорных сигналов",
            "memory": f"{len(data['memories'])} записей в текущем срезе",
            "graph": (
                f"{int(graph_stats.get('entities') or 0)} сущностей · "
                f"{int(graph_stats.get('relations') or 0)} связей"
            ),
            "planner": (
                f"{len(planner.get('tasks') or [])} задач · "
                f"{len(planner.get('goals') or [])} целей"
            ),
            "logic": self._mode_detail(data["logic"]),
            "context": f"{len(data['context'])} последних сборок контекста",
            "causal": f"{len(data['causal'])} причинных оценок",
            "hypotheses": f"{hypothesis_count} гипотез в последнем запуске",
            "learning": f"{len(data['learning_events'])} feedback-событий",
            "counterfactual": f"{len(data['counterfactual'])} оценок альтернатив",
            "quality": self._quality_detail(data["decision_quality"]),
            "action": f"{len(data['action_selection'])} выборов действия",
            "execution": (
                f"{len(data['approvals'])} разрешений · "
                f"{len(data['attempts'])} попыток"
            ),
            "performance": self._performance_detail(data["performance"]),
            "continuous-learning": (
                f"{data['learning_status'].get('mode') or 'IDLE'} · "
                f"{int((data['long_term_growth'].get('skills') or {}).get('durable') or 0)} "
                f"устойчивых навыков · "
                f"{int((data['long_term_growth'].get('skills') or {}).get('mastered') or 0)} "
                "освоено"
            ),
            "metacognition": self._meta_detail(data["metacognition"]),
            "verification": (
                f"{len(data['verification'])} проверок · "
                f"{verification_unresolved} нерешённых сигналов"
            ),
            "decision": (
                f"trace {str(data['trace'].get('request_id') or '')[:8]}"
                if data["trace"].get("request_id")
                else "решений ещё нет"
            ),
            "tool": f"{len(data['tools'])} последних действий",
            "reflection": f"{len(data['reflection'])} самооценок",
            "learning-plan": f"{len(data['learning_plans'])} планов обучения",
            "experiment": f"{len(data['experiments'])} безопасных экспериментов",
            "learning-check": (
                "метрика качества доступна"
                if data["learning_quality"]
                else "данные ещё накапливаются"
            ),
            "consolidation": f"{len(consolidation_events)} событий закрепления",
        }

        channels: list[dict] = []
        phase_channel = data["phase_channel"]
        for index, (channel_id, label) in enumerate(
            self.CHANNEL_LABELS,
            start=1,
        ):
            status = "active" if channel_id == phase_channel else (
                "active" if counts[channel_id] else "idle"
            )
            if (
                channel_id == "verification"
                and (verification_unresolved or data["unresolved"])
            ):
                status = "attention"
            if channel_id == "quality" and data["unresolved"]:
                status = "attention"
            channels.append(
                {
                    "index": index,
                    "id": channel_id,
                    "label": label,
                    "status": status,
                    "activity": int(counts[channel_id]),
                    "detail": details[channel_id],
                }
            )
        return channels

    @staticmethod
    def _latest(items: list[dict]) -> dict:
        return items[0] if items else {}

    @staticmethod
    def _json_count(value: Any) -> int:
        if isinstance(value, (list, dict)):
            return len(value)
        return 0

    def _safe_trace(self, trace: dict) -> dict:
        if not trace or not trace.get("request_id"):
            return {
                "available": False,
                "policy": self.TRACE_POLICY,
            }

        logic = trace.get("logic") or {}
        meta = trace.get("metacognition") or {}
        verification = trace.get("verification") or {}
        quality = trace.get("decision_quality") or {}
        performance = trace.get("performance") or {}
        provider = trace.get("provider_runtime") or {}
        memories = trace.get("memories") or []
        evidence = logic.get("evidence") or []
        contradictions = logic.get("contradictions") or []
        unresolved = logic.get("unresolved") or []
        verify_unresolved = verification.get("unresolved") or []
        intelligence = trace.get("cognitive_intelligence") or {}
        intelligence_route = (
            intelligence.get("route")
            or trace.get("cognitive_intelligence_route")
            or {}
        )
        intelligence_outcome = intelligence.get("outcome") or {}

        return {
            "available": True,
            "policy": self.TRACE_POLICY,
            "request_id": trace.get("request_id"),
            "trace_id": trace.get("trace_id"),
            "status": trace.get("trace_status"),
            "created_at": trace.get("trace_created_at"),
            "query_preview": str(trace.get("query") or "")[:180],
            "mode": logic.get("mode"),
            "logic_confidence": logic.get("confidence"),
            "metacognition_status": meta.get("status"),
            "metacognition_confidence": meta.get("confidence"),
            "verification_ran": bool(verification.get("ran")),
            "verification_unresolved": len(verify_unresolved),
            "memory_sources": len(memories),
            "evidence_items": len(evidence),
            "contradictions": len(contradictions),
            "unresolved": len(unresolved),
            "decision_quality": quality.get("overall"),
            "provider": provider.get("provider"),
            "model": provider.get("model"),
            "provider_available": provider.get("available"),
            "provider_latency_ms": provider.get("latency_ms"),
            "total_ms": performance.get("total_ms"),
            "bottleneck": performance.get("bottleneck"),
            "budget_status": performance.get("budget_status"),
            "task_family": intelligence_route.get("task_family"),
            "base_mode": intelligence_route.get("base_mode"),
            "adapted_mode": intelligence_route.get("adapted_mode"),
            "route_confidence": intelligence_route.get("route_confidence"),
            "adaptive_skill_count": len(
                intelligence_route.get("selected_skills") or []
            ),
            "adaptive_knowledge_count": len(
                intelligence_route.get("selected_knowledge") or []
            ),
            "transfer_used": bool(
                intelligence_route.get("transfer_used")
            ),
            "intelligence_outcome": intelligence_outcome.get(
                "outcome_score"
            ),
        }

    @staticmethod
    def _event_view(item: dict) -> dict:
        payload = item.get("payload") or {}
        keys = (
            "request_id",
            "trace_id",
            "intent",
            "phase",
            "status",
            "provider",
            "model",
            "capability",
            "mode",
        )
        summary = {
            key: payload.get(key)
            for key in keys
            if payload.get(key) not in (None, "", [], {})
        }
        return {
            "id": item.get("id"),
            "event_type": item.get("event_type"),
            "importance": item.get("importance"),
            "created_at": item.get("created_at"),
            "summary": summary,
        }

    @staticmethod
    def _entity_view(item: dict) -> dict:
        return {
            "id": item.get("id"),
            "type": item.get("entity_type"),
            "name": item.get("canonical_name"),
        }

    @staticmethod
    def _relation_view(item: dict) -> dict:
        return {
            "id": item.get("id"),
            "source_id": (
                item.get("source_entity_id")
                or item.get("source_id")
            ),
            "target_id": (
                item.get("target_entity_id")
                or item.get("target_id")
            ),
            "type": item.get("relation_type"),
            "confidence": item.get("confidence"),
        }

    @staticmethod
    def _latest_phase(events: list[dict]) -> str:
        for item in events:
            if item.get("event_type") == "cognition.phase":
                payload = item.get("payload") or {}
                phase = str(payload.get("phase") or "").strip()
                if phase:
                    return phase
        if events:
            latest_type = str(events[0].get("event_type") or "")
            if latest_type == "input.received":
                return "input"
            if latest_type == "response.created":
                return "completed"
        return ""

    @staticmethod
    def _unresolved_count(
        trace: dict,
        verification: list[dict],
    ) -> int:
        logic = trace.get("logic") or {}
        latest_verification = verification[0] if verification else {}
        unresolved = len(logic.get("unresolved") or [])
        unresolved += len(
            (trace.get("verification") or {}).get("unresolved") or []
        )
        unresolved += LiveBrainRuntime._json_count(
            latest_verification.get("unresolved")
        )
        return unresolved

    @staticmethod
    def _mode_detail(items: list[dict]) -> str:
        if not items:
            return "режим ещё не выбран"
        mode = items[0].get("mode") or "—"
        confidence = items[0].get("confidence")
        if isinstance(confidence, (int, float)):
            return f"{mode} · {round(confidence * 100)}% уверенности"
        return str(mode)

    @staticmethod
    def _quality_detail(items: list[dict]) -> str:
        if not items:
            return "оценок качества ещё нет"
        overall = items[0].get("overall")
        if isinstance(overall, (int, float)):
            return f"{round(overall * 100)}% по последнему решению"
        return "оценка сохранена"

    @staticmethod
    def _performance_detail(items: list[dict]) -> str:
        if not items:
            return "замеров пока нет"
        total = items[0].get("total_ms")
        status = items[0].get("budget_status") or ""
        if isinstance(total, (int, float)):
            return f"{int(total)} мс · {status or 'измерено'}"
        return str(status or "измерено")

    @staticmethod
    def _meta_detail(items: list[dict]) -> str:
        if not items:
            return "самопроверка ещё не выполнялась"
        status = items[0].get("status") or "—"
        confidence = items[0].get("confidence")
        if isinstance(confidence, (int, float)):
            return f"{status} · {round(confidence * 100)}%"
        return str(status)
