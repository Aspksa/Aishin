from __future__ import annotations

import sqlite3
from collections.abc import Callable

Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]

LATEST_SCHEMA_VERSION = 26


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


def _migration_020_evolution_engine(
    conn: sqlite3.Connection,
) -> None:
    """Bounded meta-learning, curriculum, transfer and policy evolution."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS evolution_state (
            scope TEXT PRIMARY KEY,
            generation INTEGER NOT NULL DEFAULT 1,
            evolution_score REAL NOT NULL DEFAULT 0.0,
            stability_score REAL NOT NULL DEFAULT 1.0,
            plasticity_score REAL NOT NULL DEFAULT 0.0,
            learning_velocity REAL NOT NULL DEFAULT 0.0,
            active_policy_count INTEGER NOT NULL DEFAULT 0,
            challenger_count INTEGER NOT NULL DEFAULT 0,
            rollback_count INTEGER NOT NULL DEFAULT 0,
            last_cycle_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS evolution_capabilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            capability_key TEXT NOT NULL,
            label TEXT NOT NULL,
            family TEXT NOT NULL DEFAULT 'general',
            sample_count INTEGER NOT NULL DEFAULT 0,
            success_rate REAL NOT NULL DEFAULT 0.0,
            unresolved_rate REAL NOT NULL DEFAULT 0.0,
            average_outcome REAL NOT NULL DEFAULT 0.0,
            recent_outcome REAL NOT NULL DEFAULT 0.0,
            baseline_outcome REAL NOT NULL DEFAULT 0.0,
            trend REAL NOT NULL DEFAULT 0.0,
            confidence REAL NOT NULL DEFAULT 0.0,
            learning_gap REAL NOT NULL DEFAULT 1.0,
            fitness REAL NOT NULL DEFAULT 0.0,
            last_evidence_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, capability_key)
        );

        CREATE TABLE IF NOT EXISTS evolution_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            family TEXT NOT NULL,
            variant_key TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 1,
            parent_variant_id INTEGER,
            lifecycle TEXT NOT NULL DEFAULT 'shadow',
            policy_json TEXT NOT NULL DEFAULT '{}',
            rationale TEXT NOT NULL DEFAULT '',
            baseline_fitness REAL NOT NULL DEFAULT 0.0,
            observed_fitness REAL NOT NULL DEFAULT 0.0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            unresolved_total INTEGER NOT NULL DEFAULT 0,
            risk_delta REAL NOT NULL DEFAULT 0.0,
            auto_promotable INTEGER NOT NULL DEFAULT 0,
            promoted_at TEXT,
            retired_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, variant_key),
            FOREIGN KEY(parent_variant_id) REFERENCES evolution_variants(id)
        );

        CREATE TABLE IF NOT EXISTS evolution_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            family TEXT NOT NULL,
            variant_id INTEGER,
            assignment_type TEXT NOT NULL DEFAULT 'baseline',
            policy_json TEXT NOT NULL DEFAULT '{}',
            baseline_fitness REAL NOT NULL DEFAULT 0.0,
            outcome_score REAL,
            successful INTEGER,
            unresolved_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            UNIQUE(scope, request_id),
            FOREIGN KEY(variant_id) REFERENCES evolution_variants(id)
        );

        CREATE TABLE IF NOT EXISTS evolution_curriculum (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            item_key TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_key TEXT NOT NULL,
            title TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            priority REAL NOT NULL DEFAULT 0.5,
            gap_score REAL NOT NULL DEFAULT 0.0,
            expected_metric TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            plan_json TEXT NOT NULL DEFAULT '{}',
            progress REAL NOT NULL DEFAULT 0.0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            UNIQUE(scope, item_key)
        );

        CREATE TABLE IF NOT EXISTS evolution_transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            transfer_key TEXT NOT NULL,
            source_family TEXT NOT NULL,
            target_family TEXT NOT NULL,
            skill_id INTEGER,
            confidence REAL NOT NULL DEFAULT 0.0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            successes INTEGER NOT NULL DEFAULT 0,
            failures INTEGER NOT NULL DEFAULT 0,
            success_rate REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'observed',
            evidence_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, transfer_key)
        );

        CREATE TABLE IF NOT EXISTS evolution_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            trigger TEXT NOT NULL,
            generation INTEGER NOT NULL DEFAULT 1,
            evolution_score REAL NOT NULL DEFAULT 0.0,
            stability_score REAL NOT NULL DEFAULT 0.0,
            plasticity_score REAL NOT NULL DEFAULT 0.0,
            learning_velocity REAL NOT NULL DEFAULT 0.0,
            variants_created INTEGER NOT NULL DEFAULT 0,
            variants_promoted INTEGER NOT NULL DEFAULT 0,
            variants_retired INTEGER NOT NULL DEFAULT 0,
            variants_rolled_back INTEGER NOT NULL DEFAULT 0,
            curriculum_created INTEGER NOT NULL DEFAULT 0,
            transfers_updated INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS evolution_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            event_type TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT '',
            subject_key TEXT NOT NULL DEFAULT '',
            generation INTEGER NOT NULL DEFAULT 1,
            score REAL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_evolution_capabilities_scope_fitness
        ON evolution_capabilities(scope, fitness DESC, learning_gap DESC);

        CREATE INDEX IF NOT EXISTS idx_evolution_variants_scope_lifecycle
        ON evolution_variants(scope, lifecycle, family, updated_at DESC);

        CREATE INDEX IF NOT EXISTS idx_evolution_assignments_scope_completed
        ON evolution_assignments(scope, completed_at DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_evolution_curriculum_scope_status
        ON evolution_curriculum(scope, status, priority DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_evolution_transfers_scope_status
        ON evolution_transfers(scope, status, success_rate DESC);

        CREATE INDEX IF NOT EXISTS idx_evolution_cycles_scope_created
        ON evolution_cycles(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_evolution_events_scope_created
        ON evolution_events(scope, id DESC);
        """
    )


