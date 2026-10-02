from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'data'
DB_PATH = DATA_DIR / 'aishin.db'

MODULES = [
    ('assistant', 'Aishin Kitsune', 'Личная помощница'),
    ('account', 'Личный кабинет', 'Профиль и персональные настройки'),
    ('mobile', 'Мобильное приложение', 'Связь с мобильным клиентом'),
    ('workspace', 'Рабочее пространство', 'Проекты, документы и рабочие инструменты'),
]


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row['name'] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _ensure_column(conn: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name not in _columns(conn, table):
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')


def init_db() -> None:
    with connect() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS runtime_state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'personal',
                payload_json TEXT NOT NULL DEFAULT '{}',
                importance REAL NOT NULL DEFAULT 0.5,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                scope TEXT NOT NULL DEFAULT 'personal',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                data_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scope, entity_type, canonical_name)
            );

            CREATE TABLE IF NOT EXISTS relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                source_entity_id INTEGER NOT NULL,
                relation_type TEXT NOT NULL,
                target_entity_id INTEGER NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                evidence TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(scope, source_entity_id, relation_type, target_entity_id),
                FOREIGN KEY(source_entity_id) REFERENCES entities(id),
                FOREIGN KEY(target_entity_id) REFERENCES entities(id)
            );

            CREATE TABLE IF NOT EXISTS permissions (
                capability TEXT PRIMARY KEY,
                mode TEXT NOT NULL DEFAULT 'ask',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS master_profile (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'explicit_user',
                confidence REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS relationship_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                importance REAL NOT NULL DEFAULT 0.7,
                confidence REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'conversation',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS personal_timeline (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                details TEXT NOT NULL DEFAULT '',
                scope TEXT NOT NULL DEFAULT 'personal',
                importance REAL NOT NULL DEFAULT 0.5,
                occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                memory_id INTEGER,
                action TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                before_json TEXT,
                after_json TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS memory_vectors (
                memory_id INTEGER PRIMARY KEY,
                scope TEXT NOT NULL,
                model TEXT NOT NULL,
                dimensions INTEGER NOT NULL,
                vector_json TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(memory_id) REFERENCES memories(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS update_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                details TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        _ensure_column(conn, 'memories', 'importance', 'REAL NOT NULL DEFAULT 0.5')
        _ensure_column(conn, 'memories', 'tags_json', "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(conn, 'memories', 'source', "TEXT NOT NULL DEFAULT 'unknown'")
        _ensure_column(conn, 'memories', 'last_accessed_at', 'TEXT')
        _ensure_column(conn, 'memories', 'fingerprint', 'TEXT')
        _ensure_column(conn, 'memories', 'memory_key', 'TEXT')
        _ensure_column(conn, 'memories', 'status', "TEXT NOT NULL DEFAULT 'active'")
        _ensure_column(conn, 'memories', 'superseded_by', 'INTEGER')
        _ensure_column(conn, 'relationship_memory', 'fingerprint', 'TEXT')
        _ensure_column(conn, 'relationship_memory', 'status', "TEXT NOT NULL DEFAULT 'active'")
        conn.executemany('''
            INSERT INTO modules(code, title, description)
            VALUES (?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                description = excluded.description
        ''', MODULES)

        conn.execute(
            """INSERT OR IGNORE INTO master_profile(key, value_json, source, confidence)
               VALUES (?, ?, ?, ?)""",
            ("primary_address", json.dumps("Господин", ensure_ascii=False), "project_foundation", 1.0),
        )
        conn.execute(
            """INSERT OR IGNORE INTO master_profile(key, value_json, source, confidence)
               VALUES (?, ?, ?, ?)""",
            ("assistant_mode", json.dumps("personal_single_owner", ensure_ascii=False), "project_foundation", 1.0),
        )

        seed_key = "personal_aishin_relationship_seed_v1"
        seeded = conn.execute("SELECT 1 FROM settings WHERE key=?", (seed_key,)).fetchone()
        if not seeded:
            shared = "Айшин и Господин вместе создают и развивают проект Aishin."
            conn.execute(
                """INSERT INTO relationship_memory(kind, content, importance, confidence, source)
                   VALUES (?, ?, ?, ?, ?)""",
                ("shared_project_principle", shared, 1.0, 1.0, "explicit_user"),
            )
            conn.execute(
                """INSERT INTO personal_timeline(event_type, title, details, scope, importance)
                   VALUES (?, ?, ?, ?, ?)""",
                ("shared_project_principle", "Совместное развитие Aishin", shared, "relationship", 1.0),
            )
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?)",
                (seed_key, "1"),
            )

        conn.commit()


def list_modules() -> list[dict]:
    with connect() as conn:
        rows = conn.execute('SELECT code, title, description, enabled FROM modules ORDER BY id').fetchall()
    return [dict(row) for row in rows]


def record_update(status: str, details: str) -> None:
    with connect() as conn:
        conn.execute('INSERT INTO update_history(status, details) VALUES (?, ?)', (status, details))
        conn.commit()


def set_runtime_state(key: str, value: dict) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    with connect() as conn:
        conn.execute('''
            INSERT INTO runtime_state(key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json=excluded.value_json,
                updated_at=CURRENT_TIMESTAMP
        ''', (key, payload))
        conn.commit()


def get_runtime_state(key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute('SELECT value_json FROM runtime_state WHERE key=?', (key,)).fetchone()
    return json.loads(row['value_json']) if row else None


def add_event(event_type: str, scope: str, payload: dict, importance: float) -> int:
    with connect() as conn:
        cur = conn.execute('INSERT INTO events(event_type, scope, payload_json, importance) VALUES (?, ?, ?, ?)', (event_type, scope, json.dumps(payload, ensure_ascii=False), importance))
        conn.commit()
        return int(cur.lastrowid)


def recent_events(limit: int = 30) -> list[dict]:
    with connect() as conn:
        rows = conn.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    result=[]
    for row in rows:
        item=dict(row); item['payload']=json.loads(item.pop('payload_json')); result.append(item)
    return result


def add_message(role: str, content: str, scope: str = 'personal') -> int:
    with connect() as conn:
        cur=conn.execute('INSERT INTO messages(role, content, scope) VALUES (?, ?, ?)', (role, content, scope))
        conn.commit(); return int(cur.lastrowid)


def recent_messages(limit: int = 20, scope: str | None = None) -> list[dict]:
    with connect() as conn:
        if scope:
            rows=conn.execute('SELECT * FROM messages WHERE scope=? ORDER BY id DESC LIMIT ?', (scope, limit)).fetchall()
        else:
            rows=conn.execute('SELECT * FROM messages ORDER BY id DESC LIMIT ?', (limit,)).fetchall()
    return [dict(row) for row in reversed(rows)]


def add_memory(*, scope: str, kind: str, content: str, confidence: float, importance: float, tags: list[str], source: str, fingerprint: str | None = None, memory_key: str | None = None) -> int:
    with connect() as conn:
        cur=conn.execute('''
            INSERT INTO memories(scope, kind, content, confidence, importance, tags_json, source, fingerprint, memory_key)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (scope, kind, content, confidence, importance, json.dumps(tags, ensure_ascii=False), source, fingerprint, memory_key))
        conn.commit(); return int(cur.lastrowid)


def _memory_row(row: sqlite3.Row) -> dict:
    item=dict(row)
    item['tags']=json.loads(item.pop('tags_json') or '[]')
    return item


def recent_memories(scope: str = 'personal', limit: int = 12) -> list[dict]:
    with connect() as conn:
        rows=conn.execute("SELECT * FROM memories WHERE scope=? AND status='active' ORDER BY importance DESC, id DESC LIMIT ?", (scope, limit)).fetchall()
    return [_memory_row(row) for row in rows]


def search_memories(terms: list[str], scope: str = 'personal', limit: int = 8) -> list[dict]:
    if not terms:
        return recent_memories(scope, limit)
    where=' OR '.join(['LOWER(content) LIKE ?' for _ in terms])
    params=[f'%{term.lower()}%' for term in terms]
    with connect() as conn:
        rows=conn.execute(f'''SELECT * FROM memories WHERE scope=? AND status='active' AND ({where}) ORDER BY importance DESC, confidence DESC, id DESC LIMIT ?''', [scope, *params, limit]).fetchall()
    return [_memory_row(row) for row in rows]


def touch_memory(memory_id: int) -> None:
    with connect() as conn:
        conn.execute('UPDATE memories SET last_accessed_at=CURRENT_TIMESTAMP WHERE id=?', (memory_id,))
        conn.commit()


def upsert_entity(scope: str, entity_type: str, canonical_name: str, data: dict | None = None) -> int:
    payload = json.dumps(data or {}, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """INSERT INTO entities(scope, entity_type, canonical_name, data_json)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(scope, entity_type, canonical_name)
               DO UPDATE SET data_json=excluded.data_json, updated_at=CURRENT_TIMESTAMP""",
            (scope, entity_type, canonical_name, payload),
        )
        row = conn.execute(
            "SELECT id FROM entities WHERE scope=? AND entity_type=? AND canonical_name=?",
            (scope, entity_type, canonical_name),
        ).fetchone()
        conn.commit()
        return int(row["id"])


def add_relation(scope: str, source_id: int, relation_type: str, target_id: int, confidence: float = 1.0, evidence: str = "") -> int:
    with connect() as conn:
        conn.execute(
            """INSERT INTO relations(scope, source_entity_id, relation_type, target_entity_id, confidence, evidence)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(scope, source_entity_id, relation_type, target_entity_id)
               DO UPDATE SET confidence=excluded.confidence, evidence=excluded.evidence""",
            (scope, source_id, relation_type, target_id, confidence, evidence),
        )
        row = conn.execute(
            """SELECT id FROM relations
               WHERE scope=? AND source_entity_id=? AND relation_type=? AND target_entity_id=?""",
            (scope, source_id, relation_type, target_id),
        ).fetchone()
        conn.commit()
        return int(row["id"])


def graph_neighborhood(entity_id: int, scope: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT r.relation_type, r.confidence, r.evidence,
                      s.id AS source_id, s.entity_type AS source_type, s.canonical_name AS source_name,
                      t.id AS target_id, t.entity_type AS target_type, t.canonical_name AS target_name
               FROM relations r
               JOIN entities s ON s.id=r.source_entity_id
               JOIN entities t ON t.id=r.target_entity_id
               WHERE r.scope=? AND (r.source_entity_id=? OR r.target_entity_id=?)
               ORDER BY r.confidence DESC, r.id DESC""",
            (scope, entity_id, entity_id),
        ).fetchall()
    return [dict(row) for row in rows]


def set_permission(capability: str, mode: str) -> None:
    if mode not in {"allow", "ask", "deny"}:
        raise ValueError("permission mode must be allow, ask or deny")
    with connect() as conn:
        conn.execute(
            """INSERT INTO permissions(capability, mode, updated_at)
               VALUES (?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(capability) DO UPDATE SET mode=excluded.mode, updated_at=CURRENT_TIMESTAMP""",
            (capability, mode),
        )
        conn.commit()


def get_permission(capability: str) -> str:
    with connect() as conn:
        row = conn.execute("SELECT mode FROM permissions WHERE capability=?", (capability,)).fetchone()
    return row["mode"] if row else "ask"


def ensure_permission(capability: str, mode: str) -> None:
    if mode not in {"allow", "ask", "deny"}:
        raise ValueError("permission mode must be allow, ask or deny")
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO permissions(capability, mode) VALUES (?, ?)",
            (capability, mode),
        )
        conn.commit()


def set_master_profile_value(key: str, value, source: str = "explicit_user", confidence: float = 1.0) -> None:
    payload = json.dumps(value, ensure_ascii=False)
    with connect() as conn:
        conn.execute(
            """INSERT INTO master_profile(key, value_json, source, confidence, updated_at)
               VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(key) DO UPDATE SET
                 value_json=excluded.value_json,
                 source=excluded.source,
                 confidence=excluded.confidence,
                 updated_at=CURRENT_TIMESTAMP""",
            (key, payload, source, confidence),
        )
        conn.commit()


def get_master_profile() -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value_json, source, confidence, updated_at FROM master_profile ORDER BY key"
        ).fetchall()
    result = {}
    for row in rows:
        result[row["key"]] = {
            "value": json.loads(row["value_json"]),
            "source": row["source"],
            "confidence": row["confidence"],
            "updated_at": row["updated_at"],
        }
    return result


def add_relationship_memory(kind: str, content: str, importance: float = 0.7, confidence: float = 1.0, source: str = "conversation", fingerprint: str | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO relationship_memory(kind, content, importance, confidence, source, fingerprint)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (kind, content, importance, confidence, source, fingerprint),
        )
        conn.commit()
        return int(cur.lastrowid)


def recent_relationship_memories(limit: int = 12) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM relationship_memory
               WHERE status='active'
               ORDER BY importance DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def add_timeline_event(event_type: str, title: str, details: str = "", scope: str = "personal", importance: float = 0.5, occurred_at: str | None = None) -> int:
    with connect() as conn:
        if occurred_at:
            cur = conn.execute(
                """INSERT INTO personal_timeline(event_type, title, details, scope, importance, occurred_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event_type, title, details, scope, importance, occurred_at),
            )
        else:
            cur = conn.execute(
                """INSERT INTO personal_timeline(event_type, title, details, scope, importance)
                   VALUES (?, ?, ?, ?, ?)""",
                (event_type, title, details, scope, importance),
            )
        conn.commit()
        return int(cur.lastrowid)


def recent_timeline(limit: int = 20, scope: str | None = None) -> list[dict]:
    with connect() as conn:
        if scope:
            rows = conn.execute(
                """SELECT * FROM personal_timeline
                   WHERE scope=? ORDER BY occurred_at DESC, id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM personal_timeline
                   ORDER BY occurred_at DESC, id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def find_memory_by_fingerprint(scope: str, fingerprint: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM memories
               WHERE scope=? AND fingerprint=? AND status='active'
               ORDER BY id DESC LIMIT 1""",
            (scope, fingerprint),
        ).fetchone()
    return _memory_row(row) if row else None


def find_active_memory_by_key(scope: str, memory_key: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM memories
               WHERE scope=? AND memory_key=? AND status='active'
               ORDER BY id DESC LIMIT 1""",
            (scope, memory_key),
        ).fetchone()
    return _memory_row(row) if row else None


def active_memories_for_scope(scope: str, limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT * FROM memories
               WHERE scope=? AND status='active'
               ORDER BY id DESC LIMIT ?""",
            (scope, limit),
        ).fetchall()
    return [_memory_row(row) for row in rows]


def update_memory_strength(memory_id: int, *, confidence: float, importance: float) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE memories
               SET confidence=?, importance=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (confidence, importance, memory_id),
        )
        conn.commit()


def supersede_memory(old_memory_id: int, new_memory_id: int) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE memories
               SET status='superseded', superseded_by=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (new_memory_id, old_memory_id),
        )
        conn.commit()


def log_memory_change(scope: str, memory_id: int | None, action: str, reason: str = "", before: dict | None = None, after: dict | None = None) -> int:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO memory_changes(scope, memory_id, action, reason, before_json, after_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                scope,
                memory_id,
                action,
                reason,
                json.dumps(before, ensure_ascii=False) if before is not None else None,
                json.dumps(after, ensure_ascii=False) if after is not None else None,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def recent_memory_changes(limit: int = 30) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM memory_changes ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        if item.get("before_json"):
            item["before"] = json.loads(item.pop("before_json"))
        else:
            item.pop("before_json", None)
        if item.get("after_json"):
            item["after"] = json.loads(item.pop("after_json"))
        else:
            item.pop("after_json", None)
        result.append(item)
    return result


def find_relationship_by_fingerprint(fingerprint: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            """SELECT * FROM relationship_memory
               WHERE fingerprint=? AND status='active'
               ORDER BY id DESC LIMIT 1""",
            (fingerprint,),
        ).fetchone()
    return dict(row) if row else None


def update_relationship_strength(memory_id: int, *, confidence: float, importance: float) -> None:
    with connect() as conn:
        conn.execute(
            """UPDATE relationship_memory
               SET confidence=?, importance=?, updated_at=CURRENT_TIMESTAMP
               WHERE id=?""",
            (confidence, importance, memory_id),
        )
        conn.commit()


def upsert_memory_vector(memory_id: int, scope: str, model: str, vector: list[float], content_hash: str) -> None:
    with connect() as conn:
        conn.execute(
            """INSERT INTO memory_vectors(memory_id, scope, model, dimensions, vector_json, content_hash, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(memory_id) DO UPDATE SET
                 scope=excluded.scope,
                 model=excluded.model,
                 dimensions=excluded.dimensions,
                 vector_json=excluded.vector_json,
                 content_hash=excluded.content_hash,
                 updated_at=CURRENT_TIMESTAMP""",
            (memory_id, scope, model, len(vector), json.dumps(vector), content_hash),
        )
        conn.commit()


def get_memory_vector(memory_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM memory_vectors WHERE memory_id=?",
            (memory_id,),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["vector"] = json.loads(item.pop("vector_json"))
    return item


def active_memory_vectors(scope: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT m.*, v.model AS vector_model, v.dimensions, v.vector_json, v.content_hash
               FROM memories m
               JOIN memory_vectors v ON v.memory_id=m.id
               WHERE m.scope=? AND m.status='active'""",
            (scope,),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item.pop("tags_json") or "[]")
        item["vector"] = json.loads(item.pop("vector_json"))
        result.append(item)
    return result


def active_memories_missing_vector(scope: str, model: str, limit: int = 64) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """SELECT m.*
               FROM memories m
               LEFT JOIN memory_vectors v ON v.memory_id=m.id
               WHERE m.scope=? AND m.status='active'
                 AND (v.memory_id IS NULL OR v.model<>?)
               ORDER BY m.id ASC
               LIMIT ?""",
            (scope, model, limit),
        ).fetchall()
    return [_memory_row(row) for row in rows]
