from __future__ import annotations

import asyncio
import subprocess
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field
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
heartbeat: Heartbeat | None = None
heartbeat_task: asyncio.Task | None = None
learning_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global heartbeat, heartbeat_task, learning_task
    init_db()
    engine.startup()
    heartbeat = Heartbeat(
        interval_seconds=60,
        planner=engine.planner,
        sensors=engine.sensors,
        proactive=engine.proactive,
    )
    heartbeat_task = asyncio.create_task(heartbeat.run())
    learning_task = asyncio.create_task(
        engine.continuous_learning.run()
    )
    try:
        yield
    finally:
        if heartbeat is not None:
            heartbeat.stop()
        engine.continuous_learning.stop()
        if heartbeat_task:
            await heartbeat_task
        if learning_task:
            await learning_task


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


class GoalCreate(BaseModel):
    title: str
    description: str = ''
    scope: str = 'personal'
    priority: float = 0.5
    due_at: str | None = None


class TaskCreate(BaseModel):
    title: str
    description: str = ''
    scope: str = 'personal'
    goal_id: int | None = None
    priority: float = 0.5
    due_at: str | None = None


class TaskDependencyCreate(BaseModel):
    scope: str = 'personal'
    task_id: int
    depends_on_task_id: int


class StatusUpdate(BaseModel):
    scope: str = 'personal'
    status: str
    blocked_reason: str = ''


class ToolInvoke(BaseModel):
    scope: str = 'personal'
    arguments: dict = Field(default_factory=dict)
    dry_run: bool = True
    approved: bool = False


class PermissionUpdate(BaseModel):
    mode: str


class DecisionAction(BaseModel):
    scope: str = 'personal'
    execute: bool = False
    reason: str = ''


class RollbackAction(BaseModel):
    scope: str = 'personal'
    approved: bool = False


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
        'ai_resilience': engine.ai.diagnostics(),
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
        'planner': {
            'open_items': engine.planner.open_items(scope=engine.state.load().current_scope),
            'notices': [
                notice.__dict__
                for notice in engine.planner.inspect(scope=engine.state.load().current_scope)
            ],
        },
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


@app.get('/api/assistant/graph/entities')
def assistant_graph_entities(
    scope: str = 'personal',
    limit: int = 100,
    entity_type: str | None = None,
) -> list[dict]:
    limit = max(1, min(limit, 500))
    return engine.graph.entities(
        scope=scope,
        limit=limit,
        entity_type=entity_type,
    )


@app.get('/api/assistant/graph/relations')
def assistant_graph_relations(
    scope: str = 'personal',
    limit: int = 200,
) -> list[dict]:
    limit = max(1, min(limit, 500))
    return engine.graph.relations(scope=scope, limit=limit)


@app.get('/api/assistant/graph/search')
def assistant_graph_search(
    query: str,
    scope: str = 'personal',
    limit: int = 20,
) -> list[dict]:
    text = query.strip()
    if not text:
        raise HTTPException(status_code=400, detail='Поисковый запрос пустой')
    return engine.graph.search(text, scope=scope, limit=max(1, min(limit, 100)))


@app.get('/api/assistant/graph/stats')
def assistant_graph_stats(scope: str = 'personal') -> dict:
    return engine.graph.stats(scope=scope)


