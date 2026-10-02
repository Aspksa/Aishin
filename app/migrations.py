from __future__ import annotations

import sqlite3
from collections.abc import Callable

Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]

LATEST_SCHEMA_VERSION = 9


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
