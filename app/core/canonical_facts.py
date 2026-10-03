from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..db import connect


_SPACE_RE = re.compile(r"\s+")


class CanonicalFactsEngine:
    """Strict canonical identity + evidence fusion across persisted Aishin stores.

    No semantic/fuzzy merging is performed. Facts merge only when they share an
    explicit canonical key or an auditable lineage link.
    """

    VERSION = "aishin-canonical-facts-v1"
    SOURCE_TYPES = (
        "document_fact",
        "research_evidence",
        "memory",
        "graph_relation",
    )

    def __init__(
        self,
        *,
        events: Any | None = None,
        knowledge_lifecycle: Any | None = None,
    ) -> None:
        self.events = events
        self.knowledge_lifecycle = knowledge_lifecycle
        self._signatures: dict[str, tuple] = {}

    def ensure_fresh(self, *, scope: str) -> dict:
        scope = (scope or "personal").strip() or "personal"
        signature = self._source_signature(scope)
        if self._signatures.get(scope) == signature:
            return {
                "version": self.VERSION,
                "scope": scope,
                "refreshed": False,
                "summary": self.summary(scope=scope),
            }
        result = self.sync_scope(scope=scope)
        result["refreshed"] = True
        return result

    def sync_scope(self, *, scope: str) -> dict:
        scope = (scope or "personal").strip() or "personal"
        self._deactivate_previous(scope)

        counters = {
            "document_facts": self._sync_document_facts(scope),
            "research_claims": self._sync_research_claims(scope),
            "memories": self._sync_memories(scope),
            "graph_relations": self._sync_graph(scope),
        }

        with connect() as conn:
            fact_ids = [
                int(row["id"])
                for row in conn.execute(
                    "SELECT id FROM canonical_facts WHERE scope=? ORDER BY id",
                    (scope,),
                ).fetchall()
            ]

        changed = 0
        lifecycle_links = 0
        for fact_id in fact_ids:
            result = self._recompute_fact(fact_id)
            if result.get("changed"):
                changed += 1
            if result.get("lifecycle_linked"):
                lifecycle_links += 1

        summary = self.summary(scope=scope)
        self._signatures[scope] = self._source_signature(scope)
        payload = {
            "version": self.VERSION,
            "scope": scope,
            "sources": counters,
            "facts_recomputed": len(fact_ids),
            "facts_changed": changed,
            "lifecycle_links": lifecycle_links,
            "summary": summary,
        }
        self._emit(
            "canonical_facts.synced",
            scope=scope,
            payload=payload,
            importance=0.35,
        )
        return payload

    def summary(self, *, scope: str) -> dict:
        with connect() as conn:
            states = {
                str(row["state"]): int(row["n"])
                for row in conn.execute(
                    """SELECT state, COUNT(*) AS n
                       FROM canonical_facts
                       WHERE scope=? GROUP BY state""",
                    (scope,),
                ).fetchall()
            }
            values = int(
                conn.execute(
                    """SELECT COUNT(*) FROM canonical_fact_values
                       WHERE scope=?""",
                    (scope,),
                ).fetchone()[0]
            )
            evidence = int(
                conn.execute(
                    """SELECT COUNT(*) FROM canonical_fact_evidence
                       WHERE scope=? AND active=1""",
                    (scope,),
                ).fetchone()[0]
            )
            independent = int(
                conn.execute(
                    """SELECT COUNT(DISTINCT independence_group)
                       FROM canonical_fact_evidence
                       WHERE scope=? AND active=1 AND is_independent=1
                         AND stance='support'""",
                    (scope,),
                ).fetchone()[0]
            )
            superseded_values = int(
                conn.execute(
                    """SELECT COUNT(*) FROM canonical_fact_values
                       WHERE scope=? AND state='superseded'""",
                    (scope,),
                ).fetchone()[0]
            )
            links = int(
                conn.execute(
                    """SELECT COUNT(*) FROM canonical_fact_links
                       WHERE scope=? AND active=1""",
                    (scope,),
                ).fetchone()[0]
            )
        return {
            "version": self.VERSION,
            "scope": scope,
            "facts": sum(states.values()),
            "states": {
                "observed": states.get("observed", 0),
                "supported": states.get("supported", 0),
                "verified": states.get("verified", 0),
                "conflicted": states.get("conflicted", 0),
                "empty": states.get("empty", 0),
            },
            "values": values,
            "active_evidence": evidence,
            "independent_groups": independent,
            "superseded_values": superseded_values,
            "lineage_links": links,
        }

    def facts(
        self,
        *,
        scope: str,
        state: str | None = None,
        namespace: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where = ["scope=?"]
        params: list[Any] = [scope]
        if state:
            where.append("state=?")
            params.append(state)
        if namespace:
            where.append("namespace=?")
            params.append(namespace)
        params.append(max(1, min(int(limit), 500)))
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM canonical_facts
                    WHERE {' AND '.join(where)}
                    ORDER BY
                      CASE state
                        WHEN 'conflicted' THEN 0
                        WHEN 'verified' THEN 1
                        WHEN 'supported' THEN 2
                        ELSE 3
                      END,
                      confidence DESC, id DESC
                    LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [self._fact_detail(dict(row)) for row in rows]

    def fact(
        self,
        fact_id: int,
        *,
        scope: str,
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM canonical_facts WHERE id=? AND scope=?",
                (int(fact_id), scope),
            ).fetchone()
        return self._fact_detail(dict(row)) if row else None

    def history(
        self,
        *,
        scope: str,
        canonical_key: str | None = None,
        fact_id: int | None = None,
        limit: int = 200,
    ) -> dict:
        with connect() as conn:
            if fact_id is None and canonical_key:
                row = conn.execute(
                    """SELECT id FROM canonical_facts
                       WHERE scope=? AND canonical_key=?""",
                    (scope, canonical_key),
                ).fetchone()
                fact_id = int(row["id"]) if row else None
            if fact_id is None:
                return {"scope": scope, "fact": None, "values": [], "events": []}
            fact_row = conn.execute(
                "SELECT * FROM canonical_facts WHERE id=? AND scope=?",
                (int(fact_id), scope),
            ).fetchone()
            if not fact_row:
                return {"scope": scope, "fact": None, "values": [], "events": []}
            value_rows = conn.execute(
                """SELECT * FROM canonical_fact_values
                   WHERE fact_id=? ORDER BY id ASC""",
                (int(fact_id),),
            ).fetchall()
            event_rows = conn.execute(
                """SELECT * FROM canonical_fact_events
                   WHERE fact_id=? ORDER BY id DESC LIMIT ?""",
                (int(fact_id), max(1, min(int(limit), 1000))),
            ).fetchall()

        values = []
        for row in value_rows:
            item = dict(row)
            item["evidence"] = self._value_evidence(int(item["id"]))
            values.append(item)
        events = []
        for row in event_rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            events.append(item)
        return {
            "scope": scope,
            "fact": dict(fact_row),
            "values": values,
            "events": events,
        }

    def dashboard(self, *, scope: str, limit: int = 40) -> dict:
        return {
            "summary": self.summary(scope=scope),
            "facts": self.facts(scope=scope, limit=limit),
            "recent_events": self.events_view(scope=scope, limit=limit),
            "read_only": True,
        }

    def events_view(self, *, scope: str, limit: int = 80) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM canonical_fact_events
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = self._json(item.pop("details_json"), {})
            result.append(item)
        return result

    def reasoning_evidence(
        self,
        query: str,
        *,
        scope: str,
        limit: int = 8,
    ) -> list[dict]:
        self.ensure_fresh(scope=scope)
        query_tokens = self._tokens(query)
        candidates = self.facts(scope=scope, limit=160)
        ranked: list[tuple[float, dict]] = []
        for fact in candidates:
            if fact.get("state") not in {"supported", "verified"}:
                continue
            text = " ".join(
                [
                    str(fact.get("canonical_key") or ""),
                    str(fact.get("subject") or ""),
                    str(fact.get("predicate") or ""),
                    str(fact.get("current_value") or ""),
                ]
            )
            tokens = self._tokens(text)
            overlap = len(query_tokens & tokens) if query_tokens else 0
            if query_tokens and overlap == 0:
                continue
            score = (
                0.55 * float(fact.get("confidence") or 0.0)
                + 0.25 * min(1.0, overlap / max(1, len(query_tokens)))
                + 0.20 * (
                    1.0 if fact.get("state") == "verified" else 0.65
                )
            )
            ranked.append((score, fact))
        ranked.sort(key=lambda item: item[0], reverse=True)

        result: list[dict] = []
        for score, fact in ranked[: max(1, min(int(limit), 24))]:
            value_id = fact.get("current_value_id")
            if not value_id:
                continue
            primary = [
                item
                for item in self._value_evidence(int(value_id))
                if item.get("active")
                and item.get("stance") == "support"
                and item.get("is_independent")
            ]
            groups_seen: set[str] = set()
            statement = self._statement_for_fact(fact)
            if not primary:
                continue
            for evidence in primary:
                group = str(evidence.get("independence_group") or "")
                if not group or group in groups_seen:
                    continue
                groups_seen.add(group)
                result.append(
                    {
                        "source": "canonical_fact",
                        "source_type": "canonical_fact",
                        "source_ref": (
                            f"{fact['canonical_key']}::"
                            f"{evidence.get('source_ref') or ''}"
                        ),
                        "source_group": group,
                        "independence": 0.0,
                        "confidence": min(
                            float(fact.get("confidence") or 0.0),
                            float(evidence.get("confidence") or 0.0),
                        ),
                        "retrieval_score": round(score, 4),
                        "content": statement[:1200],
                        "provenance": {
                            "canonical_fact_id": int(fact["id"]),
                            "canonical_key": fact["canonical_key"],
                            "canonical_state": fact["state"],
                            "canonical_value_id": int(value_id),
                            "primary_source_type": evidence.get("source_type"),
                            "primary_source_ref": evidence.get("source_ref"),
                            "primary_source_group": evidence.get("source_group"),
                            "primary_provenance": evidence.get("provenance") or {},
                        },
                        "trust_boundary": "derived_canonical_projection",
                    }
                )
                if len(groups_seen) >= 3:
                    break
        return result[: max(1, min(int(limit) * 3, 24))]

    def prompt_block(self, *, scope: str) -> str:
        verified = self.facts(
            scope=scope,
            state="verified",
            limit=5,
        )
        conflicts = self.facts(
            scope=scope,
            state="conflicted",
            limit=3,
        )
        lines = [
            "Canonical Facts & Evidence Fusion.",
            "Use only current canonical values with their evidence state.",
            "A canonical key means strict identity, not semantic similarity.",
        ]
        for item in verified:
            lines.append(
                f"- VERIFIED {item['canonical_key']}: "
                f"{item.get('current_value') or '—'} "
                f"(confidence={float(item.get('confidence') or 0):.2f})"
            )
        for item in conflicts:
            values = [
                str(value.get("display_value") or "")
                for value in item.get("values") or []
                if value.get("state") != "superseded"
            ][:4]
            lines.append(
                f"- CONFLICT {item['canonical_key']}: "
                + " | ".join(values)
            )
        if conflicts:
            lines.append(
                "Do not collapse conflicted canonical values into one fact."
            )
        return "\n".join(lines)

    def _source_signature(self, scope: str) -> tuple:
        with connect() as conn:
            document = conn.execute(
                """SELECT COUNT(*) AS n, COALESCE(MAX(f.id), 0) AS max_id,
                          COALESCE(MAX(f.updated_at), '') AS updated
                   FROM document_facts f
                   JOIN documents d ON d.id=f.document_id
                   WHERE f.scope=? AND f.status='grounded'
                     AND d.status='studied'""",
                (scope,),
            ).fetchone()
            research = conn.execute(
                """SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id,
                          COALESCE(MAX(updated_at), '') AS updated
                   FROM research_claims WHERE scope=?""",
                (scope,),
            ).fetchone()
            memory = conn.execute(
                """SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id,
                          COALESCE(MAX(updated_at), '') AS updated
                   FROM memories
                   WHERE scope=? AND status='active'
                     AND memory_key IS NOT NULL
                     AND TRIM(memory_key)<>''""",
                (scope,),
            ).fetchone()
            graph = conn.execute(
                """SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id,
                          COALESCE(SUM(confidence), 0.0) AS confidence_sum,
                          COALESCE(SUM(LENGTH(evidence)), 0) AS evidence_chars
                   FROM relations WHERE scope=?""",
                (scope,),
            ).fetchone()
            graph_entities = conn.execute(
                """SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id,
                          COALESCE(MAX(updated_at), '') AS updated
                   FROM entities WHERE scope=? AND entity_type='research_claim'""",
                (scope,),
            ).fetchone()
        return (
            int(document["n"]), int(document["max_id"]), str(document["updated"]),
            int(research["n"]), int(research["max_id"]), str(research["updated"]),
            int(memory["n"]), int(memory["max_id"]), str(memory["updated"]),
            int(graph["n"]), int(graph["max_id"]),
            round(float(graph["confidence_sum"] or 0.0), 6),
            int(graph["evidence_chars"] or 0),
            int(graph_entities["n"]), int(graph_entities["max_id"]),
            str(graph_entities["updated"]),
        )

    def _deactivate_previous(self, scope: str) -> None:
        with connect() as conn:
            placeholders = ",".join("?" for _ in self.SOURCE_TYPES)
            conn.execute(
                f"""UPDATE canonical_fact_evidence
                    SET active=0
                    WHERE scope=? AND source_type IN ({placeholders})""",
                (scope, *self.SOURCE_TYPES),
            )
            conn.execute(
                """UPDATE canonical_fact_links
                   SET active=0, updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (scope,),
            )
            conn.commit()

    def _sync_document_facts(self, scope: str) -> int:
        with connect() as conn:
            rows = conn.execute(
                """SELECT f.*, d.filename, d.family_key, d.version_label,
                          d.version_rank, d.previous_version_id,
                          d.quality_score AS document_quality,
                          d.studied_at
                   FROM document_facts f
                   JOIN documents d ON d.id=f.document_id
                   WHERE f.scope=? AND f.status='grounded'
                     AND d.status='studied'
                   ORDER BY f.id ASC""",
                (scope,),
            ).fetchall()

        count = 0
        for row in rows:
            item = dict(row)
            family = str(item.get("family_key") or "").strip()
            fact_type = str(item.get("fact_type") or "statement")
            subject = str(item.get("subject") or "").strip()
            structured = (
                fact_type in {"key_value", "ai_grounded"}
                and subject.casefold() != "document"
            )
            if structured:
                # Atomic structured facts may fuse across independent document
                # families because fact_key is derived from subject+predicate.
                canonical_key = (
                    f"fact:{self._key_part(str(item['fact_key']))}"
                )
            else:
                # Generic metadata such as mentions_date/amount/email is not
                # globally unique. Keep it inside document lineage/family.
                identity = family or f"document-{int(item['document_id'])}"
                canonical_key = (
                    f"document:{self._key_part(identity)}:"
                    f"{self._key_part(str(item['fact_key']))}"
                )
            fact_id, value_id = self._upsert_fact_value(
                scope=scope,
                canonical_key=canonical_key,
                namespace="document",
                subject=str(item.get("subject") or ""),
                predicate=str(item.get("predicate") or ""),
                fact_type=str(item.get("fact_type") or "statement"),
                display_value=str(item.get("value") or ""),
                normalized_value=str(item.get("normalized_value") or ""),
            )
            provenance = self._json(item.get("provenance_json"), {})
            provenance.update(
                {
                    "document_id": int(item["document_id"]),
                    "document_fact_id": int(item["id"]),
                    "filename": item.get("filename"),
                    "family_key": family,
                    "version_label": item.get("version_label"),
                    "version_rank": item.get("version_rank"),
                    "previous_version_id": item.get("previous_version_id"),
                    "document_quality": item.get("document_quality"),
                }
            )
            independence_group = (
                f"document_family:{family}"
                if family
                else f"document:{int(item['document_id'])}"
            )
            self._upsert_evidence(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                source_type="document_fact",
                source_ref=f"document_fact:{int(item['id'])}",
                source_group=f"document:{int(item['document_id'])}",
                independence_group=independence_group,
                source_record_type="document_fact",
                source_record_id=int(item["id"]),
                stance="support",
                is_independent=True,
                confidence=float(item.get("confidence") or 0.0),
                lineage_root=(
                    f"document_family:{family}" if family else ""
                ),
                provenance=provenance,
                content_excerpt=(
                    f"{item.get('subject') or ''} "
                    f"{item.get('predicate') or ''} "
                    f"{item.get('value') or ''}"
                ).strip(),
            )
            self._upsert_link(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                linked_type="document_fact",
                linked_id=int(item["id"]),
                linked_key=str(item["fact_key"]),
                relation="source",
                metadata=provenance,
            )
            count += 1
        return count

    def _sync_research_claims(self, scope: str) -> int:
        with connect() as conn:
            claims = conn.execute(
                """SELECT * FROM research_claims
                   WHERE scope=? AND status IN
                     ('candidate','supported','trusted','conflicted')
                   ORDER BY id ASC""",
                (scope,),
            ).fetchall()

        count = 0
        for row in claims:
            claim = dict(row)
            statement = str(claim.get("statement") or "").strip()
            if not statement:
                continue
            canonical_key = f"research:{claim['claim_key']}"
            normalized_value = "statement:" + self._hash(statement)
            fact_id, value_id = self._upsert_fact_value(
                scope=scope,
                canonical_key=canonical_key,
                namespace="research",
                subject="research",
                predicate="claim",
                fact_type="statement",
                display_value=statement,
                normalized_value=normalized_value,
            )

            support_ids = self._int_list(
                self._json(claim.get("support_evidence_json"), [])
            )
            contradiction_ids = self._int_list(
                self._json(claim.get("contradiction_evidence_json"), [])
            )
            evidence_ids = sorted(set(support_ids + contradiction_ids))
            evidence_map: dict[int, dict] = {}
            if evidence_ids:
                placeholders = ",".join("?" for _ in evidence_ids)
                with connect() as conn:
                    rows = conn.execute(
                        f"""SELECT * FROM research_evidence
                            WHERE scope=? AND id IN ({placeholders})""",
                        (scope, *evidence_ids),
                    ).fetchall()
                evidence_map = {int(item["id"]): dict(item) for item in rows}

            for evidence_id in evidence_ids:
                evidence = evidence_map.get(evidence_id)
                if not evidence:
                    continue
                stance = (
                    "contradict"
                    if evidence_id in contradiction_ids
                    else "support"
                )
                source_group = str(
                    evidence.get("source_group") or f"research:{evidence_id}"
                )
                is_independent = source_group != "derived_knowledge"
                metadata = self._json(evidence.get("metadata_json"), {})
                self._upsert_evidence(
                    scope=scope,
                    fact_id=fact_id,
                    value_id=value_id,
                    source_type="research_evidence",
                    source_ref=f"research_evidence:{evidence_id}",
                    source_group=source_group,
                    independence_group=source_group,
                    source_record_type="research_evidence",
                    source_record_id=evidence_id,
                    stance=stance,
                    is_independent=is_independent,
                    confidence=float(
                        evidence.get("evidence_score")
                        or evidence.get("reliability")
                        or 0.0
                    ),
                    lineage_root=source_group,
                    provenance={
                        "research_claim_id": int(claim["id"]),
                        "research_session_id": int(claim["session_id"]),
                        "research_evidence_id": evidence_id,
                        "source_type": evidence.get("source_type"),
                        "source_ref": evidence.get("source_ref"),
                        "metadata": metadata,
                    },
                    content_excerpt=str(evidence.get("content") or "")[:800],
                )

            self._upsert_link(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                linked_type="research_claim",
                linked_id=int(claim["id"]),
                linked_key=str(claim["claim_key"]),
                relation="canonical_source",
                metadata={
                    "status": claim.get("status"),
                    "confidence": claim.get("confidence"),
                    "independent_groups": claim.get("independent_groups"),
                },
            )
            if claim.get("promoted_memory_id"):
                self._upsert_link(
                    scope=scope,
                    fact_id=fact_id,
                    value_id=value_id,
                    linked_type="memory",
                    linked_id=int(claim["promoted_memory_id"]),
                    linked_key=f"research_claim:{claim['claim_key']}",
                    relation="derived_promotion",
                    metadata={"independent": False},
                )
            if claim.get("promoted_entity_id"):
                self._upsert_link(
                    scope=scope,
                    fact_id=fact_id,
                    value_id=value_id,
                    linked_type="graph_entity",
                    linked_id=int(claim["promoted_entity_id"]),
                    linked_key=f"research_claim:{claim['claim_key']}",
                    relation="derived_promotion",
                    metadata={"independent": False},
                )
            count += 1
        return count

    def _sync_memories(self, scope: str) -> int:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM memories
                   WHERE scope=? AND status='active'
                     AND memory_key IS NOT NULL
                     AND TRIM(memory_key)<>''
                   ORDER BY id ASC""",
                (scope,),
            ).fetchall()

        count = 0
        for row in rows:
            item = dict(row)
            memory_key = str(item.get("memory_key") or "").strip()
            if memory_key.startswith("research_claim:"):
                claim_key = memory_key.split(":", 1)[1]
                target = self._fact_by_key(
                    scope, f"research:{claim_key}"
                )
                if target:
                    self._upsert_link(
                        scope=scope,
                        fact_id=int(target["id"]),
                        value_id=target.get("current_value_id"),
                        linked_type="memory",
                        linked_id=int(item["id"]),
                        linked_key=memory_key,
                        relation="derived_promotion",
                        metadata={
                            "kind": item.get("kind"),
                            "source": item.get("source"),
                            "independent": False,
                        },
                    )
                count += 1
                continue

            canonical_key = f"memory:{self._key_part(memory_key)}"
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            fact_id, value_id = self._upsert_fact_value(
                scope=scope,
                canonical_key=canonical_key,
                namespace="memory",
                subject="memory",
                predicate=memory_key,
                fact_type="statement",
                display_value=content,
                normalized_value="statement:" + self._hash(content),
            )
            source = str(item.get("source") or "unknown")
            kind = str(item.get("kind") or "context")
            derived = (
                source.startswith("autonomous_research:")
                or kind == "researched_knowledge"
            )
            self._upsert_evidence(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                source_type="memory",
                source_ref=f"memory:{int(item['id'])}",
                source_group=f"memory:{memory_key}",
                independence_group=f"memory:{memory_key}",
                source_record_type="memory",
                source_record_id=int(item["id"]),
                stance="support",
                is_independent=not derived,
                confidence=float(item.get("confidence") or 0.0),
                lineage_root=f"memory:{memory_key}",
                provenance={
                    "memory_id": int(item["id"]),
                    "memory_key": memory_key,
                    "kind": kind,
                    "source": source,
                    "tags": self._json(item.get("tags_json"), []),
                },
                content_excerpt=content[:800],
            )
            self._upsert_link(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                linked_type="memory",
                linked_id=int(item["id"]),
                linked_key=memory_key,
                relation="source" if not derived else "derived_promotion",
                metadata={"source": source, "kind": kind, "independent": not derived},
            )
            count += 1
        return count

    def _sync_graph(self, scope: str) -> int:
        with connect() as conn:
            entities = conn.execute(
                """SELECT * FROM entities
                   WHERE scope=? AND entity_type='research_claim'""",
                (scope,),
            ).fetchall()
            relations = conn.execute(
                """SELECT r.*, s.entity_type AS source_type,
                          s.canonical_name AS source_name,
                          t.entity_type AS target_type,
                          t.canonical_name AS target_name
                   FROM relations r
                   JOIN entities s ON s.id=r.source_entity_id
                   JOIN entities t ON t.id=r.target_entity_id
                   WHERE r.scope=?
                   ORDER BY r.id ASC""",
                (scope,),
            ).fetchall()

        for row in entities:
            item = dict(row)
            data = self._json(item.get("data_json"), {})
            provenance = data.get("provenance") or {}
            claim_id = provenance.get("research_claim_id")
            if claim_id is None:
                continue
            with connect() as conn:
                claim = conn.execute(
                    """SELECT claim_key FROM research_claims
                       WHERE id=? AND scope=?""",
                    (int(claim_id), scope),
                ).fetchone()
            if not claim:
                continue
            fact = self._fact_by_key(scope, f"research:{claim['claim_key']}")
            if fact:
                self._upsert_link(
                    scope=scope,
                    fact_id=int(fact["id"]),
                    value_id=fact.get("current_value_id"),
                    linked_type="graph_entity",
                    linked_id=int(item["id"]),
                    linked_key=str(item.get("canonical_name") or ""),
                    relation="derived_promotion",
                    metadata={"independent": False, "provenance": provenance},
                )

        count = 0
        for row in relations:
            item = dict(row)
            identity = "|".join(
                [
                    str(item.get("source_type") or ""),
                    str(item.get("source_name") or ""),
                    str(item.get("relation_type") or ""),
                    str(item.get("target_type") or ""),
                    str(item.get("target_name") or ""),
                ]
            )
            canonical_key = "graph_relation:" + self._hash(identity)
            display = (
                f"{item.get('source_name') or ''} "
                f"{item.get('relation_type') or ''} "
                f"{item.get('target_name') or ''}"
            ).strip()
            fact_id, value_id = self._upsert_fact_value(
                scope=scope,
                canonical_key=canonical_key,
                namespace="graph",
                subject=str(item.get("source_name") or ""),
                predicate=str(item.get("relation_type") or ""),
                fact_type="relation",
                display_value=display,
                normalized_value="relation:true",
            )
            self._upsert_evidence(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                source_type="graph_relation",
                source_ref=f"relation:{int(item['id'])}",
                source_group=f"graph_relation:{int(item['id'])}",
                independence_group=f"graph_relation:{int(item['id'])}",
                source_record_type="graph_relation",
                source_record_id=int(item["id"]),
                stance="support",
                is_independent=False,
                confidence=float(item.get("confidence") or 0.0),
                lineage_root="knowledge_graph",
                provenance={
                    "relation_id": int(item["id"]),
                    "source_entity_id": int(item["source_entity_id"]),
                    "target_entity_id": int(item["target_entity_id"]),
                    "evidence": str(item.get("evidence") or "")[:800],
                },
                content_excerpt=display,
            )
            self._upsert_link(
                scope=scope,
                fact_id=fact_id,
                value_id=value_id,
                linked_type="graph_relation",
                linked_id=int(item["id"]),
                linked_key=canonical_key,
                relation="derived_model",
                metadata={"independent": False},
            )
            count += 1
        return count

    def _upsert_fact_value(
        self,
        *,
        scope: str,
        canonical_key: str,
        namespace: str,
        subject: str,
        predicate: str,
        fact_type: str,
        display_value: str,
        normalized_value: str,
    ) -> tuple[int, int]:
        normalized_value = self._normalize_value(normalized_value or display_value)
        if not normalized_value:
            normalized_value = "empty:" + self._hash(display_value)
        with connect() as conn:
            row = conn.execute(
                """SELECT id FROM canonical_facts
                   WHERE scope=? AND canonical_key=?""",
                (scope, canonical_key),
            ).fetchone()
            if row:
                fact_id = int(row["id"])
                conn.execute(
                    """UPDATE canonical_facts
                       SET namespace=?, subject=?, predicate=?, fact_type=?,
                           last_seen_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        namespace,
                        subject[:300],
                        predicate[:180],
                        fact_type[:80],
                        fact_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO canonical_facts(
                           scope, canonical_key, namespace, subject,
                           predicate, fact_type
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        scope,
                        canonical_key[:900],
                        namespace[:80],
                        subject[:300],
                        predicate[:180],
                        fact_type[:80],
                    ),
                )
                fact_id = int(cur.lastrowid)

            value = conn.execute(
                """SELECT id FROM canonical_fact_values
                   WHERE fact_id=? AND normalized_value=?""",
                (fact_id, normalized_value[:1800]),
            ).fetchone()
            if value:
                value_id = int(value["id"])
                conn.execute(
                    """UPDATE canonical_fact_values
                       SET display_value=?, last_seen_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (display_value[:1800], value_id),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO canonical_fact_values(
                           scope, fact_id, normalized_value, display_value
                       ) VALUES (?, ?, ?, ?)""",
                    (
                        scope,
                        fact_id,
                        normalized_value[:1800],
                        display_value[:1800],
                    ),
                )
                value_id = int(cur.lastrowid)
            conn.commit()
        return fact_id, value_id

    def _upsert_evidence(
        self,
        *,
        scope: str,
        fact_id: int,
        value_id: int,
        source_type: str,
        source_ref: str,
        source_group: str,
        independence_group: str,
        source_record_type: str,
        source_record_id: int | None,
        stance: str,
        is_independent: bool,
        confidence: float,
        lineage_root: str,
        provenance: dict,
        content_excerpt: str,
    ) -> None:
        confidence = max(0.0, min(1.0, float(confidence)))
        with connect() as conn:
            conn.execute(
                """INSERT INTO canonical_fact_evidence(
                       scope, fact_id, value_id, source_type, source_ref,
                       source_group, independence_group, source_record_type,
                       source_record_id, stance, is_independent, confidence,
                       lineage_root, provenance_json, content_excerpt, active
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(value_id, source_type, source_ref, stance)
                   DO UPDATE SET
                       source_group=excluded.source_group,
                       independence_group=excluded.independence_group,
                       source_record_type=excluded.source_record_type,
                       source_record_id=excluded.source_record_id,
                       is_independent=excluded.is_independent,
                       confidence=excluded.confidence,
                       lineage_root=excluded.lineage_root,
                       provenance_json=excluded.provenance_json,
                       content_excerpt=excluded.content_excerpt,
                       active=1,
                       last_seen_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    fact_id,
                    value_id,
                    source_type,
                    source_ref[:500],
                    source_group[:500],
                    independence_group[:500],
                    source_record_type[:120],
                    source_record_id,
                    stance,
                    1 if is_independent else 0,
                    confidence,
                    lineage_root[:500],
                    json.dumps(provenance, ensure_ascii=False),
                    content_excerpt[:1000],
                ),
            )
            conn.commit()

    def _upsert_link(
        self,
        *,
        scope: str,
        fact_id: int,
        value_id: int | None,
        linked_type: str,
        linked_id: int | None,
        linked_key: str,
        relation: str,
        metadata: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO canonical_fact_links(
                       scope, fact_id, value_id, linked_type, linked_id,
                       linked_key, relation, metadata_json, active
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
                   ON CONFLICT(fact_id, linked_type, linked_id, linked_key, relation)
                   DO UPDATE SET
                       value_id=excluded.value_id,
                       metadata_json=excluded.metadata_json,
                       active=1,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    fact_id,
                    value_id,
                    linked_type[:120],
                    linked_id,
                    linked_key[:700],
                    relation[:120],
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            conn.commit()

    def _recompute_fact(self, fact_id: int) -> dict:
        with connect() as conn:
            fact = conn.execute(
                "SELECT * FROM canonical_facts WHERE id=?",
                (fact_id,),
            ).fetchone()
            values = conn.execute(
                """SELECT * FROM canonical_fact_values
                   WHERE fact_id=? ORDER BY id""",
                (fact_id,),
            ).fetchall()
        if not fact:
            return {"changed": False, "lifecycle_linked": False}

        lineage_replacements = self._prune_document_lineage_evidence(
            fact=dict(fact),
        )

        value_results = []
        for row in values:
            replacement = lineage_replacements.get(int(row["id"])) or {}
            value_results.append(
                self._recompute_value(
                    dict(row),
                    superseded_by_value_id=replacement.get("winner_value_id"),
                    lineage_families=replacement.get("families") or [],
                )
            )

        with connect() as conn:
            refreshed = [
                dict(row)
                for row in conn.execute(
                    """SELECT * FROM canonical_fact_values
                       WHERE fact_id=? ORDER BY id""",
                    (fact_id,),
                ).fetchall()
            ]

        active = [
            item
            for item in refreshed
            if int(item.get("active_evidence") or 0) > 0
            and item.get("state") != "superseded"
        ]
        old_state = str(fact["state"])
        old_value_id = fact["current_value_id"]
        old_value = str(fact["current_value"] or "")

        if not active:
            state = "empty"
            current = None
            confidence = 0.0
        elif len(active) > 1:
            state = "conflicted"
            current = sorted(
                active,
                key=lambda item: (
                    float(item.get("confidence") or 0.0),
                    int(item.get("independent_groups") or 0),
                    int(item["id"]),
                ),
                reverse=True,
            )[0]
            confidence = float(current.get("confidence") or 0.0)
        else:
            current = active[0]
            state = str(current.get("state") or "observed")
            confidence = float(current.get("confidence") or 0.0)

        current_id = int(current["id"]) if current else None
        current_value = str(current.get("display_value") or "") if current else ""
        current_normalized = (
            str(current.get("normalized_value") or "") if current else ""
        )
        independent_groups = max(
            [int(item.get("independent_groups") or 0) for item in active]
            or [0]
        )
        evidence_count = sum(
            int(item.get("active_evidence") or 0) for item in active
        )
        conflict_count = max(0, len(active) - 1)

        changed = (
            old_state != state
            or old_value_id != current_id
            or old_value != current_value
        )
        with connect() as conn:
            conn.execute(
                """UPDATE canonical_facts
                   SET state=?, confidence=?, current_value_id=?,
                       current_value=?, current_normalized_value=?,
                       active_values=?, independent_groups=?,
                       evidence_count=?, conflict_count=?,
                       verified_at=CASE
                         WHEN ?='verified' AND verified_at IS NULL
                         THEN CURRENT_TIMESTAMP ELSE verified_at END,
                       conflicted_at=CASE
                         WHEN ?='conflicted' AND conflicted_at IS NULL
                         THEN CURRENT_TIMESTAMP ELSE conflicted_at END,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    state,
                    round(confidence, 4),
                    current_id,
                    current_value[:1800],
                    current_normalized[:1800],
                    len(active),
                    independent_groups,
                    evidence_count,
                    conflict_count,
                    state,
                    state,
                    fact_id,
                ),
            )
            conn.commit()

        if changed:
            self._event(
                scope=str(fact["scope"]),
                fact_id=fact_id,
                value_id=current_id,
                event_type="fact_state_changed",
                from_state=old_state,
                to_state=state,
                details={
                    "previous_value_id": old_value_id,
                    "current_value_id": current_id,
                    "previous_value": old_value[:600],
                    "current_value": current_value[:600],
                    "active_values": len(active),
                    "independent_groups": independent_groups,
                },
            )

        lifecycle_linked = self._sync_lifecycle(fact_id)
        return {
            "changed": changed,
            "state": state,
            "current_value_id": current_id,
            "lifecycle_linked": lifecycle_linked,
        }

    def _recompute_value(
        self,
        value: dict,
        *,
        superseded_by_value_id: int | None = None,
        lineage_families: list[str] | None = None,
    ) -> dict:
        value_id = int(value["id"])
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM canonical_fact_evidence
                   WHERE value_id=? AND active=1""",
                (value_id,),
            ).fetchall()

        supports = [
            dict(row)
            for row in rows
            if row["stance"] == "support"
        ]
        contradictions = [
            dict(row)
            for row in rows
            if row["stance"] == "contradict"
        ]
        independent_support = [
            row for row in supports if int(row["is_independent"] or 0) == 1
        ]
        independent_contradictions = [
            row
            for row in contradictions
            if int(row["is_independent"] or 0) == 1
        ]

        support_by_group: dict[str, float] = {}
        for row in independent_support:
            group = str(row["independence_group"])
            support_by_group[group] = max(
                support_by_group.get(group, 0.0),
                float(row["confidence"] or 0.0),
            )
        contradiction_by_group: dict[str, float] = {}
        for row in independent_contradictions:
            group = str(row["independence_group"])
            contradiction_by_group[group] = max(
                contradiction_by_group.get(group, 0.0),
                float(row["confidence"] or 0.0),
            )

        support_groups = len(support_by_group)
        contradiction_groups = len(contradiction_by_group)
        average_support = (
            sum(support_by_group.values()) / support_groups
            if support_groups
            else 0.0
        )
        average_contradiction = (
            sum(contradiction_by_group.values()) / contradiction_groups
            if contradiction_groups
            else 0.0
        )

        if contradiction_groups and average_contradiction >= 0.55:
            state = "conflicted"
        elif (
            support_groups >= 3
            and average_support >= 0.72
        ) or (
            support_groups >= 2
            and average_support >= 0.85
        ):
            state = "verified"
        elif (
            support_groups >= 2
            and average_support >= 0.60
        ) or (
            support_groups >= 1
            and average_support >= 0.85
        ):
            state = "supported"
        else:
            state = "observed"

        if support_groups:
            confidence = max(
                0.0,
                min(
                    1.0,
                    average_support
                    + min(0.12, 0.04 * max(0, support_groups - 1))
                    - 0.18 * min(2, contradiction_groups),
                ),
            )
        else:
            confidence = min(
                0.49,
                max(
                    [float(row["confidence"] or 0.0) * 0.5 for row in supports]
                    or [0.0]
                ),
            )

        source_types = len({str(row["source_type"]) for row in supports})
        intrinsic_state = state
        old_state = str(value.get("state") or "observed")
        forced_superseded = superseded_by_value_id is not None
        if forced_superseded:
            state = "superseded"
        elif old_state == "superseded" and not rows:
            # Historical value with no currently active source stays historical.
            state = "superseded"
        else:
            state = intrinsic_state

        with connect() as conn:
            conn.execute(
                """UPDATE canonical_fact_values
                   SET state=?, confidence=?, independent_groups=?,
                       source_types=?, active_evidence=?,
                       contradiction_groups=?,
                       superseded_at=CASE
                         WHEN ?='superseded' AND superseded_at IS NULL
                         THEN CURRENT_TIMESTAMP
                         WHEN ?<>'superseded' THEN NULL
                         ELSE superseded_at END,
                       superseded_by_value_id=CASE
                         WHEN ?='superseded' THEN ?
                         ELSE NULL END,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    state,
                    round(confidence, 4),
                    support_groups,
                    source_types,
                    len(rows),
                    contradiction_groups,
                    state,
                    state,
                    state,
                    superseded_by_value_id,
                    value_id,
                ),
            )
            conn.commit()

        if old_state != state:
            if state == "superseded" and superseded_by_value_id is not None:
                event_type = "value_superseded_by_document_version"
            elif old_state == "superseded" and state != "superseded":
                event_type = "value_reactivated_by_document_lineage"
            else:
                event_type = "value_state_changed"
            self._event(
                scope=str(value["scope"]),
                fact_id=int(value["fact_id"]),
                value_id=value_id,
                event_type=event_type,
                from_state=old_state,
                to_state=state,
                details={
                    "independent_groups": support_groups,
                    "contradiction_groups": contradiction_groups,
                    "average_support": round(average_support, 4),
                    "average_contradiction": round(average_contradiction, 4),
                    "superseded_by_value_id": superseded_by_value_id,
                    "families": list(lineage_families or []),
                    "ordering": (
                        "version_rank_or_previous_version"
                        if event_type in {
                            "value_superseded_by_document_version",
                            "value_reactivated_by_document_lineage",
                        }
                        else ""
                    ),
                },
            )

        return {
            **value,
            "state": state,
            "intrinsic_state": intrinsic_state,
            "confidence": confidence,
            "independent_groups": support_groups,
            "source_types": source_types,
            "active_evidence": len(rows),
            "contradiction_groups": contradiction_groups,
        }

    def _prune_document_lineage_evidence(
        self,
        *,
        fact: dict,
    ) -> dict[int, dict]:
        """Deactivate superseded document-version evidence before value scoring.

        Lineage is evaluated independently per document family. This prevents an
        old version in family A from counting as current evidence merely because
        the same value is still current in family B.
        """
        if str(fact.get("namespace")) != "document":
            return {}

        with connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    """SELECT e.id AS evidence_id, e.value_id,
                              e.provenance_json
                       FROM canonical_fact_evidence e
                       WHERE e.fact_id=? AND e.active=1
                         AND e.source_type='document_fact'
                         AND e.stance='support'
                       ORDER BY e.id""",
                    (int(fact["id"]),),
                ).fetchall()
            ]
        if len(rows) <= 1:
            return {}

        by_family: dict[str, list[dict]] = {}
        for row in rows:
            provenance = self._json(row.get("provenance_json"), {})
            family = str(provenance.get("family_key") or "").strip()
            document_id = provenance.get("document_id")
            if not family or document_id is None:
                continue
            row["provenance"] = provenance
            by_family.setdefault(family, []).append(row)

        replacement_candidates: dict[int, dict[int, set[str]]] = {}
        for family, family_rows in by_family.items():
            represented = {
                int(row["provenance"].get("document_id") or 0)
                for row in family_rows
            }
            if len(represented) <= 1:
                continue

            rank_by_document: dict[int, int | None] = {}
            previous_by_document: dict[int, int | None] = {}
            for row in family_rows:
                provenance = row["provenance"]
                document_id = int(provenance.get("document_id") or 0)
                raw_rank = provenance.get("version_rank")
                try:
                    rank = int(raw_rank) if raw_rank is not None else None
                except (TypeError, ValueError):
                    rank = None
                rank_by_document[document_id] = rank
                raw_previous = provenance.get("previous_version_id")
                try:
                    previous = (
                        int(raw_previous)
                        if raw_previous is not None
                        else None
                    )
                except (TypeError, ValueError):
                    previous = None
                previous_by_document[document_id] = previous

            ranked = [
                (document_id, rank)
                for document_id, rank in rank_by_document.items()
                if rank is not None
            ]
            latest_documents: set[int] = set()
            if (
                len(ranked) == len(represented)
                and len({rank for _, rank in ranked}) > 1
            ):
                max_rank = max(rank for _, rank in ranked)
                latest_documents = {
                    document_id
                    for document_id, rank in ranked
                    if rank == max_rank
                }
            else:
                referenced_previous = {
                    previous
                    for previous in previous_by_document.values()
                    if previous in represented
                }
                leaves = represented - referenced_previous
                if leaves and len(leaves) < len(represented):
                    latest_documents = leaves

            if not latest_documents:
                continue

            latest_value_ids = {
                int(row["value_id"])
                for row in family_rows
                if int(row["provenance"].get("document_id") or 0)
                in latest_documents
            }
            # Conflicting latest versions are ambiguous; retain all evidence.
            if len(latest_value_ids) != 1:
                continue
            winner_value_id = next(iter(latest_value_ids))

            historical_rows = [
                row
                for row in family_rows
                if int(row["provenance"].get("document_id") or 0)
                not in latest_documents
            ]
            if not historical_rows:
                continue

            with connect() as conn:
                for row in historical_rows:
                    conn.execute(
                        """UPDATE canonical_fact_evidence
                           SET active=0, last_seen_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (int(row["evidence_id"]),),
                    )
                conn.commit()

            for row in historical_rows:
                loser_value_id = int(row["value_id"])
                if loser_value_id == winner_value_id:
                    continue
                replacement_candidates.setdefault(
                    loser_value_id,
                    {},
                ).setdefault(
                    winner_value_id,
                    set(),
                ).add(family)

        replacements: dict[int, dict] = {}
        with connect() as conn:
            for loser_value_id, winners in replacement_candidates.items():
                active_row = conn.execute(
                    """SELECT COUNT(*) AS n
                       FROM canonical_fact_evidence
                       WHERE value_id=? AND active=1
                         AND stance='support'""",
                    (loser_value_id,),
                ).fetchone()
                # If another current source still supports this value, it is
                # not historical globally; keep it active as a competing value.
                if int(active_row["n"] or 0) > 0:
                    continue
                if len(winners) != 1:
                    continue
                winner_value_id, families = next(iter(winners.items()))
                replacements[loser_value_id] = {
                    "winner_value_id": int(winner_value_id),
                    "families": sorted(families),
                }
        return replacements

    def _sync_lifecycle(self, fact_id: int) -> bool:
        if self.knowledge_lifecycle is None:
            return False
        fact = self.fact(fact_id, scope=self._scope_for_fact(fact_id))
        if not fact:
            return False
        if fact.get("state") in {"empty", "conflicted"}:
            result = self.knowledge_lifecycle.update_canonical_status(
                scope=str(fact["scope"]),
                canonical_key=str(fact["canonical_key"]),
                canonical_state=str(fact.get("state") or "empty"),
                confidence=float(fact.get("confidence") or 0.0),
            )
            return bool(result.get("updated"))
        if not fact.get("current_value_id"):
            return False

        value_id = int(fact["current_value_id"])
        evidence = [
            row
            for row in self._value_evidence(value_id)
            if row.get("active")
            and row.get("stance") == "support"
            and row.get("is_independent")
        ]
        statement = self._statement_for_fact(fact)
        result = self.knowledge_lifecycle.observe_canonical_fact(
            scope=str(fact["scope"]),
            canonical_key=str(fact["canonical_key"]),
            normalized_value=str(fact.get("current_normalized_value") or ""),
            statement=statement,
            canonical_state=str(fact.get("state") or "observed"),
            confidence=float(fact.get("confidence") or 0.0),
            evidence=evidence,
        )
        claim_id = result.get("claim_id") if isinstance(result, dict) else None
        if claim_id:
            self._upsert_link(
                scope=str(fact["scope"]),
                fact_id=fact_id,
                value_id=value_id,
                linked_type="knowledge_claim",
                linked_id=int(claim_id),
                linked_key=str(fact["canonical_key"]),
                relation="lifecycle_projection",
                metadata={
                    "canonical_state": fact.get("state"),
                    "canonical_confidence": fact.get("confidence"),
                },
            )
            return True
        return False

    def _fact_detail(self, fact: dict) -> dict:
        fact_id = int(fact["id"])
        with connect() as conn:
            values = [
                dict(row)
                for row in conn.execute(
                    """SELECT * FROM canonical_fact_values
                       WHERE fact_id=?
                       ORDER BY
                         CASE state
                           WHEN 'verified' THEN 0
                           WHEN 'supported' THEN 1
                           WHEN 'observed' THEN 2
                           WHEN 'conflicted' THEN 3
                           ELSE 4
                         END,
                         confidence DESC, id DESC""",
                    (fact_id,),
                ).fetchall()
            ]
            links = [
                dict(row)
                for row in conn.execute(
                    """SELECT * FROM canonical_fact_links
                       WHERE fact_id=? AND active=1 ORDER BY id DESC""",
                    (fact_id,),
                ).fetchall()
            ]
        for value in values:
            value["evidence"] = self._value_evidence(int(value["id"]))
        for link in links:
            link["metadata"] = self._json(link.pop("metadata_json"), {})
        fact["values"] = values
        fact["links"] = links
        return fact

    def _value_evidence(self, value_id: int) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM canonical_fact_evidence
                   WHERE value_id=?
                   ORDER BY active DESC, is_independent DESC,
                            confidence DESC, id DESC""",
                (int(value_id),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["active"] = bool(item.get("active"))
            item["is_independent"] = bool(item.get("is_independent"))
            item["provenance"] = self._json(
                item.pop("provenance_json"),
                {},
            )
            result.append(item)
        return result

    def _fact_by_key(self, scope: str, canonical_key: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM canonical_facts
                   WHERE scope=? AND canonical_key=?""",
                (scope, canonical_key),
            ).fetchone()
        return dict(row) if row else None

    def _scope_for_fact(self, fact_id: int) -> str:
        with connect() as conn:
            row = conn.execute(
                "SELECT scope FROM canonical_facts WHERE id=?",
                (int(fact_id),),
            ).fetchone()
        return str(row["scope"]) if row else "personal"

    def _event(
        self,
        *,
        scope: str,
        fact_id: int,
        value_id: int | None,
        event_type: str,
        from_state: str,
        to_state: str,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO canonical_fact_events(
                       scope, fact_id, value_id, event_type,
                       from_state, to_state, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    fact_id,
                    value_id,
                    event_type,
                    from_state[:80],
                    to_state[:80],
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
        self._emit(
            "canonical_facts.event",
            scope=scope,
            payload={
                "fact_id": fact_id,
                "value_id": value_id,
                "event_type": event_type,
                "from_state": from_state,
                "to_state": to_state,
            },
            importance=0.62 if "conflict" in to_state or "superseded" in to_state else 0.38,
        )

    def _statement_for_fact(self, fact: dict) -> str:
        if fact.get("namespace") == "research":
            return str(fact.get("current_value") or "")
        subject = str(fact.get("subject") or "").strip()
        predicate = str(fact.get("predicate") or "").strip()
        value = str(fact.get("current_value") or "").strip()
        return " ".join(part for part in (subject, predicate, value) if part)

    def _emit(
        self,
        event_type: str,
        *,
        scope: str,
        payload: dict,
        importance: float,
    ) -> None:
        if self.events is not None:
            self.events.emit(
                event_type,
                scope=scope,
                payload=payload,
                importance=importance,
            )

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if value is None:
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(str(value))
        except (TypeError, ValueError, json.JSONDecodeError):
            return default

    @staticmethod
    def _int_list(value: Any) -> list[int]:
        result = []
        for item in value if isinstance(value, list) else []:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        normalized = cls._normalize_value(text)
        return {
            token
            for token in re.findall(r"[a-zа-я0-9_./:+#%-]+", normalized)
            if len(token) >= 3 or any(ch.isdigit() for ch in token)
        }

    @classmethod
    def _normalize_value(cls, value: str) -> str:
        return _SPACE_RE.sub(
            " ",
            str(value or "").strip().casefold().replace("ё", "е"),
        )[:1800]

    @classmethod
    def _key_part(cls, value: str) -> str:
        normalized = cls._normalize_value(value)
        if len(normalized) <= 220:
            return normalized.replace(" ", "_")
        return cls._hash(normalized)

    @classmethod
    def _hash(cls, value: str) -> str:
        return hashlib.sha256(
            cls._normalize_value(value).encode("utf-8")
        ).hexdigest()
