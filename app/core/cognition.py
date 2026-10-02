from dataclasses import dataclass
from ..personality import personality
from .memory import MemorySystem
from .self_model import SelfModel
from .personal import PersonalAishin

@dataclass
class CognitiveContext:
    user_message: str
    scope: str
    recalled_memories: list[dict]
    system_prompt: str

class Cognition:
    def __init__(self, memory: MemorySystem):
        self.memory = memory
        self.self_model = SelfModel()
        self.personal = PersonalAishin()

    def build_context(self, message: str, *, scope: str):
        recalled = self.memory.recall(message, scope=scope, limit=8)
        block = self.memory.context_block(recalled)
        prompt = personality.system_prompt + '\n\n' + self.self_model.prompt_block() + '\n\n' + self.personal.prompt_block(scope=scope)
        if block:
            prompt += '\n\nРелевантная память. Учитывай тип и confidence, проверяй противоречия:\n' + block
        return CognitiveContext(message, scope, recalled, prompt)

    @staticmethod
    def classify(message: str):
        text = message.lower()
        if any(x in text for x in ('запомни','помни','сохрани')):
            return 'memory'
        if any(x in text for x in ('ошибка','проверь','противореч')):
            return 'verification'
        if any(x in text for x in ('план','сделай','создай','реализ')):
            return 'action'
        return 'conversation'