def _migration_021_autonomous_research(
    conn: sqlite3.Connection,
) -> None:
    """Evidence-ledger research, knowledge gaps and guarded claim promotion."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS research_state (
            scope TEXT PRIMARY KEY,
            research_score REAL NOT NULL DEFAULT 0.0,
            coverage_score REAL NOT NULL DEFAULT 0.0,
            evidence_quality REAL NOT NULL DEFAULT 0.0,
            contradiction_resolution REAL NOT NULL DEFAULT 0.0,
            knowledge_precision REAL NOT NULL DEFAULT 0.0,
            open_gap_count INTEGER NOT NULL DEFAULT 0,
            active_session_count INTEGER NOT NULL DEFAULT 0,
            trusted_claim_count INTEGER NOT NULL DEFAULT 0,
            conflicted_claim_count INTEGER NOT NULL DEFAULT 0,
            last_cycle_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS research_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            source_key TEXT NOT NULL,
            source_type TEXT NOT NULL,
            label TEXT NOT NULL,
            locator TEXT NOT NULL DEFAULT '',
            independent_group TEXT NOT NULL DEFAULT '',
            trust_prior REAL NOT NULL DEFAULT 0.70,
            enabled INTEGER NOT NULL DEFAULT 1,
            auto_read INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, source_key)
        );

        CREATE TABLE IF NOT EXISTS research_gaps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            gap_key TEXT NOT NULL,
            question TEXT NOT NULL,
            origin TEXT NOT NULL,
            origin_ref TEXT NOT NULL DEFAULT '',
            priority REAL NOT NULL DEFAULT 0.5,
            uncertainty REAL NOT NULL DEFAULT 0.5,
            impact REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'open',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_session_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            UNIQUE(scope, gap_key)
        );

        CREATE TABLE IF NOT EXISTS research_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            gap_id INTEGER,
            request_id TEXT,
            question TEXT NOT NULL,
            trigger TEXT NOT NULL DEFAULT 'manual',
            status TEXT NOT NULL DEFAULT 'planned',
            plan_json TEXT NOT NULL DEFAULT '{}',
            source_plan_json TEXT NOT NULL DEFAULT '[]',
            evidence_count INTEGER NOT NULL DEFAULT 0,
            independent_groups INTEGER NOT NULL DEFAULT 0,
            contradiction_count INTEGER NOT NULL DEFAULT 0,
            claim_count INTEGER NOT NULL DEFAULT 0,
            synthesis_used INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(gap_id) REFERENCES research_gaps(id)
        );

        CREATE TABLE IF NOT EXISTS research_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            session_id INTEGER NOT NULL,
            evidence_key TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            source_group TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            stance TEXT NOT NULL DEFAULT 'context',
            reliability REAL NOT NULL DEFAULT 0.0,
            relevance REAL NOT NULL DEFAULT 0.0,
            freshness REAL NOT NULL DEFAULT 1.0,
            independence REAL NOT NULL DEFAULT 1.0,
            evidence_score REAL NOT NULL DEFAULT 0.0,
            content_hash TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, session_id, evidence_key),
            FOREIGN KEY(session_id) REFERENCES research_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS research_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            claim_key TEXT NOT NULL,
            session_id INTEGER NOT NULL,
            statement TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'candidate',
            confidence REAL NOT NULL DEFAULT 0.0,
            weighted_support REAL NOT NULL DEFAULT 0.0,
            weighted_contradiction REAL NOT NULL DEFAULT 0.0,
            support_count INTEGER NOT NULL DEFAULT 0,
            contradiction_count INTEGER NOT NULL DEFAULT 0,
            independent_groups INTEGER NOT NULL DEFAULT 0,
            source_diversity INTEGER NOT NULL DEFAULT 0,
            support_evidence_json TEXT NOT NULL DEFAULT '[]',
            contradiction_evidence_json TEXT NOT NULL DEFAULT '[]',
            missing_json TEXT NOT NULL DEFAULT '[]',
            promoted_memory_id INTEGER,
            promoted_entity_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            promoted_at TEXT,
            rejected_at TEXT,
            UNIQUE(scope, claim_key),
            FOREIGN KEY(session_id) REFERENCES research_sessions(id)
        );

        CREATE TABLE IF NOT EXISTS research_contradictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            session_id INTEGER NOT NULL,
            claim_id INTEGER,
            left_evidence_id INTEGER,
            right_evidence_id INTEGER,
            contradiction_type TEXT NOT NULL DEFAULT 'semantic',
            severity REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'open',
            resolution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            FOREIGN KEY(session_id) REFERENCES research_sessions(id),
            FOREIGN KEY(claim_id) REFERENCES research_claims(id),
            FOREIGN KEY(left_evidence_id) REFERENCES research_evidence(id),
            FOREIGN KEY(right_evidence_id) REFERENCES research_evidence(id)
        );

        CREATE TABLE IF NOT EXISTS research_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            trigger TEXT NOT NULL,
            gaps_discovered INTEGER NOT NULL DEFAULT 0,
            sessions_run INTEGER NOT NULL DEFAULT 0,
            evidence_added INTEGER NOT NULL DEFAULT 0,
            claims_created INTEGER NOT NULL DEFAULT 0,
            claims_promoted INTEGER NOT NULL DEFAULT 0,
            contradictions_open INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            summary_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS research_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            event_type TEXT NOT NULL,
            subject_type TEXT NOT NULL DEFAULT '',
            subject_key TEXT NOT NULL DEFAULT '',
            score REAL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_research_gaps_scope_status
        ON research_gaps(scope, status, priority DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_research_sessions_scope_created
        ON research_sessions(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_research_evidence_session_score
        ON research_evidence(session_id, evidence_score DESC, id ASC);

        CREATE INDEX IF NOT EXISTS idx_research_claims_scope_status
        ON research_claims(scope, status, confidence DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_research_contradictions_scope_status
        ON research_contradictions(scope, status, severity DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_research_cycles_scope_created
        ON research_cycles(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_research_events_scope_created
        ON research_events(scope, id DESC);
        """
    )


