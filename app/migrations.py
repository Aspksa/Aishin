from __future__ import annotations

import sqlite3
from collections.abc import Callable

Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]

LATEST_SCHEMA_VERSION = 19


def _migration_001_baseline(conn: sqlite3.Connection) -> None:
    """Record the current 0.0.3 schema as the managed migration baseline."""
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_memories_scope_status
           ON memories(scope, status, importance DESC, id DESC)"""
    )
    conn.execute(
        """CREATE INDEX IF NOT EXISTS idx_events_scope_created
           ON events(scope, created_at DESC)"""
    )


def _migration_002_runtime_indexes(conn: sqlite3.Connection) -> None:
    """Indexes for the living-core read paths introduced in 0.0.3."""
    statements = (
        """CREATE INDEX IF NOT EXISTS idx_relationship_memory_status
           ON relationship_memory(status, importance DESC, id DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_timeline_scope_occurred
           ON personal_timeline(scope, occurred_at DESC, id DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_entities_scope_type_name
           ON entities(scope, entity_type, canonical_name)""",
        """CREATE INDEX IF NOT EXISTS idx_relations_scope_source
           ON relations(scope, source_entity_id)""",
        """CREATE INDEX IF NOT EXISTS idx_relations_scope_target
           ON relations(scope, target_entity_id)""",
        """CREATE INDEX IF NOT EXISTS idx_tasks_scope_status_priority
           ON tasks(scope, status, priority DESC, id DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_goals_scope_status_priority
           ON goals(scope, status, priority DESC, id DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_sensor_scope_created
           ON sensor_snapshots(scope, created_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_tool_actions_scope_created
           ON tool_actions(scope, created_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_meta_scope_created
           ON metacognitive_assessments(scope, created_at DESC)""",
        """CREATE INDEX IF NOT EXISTS idx_verification_scope_created
           ON verification_runs(scope, created_at DESC)""",
    )
    for statement in statements:
        conn.execute(statement)


def _migration_003_logic_engine(conn: sqlite3.Connection) -> None:
    """Aishin Logic Engine v1: decision journal, evidence and rule audit."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS logic_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            intent TEXT NOT NULL,
            mode TEXT NOT NULL,
            complexity REAL NOT NULL DEFAULT 0.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            selected_strategy TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            contradictions_json TEXT NOT NULL DEFAULT '[]',
            alternatives_json TEXT NOT NULL DEFAULT '[]',
            unresolved_json TEXT NOT NULL DEFAULT '[]',
            rule_hits_json TEXT NOT NULL DEFAULT '[]',
            verification_required INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS logic_rule_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_logic_decisions_scope_created
        ON logic_decisions(scope, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_logic_rule_events_scope_created
        ON logic_rule_events(scope, created_at DESC);
        """
    )


def _migration_004_context_and_causality(conn: sqlite3.Connection) -> None:
    """Context Orchestrator and Causal Reasoning audit tables."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS context_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            query TEXT NOT NULL,
            budget_json TEXT NOT NULL DEFAULT '{}',
            selected_json TEXT NOT NULL DEFAULT '{}',
            estimated_chars INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS causal_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            claims_json TEXT NOT NULL DEFAULT '[]',
            unresolved_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_context_traces_scope_created
        ON context_traces(scope, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_causal_assessments_scope_created
        ON causal_assessments(scope, created_at DESC);
        """
    )


def _migration_005_hypotheses_and_logic_learning(conn: sqlite3.Connection) -> None:
    """Hypothesis Manager and feedback-grounded Logic Learning."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hypothesis_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            mode TEXT NOT NULL,
            hypotheses_json TEXT NOT NULL DEFAULT '[]',
            selected_test_json TEXT NOT NULL DEFAULT '{}',
            stop_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS logic_strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            mode TEXT NOT NULL,
            strategy TEXT NOT NULL,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            reliability REAL NOT NULL DEFAULT 0.5,
            last_feedback TEXT NOT NULL DEFAULT '',
            last_used_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, strategy_key)
        );

        CREATE TABLE IF NOT EXISTS logic_learning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            strategy_id INTEGER,
            feedback TEXT NOT NULL,
            outcome TEXT NOT NULL,
            delta REAL NOT NULL DEFAULT 0.0,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(strategy_id) REFERENCES logic_strategies(id)
        );

        CREATE INDEX IF NOT EXISTS idx_hypothesis_runs_scope_created
        ON hypothesis_runs(scope, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_logic_strategies_scope_reliability
        ON logic_strategies(scope, reliability DESC, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_logic_learning_events_scope_created
        ON logic_learning_events(scope, created_at DESC);
        """
    )


def _migration_006_counterfactual_and_decision_quality(
    conn: sqlite3.Connection,
) -> None:
    """Counterfactual Reasoning and Decision Quality Scoring."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS counterfactual_assessments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            mode TEXT NOT NULL,
            scenarios_json TEXT NOT NULL DEFAULT '[]',
            assumptions_json TEXT NOT NULL DEFAULT '[]',
            unresolved_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS decision_quality_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            mode TEXT NOT NULL,
            overall REAL NOT NULL DEFAULT 0.0,
            components_json TEXT NOT NULL DEFAULT '{}',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            recommendation TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_counterfactual_scope_created
        ON counterfactual_assessments(scope, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_decision_quality_scope_created
        ON decision_quality_scores(scope, created_at DESC);
        """
    )


def _migration_007_action_selection(conn: sqlite3.Connection) -> None:
    """Expected-utility action selection audit. Selection never executes tools."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS action_selections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            mode TEXT NOT NULL,
            candidates_json TEXT NOT NULL DEFAULT '[]',
            selected_json TEXT NOT NULL DEFAULT '{}',
            decision_quality REAL NOT NULL DEFAULT 0.0,
            selection_state TEXT NOT NULL DEFAULT 'proposal_only',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_action_selections_scope_created
        ON action_selections(scope, created_at DESC);
        """
    )


def _migration_008_execution_coordinator(conn: sqlite3.Connection) -> None:
    """One-shot approval and execution revalidation audit."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS execution_approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            decision_id INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            capability TEXT NOT NULL,
            arguments_hash TEXT NOT NULL,
            preview_hash TEXT NOT NULL,
            permission_mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            expires_at TEXT NOT NULL,
            consumed_at TEXT,
            invalidated_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS execution_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            decision_id INTEGER NOT NULL,
            approval_id INTEGER,
            tool_name TEXT NOT NULL,
            status TEXT NOT NULL,
            revalidation_json TEXT NOT NULL DEFAULT '{}',
            tool_result_json TEXT NOT NULL DEFAULT '{}',
            rollback_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(approval_id) REFERENCES execution_approvals(id)
        );

        CREATE INDEX IF NOT EXISTS idx_execution_approvals_decision
        ON execution_approvals(scope, decision_id, status, id DESC);

        CREATE INDEX IF NOT EXISTS idx_execution_attempts_scope_created
        ON execution_attempts(scope, created_at DESC);
        """
    )


def _migration_009_cloud_resilience_and_request_traces(
    conn: sqlite3.Connection,
) -> None:
    """Per-request cognitive trace isolation for concurrent requests."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cognitive_request_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            query TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'completed',
            trace_json TEXT NOT NULL DEFAULT '{}',
            provider_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_cognitive_traces_scope_created
        ON cognitive_request_traces(scope, id DESC);
        """
    )


def _migration_010_performance_observability(
    conn: sqlite3.Connection,
) -> None:
    """Per-request stage timings and latency budget audit."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS performance_traces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            stages_json TEXT NOT NULL DEFAULT '{}',
            budgets_json TEXT NOT NULL DEFAULT '{}',
            total_ms INTEGER NOT NULL DEFAULT 0,
            bottleneck TEXT NOT NULL DEFAULT '',
            budget_status TEXT NOT NULL DEFAULT 'within_budget',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_performance_scope_created
        ON performance_traces(scope, id DESC);
        """
    )


def _migration_011_proactive_lifecycle(conn: sqlite3.Connection) -> None:
    """Persistent condition lifecycle for proactive decision dedupe."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS proactive_conditions (
            scope TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            source TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            generation INTEGER NOT NULL DEFAULT 1,
            last_decision_id INTEGER,
            disposition TEXT NOT NULL DEFAULT '',
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(scope, fingerprint)
        );

        CREATE INDEX IF NOT EXISTS idx_proactive_conditions_active
        ON proactive_conditions(scope, active, updated_at DESC);
        """
    )


def _migration_012_continuous_learning(conn: sqlite3.Connection) -> None:
    """Continuous learning queue, automatic mode state and learned patterns."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS continuous_learning_state (
            scope TEXT PRIMARY KEY,
            mode TEXT NOT NULL DEFAULT 'IDLE',
            mode_reason TEXT NOT NULL DEFAULT '',
            worker_status TEXT NOT NULL DEFAULT 'stopped',
            cursor_json TEXT NOT NULL DEFAULT '{}',
            last_cycle_at TEXT,
            last_maintenance_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS continuous_learning_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            priority REAL NOT NULL DEFAULT 0.5,
            payload_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, source_type, source_id)
        );

        CREATE TABLE IF NOT EXISTS learning_patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            category TEXT NOT NULL,
            pattern_key TEXT NOT NULL,
            observations INTEGER NOT NULL DEFAULT 0,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            score REAL NOT NULL DEFAULT 0.5,
            evidence_json TEXT NOT NULL DEFAULT '[]',
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, category, pattern_key)
        );

        CREATE TABLE IF NOT EXISTS continuous_learning_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            queue_depth_before INTEGER NOT NULL DEFAULT 0,
            processed INTEGER NOT NULL DEFAULT 0,
            learned INTEGER NOT NULL DEFAULT 0,
            cloud_used INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'success',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_learning_queue_scope_status
        ON continuous_learning_queue(scope, status, priority DESC, id ASC);

        CREATE INDEX IF NOT EXISTS idx_learning_patterns_scope_score
        ON learning_patterns(scope, score DESC, observations DESC);

        CREATE INDEX IF NOT EXISTS idx_learning_cycles_scope_created
        ON continuous_learning_cycles(scope, id DESC);
        """
    )


def _migration_013_learning_quality_and_strategy_evolution(
    conn: sqlite3.Connection,
) -> None:
    """Learning Quality Gate, strategy evolution and drift/decay state."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS learning_pattern_quality (
            pattern_id INTEGER PRIMARY KEY,
            scope TEXT NOT NULL,
            lifecycle TEXT NOT NULL DEFAULT 'candidate',
            raw_score REAL NOT NULL DEFAULT 0.5,
            effective_score REAL NOT NULL DEFAULT 0.5,
            decay_factor REAL NOT NULL DEFAULT 1.0,
            contradiction_rate REAL NOT NULL DEFAULT 0.0,
            age_days REAL NOT NULL DEFAULT 0.0,
            reason TEXT NOT NULL DEFAULT '',
            promoted_at TEXT,
            deprecated_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(pattern_id) REFERENCES learning_patterns(id)
        );

        CREATE TABLE IF NOT EXISTS strategy_quality_state (
            strategy_id INTEGER PRIMARY KEY,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            lifecycle TEXT NOT NULL DEFAULT 'candidate',
            raw_reliability REAL NOT NULL DEFAULT 0.5,
            effective_reliability REAL NOT NULL DEFAULT 0.5,
            decay_factor REAL NOT NULL DEFAULT 1.0,
            drift_score REAL NOT NULL DEFAULT 0.0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            rank_in_mode INTEGER,
            reason TEXT NOT NULL DEFAULT '',
            promoted_at TEXT,
            deprecated_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(strategy_id) REFERENCES logic_strategies(id)
        );

        CREATE TABLE IF NOT EXISTS learning_quality_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            old_lifecycle TEXT NOT NULL DEFAULT '',
            new_lifecycle TEXT NOT NULL DEFAULT '',
            old_score REAL,
            new_score REAL,
            reason TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_pattern_quality_scope_lifecycle
        ON learning_pattern_quality(scope, lifecycle, effective_score DESC);

        CREATE INDEX IF NOT EXISTS idx_strategy_quality_scope_mode
        ON strategy_quality_state(
            scope, mode, lifecycle, effective_reliability DESC
        );

        CREATE INDEX IF NOT EXISTS idx_learning_quality_events_scope_created
        ON learning_quality_events(scope, id DESC);
        """
    )


def _migration_014_reflection_planning_experiments_context_budget(
    conn: sqlite3.Connection,
) -> None:
    """Self-reflection, learning planner, safe experiments and context budget."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS self_reflection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            quality_score REAL NOT NULL DEFAULT 0.0,
            confidence_score REAL NOT NULL DEFAULT 0.0,
            error_count INTEGER NOT NULL DEFAULT 0,
            correction_signal INTEGER NOT NULL DEFAULT 0,
            weak_spots_json TEXT NOT NULL DEFAULT '[]',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS learning_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            topic TEXT NOT NULL,
            rationale TEXT NOT NULL DEFAULT '',
            priority REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'open',
            target_metric TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS learning_plan_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            plan_id INTEGER NOT NULL,
            event TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(plan_id) REFERENCES learning_plans(id)
        );

        CREATE TABLE IF NOT EXISTS safe_experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            name TEXT NOT NULL,
            hypothesis TEXT NOT NULL DEFAULT '',
            baseline_strategy TEXT NOT NULL DEFAULT '',
            candidate_strategy TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'shadow',
            risk_level TEXT NOT NULL DEFAULT 'low',
            required_samples INTEGER NOT NULL DEFAULT 5,
            observed_samples INTEGER NOT NULL DEFAULT 0,
            baseline_score REAL NOT NULL DEFAULT 0.0,
            candidate_score REAL NOT NULL DEFAULT 0.0,
            decision TEXT NOT NULL DEFAULT 'insufficient_evidence',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS experiment_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL,
            scope TEXT NOT NULL,
            request_id TEXT NOT NULL,
            baseline_score REAL NOT NULL DEFAULT 0.0,
            candidate_score REAL NOT NULL DEFAULT 0.0,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(experiment_id, request_id),
            FOREIGN KEY(experiment_id) REFERENCES safe_experiments(id)
        );

        CREATE TABLE IF NOT EXISTS context_budget_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            token_budget INTEGER NOT NULL,
            estimated_tokens_before INTEGER NOT NULL DEFAULT 0,
            estimated_tokens_after INTEGER NOT NULL DEFAULT 0,
            trimmed_chars INTEGER NOT NULL DEFAULT 0,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_reflection_scope_created
        ON self_reflection_runs(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_learning_plans_scope_status
        ON learning_plans(scope, status, priority DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_safe_experiments_scope_status
        ON safe_experiments(scope, status, id DESC);

        CREATE INDEX IF NOT EXISTS idx_context_budget_scope_created
        ON context_budget_reports(scope, id DESC);
        """
    )


def _migration_015_weighted_learning_evidence(
    conn: sqlite3.Connection,
) -> None:
    """Weighted evidence for stronger continuous learning."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS learning_evidence_metrics (
            pattern_id INTEGER PRIMARY KEY,
            scope TEXT NOT NULL,
            weighted_observations REAL NOT NULL DEFAULT 0.0,
            weighted_successes REAL NOT NULL DEFAULT 0.0,
            weighted_failures REAL NOT NULL DEFAULT 0.0,
            evidence_confidence REAL NOT NULL DEFAULT 0.5,
            source_types_json TEXT NOT NULL DEFAULT '[]',
            last_signal_weight REAL NOT NULL DEFAULT 0.0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(pattern_id) REFERENCES learning_patterns(id)
        );

        CREATE INDEX IF NOT EXISTS idx_learning_evidence_scope
        ON learning_evidence_metrics(
            scope, evidence_confidence DESC, weighted_observations DESC
        );
        """
    )


def _migration_016_development_metrics(
    conn: sqlite3.Connection,
) -> None:
    """Persistent transparent Aishin development history."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS development_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            overall_score REAL NOT NULL DEFAULT 0.0,
            components_json TEXT NOT NULL DEFAULT '{}',
            counters_json TEXT NOT NULL DEFAULT '{}',
            reasons_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_development_scope_created
        ON development_snapshots(scope, id DESC);
        """
    )


def _migration_017_long_term_growth(
    conn: sqlite3.Connection,
) -> None:
    """Durable skill mastery, knowledge trust and specialization map."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS growth_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            skill_key TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id INTEGER,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            lifecycle TEXT NOT NULL DEFAULT 'forming',
            mastery_score REAL NOT NULL DEFAULT 0.0,
            reliability REAL NOT NULL DEFAULT 0.0,
            evidence_count REAL NOT NULL DEFAULT 0.0,
            successes REAL NOT NULL DEFAULT 0.0,
            failures REAL NOT NULL DEFAULT 0.0,
            freshness REAL NOT NULL DEFAULT 1.0,
            stability REAL NOT NULL DEFAULT 0.0,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_evidence_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, skill_key)
        );

        CREATE TABLE IF NOT EXISTS knowledge_trust (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            label TEXT NOT NULL,
            base_confidence REAL NOT NULL DEFAULT 0.0,
            freshness REAL NOT NULL DEFAULT 1.0,
            corroboration REAL NOT NULL DEFAULT 0.0,
            conflict_penalty REAL NOT NULL DEFAULT 0.0,
            trust_score REAL NOT NULL DEFAULT 0.0,
            trust_level TEXT NOT NULL DEFAULT 'unverified',
            evidence_count INTEGER NOT NULL DEFAULT 1,
            reasons_json TEXT NOT NULL DEFAULT '[]',
            last_seen_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, subject_type, subject_id)
        );

        CREATE TABLE IF NOT EXISTS growth_specializations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            specialization_key TEXT NOT NULL,
            label TEXT NOT NULL,
            skill_count INTEGER NOT NULL DEFAULT 0,
            mastered_skills INTEGER NOT NULL DEFAULT 0,
            evidence_count REAL NOT NULL DEFAULT 0.0,
            depth_score REAL NOT NULL DEFAULT 0.0,
            breadth_score REAL NOT NULL DEFAULT 0.0,
            trust_score REAL NOT NULL DEFAULT 0.0,
            overall_score REAL NOT NULL DEFAULT 0.0,
            level TEXT NOT NULL DEFAULT 'forming',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, specialization_key)
        );

        CREATE TABLE IF NOT EXISTS long_term_growth_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            overall_score REAL NOT NULL DEFAULT 0.0,
            durable_skills INTEGER NOT NULL DEFAULT 0,
            mastered_skills INTEGER NOT NULL DEFAULT 0,
            specializations INTEGER NOT NULL DEFAULT 0,
            trusted_knowledge INTEGER NOT NULL DEFAULT 0,
            stale_knowledge INTEGER NOT NULL DEFAULT 0,
            average_trust REAL NOT NULL DEFAULT 0.0,
            average_freshness REAL NOT NULL DEFAULT 0.0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS long_term_growth_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            old_state TEXT NOT NULL DEFAULT '',
            new_state TEXT NOT NULL DEFAULT '',
            score REAL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_growth_skills_scope_lifecycle
        ON growth_skills(scope, lifecycle, mastery_score DESC);

        CREATE INDEX IF NOT EXISTS idx_knowledge_trust_scope_level
        ON knowledge_trust(scope, trust_level, trust_score DESC);

        CREATE INDEX IF NOT EXISTS idx_growth_specializations_scope_score
        ON growth_specializations(scope, overall_score DESC);

        CREATE INDEX IF NOT EXISTS idx_long_term_growth_snapshots_scope
        ON long_term_growth_snapshots(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_long_term_growth_events_scope
        ON long_term_growth_events(scope, id DESC);
        """
    )


def _migration_018_cognitive_intelligence(
    conn: sqlite3.Connection,
) -> None:
    """Adaptive skill routing and evidence-grounded intelligence metrics."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cognitive_intelligence_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            query_preview TEXT NOT NULL DEFAULT '',
            task_family TEXT NOT NULL DEFAULT 'general',
            intent TEXT NOT NULL DEFAULT 'conversation',
            base_mode TEXT NOT NULL DEFAULT 'FAST',
            adapted_mode TEXT NOT NULL DEFAULT 'FAST',
            route_confidence REAL NOT NULL DEFAULT 0.0,
            context_multiplier REAL NOT NULL DEFAULT 1.0,
            selected_skill_ids_json TEXT NOT NULL DEFAULT '[]',
            selected_specialization_ids_json TEXT NOT NULL DEFAULT '[]',
            selected_knowledge_ids_json TEXT NOT NULL DEFAULT '[]',
            transfer_used INTEGER NOT NULL DEFAULT 0,
            transfer_skill_ids_json TEXT NOT NULL DEFAULT '[]',
            rationale_json TEXT NOT NULL DEFAULT '[]',
            outcome_score REAL,
            successful INTEGER,
            unresolved_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS cognitive_intelligence_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            formula_version TEXT NOT NULL,
            overall_score REAL NOT NULL DEFAULT 0.0,
            dimensions_json TEXT NOT NULL DEFAULT '{}',
            evidence_json TEXT NOT NULL DEFAULT '{}',
            route_stats_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_intelligence_routes_scope_created
        ON cognitive_intelligence_routes(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_intelligence_routes_family_outcome
        ON cognitive_intelligence_routes(
            scope, task_family, successful, outcome_score DESC
        );

        CREATE INDEX IF NOT EXISTS idx_intelligence_snapshots_scope_created
        ON cognitive_intelligence_snapshots(scope, id DESC);
        """
    )


def _migration_019_proactive_intelligence(
    conn: sqlite3.Connection,
) -> None:
    """Situation model, anomaly lifecycle and calibrated attention manager."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS situation_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            trigger TEXT NOT NULL DEFAULT 'manual',
            awareness_score REAL NOT NULL DEFAULT 0.0,
            object_counts_json TEXT NOT NULL DEFAULT '{}',
            state_json TEXT NOT NULL DEFAULT '{}',
            delta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS proactive_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            source TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT '',
            subject_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            details_json TEXT NOT NULL DEFAULT '{}',
            severity REAL NOT NULL DEFAULT 0.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            impact REAL NOT NULL DEFAULT 0.0,
            urgency REAL NOT NULL DEFAULT 0.0,
            risk_score REAL NOT NULL DEFAULT 0.0,
            attention_score REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'observed',
            occurrences INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, fingerprint)
        );

        CREATE TABLE IF NOT EXISTS proactive_incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            signal_id INTEGER,
            incident_type TEXT NOT NULL,
            source TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT '',
            subject_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            suggested_action TEXT NOT NULL DEFAULT '',
            severity REAL NOT NULL DEFAULT 0.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            impact REAL NOT NULL DEFAULT 0.0,
            urgency REAL NOT NULL DEFAULT 0.0,
            risk_score REAL NOT NULL DEFAULT 0.0,
            attention_score REAL NOT NULL DEFAULT 0.0,
            verification_state TEXT NOT NULL DEFAULT 'observed',
            status TEXT NOT NULL DEFAULT 'active',
            decision_id INTEGER,
            occurrences INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            snoozed_until TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, fingerprint),
            FOREIGN KEY(signal_id) REFERENCES proactive_signals(id)
        );

        CREATE TABLE IF NOT EXISTS proactive_expectations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            expectation_key TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            title TEXT NOT NULL,
            expected_state TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 1.0,
            due_at TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            details_json TEXT NOT NULL DEFAULT '{}',
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            UNIQUE(scope, expectation_key)
        );

        CREATE TABLE IF NOT EXISTS proactive_attention_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            incident_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(incident_id) REFERENCES proactive_incidents(id)
        );

        CREATE TABLE IF NOT EXISTS proactive_attention_profile (
            scope TEXT PRIMARY KEY,
            base_threshold REAL NOT NULL DEFAULT 0.48,
            calibrated_threshold REAL NOT NULL DEFAULT 0.48,
            useful_count INTEGER NOT NULL DEFAULT 0,
            noisy_count INTEGER NOT NULL DEFAULT 0,
            false_positive_count INTEGER NOT NULL DEFAULT 0,
            handled_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS proactive_intelligence_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            trigger TEXT NOT NULL,
            awareness_score REAL NOT NULL DEFAULT 0.0,
            signals_observed INTEGER NOT NULL DEFAULT 0,
            incidents_created INTEGER NOT NULL DEFAULT 0,
            incidents_updated INTEGER NOT NULL DEFAULT 0,
            incidents_resolved INTEGER NOT NULL DEFAULT 0,
            decisions_created INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            stats_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_situation_snapshots_scope_created
        ON situation_snapshots(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_proactive_signals_scope_attention
        ON proactive_signals(
            scope, status, attention_score DESC, last_seen_at DESC
        );

        CREATE INDEX IF NOT EXISTS idx_proactive_incidents_scope_status
        ON proactive_incidents(
            scope, status, attention_score DESC, updated_at DESC
        );

        CREATE INDEX IF NOT EXISTS idx_proactive_expectations_scope_status
        ON proactive_expectations(scope, status, due_at);

        CREATE INDEX IF NOT EXISTS idx_attention_feedback_scope_created
        ON proactive_attention_feedback(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_proactive_runs_scope_created
        ON proactive_intelligence_runs(scope, id DESC);
        """
    )


MIGRATIONS: tuple[Migration, ...] = (
    (1, "baseline_0_0_3", _migration_001_baseline),
    (2, "living_core_runtime_indexes", _migration_002_runtime_indexes),
    (3, "logic_engine_v1", _migration_003_logic_engine),
    (4, "context_orchestrator_and_causality", _migration_004_context_and_causality),
    (5, "hypotheses_and_logic_learning", _migration_005_hypotheses_and_logic_learning),
    (6, "counterfactual_and_decision_quality", _migration_006_counterfactual_and_decision_quality),
    (7, "action_selection", _migration_007_action_selection),
    (8, "execution_coordinator", _migration_008_execution_coordinator),
    (9, "cloud_resilience_and_request_traces", _migration_009_cloud_resilience_and_request_traces),
    (10, "performance_observability", _migration_010_performance_observability),
    (11, "proactive_lifecycle", _migration_011_proactive_lifecycle),
    (12, "continuous_learning", _migration_012_continuous_learning),
    (13, "learning_quality_and_strategy_evolution", _migration_013_learning_quality_and_strategy_evolution),
    (14, "reflection_planner_experiments_context_budget", _migration_014_reflection_planning_experiments_context_budget),
    (15, "weighted_learning_evidence", _migration_015_weighted_learning_evidence),
    (16, "development_metrics", _migration_016_development_metrics),
    (17, "long_term_growth", _migration_017_long_term_growth),
    (18, "cognitive_intelligence", _migration_018_cognitive_intelligence),
    (19, "proactive_intelligence", _migration_019_proactive_intelligence),
)


def _ensure_migration_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
               version INTEGER PRIMARY KEY,
               name TEXT NOT NULL,
               applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_migration_table(conn)
    rows = conn.execute(
        "SELECT version FROM schema_migrations ORDER BY version"
    ).fetchall()
    return {int(row[0]) for row in rows}


def run_migrations(conn: sqlite3.Connection) -> list[dict]:
    """Apply missing migrations transactionally and return what changed."""
    _ensure_migration_table(conn)
    applied = applied_versions(conn)
    completed: list[dict] = []

    for version, name, migration in MIGRATIONS:
        if version in applied:
            continue

        if version > LATEST_SCHEMA_VERSION:
            raise RuntimeError(
                f"Migration {version} exceeds LATEST_SCHEMA_VERSION={LATEST_SCHEMA_VERSION}"
            )

        with conn:
            migration(conn)
            conn.execute(
                """INSERT INTO schema_migrations(version, name)
                   VALUES (?, ?)""",
                (version, name),
            )
        completed.append({"version": version, "name": name})

    return completed


def schema_status(conn: sqlite3.Connection) -> dict:
    _ensure_migration_table(conn)
    rows = conn.execute(
        """SELECT version, name, applied_at
           FROM schema_migrations ORDER BY version"""
    ).fetchall()
    versions = [int(row[0]) for row in rows]
    current = max(versions, default=0)
    return {
        "current_version": current,
        "latest_version": LATEST_SCHEMA_VERSION,
        "up_to_date": current == LATEST_SCHEMA_VERSION,
        "applied": [
            {
                "version": int(row[0]),
                "name": row[1],
                "applied_at": row[2],
            }
            for row in rows
        ],
    }
