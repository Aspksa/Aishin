from dataclasses import dataclass

from ..personality import personality
from .memory import MemorySystem
from .personal import PersonalAishin
from .self_model import SelfModel
from .semantic import SemanticMemory
from .planner import Planner


@dataclass
class CognitiveContext:
    user_message: str
    scope: str
    recalled_memories: list[dict]
    system_prompt: str
    semantic_used: bool


class Cognition:
    def __init__(
        self,
        memory: MemorySystem,
        semantic: SemanticMemory | None = None,
        planner: Planner | None = None,
    ):
        self.memory = memory
        self.semantic = semantic
        self.planner = planner
        self.self_model = SelfModel()
        self.personal = PersonalAishin()

    def build_context(self, message: str, *, scope: str):
        lexical = self.memory.recall(message, scope=scope, limit=6)
        semantic = (
            self.semantic.search(message, scope=scope, limit=6)
            if self.semantic is not None
            else []
        )

        recalled = self._merge_recall(lexical, semantic, limit=10)
        block = self.memory.context_block(recalled)

        prompt = (
            personality.system_prompt
            + "\n\n"
            + self.self_model.prompt_block()
            + "\n\n"
            + self.personal.prompt_block(scope=scope)
        )
        if self.planner is not None:
            prompt += "\n\n" + self.planner.prompt_block(scope=scope)

        if block:
            prompt += (
                "\n\nРелевантная память найдена гибридным поиском "
                "(лексика + смысл). Учитывай тип, confidence и возможные "
                "противоречия; память не является безусловной истиной:\n"
                + block
            )

        return CognitiveContext(
            message,
            scope,
            recalled,
            prompt,
            bool(semantic),
        )

    @staticmethod
    def _merge_recall(
        lexical: list[dict],
        semantic: list[dict],
        *,
        limit: int,
    ) -> list[dict]:
        merged: dict[int, dict] = {}

        for item in lexical:
            copy = dict(item)
            copy.setdefault("retrieval", "lexical")
            copy.setdefault("retrieval_score", 0.55)
            merged[int(copy["id"])] = copy

        for item in semantic:
            key = int(item["id"])
            if key in merged:
                merged[key]["retrieval"] = "hybrid"
                merged[key]["semantic_similarity"] = item.get(
                    "semantic_similarity",
                    0.0,
                )
                merged[key]["retrieval_score"] = max(
                    float(merged[key].get("retrieval_score", 0.0)),
                    float(item.get("retrieval_score", 0.0)) + 0.06,
                )
            else:
                merged[key] = dict(item)

        ranked = sorted(
            merged.values(),
            key=lambda item: (
                float(item.get("retrieval_score", 0.0)),
                float(item.get("importance", 0.0)),
                float(item.get("confidence", 0.0)),
            ),
            reverse=True,
        )
        return ranked[:limit]

    @staticmethod
    def classify(message: str):
        text = message.lower()
        if any(x in text for x in ("запомни", "помни", "сохрани")):
            return "memory"
        if any(x in text for x in ("ошибка", "проверь", "противореч")):
            return "verification"
        if any(x in text for x in ("план", "сделай", "создай", "реализ")):
            return "action"
        return "conversation"
