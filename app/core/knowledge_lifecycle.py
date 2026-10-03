from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from ..db import connect

_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_./:+#%-]+", re.UNICODE)


class KnowledgeLifecycleEngine:
    """Persistent evidence-first lifecycle for knowledge and hypotheses.

    Assistant text is never a knowledge source. Only evidence already present
    in the reasoning path may create or strengthen a durable claim.
    """

    VERSION = "aishin-knowledge-lifecycle-v1"
    CLAIM_STATES = ("observed", "supported", "verified", "contradicted", "rejected", "superseded")
    HYPOTHESIS_STATES = ("candidate", "testing", "supported", "confirmed", "rejected")

    def __init__(self, *, events: Any | None = None) -> None:
        self.events = events

    def observe_reasoning(
        self,
        *,
        request_id: str,
        scope: str,
        evidence: list[dict],
        contradictions: list[dict],
        hypothesis_run: dict,
        verification: dict | None,
    ) -> dict:
        scope = (scope or "personal").strip() or "personal"
        verification_ok = self._verification_passed(verification)
        sources = [
            src for i, item in enumerate(evidence[:48])
            if (src := self._source(item, i, False)) is not None
        ]
        opposing = [
            src for i, item in enumerate(contradictions[:24])
            if (src := self._source(item, i, True)) is not None
        ]
        claim_ids: list[int] = []
        for source in sources:
            claim_id = self._upsert_claim(
                scope, request_id, source["content"], source["source_type"]
            )
            claim_ids.append(claim_id)
            self._claim_evidence(scope, claim_id, request_id, source, "support")

        unique_claim_ids = set(claim_ids)
        if verification_ok and unique_claim_ids:
            with connect() as conn:
                for claim_id in unique_claim_ids:
                    conn.execute(
                        """UPDATE knowledge_claims
                           SET verification_passes=verification_passes+1,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (claim_id,),
                    )
                conn.commit()

        for claim_id in unique_claim_ids:
            claim = self._claim(claim_id)
            if not claim:
                continue
            for source in opposing:
                if self._similarity(claim["statement"], source["content"]) >= 0.16:
                    self._claim_evidence(
                        scope, claim_id, request_id, source, "contradict"
                    )

        claims = [self._recompute_claim(cid) for cid in unique_claim_ids]
        claims = [item for item in claims if item]
        hypotheses = self._observe_hypotheses(
            request_id=request_id,
            scope=scope,
            run=hypothesis_run or {},
            evidence=sources,
            contradictions=opposing,
            verification_ok=verification_ok,
        )
        result = {
            "version": self.VERSION,
            "scope": scope,
            "request_id": request_id,
            "verification_passed": verification_ok,
            "claims_observed": len(claims),
            "claim_states": self._state_counts(claims),
            "hypotheses_observed": len(hypotheses),
            "hypothesis_states": self._state_counts(hypotheses),
        }
        self._emit("knowledge.lifecycle.observed", scope, result, 0.28)
        return result

    def record_response_grounding(
        self, *, request_id: str, scope: str, grounding: dict
    ) -> dict:
        if not grounding or not grounding.get("applicable"):
            return {"recorded": False, "reason": "grounding_not_applicable"}
        unsupported = int(grounding.get("claims_unsupported") or 0)
        status = str(grounding.get("status") or "unscored")
        event_type = (
            "response_grounding_risk"
            if unsupported or status == "weak"
            else "response_grounding_ok"
        )
        event_id = self._learning_event(
            scope,
            event_type,
            "request",
            0,
            f"grounding={status}; unsupported={unsupported}",
            float(grounding.get("overall") or 0.0),
            {
                "request_id": request_id,
                "grounding_status": status,
                "overall": grounding.get("overall"),
                "claims_total": grounding.get("claims_total"),
                "claims_supported": grounding.get("claims_supported"),
                "claims_partial": grounding.get("claims_partial"),
                "claims_unsupported": unsupported,
                "source_groups": grounding.get("source_groups"),
            },
        )
        return {"recorded": True, "event_id": event_id, "event_type": event_type}

    def summary(self, *, scope: str) -> dict:
        with connect() as conn:
            claims = {
                str(row["state"]): int(row["n"])
                for row in conn.execute(
                    "SELECT state, COUNT(*) n FROM knowledge_claims WHERE scope=? GROUP BY state",
                    (scope,),
                ).fetchall()
            }
            hypotheses = {
                str(row["state"]): int(row["n"])
                for row in conn.execute(
                    "SELECT state, COUNT(*) n FROM hypothesis_registry WHERE scope=? GROUP BY state",
                    (scope,),
                ).fetchall()
            }
            events = {
                str(row["event_type"]): int(row["n"])
                for row in conn.execute(
                    "SELECT event_type, COUNT(*) n FROM knowledge_learning_events WHERE scope=? GROUP BY event_type",
                    (scope,),
                ).fetchall()
            }
            evidence_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM knowledge_evidence WHERE scope=?", (scope,)
                ).fetchone()[0]
            )
            studied_documents = int(
                conn.execute(
                    """SELECT COUNT(*) FROM documents
                       WHERE scope=? AND status='studied'""",
                    (scope,),
                ).fetchone()[0]
            )
            grounded_document_facts = int(
                conn.execute(
                    """SELECT COUNT(*) FROM document_facts
                       WHERE scope=? AND status='grounded'""",
                    (scope,),
                ).fetchone()[0]
            )
            trusted_research_claims = int(
                conn.execute(
                    """SELECT COUNT(*) FROM research_claims
                       WHERE scope=? AND status='trusted'""",
                    (scope,),
                ).fetchone()[0]
            )
        claim_states = {key: claims.get(key, 0) for key in self.CLAIM_STATES}
        hypothesis_states = {
            key: hypotheses.get(key, 0) for key in self.HYPOTHESIS_STATES
        }
        return {
            "version": self.VERSION,
            "scope": scope,
            "claims": claim_states,
            "hypotheses": hypothesis_states,
            "evidence_count": evidence_count,
            "studied_documents": studied_documents,
            "grounded_document_facts": grounded_document_facts,
            "trusted_research_claims": trusted_research_claims,
            "verified_knowledge": claim_states["verified"],
            "contradicted_knowledge": claim_states["contradicted"],
            "confirmed_hypotheses": hypothesis_states["confirmed"],
            "rejected_hypotheses": hypothesis_states["rejected"],
            "errors_detected": events.get("error_detected", 0),
            "corrections_confirmed": events.get("correction_confirmed", 0),
            "learning_events": events,
        }

    def claims(self, *, scope: str, state: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            if state:
                rows = conn.execute(
                    "SELECT * FROM knowledge_claims WHERE scope=? AND state=? ORDER BY id DESC LIMIT ?",
                    (scope, state, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM knowledge_claims WHERE scope=? ORDER BY id DESC LIMIT ?",
                    (scope, limit),
                ).fetchall()
            items = [dict(row) for row in rows]
            ids = [int(item["id"]) for item in items]
            evidence_by_claim: dict[int, list[dict]] = {cid: [] for cid in ids}
            if ids:
                placeholders = ",".join("?" for _ in ids)
                evidence_rows = conn.execute(
                    f"""SELECT * FROM knowledge_evidence
                        WHERE claim_id IN ({placeholders})
                        ORDER BY id DESC""",
                    tuple(ids),
                ).fetchall()
                for row in evidence_rows:
                    item = dict(row)
                    claim_id = int(item["claim_id"])
                    if len(evidence_by_claim[claim_id]) >= 12:
                        continue
                    item["provenance"] = json.loads(
                        item.pop("provenance_json") or "{}"
                    )
                    evidence_by_claim[claim_id].append(item)
        for item in items:
            item["evidence"] = evidence_by_claim.get(int(item["id"]), [])
        return items

    def supersede_claim(
        self,
        *,
        scope: str,
        old_claim_id: int,
        new_claim_id: int,
        reason: str,
    ) -> dict:
        if int(old_claim_id) == int(new_claim_id):
            raise ValueError("Old and new claim must be different.")
        with connect() as conn:
            old = conn.execute(
                "SELECT * FROM knowledge_claims WHERE id=? AND scope=?",
                (int(old_claim_id), scope),
            ).fetchone()
            new = conn.execute(
                "SELECT * FROM knowledge_claims WHERE id=? AND scope=?",
                (int(new_claim_id), scope),
            ).fetchone()
        if not old or not new:
            raise ValueError("Knowledge claim not found in requested scope.")
        if str(new["state"]) not in {"supported", "verified"}:
            raise ValueError(
                "Replacement claim must be supported or verified before superseding."
            )
        if str(old["state"]) == "superseded":
            return self._claim(int(old_claim_id)) or {}

        clean_reason = " ".join(str(reason or "").split())[:700]
        if not clean_reason:
            clean_reason = "explicit_knowledge_replacement"
        previous_state = str(old["state"])
        with connect() as conn:
            conn.execute(
                """UPDATE knowledge_claims
                   SET state='superseded', superseded_by_id=?,
                       superseded_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (int(new_claim_id), int(old_claim_id), scope),
            )
            conn.commit()
        self._transition(
            scope,
            int(old_claim_id),
            previous_state,
            "superseded",
            clean_reason,
            {"superseded_by_id": int(new_claim_id)},
        )
        self._learning_event(
            scope,
            "knowledge_superseded",
            "knowledge_claim",
            int(old_claim_id),
            f"claim superseded by {int(new_claim_id)}",
            float(new["confidence"] or 0.0),
            {
                "previous_state": previous_state,
                "new_claim_id": int(new_claim_id),
                "reason": clean_reason,
            },
        )
        return self._claim(int(old_claim_id)) or {}

    def observe_canonical_fact(
        self,
        *,
        scope: str,
        canonical_key: str,
        normalized_value: str,
        statement: str,
        canonical_state: str,
        confidence: float,
        evidence: list[dict],
    ) -> dict:
        """Project Canonical Facts into Lifecycle without duplicating scoring."""
        scope = (scope or "personal").strip() or "personal"
        canonical_key = str(canonical_key or "").strip()
        statement = " ".join(str(statement or "").split())[:1200]
        if not canonical_key or not statement:
            return {"claim_id": None, "state": "ignored"}

        mapped_state = (
            canonical_state
            if canonical_state in {"observed", "supported", "verified"}
            else "observed"
        )
        origin_request_id = f"canonical:{canonical_key}"[:1000]
        claim_key = self._hash(
            f"canonical:{canonical_key}:{normalized_value}"
        )

        with connect() as conn:
            row = conn.execute(
                """SELECT id, state FROM knowledge_claims
                   WHERE scope=? AND claim_key=?""",
                (scope, claim_key),
            ).fetchone()
            if row:
                claim_id = int(row["id"])
                old_state = str(row["state"])
                conn.execute(
                    """UPDATE knowledge_claims
                       SET statement=?, origin_type='canonical_fact',
                           origin_request_id=?, last_request_id=?,
                           state=?, confidence=?,
                           support_score=?, support_groups=?,
                           contradiction_score=0.0,
                           contradiction_groups=0,
                           observations=observations+1,
                           verification_passes=CASE
                             WHEN ?='verified'
                             THEN MAX(verification_passes, 1)
                             ELSE verification_passes
                           END,
                           last_seen_at=CURRENT_TIMESTAMP,
                           verified_at=CASE
                             WHEN ?='verified' AND verified_at IS NULL
                             THEN CURRENT_TIMESTAMP ELSE verified_at END,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        statement,
                        origin_request_id,
                        origin_request_id,
                        mapped_state,
                        max(0.0, min(1.0, float(confidence))),
                        max(0.0, min(1.0, float(confidence))),
                        len({
                            str(item.get("independence_group") or "")
                            for item in evidence
                            if item.get("independence_group")
                        }),
                        mapped_state,
                        mapped_state,
                        claim_id,
                    ),
                )
            else:
                old_state = ""
                cur = conn.execute(
                    """INSERT INTO knowledge_claims(
                           scope, claim_key, statement, origin_type,
                           origin_request_id, last_request_id,
                           state, confidence, support_score,
                           support_groups, verification_passes,
                           first_seen_at, last_seen_at, verified_at
                       ) VALUES (?, ?, ?, 'canonical_fact', ?, ?, ?, ?, ?, ?, ?,
                                 CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                                 CASE WHEN ?='verified'
                                      THEN CURRENT_TIMESTAMP ELSE NULL END)""",
                    (
                        scope,
                        claim_key,
                        statement,
                        origin_request_id,
                        origin_request_id,
                        mapped_state,
                        max(0.0, min(1.0, float(confidence))),
                        max(0.0, min(1.0, float(confidence))),
                        len({
                            str(item.get("independence_group") or "")
                            for item in evidence
                            if item.get("independence_group")
                        }),
                        1 if mapped_state == "verified" else 0,
                        mapped_state,
                    ),
                )
                claim_id = int(cur.lastrowid)

            provenance = {
                "canonical_key": canonical_key,
                "normalized_value": normalized_value,
                "canonical_state": canonical_state,
                "independence_groups": sorted({
                    str(item.get("independence_group") or "")
                    for item in evidence
                    if item.get("independence_group")
                }),
                "source_refs": [
                    str(item.get("source_ref") or "")
                    for item in evidence[:20]
                ],
            }
            content_hash = self._hash(statement)
            conn.execute(
                """INSERT INTO knowledge_evidence(
                       scope, claim_id, request_id, source_type, source_ref,
                       source_group, stance, confidence, provenance_json,
                       content_hash, content_excerpt
                   ) VALUES (?, ?, ?, 'canonical_fact', ?, ?, 'support', ?, ?, ?, ?)
                   ON CONFLICT(claim_id, source_group, stance, content_hash)
                   DO UPDATE SET
                       confidence=excluded.confidence,
                       provenance_json=excluded.provenance_json,
                       content_excerpt=excluded.content_excerpt""",
                (
                    scope,
                    claim_id,
                    origin_request_id,
                    canonical_key[:500],
                    f"canonical:{canonical_key}"[:500],
                    max(0.0, min(1.0, float(confidence))),
                    json.dumps(provenance, ensure_ascii=False),
                    content_hash,
                    statement[:800],
                ),
            )
            conn.commit()

        if old_state and old_state != mapped_state:
            self._transition(
                scope,
                claim_id,
                old_state,
                mapped_state,
                "canonical_fact_projection",
                {
                    "canonical_key": canonical_key,
                    "canonical_state": canonical_state,
                    "confidence": confidence,
                },
            )

        if mapped_state in {"supported", "verified"}:
            with connect() as conn:
                previous = conn.execute(
                    """SELECT id, state FROM knowledge_claims
                       WHERE scope=? AND origin_type='canonical_fact'
                         AND origin_request_id=? AND id<>?
                         AND state<>'superseded'
                       ORDER BY id DESC""",
                    (scope, origin_request_id, claim_id),
                ).fetchall()
            for item in previous:
                previous_id = int(item["id"])
                with connect() as conn:
                    conn.execute(
                        """UPDATE knowledge_claims
                           SET state='superseded',
                               superseded_by_id=?,
                               superseded_at=CURRENT_TIMESTAMP,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (claim_id, previous_id),
                    )
                    conn.commit()
                self._transition(
                    scope,
                    previous_id,
                    str(item["state"]),
                    "superseded",
                    "canonical_value_superseded",
                    {
                        "canonical_key": canonical_key,
                        "new_claim_id": claim_id,
                    },
                )

        return {
            "claim_id": claim_id,
            "state": mapped_state,
            "canonical_key": canonical_key,
        }

    def hypotheses(self, *, scope: str, state: str | None = None, limit: int = 50) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            if state:
                rows = conn.execute(
                    "SELECT * FROM hypothesis_registry WHERE scope=? AND state=? ORDER BY id DESC LIMIT ?",
                    (scope, state, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM hypothesis_registry WHERE scope=? ORDER BY id DESC LIMIT ?",
                    (scope, limit),
                ).fetchall()
            items = [dict(row) for row in rows]
            ids = [int(item["id"]) for item in items]
            evidence_by_hypothesis: dict[int, list[dict]] = {
                hid: [] for hid in ids
            }
            if ids:
                placeholders = ",".join("?" for _ in ids)
                evidence_rows = conn.execute(
                    f"""SELECT * FROM hypothesis_evidence
                        WHERE hypothesis_id IN ({placeholders})
                        ORDER BY id DESC""",
                    tuple(ids),
                ).fetchall()
                for row in evidence_rows:
                    item = dict(row)
                    hypothesis_id = int(item["hypothesis_id"])
                    if len(evidence_by_hypothesis[hypothesis_id]) >= 12:
                        continue
                    evidence_by_hypothesis[hypothesis_id].append(item)
        for item in items:
            item["evidence"] = evidence_by_hypothesis.get(
                int(item["id"]),
                [],
            )
        return items

    def transitions(self, *, scope: str, limit: int = 80) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_transitions WHERE scope=? ORDER BY id DESC LIMIT ?",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def learning_events(self, *, scope: str, limit: int = 80) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM knowledge_learning_events WHERE scope=? ORDER BY id DESC LIMIT ?",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def dashboard(self, *, scope: str, limit: int = 30) -> dict:
        return {
            "summary": self.summary(scope=scope),
            "claims": self.claims(scope=scope, limit=limit),
            "hypotheses": self.hypotheses(scope=scope, limit=limit),
            "transitions": self.transitions(scope=scope, limit=limit),
            "learning_events": self.learning_events(scope=scope, limit=limit),
        }

    def prompt_block(self, *, scope: str) -> str:
        verified = self.claims(scope=scope, state="verified", limit=4)
        supported = self.claims(scope=scope, state="supported", limit=3)
        contradicted = self.claims(scope=scope, state="contradicted", limit=3)
        lines = [
            "Knowledge Lifecycle.",
            "Lifecycle status is evidence quality metadata, not absolute truth.",
        ]
        for item in verified or supported:
            lines.append(
                f"- {str(item.get('state')).upper()} "
                f"({float(item.get('confidence') or 0):.2f}): "
                f"{str(item.get('statement') or '')[:300]}"
            )
        for item in contradicted:
            lines.append(
                f"- CONTRADICTED: {str(item.get('statement') or '')[:260]}"
            )
        if contradicted:
            lines.append(
                "Do not present contradicted knowledge as settled until re-verified."
            )
        return "\n".join(lines)

    def _observe_hypotheses(
        self,
        *,
        request_id: str,
        scope: str,
        run: dict,
        evidence: list[dict],
        contradictions: list[dict],
        verification_ok: bool,
    ) -> list[dict]:
        selected = run.get("selected_test") or {}
        selected_keys = set(selected.get("competing_hypotheses") or [])
        result: list[dict] = []
        for item in (run.get("hypotheses") or [])[:8]:
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            key = str(item.get("key") or "").strip() or (
                "hyp:" + self._hash(title)
            )
            confidence = max(0.0, min(1.0, float(item.get("confidence") or 0.0)))
            hid = self._upsert_hypothesis(
                scope, key, title, confidence, run.get("run_id"), verification_ok
            )
            for snippet in item.get("supporting") or []:
                source = self._best_source(str(snippet), evidence)
                if source:
                    self._hypothesis_evidence(
                        scope, hid, request_id, source, "support"
                    )
            for snippet in item.get("opposing") or []:
                source = self._best_source(
                    str(snippet), contradictions + evidence
                )
                if source:
                    self._hypothesis_evidence(
                        scope, hid, request_id, source, "oppose"
                    )
            updated = self._recompute_hypothesis(
                hid,
                confidence,
                key in selected_keys or bool(selected),
            )
            if updated:
                result.append(updated)
        return result

    def _upsert_claim(self, scope: str, request_id: str, statement: str, origin_type: str) -> int:
        statement = " ".join(statement.split())[:1200]
        claim_key = self._hash(statement)
        with connect() as conn:
            row = conn.execute(
                "SELECT id FROM knowledge_claims WHERE scope=? AND claim_key=?",
                (scope, claim_key),
            ).fetchone()
            if row:
                cid = int(row["id"])
                conn.execute(
                    """UPDATE knowledge_claims SET observations=observations+1,
                       last_request_id=?, last_seen_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                    (request_id, cid),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO knowledge_claims(
                       scope, claim_key, statement, origin_type,
                       origin_request_id, last_request_id, first_seen_at, last_seen_at
                       ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    (scope, claim_key, statement, origin_type, request_id, request_id),
                )
                cid = int(cur.lastrowid)
            conn.commit()
        return cid

    def _claim_evidence(
        self, scope: str, claim_id: int, request_id: str, source: dict, stance: str
    ) -> None:
        content = source["content"][:1600]
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO knowledge_evidence(
                   scope, claim_id, request_id, source_type, source_ref,
                   source_group, stance, confidence, provenance_json,
                   content_hash, content_excerpt
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope, claim_id, request_id, source["source_type"],
                    source["source_ref"], source["source_group"], stance,
                    source["confidence"],
                    json.dumps(source.get("provenance") or {}, ensure_ascii=False),
                    self._hash(content), content[:800],
                ),
            )
            conn.commit()

    def _recompute_claim(self, claim_id: int) -> dict | None:
        with connect() as conn:
            claim = conn.execute(
                "SELECT * FROM knowledge_claims WHERE id=?", (claim_id,)
            ).fetchone()
            rows = conn.execute(
                "SELECT stance, confidence, source_group FROM knowledge_evidence WHERE claim_id=?",
                (claim_id,),
            ).fetchall()
        if not claim:
            return None
        if claim["state"] == "superseded":
            return dict(claim)
        support = [r for r in rows if r["stance"] == "support"]
        oppose = [r for r in rows if r["stance"] == "contradict"]
        sg = len({r["source_group"] for r in support})
        og = len({r["source_group"] for r in oppose})
        ss = sum(float(r["confidence"] or 0) for r in support) / len(support) if support else 0.0
        os = sum(float(r["confidence"] or 0) for r in oppose) / len(oppose) if oppose else 0.0
        vp = int(claim["verification_passes"] or 0)
        if og >= 2 and os >= 0.55 and ss < 0.45:
            state = "rejected"
        elif og >= 1 and os >= 0.35:
            state = "contradicted"
        elif (sg >= 2 and ss >= 0.65 and vp >= 1 and og == 0) or (
            sg >= 3 and ss >= 0.75 and og == 0
        ):
            state = "verified"
        elif sg >= 2 and ss >= 0.55:
            state = "supported"
        else:
            state = "observed"
        confidence = max(
            0.0,
            min(1.0, 0.2 + 0.18 * min(3, sg) + 0.35 * ss - 0.2 * min(2, og) - 0.2 * os),
        )
        old = str(claim["state"])
        with connect() as conn:
            conn.execute(
                """UPDATE knowledge_claims SET state=?, confidence=?,
                   support_score=?, contradiction_score=?, support_groups=?,
                   contradiction_groups=?, updated_at=CURRENT_TIMESTAMP,
                   verified_at=CASE WHEN ?='verified' AND verified_at IS NULL
                                    THEN CURRENT_TIMESTAMP ELSE verified_at END,
                   contradicted_at=CASE WHEN ? IN ('contradicted','rejected')
                                         AND contradicted_at IS NULL
                                        THEN CURRENT_TIMESTAMP ELSE contradicted_at END
                   WHERE id=?""",
                (state, round(confidence,4), round(ss,4), round(os,4), sg, og, state, state, claim_id),
            )
            conn.commit()
        if old != state:
            self._transition(
                str(claim["scope"]), claim_id, old, state,
                f"support_groups={sg}; contradiction_groups={og}; verification_passes={vp}",
                {"support_score": ss, "contradiction_score": os},
            )
            if state in {"contradicted", "rejected"}:
                self._learning_event(
                    str(claim["scope"]), "error_detected", "knowledge_claim",
                    claim_id, f"claim became {state}", max(os, confidence),
                    {"previous_state": old},
                )
            elif state == "verified":
                self._learning_event(
                    str(claim["scope"]),
                    "correction_confirmed" if old in {"contradicted","rejected"} else "knowledge_verified",
                    "knowledge_claim", claim_id, f"claim verified from {old}",
                    confidence, {"previous_state": old},
                )
        return self._claim(claim_id)

    def _upsert_hypothesis(
        self, scope: str, key: str, title: str, confidence: float,
        run_id: Any, verification_ok: bool
    ) -> int:
        with connect() as conn:
            row = conn.execute(
                "SELECT id FROM hypothesis_registry WHERE scope=? AND hypothesis_key=?",
                (scope, key),
            ).fetchone()
            if row:
                hid = int(row["id"])
                conn.execute(
                    """UPDATE hypothesis_registry SET title=?, confidence=?,
                       observations=observations+1, last_run_id=?,
                       verification_passes=verification_passes+?,
                       last_seen_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (title[:700], confidence, run_id, 1 if verification_ok else 0, hid),
                )
            else:
                cur = conn.execute(
                    """INSERT INTO hypothesis_registry(
                       scope, hypothesis_key, title, confidence, observations,
                       verification_passes, last_run_id, first_seen_at, last_seen_at
                       ) VALUES (?, ?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)""",
                    (scope, key, title[:700], confidence, 1 if verification_ok else 0, run_id),
                )
                hid = int(cur.lastrowid)
            conn.commit()
        return hid

    def _hypothesis_evidence(
        self, scope: str, hypothesis_id: int, request_id: str,
        source: dict, stance: str
    ) -> None:
        content = source["content"][:1600]
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO hypothesis_evidence(
                   scope, hypothesis_id, request_id, source_type, source_ref,
                   source_group, stance, confidence, content_hash, content_excerpt
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope, hypothesis_id, request_id, source["source_type"],
                    source["source_ref"], source["source_group"], stance,
                    source["confidence"], self._hash(content), content[:800],
                ),
            )
            conn.commit()

    def _recompute_hypothesis(
        self, hypothesis_id: int, confidence: float, testing: bool
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM hypothesis_registry WHERE id=?", (hypothesis_id,)
            ).fetchone()
            ev = conn.execute(
                "SELECT stance, source_group FROM hypothesis_evidence WHERE hypothesis_id=?",
                (hypothesis_id,),
            ).fetchall()
        if not row:
            return None
        sg = len({x["source_group"] for x in ev if x["stance"] == "support" and x["source_group"]})
        og = len({x["source_group"] for x in ev if x["stance"] == "oppose" and x["source_group"]})
        vp = int(row["verification_passes"] or 0)
        if og >= 2 and confidence <= 0.35:
            state = "rejected"
        elif confidence >= 0.65 and sg >= 3 and og == 0 and vp >= 1:
            state = "confirmed"
        elif confidence >= 0.45 and sg >= 2 and og == 0:
            state = "supported"
        elif testing:
            state = "testing"
        else:
            state = "candidate"
        old = str(row["state"])
        with connect() as conn:
            conn.execute(
                """UPDATE hypothesis_registry SET state=?, confidence=?,
                   support_groups=?, opposition_groups=?, updated_at=CURRENT_TIMESTAMP,
                   confirmed_at=CASE WHEN ?='confirmed' AND confirmed_at IS NULL
                                     THEN CURRENT_TIMESTAMP ELSE confirmed_at END,
                   rejected_at=CASE WHEN ?='rejected' AND rejected_at IS NULL
                                    THEN CURRENT_TIMESTAMP ELSE rejected_at END
                   WHERE id=?""",
                (state, round(confidence,4), sg, og, state, state, hypothesis_id),
            )
            conn.commit()
        if old != state:
            with connect() as conn:
                conn.execute(
                    """INSERT INTO hypothesis_transitions(
                       scope, hypothesis_id, from_state, to_state, reason
                       ) VALUES (?, ?, ?, ?, ?)""",
                    (row["scope"], hypothesis_id, old, state,
                     f"confidence={confidence:.3f}; support_groups={sg}; opposition_groups={og}; verification_passes={vp}"),
                )
                conn.commit()
            if state in {"confirmed", "rejected"}:
                self._learning_event(
                    str(row["scope"]),
                    "hypothesis_confirmed" if state == "confirmed" else "hypothesis_rejected",
                    "hypothesis", hypothesis_id, f"hypothesis became {state}",
                    confidence, {"previous_state": old, "support_groups": sg, "opposition_groups": og},
                )
            self._emit(
                "hypothesis.lifecycle.transition", str(row["scope"]),
                {"hypothesis_id": hypothesis_id, "from": old, "to": state},
                0.6 if state in {"confirmed","rejected"} else 0.3,
            )
        with connect() as conn:
            fresh = conn.execute(
                "SELECT * FROM hypothesis_registry WHERE id=?", (hypothesis_id,)
            ).fetchone()
        return dict(fresh) if fresh else None

    def _transition(
        self, scope: str, claim_id: int, old: str, new: str,
        reason: str, details: dict
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO knowledge_transitions(
                   scope, claim_id, from_state, to_state, reason, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (scope, claim_id, old, new, reason[:500], json.dumps(details, ensure_ascii=False)),
            )
            conn.commit()
        self._emit(
            "knowledge.lifecycle.transition", scope,
            {"claim_id": claim_id, "from": old, "to": new, "reason": reason[:240]},
            0.62 if new in {"verified","contradicted","rejected"} else 0.35,
        )

    def _learning_event(
        self, scope: str, event_type: str, subject_type: str,
        subject_id: int, summary: str, confidence: float, details: dict
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO knowledge_learning_events(
                   scope, event_type, subject_type, subject_id,
                   summary, confidence, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope, event_type, subject_type, subject_id, summary[:700],
                    max(0.0, min(1.0, float(confidence))),
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def _claim(self, claim_id: int) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM knowledge_claims WHERE id=?", (claim_id,)
            ).fetchone()
        return dict(row) if row else None

    @classmethod
    def _source(cls, item: dict, index: int, contradiction: bool) -> dict | None:
        content = str(
            item.get("summary") if contradiction else (
                item.get("content") or item.get("finding") or item.get("message")
            ) or ""
        ).strip()
        if len(content) < 8:
            return None
        source_type = str(
            item.get("source_type") or item.get("source") or (
                "contradiction" if contradiction else "evidence"
            )
        )
        if source_type.casefold() in {
            "planner",
            "performance",
            "system",
            "telemetry",
        }:
            return None
        source_ref = str(
            item.get("source_ref") or item.get("id") or item.get("document_id") or index
        )
        source_group = str(
            item.get("source_group")
            or (
                f"document:{item.get('document_id')}"
                if item.get("document_id") is not None
                else f"{source_type}:{source_ref}"
            )
        )
        if source_group == "derived_knowledge":
            return None
        raw = item.get("severity") if contradiction else (
            item.get("confidence")
            if item.get("confidence") is not None
            else item.get("retrieval_score")
        )
        try:
            confidence = max(0.05, min(1.0, float(raw if raw is not None else 0.6)))
        except (TypeError, ValueError):
            confidence = 0.6
        return {
            "content": content[:1600],
            "source_type": source_type,
            "source_ref": source_ref,
            "source_group": source_group,
            "confidence": confidence,
            "provenance": item.get("provenance") or {},
        }

    @classmethod
    def _best_source(cls, text: str, sources: list[dict]) -> dict | None:
        normalized = cls._normalized_text(text)
        for source in sources:
            if cls._normalized_text(source.get("content") or "") == normalized:
                return source
        ranked = sorted(
            ((cls._similarity(text, x.get("content") or ""), x) for x in sources),
            key=lambda pair: pair[0],
            reverse=True,
        )
        return ranked[0][1] if ranked and ranked[0][0] >= 0.16 else None

    @classmethod
    def _similarity(cls, left: str, right: str) -> float:
        a, b = cls._tokens(left), cls._tokens(right)
        return len(a & b) / max(1, min(len(a), len(b))) if a and b else 0.0

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        return {
            token.casefold().replace("ё", "е")
            for token in _TOKEN_RE.findall(text or "")
            if len(token) >= 3 or any(ch.isdigit() for ch in token)
        }

    @staticmethod
    def _normalized_text(text: str) -> str:
        return " ".join(
            str(text or "").casefold().replace("ё", "е").split()
        )

    @classmethod
    def _hash(cls, text: str) -> str:
        return hashlib.sha256(
            cls._normalized_text(text).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _verification_passed(verification: dict | None) -> bool:
        if not verification or verification.get("ran") is False:
            return False
        return not (verification.get("unresolved") or []) and not (
            (verification.get("consistency") or {}).get("conflicts") or []
        )

    @staticmethod
    def _state_counts(items: list[dict]) -> dict:
        result: dict[str, int] = {}
        for item in items:
            state = str(item.get("state") or "unknown")
            result[state] = result.get(state, 0) + 1
        return result

    def _emit(self, event_type: str, scope: str, payload: dict, importance: float) -> None:
        if self.events is not None:
            self.events.emit(
                event_type, scope=scope, payload=payload, importance=importance
            )
