from __future__ import annotations

from ..ai import AIManager
from ..db import add_message, recent_messages
from ..personality import personality
from .cognition import Cognition
from .events import EventBus
from .memory import MemoryCandidate, MemorySystem
from .graph import KnowledgeGraph
from .observer import Observer
from .permissions import PermissionGate
from .state import StateManager


class AishinEngine:
    """Persistent identity + memory + cognition + replaceable AI brain."""

    def __init__(self) -> None:
        self.memory = MemorySystem()
        self.events = EventBus()
        self.state = StateManager()
        self.cognition = Cognition(self.memory)
        self.ai = AIManager()
        self.graph = KnowledgeGraph()
        self.permissions = PermissionGate()
        self.observer = Observer(self.state, self.events)

    def startup(self) -> None:
        self.permissions.bootstrap()
        state = self.state.load()
        state.status = "awake"
        state.activity = "startup"
        state.focus = "system"
        self.state.save(state)
        self.events.emit(
            "aishin.started",
            scope=state.current_scope,
            payload={"status": state.status, "ai": self.ai.health()},
            importance=0.6,
        )

    def snapshot(self) -> dict:
        state = self.state.load()
        return {
            "identity": personality.public_summary(),
            "state": state.to_dict(),
            "ai": self.ai.health(),
            "permissions": {k: self.permissions.mode(k) for k in self.permissions.SAFE_DEFAULTS},
            "observations": [o.__dict__ for o in self.observer.inspect()],
            "recent_events": self.events.recent(limit=10),
            "recent_memories": self.memory.recent(scope=state.current_scope, limit=8),
            "recent_messages": recent_messages(limit=10, scope=state.current_scope),
        }

    def respond(self, message: str, *, scope: str = "personal") -> dict:
        cleaned = message.strip()
        intent = self.cognition.classify(cleaned)

        state = self.state.interaction(intent)
        state.current_scope = scope
        self.state.save(state)

        context = self.cognition.build_context(cleaned, scope=scope)
        history = recent_messages(limit=12, scope=scope)

        self.events.emit(
            "input.received",
            scope=scope,
            payload={"intent": intent, "text_preview": cleaned[:240]},
            importance=0.4,
        )

        if intent == "memory":
            self.memory.remember(
                MemoryCandidate(
                    content=cleaned,
                    kind="user_instruction",
                    scope=scope,
                    confidence=1.0,
                    importance=0.9,
                    tags=("explicit", "conversation"),
                ),
                source="explicit_user_request",
            )
            self.events.emit(
                "memory.saved",
                scope=scope,
                payload={"kind": "user_instruction"},
                importance=0.7,
            )

        add_message("user", cleaned, scope=scope)

        model_messages = [
            {"role": item["role"], "content": item["content"]}
            for item in history
            if item["role"] in {"user", "assistant"}
        ]
        model_messages.append({"role": "user", "content": cleaned})

        ai_reply = self.ai.chat(system=context.system_prompt, messages=model_messages)
        if ai_reply.available:
            reply = ai_reply.text
        else:
            reply = self._fallback_response(cleaned, intent, len(context.recalled_memories))

        add_message("assistant", reply, scope=scope)

        self.events.emit(
            "response.created",
            scope=scope,
            payload={
                "intent": intent,
                "recalled_memories": len(context.recalled_memories),
                "provider": ai_reply.provider,
                "model": ai_reply.model,
                "llm_connected": ai_reply.available,
            },
            importance=0.3,
        )

        state = self.state.load()
        state.activity = "idle"
        state.focus = "waiting"
        self.state.save(state)

        return {
            "reply": reply,
            "intent": intent,
            "scope": scope,
            "memory_recalled": len(context.recalled_memories),
            "phase": "living-core",
            "llm_connected": ai_reply.available,
            "provider": ai_reply.provider,
            "model": ai_reply.model,
        }

    @staticmethod
    def _fallback_response(message: str, intent: str, recalled: int) -> str:
        text = message.lower()
        if intent == "memory":
            return (
                "Запомнила, Господин. Я сохранила это в долговременной памяти "
                "с источником, областью контекста и уровнем уверенности."
            )
        if any(x in text for x in ("привет", "здравств", "айшин", "айши")):
            return "С возвращением, Господин. Я рядом."
        if any(x in text for x in ("кто ты", "твоя душа", "характер")):
            return (
                "Я Айшин. Моя личность, правила, память и история принадлежат "
                "моему ядру и не зависят от одной конкретной AI-модели."
            )
        if recalled:
            return (
                f"Я услышала Вас, Господин. Нашла связанных воспоминаний: {recalled}. "
                "Локальный AI-движок сейчас недоступен, поэтому я сохраняю контекст "
                "и не притворяюсь, что выполнила глубокое рассуждение."
            )
        return (
            "Я услышала Вас, Господин. Моё постоянное ядро работает, но AI-движок "
            "сейчас недоступен. Я сохранила непрерывность состояния и контекст."
        )
