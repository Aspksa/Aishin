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
from .system_settings import CloudSettingsService
from .updater import ProjectUpdater

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT / '.env')

templates = Environment(
    loader=FileSystemLoader(APP_DIR / 'templates'),
    autoescape=select_autoescape(['html', 'xml']),
)

engine = AishinEngine()
cloud_settings = CloudSettingsService(ROOT)
project_updater = ProjectUpdater(ROOT)
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
        proactive=engine.proactive_intelligence,
        research=engine.research,
    )
    heartbeat_task = asyncio.create_task(heartbeat.run())
    engine.continuous_learning.prepare_start()
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


app = FastAPI(title='Aishin Kitsune', version='0.0.10', lifespan=lifespan)
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


class ProactiveFeedback(BaseModel):
    scope: str = 'personal'
    feedback: str
    reason: str = ''


class ResearchQueryRequest(BaseModel):
    scope: str = 'personal'
    question: str
    synthesize: bool = True
    gap_id: int | None = None


class ResearchCycleRequest(BaseModel):
    scope: str = 'personal'
    max_sessions: int = 2
    synthesize: bool = False


class ResearchSourceCreate(BaseModel):
    scope: str = 'personal'
    source_key: str
    source_type: str
    label: str
    locator: str = ''
    independent_group: str = ''
    trust_prior: float = 0.7
    enabled: bool = True
    auto_read: bool = False
    metadata: dict = Field(default_factory=dict)


class ResearchContradictionResolve(BaseModel):
    scope: str = 'personal'
    resolution: str


class CommunicationFeedback(BaseModel):
    scope: str = 'personal'
    feedback: str
    reason: str = ''


class CloudSettingsUpdate(BaseModel):
    api_key: str


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
        'version': '0.0.10',
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


@app.get('/api/assistant/development')
def assistant_development(
    scope: str = 'personal',
    days: int = 30,
) -> dict:
    days = max(1, min(3650, int(days)))
    current = engine.development.current(scope=scope, persist=True)
    return {
        'current': current,
        'history': engine.development.history(scope=scope, days=days),
        'days': days,
    }


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


@app.get('/api/assistant/intelligence')
def assistant_intelligence(
    scope: str = 'personal',
    history_limit: int = 90,
    route_limit: int = 30,
) -> dict:
    return engine.cognitive_intelligence.dashboard(
        scope=scope,
        history_limit=max(1, min(history_limit, 365)),
        route_limit=max(1, min(route_limit, 200)),
        persist=True,
    )