def _migration_022_communication_intelligence(
    conn: sqlite3.Connection,
) -> None:
    """Adaptive dialogue state, communication skills and feedback learning."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS communication_state (
            scope TEXT PRIMARY KEY,
            communication_score REAL NOT NULL DEFAULT 0.0,
            understanding_score REAL NOT NULL DEFAULT 0.0,
            adaptation_score REAL NOT NULL DEFAULT 0.0,
            persona_stability REAL NOT NULL DEFAULT 1.0,
            diversity_score REAL NOT NULL DEFAULT 0.0,
            explanation_success REAL NOT NULL DEFAULT 0.0,
            evaluated_turns INTEGER NOT NULL DEFAULT 0,
            clarification_requests INTEGER NOT NULL DEFAULT 0,
            positive_feedback INTEGER NOT NULL DEFAULT 0,
            negative_feedback INTEGER NOT NULL DEFAULT 0,
            last_turn_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS communication_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL,
            scope TEXT NOT NULL,
            user_message TEXT NOT NULL,
            base_intent TEXT NOT NULL DEFAULT '',
            communication_intent TEXT NOT NULL DEFAULT 'general',
            user_need TEXT NOT NULL DEFAULT 'answer',
            strategy TEXT NOT NULL DEFAULT 'direct',
            depth TEXT NOT NULL DEFAULT 'standard',
            tone TEXT NOT NULL DEFAULT 'calm_warm_professional',
            explanation_style TEXT NOT NULL DEFAULT 'layered',
            address_policy TEXT NOT NULL DEFAULT 'rare',
            user_signals_json TEXT NOT NULL DEFAULT '{}',
            persona_runtime_json TEXT NOT NULL DEFAULT '{}',
            recent_openers_json TEXT NOT NULL DEFAULT '[]',
            assistant_message TEXT NOT NULL DEFAULT '',
            assistant_chars INTEGER NOT NULL DEFAULT 0,
            address_count INTEGER NOT NULL DEFAULT 0,
            opener_hash TEXT NOT NULL DEFAULT '',
            repetition_score REAL NOT NULL DEFAULT 0.0,
            persona_score REAL NOT NULL DEFAULT 0.0,
            outcome TEXT NOT NULL DEFAULT 'pending',
            outcome_score REAL,
            outcome_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            evaluated_at TEXT,
            UNIQUE(scope, request_id)
        );

        CREATE TABLE IF NOT EXISTS communication_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            preference_key TEXT NOT NULL,
            value_json TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.5,
            evidence_count INTEGER NOT NULL DEFAULT 1,
            source TEXT NOT NULL DEFAULT 'conversation',
            last_evidence TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, preference_key)
        );

        CREATE TABLE IF NOT EXISTS communication_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            skill_key TEXT NOT NULL,
            label TEXT NOT NULL,
            sample_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failure_count INTEGER NOT NULL DEFAULT 0,
            average_score REAL NOT NULL DEFAULT 0.0,
            recent_score REAL NOT NULL DEFAULT 0.0,
            baseline_score REAL NOT NULL DEFAULT 0.0,
            trend REAL NOT NULL DEFAULT 0.0,
            mastery REAL NOT NULL DEFAULT 0.0,
            stability REAL NOT NULL DEFAULT 0.0,
            freshness REAL NOT NULL DEFAULT 1.0,
            last_evidence_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, skill_key)
        );

        CREATE TABLE IF NOT EXISTS communication_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            turn_id INTEGER NOT NULL,
            feedback TEXT NOT NULL,
            score REAL NOT NULL DEFAULT 0.5,
            reason TEXT NOT NULL DEFAULT '',
            explicit INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(turn_id) REFERENCES communication_turns(id)
        );

        CREATE TABLE IF NOT EXISTS communication_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            event_type TEXT NOT NULL,
            turn_id INTEGER,
            score REAL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(turn_id) REFERENCES communication_turns(id)
        );

        CREATE INDEX IF NOT EXISTS idx_communication_turns_scope_created
        ON communication_turns(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_communication_turns_scope_outcome
        ON communication_turns(scope, outcome, id DESC);

        CREATE INDEX IF NOT EXISTS idx_communication_preferences_scope
        ON communication_preferences(scope, preference_key);

        CREATE INDEX IF NOT EXISTS idx_communication_skills_scope_mastery
        ON communication_skills(scope, mastery DESC, sample_count DESC);

        CREATE INDEX IF NOT EXISTS idx_communication_feedback_scope_created
        ON communication_feedback(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_communication_events_scope_created
        ON communication_events(scope, id DESC);
        """
    )


