from __future__ import annotations

import sqlite3
from collections.abc import Callable

Migration = tuple[int, str, Callable[[sqlite3.Connection], None]]

LATEST_SCHEMA_VERSION = 2


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


MIGRATIONS: tuple[Migration, ...] = (
    (1, "baseline_0_0_3", _migration_001_baseline),
    (2, "living_core_runtime_indexes", _migration_002_runtime_indexes),
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