@app.get('/api/assistant/graph/changes')
def assistant_graph_changes(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.graph.changes(scope=scope, limit=max(1, min(limit, 100)))


@app.get('/api/assistant/planner/goals')
def assistant_planner_goals(
    scope: str = 'personal',
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.planner.goals(
        scope=scope,
        status=status,
        limit=max(1, min(limit, 300)),
    )


@app.post('/api/assistant/planner/goals')
def create_planner_goal(payload: GoalCreate) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail='Название цели пустое')
    goal_id = engine.planner.create_goal(
        scope=payload.scope.strip() or 'personal',
        title=title,
        description=payload.description.strip(),
        priority=max(0.0, min(1.0, payload.priority)),
        source='explicit_user',
        evidence=title,
        due_at=payload.due_at,
    )
    return {'status': 'created', 'id': goal_id}


@app.post('/api/assistant/planner/goals/{goal_id}/status')
def update_planner_goal_status(goal_id: int, payload: StatusUpdate) -> dict:
    try:
        engine.planner.set_goal_status(
            goal_id,
            payload.status,
            scope=payload.scope.strip() or 'personal',
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'updated', 'id': goal_id}


@app.get('/api/assistant/planner/tasks')
def assistant_planner_tasks(
    scope: str = 'personal',
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    return engine.planner.tasks(
        scope=scope,
        status=status,
        limit=max(1, min(limit, 500)),
    )


@app.post('/api/assistant/planner/tasks')
def create_planner_task(payload: TaskCreate) -> dict:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail='Название задачи пустое')
    try:
        task_id = engine.planner.create_task(
            scope=payload.scope.strip() or 'personal',
            title=title,
            description=payload.description.strip(),
            goal_id=payload.goal_id,
            priority=max(0.0, min(1.0, payload.priority)),
            source='explicit_user',
            evidence=title,
            due_at=payload.due_at,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'created', 'id': task_id}


@app.post('/api/assistant/planner/tasks/{task_id}/status')
def update_planner_task_status(task_id: int, payload: StatusUpdate) -> dict:
    try:
        engine.planner.set_task_status(
            task_id,
            payload.status,
            scope=payload.scope.strip() or 'personal',
            blocked_reason=payload.blocked_reason.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'updated', 'id': task_id}


@app.post('/api/assistant/planner/dependencies')
def create_planner_dependency(payload: TaskDependencyCreate) -> dict:
    try:
        dependency_id = engine.planner.add_dependency(
            scope=payload.scope.strip() or 'personal',
            task_id=payload.task_id,
            depends_on_task_id=payload.depends_on_task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'created', 'id': dependency_id}


@app.get('/api/assistant/planner/notices')
def assistant_planner_notices(scope: str = 'personal') -> list[dict]:
    return [
        notice.__dict__
        for notice in engine.planner.inspect(scope=scope)
    ]


@app.get('/api/assistant/planner/changes')
def assistant_planner_changes(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.planner.changes(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/sensors')
def assistant_sensors(scope: str = 'personal') -> list[dict]:
    return engine.sensors.scan(scope=scope, persist=False)


@app.post('/api/assistant/sensors/scan')
def assistant_sensor_scan(scope: str = 'personal') -> list[dict]:
    return engine.sensors.scan(scope=scope, persist=True)


@app.get('/api/assistant/sensors/history')
def assistant_sensor_history(
    scope: str = 'personal',
    sensor: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return engine.sensors.history(
        scope=scope,
        sensor=sensor,
        limit=max(1, min(limit, 200)),
    )


@app.get('/api/assistant/tools')
def assistant_tools() -> list[dict]:
    return engine.tools.catalog()


@app.post('/api/assistant/tools/{tool_name:path}')
def assistant_tool_invoke(
    tool_name: str,
    payload: ToolInvoke,
    request: Request,
) -> dict:
    if not payload.dry_run or payload.approved:
        _local_only(request)
    return engine.tools.invoke(
        tool_name,
        scope=payload.scope.strip() or 'personal',
        arguments=payload.arguments,
        dry_run=payload.dry_run,
        approved=payload.approved,
    )


@app.get('/api/assistant/tools/history')
def assistant_tool_history(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.tools.history(
        scope=scope,
        limit=max(1, min(limit, 200)),
    )


@app.post('/api/assistant/permissions/{capability}')
def assistant_permission_update(
    capability: str,
    payload: PermissionUpdate,
    request: Request,
) -> dict:
    _local_only(request)
    if capability not in engine.permissions.SAFE_DEFAULTS:
        raise HTTPException(status_code=400, detail='Неизвестная capability')
    try:
        engine.permissions.set(capability, payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        'status': 'updated',
        'capability': capability,
        'mode': engine.permissions.mode(capability),
    }


@app.post('/api/assistant/proactive/evaluate')
def assistant_proactive_evaluate(
    request: Request,
    scope: str = 'personal',
) -> dict:
    _local_only(request)
    return engine.proactive.evaluate(scope=scope).to_dict()


@app.get('/api/assistant/proactive/pending')
def assistant_proactive_pending(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.proactive.pending(
        scope=scope,
        limit=max(1, min(limit, 300)),
    )


@app.get('/api/assistant/proactive/conditions')
def assistant_proactive_conditions(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.proactive.conditions(
        scope=scope,
        limit=max(1, min(limit, 300)),
    )


@app.get('/api/assistant/proactive/history')
def assistant_proactive_history(
    scope: str = 'personal',
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.proactive.history(
        scope=scope,
        status=status,
        limit=max(1, min(limit, 300)),
    )


@app.post('/api/assistant/proactive/{decision_id}/approve')
def assistant_proactive_approve(
    decision_id: int,
    payload: DecisionAction,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.proactive.approve(
            decision_id,
            scope=payload.scope.strip() or 'personal',
            execute=payload.execute,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/assistant/proactive/{decision_id}/reject')
def assistant_proactive_reject(
    decision_id: int,
    payload: DecisionAction,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.proactive.reject(
            decision_id,
            scope=payload.scope.strip() or 'personal',
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/assistant/proactive/{decision_id}/acknowledge')
def assistant_proactive_acknowledge(
    decision_id: int,
    payload: DecisionAction,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.proactive.acknowledge(
            decision_id,
            scope=payload.scope.strip() or 'personal',
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/assistant/proactive/{decision_id}/execute')
def assistant_proactive_execute(
    decision_id: int,
    payload: DecisionAction,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.proactive.execute(
            decision_id,
            scope=payload.scope.strip() or 'personal',
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/assistant/continuous-learning/status')
def assistant_continuous_learning_status(
    scope: str = 'personal',
) -> dict:
    return engine.continuous_learning.status(
        scope=scope,
    )


@app.get('/api/assistant/continuous-learning/cycles')
def assistant_continuous_learning_cycles(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.continuous_learning.recent_cycles(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/continuous-learning/patterns')
def assistant_continuous_learning_patterns(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.continuous_learning.patterns(
        scope=scope,
        limit=max(1, min(limit, 200)),
    )


@app.get('/api/assistant/continuous-learning/queue')
def assistant_continuous_learning_queue(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.continuous_learning.queue(
        scope=scope,
        limit=max(1, min(limit, 200)),
    )


@app.get('/api/assistant/performance')
def assistant_performance(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.performance.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/cognitive-traces')
def assistant_cognitive_traces(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.cognitive_traces.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/ai-diagnostics')
def assistant_ai_diagnostics() -> dict:
    return engine.ai.diagnostics()


@app.get('/api/assistant/execution/approvals')
def assistant_execution_approvals(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.execution_coordinator.recent_approvals(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/execution/attempts')
def assistant_execution_attempts(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.execution_coordinator.recent_attempts(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.post('/api/assistant/execution/attempts/{attempt_id}/rollback')
def assistant_execution_rollback(
    attempt_id: int,
    payload: RollbackAction,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.execution_coordinator.rollback_attempt(
            attempt_id,
            scope=payload.scope.strip() or 'personal',
            approved=payload.approved,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/assistant/action-selection')
def assistant_action_selection(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.action_selector.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/counterfactual')
def assistant_counterfactual(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.counterfactual.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/decision-quality')
def assistant_decision_quality(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.decision_quality.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/hypotheses')
def assistant_hypotheses(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.hypotheses.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/logic-learning')
def assistant_logic_learning(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.logic_learning.recent_events(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/context-traces')
def assistant_context_traces(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.context_orchestrator.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/causal')
def assistant_causal(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.causal.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/logic')
def assistant_logic(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.logic.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/verification')
def assistant_verification(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.verification.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/metacognition')
def assistant_metacognition(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.metacognition.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


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