def _migration_023_document_intelligence(
    conn: sqlite3.Connection,
) -> None:
    """Document ingestion, provenance, versions, facts and semantic chunks."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS document_state (
            scope TEXT PRIMARY KEY,
            ingestion_score REAL NOT NULL DEFAULT 0.0,
            extraction_quality REAL NOT NULL DEFAULT 0.0,
            provenance_coverage REAL NOT NULL DEFAULT 0.0,
            semantic_coverage REAL NOT NULL DEFAULT 0.0,
            studied_documents INTEGER NOT NULL DEFAULT 0,
            queued_documents INTEGER NOT NULL DEFAULT 0,
            failed_documents INTEGER NOT NULL DEFAULT 0,
            duplicate_documents INTEGER NOT NULL DEFAULT 0,
            ocr_required_documents INTEGER NOT NULL DEFAULT 0,
            fact_count INTEGER NOT NULL DEFAULT 0,
            contradiction_count INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL DEFAULT '',
            extension TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            storage_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            parser TEXT NOT NULL DEFAULT '',
            parser_version TEXT NOT NULL DEFAULT '',
            document_type TEXT NOT NULL DEFAULT 'generic',
            family_key TEXT NOT NULL DEFAULT '',
            version_label TEXT NOT NULL DEFAULT '',
            version_rank INTEGER,
            duplicate_of_id INTEGER,
            previous_version_id INTEGER,
            quality_score REAL NOT NULL DEFAULT 0.0,
            extraction_coverage REAL NOT NULL DEFAULT 0.0,
            ocr_required INTEGER NOT NULL DEFAULT 0,
            page_count INTEGER NOT NULL DEFAULT 0,
            section_count INTEGER NOT NULL DEFAULT 0,
            chunk_count INTEGER NOT NULL DEFAULT 0,
            fact_count INTEGER NOT NULL DEFAULT 0,
            warning_count INTEGER NOT NULL DEFAULT 0,
            error_text TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            studied_at TEXT,
            UNIQUE(scope, sha256),
            FOREIGN KEY(duplicate_of_id) REFERENCES documents(id),
            FOREIGN KEY(previous_version_id) REFERENCES documents(id)
        );

        CREATE TABLE IF NOT EXISTS document_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            text_content TEXT NOT NULL DEFAULT '',
            char_count INTEGER NOT NULL DEFAULT 0,
            quality_score REAL NOT NULL DEFAULT 0.0,
            extraction_method TEXT NOT NULL DEFAULT '',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, page_number),
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS document_sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            parent_section_id INTEGER,
            heading TEXT NOT NULL DEFAULT '',
            level INTEGER NOT NULL DEFAULT 1,
            ordinal INTEGER NOT NULL DEFAULT 0,
            page_start INTEGER,
            page_end INTEGER,
            text_content TEXT NOT NULL DEFAULT '',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(parent_section_id) REFERENCES document_sections(id)
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            page_id INTEGER,
            section_id INTEGER,
            ordinal INTEGER NOT NULL DEFAULT 0,
            chunk_key TEXT NOT NULL,
            text_content TEXT NOT NULL,
            token_estimate INTEGER NOT NULL DEFAULT 0,
            quality_score REAL NOT NULL DEFAULT 0.0,
            content_hash TEXT NOT NULL,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, chunk_key),
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(page_id) REFERENCES document_pages(id),
            FOREIGN KEY(section_id) REFERENCES document_sections(id)
        );

        CREATE TABLE IF NOT EXISTS document_chunk_vectors (
            chunk_id INTEGER PRIMARY KEY,
            scope TEXT NOT NULL,
            model TEXT NOT NULL,
            dimensions INTEGER NOT NULL,
            vector_json TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS document_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            chunk_id INTEGER,
            fact_key TEXT NOT NULL,
            subject TEXT NOT NULL DEFAULT '',
            predicate TEXT NOT NULL DEFAULT '',
            value TEXT NOT NULL,
            normalized_value TEXT NOT NULL DEFAULT '',
            fact_type TEXT NOT NULL DEFAULT 'statement',
            confidence REAL NOT NULL DEFAULT 0.0,
            status TEXT NOT NULL DEFAULT 'candidate',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            promoted_claim_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(document_id, fact_key, normalized_value),
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
            FOREIGN KEY(chunk_id) REFERENCES document_chunks(id)
        );

        CREATE TABLE IF NOT EXISTS document_contradictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            family_key TEXT NOT NULL DEFAULT '',
            fact_key TEXT NOT NULL,
            left_fact_id INTEGER NOT NULL,
            right_fact_id INTEGER NOT NULL,
            severity REAL NOT NULL DEFAULT 0.5,
            status TEXT NOT NULL DEFAULT 'open',
            resolution TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TEXT,
            UNIQUE(scope, left_fact_id, right_fact_id),
            FOREIGN KEY(left_fact_id) REFERENCES document_facts(id),
            FOREIGN KEY(right_fact_id) REFERENCES document_facts(id)
        );

        CREATE TABLE IF NOT EXISTS document_ingestion_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            document_id INTEGER NOT NULL,
            trigger TEXT NOT NULL DEFAULT 'upload',
            status TEXT NOT NULL DEFAULT 'running',
            parser TEXT NOT NULL DEFAULT '',
            pages_extracted INTEGER NOT NULL DEFAULT 0,
            sections_extracted INTEGER NOT NULL DEFAULT 0,
            chunks_created INTEGER NOT NULL DEFAULT 0,
            facts_created INTEGER NOT NULL DEFAULT 0,
            contradictions_found INTEGER NOT NULL DEFAULT 0,
            embeddings_created INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            warnings_json TEXT NOT NULL DEFAULT '[]',
            error_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS document_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            document_id INTEGER,
            event_type TEXT NOT NULL,
            score REAL,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_documents_scope_status
        ON documents(scope, status, id DESC);

        CREATE INDEX IF NOT EXISTS idx_documents_scope_family
        ON documents(scope, family_key, version_rank DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_document_pages_document
        ON document_pages(document_id, page_number);

        CREATE INDEX IF NOT EXISTS idx_document_sections_document
        ON document_sections(document_id, ordinal);

        CREATE INDEX IF NOT EXISTS idx_document_chunks_scope_document
        ON document_chunks(scope, document_id, ordinal);

        CREATE INDEX IF NOT EXISTS idx_document_facts_scope_key
        ON document_facts(scope, fact_key, status, id DESC);

        CREATE INDEX IF NOT EXISTS idx_document_contradictions_scope_status
        ON document_contradictions(scope, status, severity DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_document_runs_scope_created
        ON document_ingestion_runs(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_document_events_scope_created
        ON document_events(scope, id DESC);
        """
    )



