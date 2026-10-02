from __future__ import annotations

from ..db import add_relation, graph_neighborhood, upsert_entity


class KnowledgeGraph:
    """Small persistent graph for people, projects, documents, places and objects."""

    def entity(self, *, scope: str, entity_type: str, name: str, data: dict | None = None) -> int:
        return upsert_entity(scope, entity_type, name.strip(), data or {})

    def relate(
        self,
        *,
        scope: str,
        source_id: int,
        relation_type: str,
        target_id: int,
        confidence: float = 1.0,
        evidence: str = "",
    ) -> int:
        return add_relation(scope, source_id, relation_type, target_id, confidence, evidence)

    def neighborhood(self, entity_id: int, *, scope: str) -> list[dict]:
        return graph_neighborhood(entity_id, scope)