@app.get('/api/assistant/intelligence/routes')
def assistant_intelligence_routes(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.cognitive_intelligence.routes(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/intelligence/history')
def assistant_intelligence_history(
    scope: str = 'personal',
    limit: int = 90,
) -> list[dict]:
    return engine.cognitive_intelligence.history(
        scope=scope,
        limit=max(1, min(limit, 1000)),
    )


@app.get('/api/assistant/intelligence/transfer')
def assistant_intelligence_transfer(
    scope: str = 'personal',
) -> list[dict]:
    return engine.cognitive_intelligence.transfer_map(scope=scope)


@app.get('/api/assistant/evolution')
def assistant_evolution(
    scope: str = 'personal',
    capability_limit: int = 30,
    variant_limit: int = 50,
    curriculum_limit: int = 50,
    transfer_limit: int = 50,
    cycle_limit: int = 60,
) -> dict:
    return engine.evolution.dashboard(
        scope=scope,
        capability_limit=max(1, min(capability_limit, 200)),
        variant_limit=max(1, min(variant_limit, 300)),
        curriculum_limit=max(1, min(curriculum_limit, 300)),
        transfer_limit=max(1, min(transfer_limit, 300)),
        cycle_limit=max(1, min(cycle_limit, 500)),
        refresh=False,
    )


@app.post('/api/assistant/evolution/cycle')
def assistant_evolution_cycle(
    request: Request,
    scope: str = 'personal',
) -> dict:
    _local_only(request)
    return engine.evolution.run_cycle(
        scope=scope,
        trigger='manual',
    ).to_dict()


@app.get('/api/assistant/evolution/capabilities')
def assistant_evolution_capabilities(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.evolution.capabilities(
        scope=scope,
        limit=max(1, min(limit, 200)),
    )


@app.get('/api/assistant/evolution/variants')
def assistant_evolution_variants(
    scope: str = 'personal',
    lifecycle: str | None = None,
    limit: int = 80,
) -> list[dict]:
    return engine.evolution.variants(
        scope=scope,
        lifecycle=lifecycle,
        limit=max(1, min(limit, 300)),
    )


@app.get('/api/assistant/evolution/curriculum')
def assistant_evolution_curriculum(
    scope: str = 'personal',
    limit: int = 80,
) -> list[dict]:
    return engine.evolution.curriculum(
        scope=scope,
        limit=max(1, min(limit, 300)),
    )


@app.get('/api/assistant/evolution/transfers')
def assistant_evolution_transfers(
    scope: str = 'personal',
    limit: int = 80,
) -> list[dict]:
    return engine.evolution.transfers(
        scope=scope,
        limit=max(1, min(limit, 300)),
    )


@app.get('/api/assistant/evolution/cycles')
def assistant_evolution_cycles(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.evolution.cycles(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/research')
def assistant_research(
    scope: str = 'personal',
    gap_limit: int = 60,
    session_limit: int = 40,
    claim_limit: int = 80,
    evidence_limit: int = 100,
    cycle_limit: int = 40,
) -> dict:
    return engine.research.dashboard(
        scope=scope,
        gap_limit=max(1, min(gap_limit, 300)),
        session_limit=max(1, min(session_limit, 300)),
        claim_limit=max(1, min(claim_limit, 500)),
        evidence_limit=max(1, min(evidence_limit, 500)),
        cycle_limit=max(1, min(cycle_limit, 300)),
    )


@app.post('/api/assistant/research/query')
def assistant_research_query(
    payload: ResearchQueryRequest,
    request: Request,
) -> dict:
    _local_only(request)
    question = payload.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail='Research question is empty')
    try:
        run = engine.research.research_query(
            scope=payload.scope.strip() or 'personal',
            question=question,
            trigger='manual_query',
            gap_id=payload.gap_id,
            synthesize=payload.synthesize,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        'run': run.to_dict(),
        'evidence': engine.research.evidence(
            scope=run.scope,
            session_id=run.session_id,
            limit=120,
        ),
        'claims': engine.research.claims(
            scope=run.scope,
            session_id=run.session_id,
            limit=80,
        ),
        'contradictions': engine.research.contradictions(
            scope=run.scope,
            session_id=run.session_id,
            status=None,
            limit=80,
        ),
    }


@app.post('/api/assistant/research/cycle')
def assistant_research_cycle(
    payload: ResearchCycleRequest,
    request: Request,
) -> dict:
    _local_only(request)
    return engine.research.run_cycle(
        scope=payload.scope.strip() or 'personal',
        trigger='manual',
        max_sessions=max(0, min(payload.max_sessions, 5)),
        synthesize=payload.synthesize,
    )


@app.get('/api/assistant/research/gaps')
def assistant_research_gaps(
    scope: str = 'personal',
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.research.gaps(
        scope=scope,
        status=status,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/research/sessions')
def assistant_research_sessions(
    scope: str = 'personal',
    limit: int = 80,
) -> list[dict]:
    return engine.research.sessions(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/research/claims')
def assistant_research_claims(
    scope: str = 'personal',
    session_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.research.claims(
        scope=scope,
        session_id=session_id,
        status=status,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/research/evidence')
def assistant_research_evidence(
    scope: str = 'personal',
    session_id: int | None = None,
    limit: int = 100,
) -> list[dict]:
    if session_id is not None:
        return engine.research.evidence(
            scope=scope,
            session_id=session_id,
            limit=max(1, min(limit, 500)),
        )
    return engine.research.recent_evidence(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/research/sources')
def assistant_research_sources(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.research.sources(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.post('/api/assistant/research/sources')
def assistant_research_source_create(
    payload: ResearchSourceCreate,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.research.register_source(
            scope=payload.scope.strip() or 'personal',
            source_key=payload.source_key,
            source_type=payload.source_type,
            label=payload.label,
            locator=payload.locator,
            independent_group=payload.independent_group,
            trust_prior=payload.trust_prior,
            enabled=payload.enabled,
            auto_read=payload.auto_read,
            metadata=payload.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/assistant/research/contradictions')
def assistant_research_contradictions(
    scope: str = 'personal',
    status: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.research.contradictions(
        scope=scope,
        status=status,
        limit=max(1, min(limit, 500)),
    )


@app.post('/api/assistant/research/contradictions/{contradiction_id}/resolve')
def assistant_research_contradiction_resolve(
    contradiction_id: int,
    payload: ResearchContradictionResolve,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.research.resolve_contradiction(
            contradiction_id,
            scope=payload.scope.strip() or 'personal',
            resolution=payload.resolution,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/assistant/communication')
def assistant_communication(
    scope: str = 'personal',
    turn_limit: int = 80,
    event_limit: int = 100,
) -> dict:
    return engine.communication.dashboard(
        scope=scope,
        turn_limit=max(1, min(turn_limit, 300)),
        event_limit=max(1, min(event_limit, 500)),
    )


@app.get('/api/assistant/communication/turns')
def assistant_communication_turns(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.communication.turns(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/communication/skills')
def assistant_communication_skills(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.communication.skills(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/communication/preferences')
def assistant_communication_preferences(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.communication.preferences(
        scope=scope,
        limit=max(1, min(limit, 200)),
    )


@app.post('/api/assistant/communication/turns/{turn_id}/feedback')
def assistant_communication_feedback(
    turn_id: int,
    payload: CommunicationFeedback,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.communication.feedback(
            turn_id,
            scope=payload.scope.strip() or 'personal',
            feedback=payload.feedback,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get('/api/assistant/growth')
def assistant_growth(
    scope: str = 'personal',
    skill_limit: int = 80,
    knowledge_limit: int = 80,
    specialization_limit: int = 40,
    history_limit: int = 60,
) -> dict:
    summary = engine.long_term_growth.refresh(
        scope=scope,
        persist_snapshot=True,
    )
    return {
        'summary': summary,
        'skills': engine.long_term_growth.skills(
            scope=scope,
            limit=max(1, min(skill_limit, 300)),
        ),
        'knowledge': engine.long_term_growth.knowledge_trust(
            scope=scope,
            limit=max(1, min(knowledge_limit, 300)),
        ),
        'specializations': engine.long_term_growth.specializations(
            scope=scope,
            limit=max(1, min(specialization_limit, 100)),
        ),
        'history': engine.long_term_growth.history(
            scope=scope,
            limit=max(1, min(history_limit, 365)),
        ),
        'events': engine.long_term_growth.recent_events(
            scope=scope,
            limit=50,
        ),
    }


@app.get('/api/assistant/growth/skills')
def assistant_growth_skills(
    scope: str = 'personal',
    lifecycle: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.long_term_growth.skills(
        scope=scope,
        lifecycle=lifecycle,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/growth/knowledge')
def assistant_growth_knowledge(
    scope: str = 'personal',
    trust_level: str | None = None,
    limit: int = 100,
) -> list[dict]:
    return engine.long_term_growth.knowledge_trust(
        scope=scope,
        trust_level=trust_level,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/growth/specializations')
def assistant_growth_specializations(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.long_term_growth.specializations(
        scope=scope,
        limit=max(1, min(limit, 200)),
    )


@app.get('/api/assistant/growth/history')
def assistant_growth_history(
    scope: str = 'personal',
    limit: int = 90,
) -> list[dict]:
    return engine.long_term_growth.history(
        scope=scope,
        limit=max(1, min(limit, 1000)),
    )


@app.post('/api/assistant/growth/refresh')
def assistant_growth_refresh(
    request: Request,
    scope: str = 'personal',
) -> dict:
    _local_only(request)
    return engine.long_term_growth.refresh(
        scope=scope,
        persist_snapshot=True,
    )


@app.get('/api/assistant/live-brain')
def assistant_live_brain(
    scope: str = 'personal',
    event_limit: int = 40,
    graph_limit: int = 18,
) -> dict:
    return engine.live_brain.snapshot(
        scope=scope,
        event_limit=max(8, min(event_limit, 120)),
        graph_limit=max(6, min(graph_limit, 40)),
    )


@app.get('/api/assistant/live-brain/export')
def assistant_live_brain_export(scope: str = 'personal') -> dict:
    return engine.live_brain.export(scope=scope)


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


@app.get('/api/assistant/proactive-intelligence')
def assistant_proactive_intelligence(
    scope: str = 'personal',
    incident_limit: int = 80,
    signal_limit: int = 80,
    run_limit: int = 40,
) -> dict:
    return engine.proactive_intelligence.dashboard(
        scope=scope,
        incident_limit=max(1, min(incident_limit, 300)),
        signal_limit=max(1, min(signal_limit, 300)),
        run_limit=max(1, min(run_limit, 200)),
        refresh=False,
    )


@app.post('/api/assistant/proactive-intelligence/scan')
def assistant_proactive_intelligence_scan(
    request: Request,
    scope: str = 'personal',
) -> dict:
    _local_only(request)
    return engine.proactive_intelligence.evaluate(
        scope=scope,
        trigger='manual',
    ).to_dict()


@app.get('/api/assistant/proactive-intelligence/incidents')
def assistant_proactive_intelligence_incidents(
    scope: str = 'personal',
    status: str | None = 'active',
    limit: int = 100,
) -> list[dict]:
    return engine.proactive_intelligence.incidents(
        scope=scope,
        status=status,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/proactive-intelligence/expectations')
def assistant_proactive_intelligence_expectations(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.proactive_intelligence.expectations(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.get('/api/assistant/proactive-intelligence/signals')
def assistant_proactive_intelligence_signals(
    scope: str = 'personal',
    limit: int = 100,
) -> list[dict]:
    return engine.proactive_intelligence.signals(
        scope=scope,
        limit=max(1, min(limit, 500)),
    )


@app.post('/api/assistant/proactive-intelligence/incidents/{incident_id}/feedback')
def assistant_proactive_intelligence_feedback(
    incident_id: int,
    payload: ProactiveFeedback,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        return engine.proactive_intelligence.feedback(
            incident_id,
            scope=payload.scope.strip() or 'personal',
            feedback=payload.feedback,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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


@app.get('/api/assistant/continuous-learning/quality')
def assistant_continuous_learning_quality(
    scope: str = 'personal',
) -> dict:
    return engine.continuous_learning.quality_status(
        scope=scope,
    )


@app.get('/api/assistant/continuous-learning/strategies')
def assistant_continuous_learning_strategies(
    scope: str = 'personal',
    mode: str | None = None,
    limit: int = 50,
) -> list[dict]:
    return engine.continuous_learning.strategy_evolution(
        scope=scope,
        mode=mode,
        limit=max(1, min(limit, 200)),
    )


@app.get('/api/assistant/continuous-learning/quality-events')
def assistant_continuous_learning_quality_events(
    scope: str = 'personal',
    limit: int = 50,
) -> list[dict]:
    return engine.continuous_learning.quality_events(
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


@app.get('/api/assistant/self-reflection')
def assistant_self_reflection(
    scope: str = 'personal',
    limit: int = 30,
) -> dict:
    return {
        'summary': engine.self_reflection.summary(
            scope=scope,
            limit=max(1, min(limit, 200)),
        ),
        'recent': engine.self_reflection.recent(
            scope=scope,
            limit=max(1, min(limit, 200)),
        ),
    }


@app.get('/api/assistant/learning-plans')
def assistant_learning_plans(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.learning_planner.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/safe-experiments')
def assistant_safe_experiments(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.experiment_manager.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
    )


@app.get('/api/assistant/context-budget')
def assistant_context_budget(
    scope: str = 'personal',
    limit: int = 30,
) -> list[dict]:
    return engine.context_budgeter.recent(
        scope=scope,
        limit=max(1, min(limit, 100)),
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


@app.get('/api/settings/cloudru')
def cloudru_settings_status() -> dict:
    status = cloud_settings.public_status()
    health = engine.ai.health()
    return {
        **status,
        "available": bool(health.get("available")),
        "model_available": health.get("model_available"),
        "error": health.get("error"),
    }


@app.post('/api/settings/cloudru')
def cloudru_settings_save(
    payload: CloudSettingsUpdate,
    request: Request,
) -> dict:
    _local_only(request)
    try:
        status = cloud_settings.save_key(payload.api_key)
        runtime = engine.reload_ai()
        return {
            "status": "saved",
            "settings": status,
            "health": runtime["health"],
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post('/api/settings/cloudru/test')
def cloudru_settings_test(request: Request) -> dict:
    _local_only(request)
    result = cloud_settings.test()
    return {
        "status": "ok" if result.get("available") else "error",
        "health": result,
    }


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


@app.get('/api/system/update/status')
def system_update_status() -> dict:
    return {
        'mode': project_updater.mode(),
        'git_checkout': (ROOT / '.git').exists(),
    }


@app.post('/api/system/update')
def system_update(request: Request) -> dict:
    _local_only(request)
    engine.events.emit('system.update.started', importance=0.5)
    try:
        result = project_updater.update()
        details = str(result.get('details') or 'Обновление завершено')
        record_update('success', details)
        engine.events.emit(
            'system.update.completed',
            payload={
                'details': details[:500],
                'mode': result.get('mode'),
                'restart_required': result.get('restart_required', True),
            },
            importance=0.6,
        )
        return result
    except Exception as exc:
        details = str(exc)
        record_update('error', details)
        engine.events.emit(
            'system.update.failed',
            payload={'error': details[:500]},
            importance=0.9,
        )
        raise HTTPException(status_code=500, detail=details)