def _migration_024_response_grounding(
    conn: sqlite3.Connection,
) -> None:
    """Post-response grounding coverage and provenance audit."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS response_grounding_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id TEXT NOT NULL UNIQUE,
            scope TEXT NOT NULL,
            mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unscored',
            applicable INTEGER NOT NULL DEFAULT 0,
            overall REAL,
            claim_coverage REAL,
            provenance_coverage REAL,
            source_diversity REAL,
            contradiction_handling REAL,
            claims_total INTEGER NOT NULL DEFAULT 0,
            claims_supported INTEGER NOT NULL DEFAULT 0,
            claims_partial INTEGER NOT NULL DEFAULT 0,
            claims_unsupported INTEGER NOT NULL DEFAULT 0,
            source_groups INTEGER NOT NULL DEFAULT 0,
            source_types_json TEXT NOT NULL DEFAULT '[]',
            warnings_json TEXT NOT NULL DEFAULT '[]',
            claims_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_response_grounding_scope_created
        ON response_grounding_runs(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_response_grounding_scope_status
        ON response_grounding_runs(scope, applicable, status, id DESC);
        """
    )



def _migration_025_knowledge_lifecycle(
    conn: sqlite3.Connection,
) -> None:
    """Evidence-first knowledge and hypothesis lifecycle with immutable audit."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            claim_key TEXT NOT NULL,
            statement TEXT NOT NULL,
            origin_type TEXT NOT NULL DEFAULT 'evidence',
            origin_request_id TEXT NOT NULL DEFAULT '',
            last_request_id TEXT NOT NULL DEFAULT '',
            state TEXT NOT NULL DEFAULT 'observed',
            confidence REAL NOT NULL DEFAULT 0.0,
            support_score REAL NOT NULL DEFAULT 0.0,
            contradiction_score REAL NOT NULL DEFAULT 0.0,
            support_groups INTEGER NOT NULL DEFAULT 0,
            contradiction_groups INTEGER NOT NULL DEFAULT 0,
            observations INTEGER NOT NULL DEFAULT 1,
            verification_passes INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            verified_at TEXT,
            contradicted_at TEXT,
            superseded_at TEXT,
            superseded_by_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, claim_key),
            FOREIGN KEY(superseded_by_id) REFERENCES knowledge_claims(id)
        );

        CREATE TABLE IF NOT EXISTS knowledge_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            claim_id INTEGER NOT NULL,
            request_id TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            source_group TEXT NOT NULL DEFAULT '',
            stance TEXT NOT NULL DEFAULT 'support',
            confidence REAL NOT NULL DEFAULT 0.0,
            provenance_json TEXT NOT NULL DEFAULT '{}',
            content_hash TEXT NOT NULL,
            content_excerpt TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(claim_id, source_group, stance, content_hash),
            FOREIGN KEY(claim_id) REFERENCES knowledge_claims(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            claim_id INTEGER NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(claim_id) REFERENCES knowledge_claims(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS hypothesis_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            hypothesis_key TEXT NOT NULL,
            title TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'candidate',
            confidence REAL NOT NULL DEFAULT 0.0,
            support_groups INTEGER NOT NULL DEFAULT 0,
            opposition_groups INTEGER NOT NULL DEFAULT 0,
            observations INTEGER NOT NULL DEFAULT 1,
            verification_passes INTEGER NOT NULL DEFAULT 0,
            last_run_id INTEGER,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT,
            rejected_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, hypothesis_key),
            FOREIGN KEY(last_run_id) REFERENCES hypothesis_runs(id)
        );

        CREATE TABLE IF NOT EXISTS hypothesis_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            hypothesis_id INTEGER NOT NULL,
            request_id TEXT NOT NULL DEFAULT '',
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            source_group TEXT NOT NULL DEFAULT '',
            stance TEXT NOT NULL DEFAULT 'support',
            confidence REAL NOT NULL DEFAULT 0.0,
            content_hash TEXT NOT NULL,
            content_excerpt TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(hypothesis_id, source_group, stance, content_hash),
            FOREIGN KEY(hypothesis_id) REFERENCES hypothesis_registry(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS hypothesis_transitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            hypothesis_id INTEGER NOT NULL,
            from_state TEXT NOT NULL,
            to_state TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(hypothesis_id) REFERENCES hypothesis_registry(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS knowledge_learning_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            event_type TEXT NOT NULL,
            subject_type TEXT NOT NULL,
            subject_id INTEGER NOT NULL DEFAULT 0,
            summary TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0.0,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_claims_scope_state
        ON knowledge_claims(scope, state, confidence DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_knowledge_evidence_claim
        ON knowledge_evidence(claim_id, stance, source_group);

        CREATE INDEX IF NOT EXISTS idx_knowledge_transitions_scope_created
        ON knowledge_transitions(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_hypothesis_registry_scope_state
        ON hypothesis_registry(scope, state, confidence DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_hypothesis_evidence_subject
        ON hypothesis_evidence(hypothesis_id, stance, source_group);

        CREATE INDEX IF NOT EXISTS idx_hypothesis_transitions_scope_created
        ON hypothesis_transitions(scope, id DESC);

        CREATE INDEX IF NOT EXISTS idx_knowledge_learning_scope_created
        ON knowledge_learning_events(scope, id DESC);
        """
    )



