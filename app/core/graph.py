from __future__ import annotations

from ..db import (
    add_relation,
    graph_neighborhood,
    graph_stats,
    list_entities,
    list_relations,
    log_graph_change,
    recent_graph_changes,
    search_entities,
    upsert_entity,
)


class KnowledgeGraph:
    """Persistent scoped world model for Aishin."""

    def entity(
        self,
        *,
        scope: str,
        entity_type: str,
        name: str,
        data: dict | None = None,
        evidence: str = "",
    ) -> int:
        entity_id = upsert_entity(
            scope,
            entity_type,
            name.strip(),
            data or {},
        )
        log_graph_change(
            scope,
            "entity_upsert",
            entity_id=entity_id,
            details={
                "entity_type": entity_type,
                "name": name.strip(),
                "evidence": evidence,
            },
        )
        return entity_id

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
        relation_id = add_relation(
            scope,
            source_id,
            relation_type,
            target_id,
            confidence,
            evidence,
        )
        log_graph_change(
            scope,
            "relation_upsert",
            relation_id=relation_id,
            details={
                "source_id": source_id,
                "relation_type": relation_type,
                "target_id": target_id,
                "confidence": confidence,
                "evidence": evidence,
            },
        )
        return relation_id

    def neighborhood(self, entity_id: int, *, scope: str) -> list[dict]:
        return graph_neighborhood(entity_id, scope)

    def entities(
        self,
        *,
        scope: str,
        limit: int = 100,
        entity_type: str | None = None,
    ) -> list[dict]:
        return list_entities(
            scope,
            limit=limit,
            entity_type=entity_type,
        )

    def search(
        self,
        query: str,
        *,
        scope: str,
        limit: int = 20,
    ) -> list[dict]:
        return search_entities(scope, query, limit=limit)

    def relations(self, *, scope: str, limit: int = 200) -> list[dict]:
        return list_relations(scope, limit=limit)

    def stats(self, *, scope: str) -> dict:
        return graph_stats(scope)

    def changes(self, *, scope: str, limit: int = 30) -> list[dict]:
        return recent_graph_changes(scope, limit=limit)

    def seed_personal_foundation(self) -> None:
        aishin_id = self.entity(
            scope="relationship",
            entity_type="assistant",
            name="Айшин",
            data={"role": "личная AI-помощница"},
            evidence="Канонический профиль Айшин",
        )
        master_id = self.entity(
            scope="relationship",
            entity_type="person",
            name="Господин",
            data={"role": "основной пользователь"},
            evidence="Личный режим Aishin",
        )
        project_id = self.entity(
            scope="relationship",
            entity_type="project",
            name="Aishin",
            data={"mode": "personal_single_owner"},
            evidence="Айшин и Господин вместе создают и развивают проект Aishin.",
        )
        self.relate(
            scope="relationship",
            source_id=aishin_id,
            relation_type="assists",
            target_id=master_id,
            confidence=1.0,
            evidence="Айшин — личная AI-помощница Господина.",
        )
        self.relate(
            scope="relationship",
            source_id=master_id,
            relation_type="develops",
            target_id=project_id,
            confidence=1.0,
            evidence="Айшин и Господин вместе создают и развивают проект Aishin.",
        )
        self.relate(
            scope="relationship",
            source_id=aishin_id,
            relation_type="develops",
            target_id=project_id,
            confidence=1.0,
            evidence="Айшин и Господин вместе создают и развивают проект Aishin.",
        )
