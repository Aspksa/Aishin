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

from .core.engine import AishinEngine
from .core.heartbeat import Heartbeat
from .db import init_db, list_modules, record_update
from .personality import personality

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent

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
        'state': engine.state.load().to_dict(),
        'permissions': {k: engine.permissions.mode(k) for k in engine.permissions.SAFE_DEFAULTS},
        'observations': [o.__dict__ for o in engine.observer.inspect()],
    }


@app.get('/api/assistant/memory')
def assistant_memory(scope: str = 'personal', limit: int = 20) -> list[dict]:
    limit = max(1, min(limit, 100))
    return engine.memory.recent(scope=scope, limit=limit)


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