def _migration_026_canonical_facts(
    conn: sqlite3.Connection,
) -> None:
    """Canonical facts, value history, evidence fusion and strict lineage."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS canonical_facts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            namespace TEXT NOT NULL DEFAULT 'general',
            subject TEXT NOT NULL DEFAULT '',
            predicate TEXT NOT NULL DEFAULT '',
            fact_type TEXT NOT NULL DEFAULT 'statement',
            state TEXT NOT NULL DEFAULT 'observed',
            confidence REAL NOT NULL DEFAULT 0.0,
            current_value_id INTEGER,
            current_value TEXT NOT NULL DEFAULT '',
            current_normalized_value TEXT NOT NULL DEFAULT '',
            active_values INTEGER NOT NULL DEFAULT 0,
            independent_groups INTEGER NOT NULL DEFAULT 0,
            evidence_count INTEGER NOT NULL DEFAULT 0,
            conflict_count INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            verified_at TEXT,
            conflicted_at TEXT,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(scope, canonical_key)
        );

        CREATE TABLE IF NOT EXISTS canonical_fact_values (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            fact_id INTEGER NOT NULL,
            normalized_value TEXT NOT NULL,
            display_value TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'observed',
            confidence REAL NOT NULL DEFAULT 0.0,
            independent_groups INTEGER NOT NULL DEFAULT 0,
            source_types INTEGER NOT NULL DEFAULT 0,
            active_evidence INTEGER NOT NULL DEFAULT 0,
            contradiction_groups INTEGER NOT NULL DEFAULT 0,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            superseded_at TEXT,
            superseded_by_value_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fact_id, normalized_value),
            FOREIGN KEY(fact_id) REFERENCES canonical_facts(id) ON DELETE CASCADE,
            FOREIGN KEY(superseded_by_value_id) REFERENCES canonical_fact_values(id)
        );

        CREATE TABLE IF NOT EXISTS canonical_fact_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            fact_id INTEGER NOT NULL,
            value_id INTEGER NOT NULL,
            source_type TEXT NOT NULL,
            source_ref TEXT NOT NULL,
            source_group TEXT NOT NULL,
            independence_group TEXT NOT NULL,
            source_record_type TEXT NOT NULL DEFAULT '',
            source_record_id INTEGER,
            stance TEXT NOT NULL DEFAULT 'support',
            is_independent INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL DEFAULT 0.0,
            lineage_root TEXT NOT NULL DEFAULT '',
            provenance_json TEXT NOT NULL DEFAULT '{}',
            content_excerpt TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(value_id, source_type, source_ref, stance),
            FOREIGN KEY(fact_id) REFERENCES canonical_facts(id) ON DELETE CASCADE,
            FOREIGN KEY(value_id) REFERENCES canonical_fact_values(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS canonical_fact_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            fact_id INTEGER NOT NULL,
            value_id INTEGER,
            linked_type TEXT NOT NULL,
            linked_id INTEGER,
            linked_key TEXT NOT NULL DEFAULT '',
            relation TEXT NOT NULL DEFAULT 'lineage',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fact_id, linked_type, linked_id, linked_key, relation),
            FOREIGN KEY(fact_id) REFERENCES canonical_facts(id) ON DELETE CASCADE,
            FOREIGN KEY(value_id) REFERENCES canonical_fact_values(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS canonical_fact_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            fact_id INTEGER NOT NULL,
            value_id INTEGER,
            event_type TEXT NOT NULL,
            from_state TEXT NOT NULL DEFAULT '',
            to_state TEXT NOT NULL DEFAULT '',
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(fact_id) REFERENCES canonical_facts(id) ON DELETE CASCADE,
            FOREIGN KEY(value_id) REFERENCES canonical_fact_values(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_canonical_facts_scope_state
        ON canonical_facts(scope, state, confidence DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_canonical_values_fact_state
        ON canonical_fact_values(fact_id, state, confidence DESC, id DESC);

        CREATE INDEX IF NOT EXISTS idx_canonical_evidence_fact_active
        ON canonical_fact_evidence(fact_id, active, stance, independence_group);

        CREATE INDEX IF NOT EXISTS idx_canonical_evidence_source
        ON canonical_fact_evidence(scope, source_type, source_record_id, active);

        CREATE INDEX IF NOT EXISTS idx_canonical_links_fact
        ON canonical_fact_links(fact_id, linked_type, active);

        CREATE INDEX IF NOT EXISTS idx_canonical_events_scope_created
        ON canonical_fact_events(scope, id DESC);
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
    (20, "evolution_engine", _migration_020_evolution_engine),
    (21, "autonomous_research", _migration_021_autonomous_research),
    (22, "communication_intelligence", _migration_022_communication_intelligence),
    (23, "document_intelligence", _migration_023_document_intelligence),
    (24, "response_grounding", _migration_024_response_grounding),
    (25, "knowledge_lifecycle", _migration_025_knowledge_lifecycle),
    (26, "canonical_facts", _migration_026_canonical_facts),
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
