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
        conn.executemany('''
            INSERT INTO modules(code, title, description)
            VALUES (?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                description = excluded.description
        ''', MODULES)
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


def add_memory(*, scope: str, kind: str, content: str, confidence: float, importance: float, tags: list[str], source: str) -> int:
    with connect() as conn:
        cur=conn.execute('''
            INSERT INTO memories(scope, kind, content, confidence, importance, tags_json, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (scope, kind, content, confidence, importance, json.dumps(tags, ensure_ascii=False), source))
        conn.commit(); return int(cur.lastrowid)


def _memory_row(row: sqlite3.Row) -> dict:
    item=dict(row)
    item['tags']=json.loads(item.pop('tags_json') or '[]')
    return item


def recent_memories(scope: str = 'personal', limit: int = 12) -> list[dict]:
    with connect() as conn:
        rows=conn.execute('SELECT * FROM memories WHERE scope=? ORDER BY importance DESC, id DESC LIMIT ?', (scope, limit)).fetchall()
    return [_memory_row(row) for row in rows]


def search_memories(terms: list[str], scope: str = 'personal', limit: int = 8) -> list[dict]:
    if not terms:
        return recent_memories(scope, limit)
    where=' OR '.join(['LOWER(content) LIKE ?' for _ in terms])
    params=[f'%{term.lower()}%' for term in terms]
    with connect() as conn:
        rows=conn.execute(f'''SELECT * FROM memories WHERE scope=? AND ({where}) ORDER BY importance DESC, confidence DESC, id DESC LIMIT ?''', [scope, *params, limit]).fetchall()
    return [_memory_row(row) for row in rows]


def touch_memory(memory_id: int) -> None:
    with connect() as conn:
        conn.execute('UPDATE memories SET last_accessed_at=CURRENT_TIMESTAMP WHERE id=?', (memory_id,))
        conn.commit()
