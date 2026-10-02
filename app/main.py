from __future__ import annotations

import asyncio
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel
from dotenv import load_dotenv

from .core.engine import AishinEngine
from .core.heartbeat import Heartbeat
from .db import init_db, list_modules, record_update
from .personality import personality

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT / '.env')

templates = Environment(
    loader=FileSystemLoader(APP_DIR / 'templates'),
    autoescape=select_autoescape(['html', 'xml']),
)

engine = AishinEngine()
heartbeat = Heartbeat(interval_seconds=60)
heartbeat_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global heartbeat_task
    init_db()
    engine.startup()
    heartbeat_task = asyncio.create_task(heartbeat.run())
    try:
        yield
    finally:
        heartbeat.stop()
        if heartbeat_task:
            await heartbeat_task


app = FastAPI(title='Aishin Kitsune', version='0.0.3', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=APP_DIR / 'static'), name='static')


class ChatMessage(BaseModel):
    message: str
    scope: str = 'personal'


class MasterProfileUpdate(BaseModel):
    key: str
    value: object
    confidence: float = 1.0


class RelationshipMemoryCreate(BaseModel):
    content: str
    kind: str = 'shared_history'
    importance: float = 0.8
    confidence: float = 1.0


class TimelineEventCreate(BaseModel):
    event_type: str
    title: str
    details: str = ''
    scope: str = 'personal'
    importance: float = 0.5


@app.get('/', response_class=HTMLResponse)
def home() -> str:
    template = templates.get_template('index.html')
    return template.render(title='Aishin Kitsune', modules=list_modules(), profile=personality.public_summary())


@app.get('/health')
def health() -> dict:
    state = engine.state.load()
    return {
        'status': 'ok',
        'name': personality.name,
        'version': '0.0.3',
        'runtime': state.to_dict(),
        'ai': engine.ai.health(),
        'semantic_memory': engine.semantic.health(),
    }


@app.get('/api/modules')
def modules() -> list[dict]:
    return list_modules()


@app.get('/api/assistant/profile')
def assistant_profile() -> dict:
    return personality.public_summary()


@app.get('/api/assistant/state')
def assistant_state() -> dict:
    return engine.snapshot()


@app.get('/api/assistant/brain')
def assistant_brain() -> dict:
    return {
        'ai': engine.ai.health(),
        'semantic_memory': engine.semantic.health(),
        'state': engine.state.load().to_dict(),
        'permissions': {k: engine.permissions.mode(k) for k in engine.permissions.SAFE_DEFAULTS},
        'observations': [o.__dict__ for o in engine.observer.inspect()],
    }


@app.get('/api/assistant/personal')
def assistant_personal() -> dict:
    state = engine.state.load()
    context = engine.personal.context(scope=state.current_scope)
    return {
        'master_profile': context.master_profile,
        'relationship_memory': context.relationship_memory,
        'timeline': context.timeline,
    }


@app.post('/api/assistant/master-profile')
def update_master_profile(payload: MasterProfileUpdate) -> dict:
    key = payload.key.strip()
    if not key:
        raise HTTPException(status_code=400, detail='Ключ профиля пустой')
    confidence = max(0.0, min(1.0, payload.confidence))
    engine.personal.set_profile_value(
        key,
        payload.value,
        source='explicit_user',
        confidence=confidence,
    )
    engine.events.emit(
        'master_profile.updated',
        scope='personal',
        payload={'key': key, 'confidence': confidence},
        importance=0.7,
    )
    return {'status': 'saved', 'key': key}


@app.post('/api/assistant/relationship-memory')
def create_relationship_memory(payload: RelationshipMemoryCreate) -> dict:
    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail='Память пустая')
    memory_id = engine.personal.remember_relationship(
        content,
        kind=payload.kind.strip() or 'shared_history',
        importance=max(0.0, min(1.0, payload.importance)),
        confidence=max(0.0, min(1.0, payload.confidence)),
        source='explicit_user',
    )
    engine.personal.add_timeline(
        event_type='relationship_memory',
        title='Важная совместная память',
        details=content,
        scope='relationship',
        importance=max(0.0, min(1.0, payload.importance)),
    )
    return {'status': 'saved', 'id': memory_id}


@app.post('/api/assistant/timeline')
def create_timeline_event(payload: TimelineEventCreate) -> dict:
    event_id = engine.personal.add_timeline(
        event_type=payload.event_type.strip() or 'event',
        title=payload.title.strip(),
        details=payload.details.strip(),
        scope=payload.scope.strip() or 'personal',
        importance=max(0.0, min(1.0, payload.importance)),
    )
    return {'status': 'saved', 'id': event_id}


@app.get('/api/assistant/memory')
def assistant_memory(scope: str = 'personal', limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    return engine.memory.recent(scope=scope, limit=limit)


@app.get('/api/assistant/semantic-search')
def assistant_semantic_search(
    query: str,
    scope: str = 'personal',
    limit: int = 8,
) -> list[dict]:
    text = query.strip()
    if not text:
        raise HTTPException(status_code=400, detail='Поисковый запрос пустой')
    limit = max(1, min(limit, 30))
    return engine.semantic.search(text, scope=scope, limit=limit)


@app.post('/api/assistant/semantic-index')
def assistant_semantic_index(scope: str = 'personal') -> dict:
    return engine.semantic.ensure_index(scope=scope, batch_size=64)


@app.get('/api/assistant/memory-changes')
def assistant_memory_changes(limit: int = 30) -> list[dict]:
    limit = max(1, min(limit, 100))
    return engine.memory.recent_changes(limit=limit)


@app.post('/api/assistant/message')
def assistant_message(payload: ChatMessage) -> dict:
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=400, detail='Сообщение пустое')
    scope = payload.scope.strip() or 'personal'
    return engine.respond(text, scope=scope)


def _local_only(request: Request) -> None:
    host = request.client.host if request.client else ''
    if host not in {'127.0.0.1', '::1', 'localhost'}:
        raise HTTPException(status_code=403, detail='Обновление разрешено только локально')


@app.post('/api/system/update')
def system_update(request: Request) -> dict:
    _local_only(request)
    engine.events.emit('system.update.started', importance=0.5)
    try:
        fetch = subprocess.run(['git', 'fetch', 'origin', 'main'], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        pull = subprocess.run(['git', 'pull', '--ff-only', 'origin', 'main'], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True)
        details = (fetch.stdout + '\n' + pull.stdout).strip() or 'Обновление проверено'
        record_update('success', details)
        engine.events.emit('system.update.completed', payload={'details': details[:500]}, importance=0.6)
        return {'status': 'success', 'details': details}
    except Exception as exc:
        details = str(exc)
        record_update('error', details)
        engine.events.emit('system.update.failed', payload={'error': details[:500]}, importance=0.9)
        raise HTTPException(status_code=500, detail=details)
