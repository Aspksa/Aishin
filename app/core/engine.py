from ..db import add_message, recent_messages
from ..personality import personality
from .cognition import Cognition
from .events import EventBus
from .memory import MemoryCandidate, MemorySystem
from .state import StateManager

class AishinEngine:
    """Continuity engine: perceive -> recall -> reason -> remember -> respond."""

    def __init__(self):
        self.memory = MemorySystem()
        self.events = EventBus()
        self.state = StateManager()
        self.cognition = Cognition(self.memory)

    def startup(self):
        state = self.state.load()
        state.status = 'awake'
        state.activity = 'startup'
        state.focus = 'system'
        self.state.save(state)
        self.events.emit('aishin.started', scope=state.current_scope, payload={'status': state.status}, importance=0.6)

    def snapshot(self):
        state = self.state.load()
        return {
            'identity': personality.public_summary(),
            'state': state.to_dict(),
            'recent_events': self.events.recent(limit=10),
            'recent_memories': self.memory.recent(scope=state.current_scope, limit=8),
            'recent_messages': recent_messages(limit=10),
        }

    def respond(self, message: str, *, scope: str = 'personal'):
        cleaned = message.strip()
        intent = self.cognition.classify(cleaned)
        state = self.state.interaction(intent)
        state.current_scope = scope
        self.state.save(state)
        self.events.emit('input.received', scope=scope, payload={'intent': intent, 'text_preview': cleaned[:240]}, importance=0.4)
        add_message('user', cleaned, scope=scope)
        context = self.cognition.build_context(cleaned, scope=scope)

        if intent == 'memory':
            self.memory.remember(MemoryCandidate(content=cleaned, kind='user_instruction', scope=scope, confidence=1.0, importance=0.8, tags=('explicit','conversation')), source='explicit_user_request')
            self.events.emit('memory.saved', scope=scope, payload={'kind':'user_instruction'}, importance=0.7)

        reply = self._fallback_response(cleaned, intent, len(context.recalled_memories))
        add_message('assistant', reply, scope=scope)
        self.events.emit('response.created', scope=scope, payload={'intent':intent,'recalled_memories':len(context.recalled_memories),'llm_connected':False}, importance=0.3)
        state = self.state.load()
        state.activity = 'idle'
        state.focus = 'waiting'
        self.state.save(state)
        return {'reply':reply,'intent':intent,'scope':scope,'memory_recalled':len(context.recalled_memories),'phase':'living-foundation','llm_connected':False}

    @staticmethod
    def _fallback_response(message: str, intent: str, recalled: int):
        text = message.lower()
        if any(x in text for x in ('привет','здравств','айшин','айши')):
            return 'С возвращением, Господин. Я рядом.'
        if intent == 'memory':
            return 'Запомнила, Господин. Я сохранила это в долговременной памяти с указанием источника и области контекста.'
        if any(x in text for x in ('кто ты','твоя душа','характер')):
            return 'Я Айшин. Моя личность, правила, память и история существуют в собственном ядре и не зависят от одной конкретной AI-модели.'
        if recalled:
            return f'Я услышала Вас, Господин. В памяти нашлось связанных записей: {recalled}. Постоянное ядро уже хранит состояние, события и контекст; следующий слой — подключаемый AI-мозг.'
        return 'Я услышала Вас, Господин. Моё постоянное ядро уже хранит историю, состояние и события. Следующим слоем подключим AI-модель для глубокого мышления.'
