from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ..ai import AIManager
from ..db import connect
from .events import EventBus
from .graph import KnowledgeGraph
from .memory import MemoryCandidate, MemorySystem
from .semantic import SemanticMemory
from .tools import ToolRegistry


_TOKEN_RE = re.compile(r"[a-zа-яё0-9_-]{3,}", re.IGNORECASE)


@dataclass
class ResearchRun:
    session_id: int
    scope: str
    question: str
    status: str
    evidence_count: int
    independent_groups: int
    contradiction_count: int
    claim_count: int
    trusted_claims: int
    synthesis_used: bool
    duration_ms: int
    gap_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class AutonomousResearchEngine:
    """Evidence-led research with guarded knowledge promotion."""

    VERSION = "aishin-autonomous-research-v1"
    FORMULA_VERSION = "evidence-ledger-research-v1"
    TRUSTED_MIN_CONFIDENCE = 0.82
    TRUSTED_MIN_SUPPORT = 2
    TRUSTED_MIN_GROUPS = 2
    AUTO_RESEARCH_MIN_PRIORITY = 0.62

    BUILTIN_SOURCES = (
        ("builtin:memory", "memory", "Долговременная память", "memory", 0.78),
        ("builtin:semantic", "semantic_memory", "Семантическая память", "memory", 0.78),
        ("builtin:graph", "knowledge_graph", "Knowledge Graph", "knowledge_graph", 0.82),
        ("builtin:messages", "messages", "История диалога", "conversation", 0.66),
        ("builtin:verification", "verification", "Verification Engine", "verification", 0.92),
        ("builtin:trusted-claims", "trusted_claims", "Подтверждённые research claims", "derived_knowledge", 0.78),
    )

    def __init__(
        self,
        *,
        ai: AIManager,
        memory: MemorySystem,
        semantic: SemanticMemory,
        graph: KnowledgeGraph,
        tools: ToolRegistry,
        events: EventBus,
    ) -> None:
        self.ai = ai
        self.memory = memory
        self.semantic = semantic
        self.graph = graph
        self.tools = tools
        self.events = events

    def bootstrap(self, *, scope: str) -> dict:
        self._ensure_state(scope)
        self._ensure_builtin_sources(scope)
        discovered = self.discover_gaps(scope=scope)
        return {
            "scope": scope,
            "gaps_discovered": discovered,
            "state": self._refresh_state(scope),
        }

    def register_source(
        self,
        *,
        scope: str,
        source_key: str,
        source_type: str,
        label: str,
        locator: str = "",
        independent_group: str = "",
        trust_prior: float = 0.70,
        enabled: bool = True,
        auto_read: bool = False,
        metadata: dict | None = None,
    ) -> dict:
        source_key = source_key.strip()
        source_type = source_type.strip()
        label = label.strip()
        allowed = {
            "memory",
            "semantic_memory",
            "knowledge_graph",
            "messages",
            "verification",
            "trusted_claims",
            "project_file",
            "manual_reference",
            "external_connector",
        }
        if not source_key or not source_type or not label:
            raise ValueError("source_key, source_type and label are required")
        if source_type not in allowed:
            raise ValueError("unsupported research source type")

        group = independent_group.strip() or (
            f"project_file:{locator.strip()}"
            if source_type == "project_file" and locator.strip()
            else source_type
        )
        with connect() as conn:
            conn.execute(
                """INSERT INTO research_sources(
                       scope, source_key, source_type, label, locator,
                       independent_group, trust_prior, enabled, auto_read,
                       metadata_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope, source_key) DO UPDATE SET
                       source_type=excluded.source_type,
                       label=excluded.label,
                       locator=excluded.locator,
                       independent_group=excluded.independent_group,
                       trust_prior=excluded.trust_prior,
                       enabled=excluded.enabled,
                       auto_read=excluded.auto_read,
                       metadata_json=excluded.metadata_json,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    source_key,
                    source_type,
                    label,
                    locator,
                    group,
                    self._clamp(trust_prior),
                    1 if enabled else 0,
                    1 if auto_read else 0,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
        self._event(
            scope,
            "research.source.registered",
            "source",
            source_key,
            self._clamp(trust_prior),
            {"source_type": source_type, "label": label},
        )
        return next(
            item
            for item in self.sources(scope=scope, limit=500)
            if item["source_key"] == source_key
        )

    def create_gap(
        self,
        *,
        scope: str,
        question: str,
        origin: str,
        origin_ref: str = "",
        priority: float = 0.5,
        uncertainty: float = 0.5,
        impact: float = 0.5,
    ) -> dict:
        question = " ".join(question.strip().split())
        if not question:
            raise ValueError("research gap question is empty")
        gap_key = self._hash(
            scope,
            origin,
            origin_ref or question.casefold(),
            question.casefold(),
        )
        with connect() as conn:
            conn.execute(
                """INSERT INTO research_gaps(
                       scope, gap_key, question, origin, origin_ref,
                       priority, uncertainty, impact
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope, gap_key) DO UPDATE SET
                       question=excluded.question,
                       priority=MAX(research_gaps.priority, excluded.priority),
                       uncertainty=MAX(research_gaps.uncertainty, excluded.uncertainty),
                       impact=MAX(research_gaps.impact, excluded.impact),
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    gap_key,
                    question,
                    origin,
                    origin_ref,
                    self._clamp(priority),
                    self._clamp(uncertainty),
                    self._clamp(impact),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM research_gaps WHERE scope=? AND gap_key=?",
                (scope, gap_key),
            ).fetchone()
        return dict(row)

    def observe_verification(
        self,
        *,
        scope: str,
        query: str,
        verification: dict | None,
        request_id: str = "",
    ) -> dict | None:
        if not verification or not verification.get("ran"):
            return None
        unresolved = [
            str(item).strip()
            for item in verification.get("unresolved") or []
            if str(item).strip()
        ]
        conflicts = [
            str(item).strip()
            for item in (verification.get("consistency") or {}).get("conflicts") or []
            if str(item).strip()
        ]
        if not unresolved and not conflicts:
            return None
        gap = self.create_gap(
            scope=scope,
            question=query.strip() or "; ".join((conflicts + unresolved)[:3]),
            origin="verification",
            origin_ref=request_id or self._hash(query),
            priority=min(1.0, 0.58 + 0.07 * len(unresolved) + 0.10 * len(conflicts)),
            uncertainty=min(1.0, 0.55 + 0.08 * len(unresolved)),
            impact=0.72 if conflicts else 0.58,
        )
        self._event(
            scope,
            "research.gap.observed",
            "gap",
            str(gap["gap_key"]),
            float(gap["priority"]),
            {"request_id": request_id, "unresolved": unresolved[:8], "conflicts": conflicts[:8]},
        )
        return gap

    def discover_gaps(self, *, scope: str) -> int:
        count = 0
        with connect() as conn:
            verification_rows = conn.execute(
                """SELECT id, query, unresolved_json
                   FROM verification_runs
                   WHERE scope=? AND unresolved_json NOT IN ('[]','', '{}')
                   ORDER BY id DESC LIMIT 40""",
                (scope,),
            ).fetchall()
            proactive_rows = conn.execute(
                """SELECT id, title, summary, verification_state,
                          attention_score, risk_score
                   FROM proactive_incidents
                   WHERE scope=? AND status='active'
                     AND verification_state IN ('needs_review','verification_observed')
                   ORDER BY attention_score DESC, id DESC LIMIT 30""",
                (scope,),
            ).fetchall()
            curriculum_rows = conn.execute(
                """SELECT id, title, priority, gap_score
                   FROM evolution_curriculum
                   WHERE scope=? AND status IN ('open','active')
                     AND gap_score>=0.45
                   ORDER BY priority DESC, gap_score DESC LIMIT 30""",
                (scope,),
            ).fetchall()
            stale_row = conn.execute(
                """SELECT COUNT(*) AS n FROM knowledge_trust
                   WHERE scope=? AND trust_level='stale'""",
                (scope,),
            ).fetchone()

        for row in verification_rows:
            unresolved = self._json(row["unresolved_json"], [])
            if not unresolved:
                continue
            self.create_gap(
                scope=scope,
                question=str(row["query"] or "").strip() or "Уточнить нерешённые данные Verification Engine",
                origin="verification_history",
                origin_ref=str(row["id"]),
                priority=min(0.92, 0.60 + 0.05 * len(unresolved)),
                uncertainty=min(1.0, 0.58 + 0.06 * len(unresolved)),
                impact=0.62,
            )
            count += 1

        for row in proactive_rows:
            self.create_gap(
                scope=scope,
                question=str(row["title"] or row["summary"] or "").strip(),
                origin="proactive_incident",
                origin_ref=str(row["id"]),
                priority=max(0.55, float(row["attention_score"] or 0.0)),
                uncertainty=0.66,
                impact=float(row["risk_score"] or 0.5),
            )
            count += 1

        for row in curriculum_rows:
            self.create_gap(
                scope=scope,
                question=f"Какие подтверждённые знания помогут закрыть учебный пробел: {row['title']}?",
                origin="evolution_curriculum",
                origin_ref=str(row["id"]),
                priority=max(float(row["priority"] or 0.5), float(row["gap_score"] or 0.0)),
                uncertainty=float(row["gap_score"] or 0.5),
                impact=float(row["priority"] or 0.5),
            )
            count += 1

        stale_count = int(stale_row["n"] or 0) if stale_row else 0
        if stale_count:
            self.create_gap(
                scope=scope,
                question=f"Какие из {stale_count} устаревающих знаний нужно перепроверить свежими свидетельствами?",
                origin="knowledge_freshness",
                origin_ref="stale_knowledge_pool",
                priority=min(0.82, 0.50 + stale_count / 100.0),
                uncertainty=0.72,
                impact=min(0.78, 0.48 + stale_count / 120.0),
            )
            count += 1
        return count

    def research_query(
        self,
        *,
        scope: str,
        question: str,
        trigger: str = "manual",
        request_id: str | None = None,
        gap_id: int | None = None,
        synthesize: bool = True,
        offline_only: bool = False,
    ) -> ResearchRun:
        started = time.perf_counter()
        question = " ".join(question.strip().split())
        if not question:
            raise ValueError("research question is empty")
        self._ensure_state(scope)
        self._ensure_builtin_sources(scope)
        plan = self._build_plan(
            scope,
            question,
            offline_only=offline_only,
        )

        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO research_sessions(
                       scope, gap_id, request_id, question, trigger, status,
                       plan_json, source_plan_json
                   ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?)""",
                (
                    scope,
                    gap_id,
                    request_id,
                    question,
                    trigger,
                    json.dumps(plan["policy"], ensure_ascii=False),
                    json.dumps([s["source_key"] for s in plan["sources"]], ensure_ascii=False),
                ),
            )
            session_id = int(cur.lastrowid)
            if gap_id:
                conn.execute(
                    """UPDATE research_gaps
                       SET status='researching', attempts=attempts+1,
                           last_session_id=?, updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND scope=?""",
                    (session_id, gap_id, scope),
                )
            conn.commit()

        evidence = self._collect_evidence(scope, session_id, question, plan)
        claims: list[dict] = []
        synthesis_used = False
        if synthesize and evidence:
            claims, synthesis_used = self._synthesize_claims(
                scope, session_id, question, evidence
            )

        status = "completed" if claims else ("evidence_only" if evidence else "insufficient")
        contradictions = self.contradictions(
            scope=scope, session_id=session_id, status="open", limit=500
        )
        trusted = [item for item in claims if item["status"] == "trusted"]
        groups = len({item["source_group"] for item in evidence if item.get("source_group")})
        duration_ms = int((time.perf_counter() - started) * 1000)

        with connect() as conn:
            conn.execute(
                """UPDATE research_sessions
                   SET status=?, evidence_count=?, independent_groups=?,
                       contradiction_count=?, claim_count=?, synthesis_used=?,
                       duration_ms=?, completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    status, len(evidence), groups, len(contradictions),
                    len(claims), 1 if synthesis_used else 0,
                    duration_ms, session_id,
                ),
            )
            if gap_id:
                resolved = bool(trusted) and not contradictions
                conn.execute(
                    """UPDATE research_gaps
                       SET status=?,
                           resolved_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE resolved_at END,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND scope=?""",
                    ("resolved" if resolved else "open", 1 if resolved else 0, gap_id, scope),
                )
            conn.commit()

        self._refresh_state(scope)
        self._event(
            scope,
            "research.session.completed",
            "session",
            str(session_id),
            self._session_quality(evidence, claims, contradictions),
            {
                "question": question[:500],
                "trigger": trigger,
                "evidence_count": len(evidence),
                "independent_groups": groups,
                "claim_count": len(claims),
                "trusted_claims": len(trusted),
                "contradictions": len(contradictions),
                "synthesis_used": synthesis_used,
            },
        )
        return ResearchRun(
            session_id=session_id,
            scope=scope,
            question=question,
            status=status,
            evidence_count=len(evidence),
            independent_groups=groups,
            contradiction_count=len(contradictions),
            claim_count=len(claims),
            trusted_claims=len(trusted),
            synthesis_used=synthesis_used,
            duration_ms=duration_ms,
            gap_id=gap_id,
        )

    def run_cycle(
        self,
        *,
        scope: str,
        trigger: str = "manual",
        max_sessions: int = 2,
        synthesize: bool = False,
        offline_only: bool = True,
    ) -> dict:
        started = time.perf_counter()
        self._ensure_state(scope)
        self._ensure_builtin_sources(scope)
        discovered = self.discover_gaps(scope=scope)
        gaps = [
            item
            for item in self.gaps(scope=scope, status="open", limit=100)
            if float(item["priority"] or 0.0) >= self.AUTO_RESEARCH_MIN_PRIORITY
        ]
        runs: list[ResearchRun] = []
        for gap in gaps[: max(0, min(int(max_sessions), 5))]:
            runs.append(
                self.research_query(
                    scope=scope,
                    question=str(gap["question"]),
                    trigger=trigger,
                    gap_id=int(gap["id"]),
                    synthesize=synthesize,
                    offline_only=offline_only,
                )
            )
        state = self._refresh_state(scope)
        open_contradictions = len(
            self.contradictions(scope=scope, status="open", limit=1000)
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        evidence_added = sum(item.evidence_count for item in runs)
        claims_created = sum(item.claim_count for item in runs)
        claims_promoted = sum(item.trusted_claims for item in runs)
        summary = {
            "state": state,
            "sessions": [item.to_dict() for item in runs],
            "external_research_sources_used": False,
            "offline_only": offline_only,
        }
        with connect() as conn:
            conn.execute(
                """INSERT INTO research_cycles(
                       scope, trigger, gaps_discovered, sessions_run,
                       evidence_added, claims_created, claims_promoted,
                       contradictions_open, duration_ms, summary_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope, trigger, discovered, len(runs), evidence_added,
                    claims_created, claims_promoted, open_contradictions,
                    duration_ms, json.dumps(summary, ensure_ascii=False),
                ),
            )
            conn.commit()
        self._event(
            scope,
            "research.cycle.completed",
            "cycle",
            trigger,
            float(state.get("research_score") or 0.0) / 100.0,
            {
                "gaps_discovered": discovered,
                "sessions_run": len(runs),
                "evidence_added": evidence_added,
                "claims_promoted": claims_promoted,
            },
        )
        return {
            "scope": scope,
            "trigger": trigger,
            "gaps_discovered": discovered,
            "sessions_run": len(runs),
            "evidence_added": evidence_added,
            "claims_created": claims_created,
            "claims_promoted": claims_promoted,
            "contradictions_open": open_contradictions,
            "duration_ms": duration_ms,
            "state": state,
        }

    def add_evidence(
        self,
        *,
        scope: str,
        session_id: int,
        source_type: str,
        source_ref: str,
        source_group: str,
        title: str,
        content: str,
        reliability: float,
        relevance: float,
        freshness: float = 1.0,
        independence: float = 1.0,
        metadata: dict | None = None,
    ) -> dict:
        content = content.strip()
        if not content:
            raise ValueError("evidence content is empty")
        content_hash = self._hash(content)
        evidence_key = self._hash(source_type, source_ref, source_group, content_hash)
        reliability = self._clamp(reliability)
        relevance = self._clamp(relevance)
        freshness = self._clamp(freshness, 0.25, 1.0)
        independence = self._clamp(independence, 0.35, 1.0)
        score = self._clamp(
            reliability * (0.55 + 0.45 * relevance) * freshness * independence
        )
        with connect() as conn:
            conn.execute(
                """INSERT INTO research_evidence(
                       scope, session_id, evidence_key, source_type,
                       source_ref, source_group, title, content,
                       reliability, relevance, freshness, independence,
                       evidence_score, content_hash, metadata_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope, session_id, evidence_key) DO UPDATE SET
                       reliability=MAX(research_evidence.reliability, excluded.reliability),
                       relevance=MAX(research_evidence.relevance, excluded.relevance),
                       freshness=MAX(research_evidence.freshness, excluded.freshness),
                       independence=MAX(research_evidence.independence, excluded.independence),
                       evidence_score=MAX(research_evidence.evidence_score, excluded.evidence_score),
                       metadata_json=excluded.metadata_json""",
                (
                    scope, session_id, evidence_key, source_type, source_ref,
                    source_group, title[:500], content[:12000],
                    reliability, relevance, freshness, independence, score,
                    content_hash, json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            conn.commit()
            row = conn.execute(
                """SELECT * FROM research_evidence
                   WHERE scope=? AND session_id=? AND evidence_key=?""",
                (scope, session_id, evidence_key),
            ).fetchone()
        return self._decode_evidence(dict(row))

    def evaluate_claim(
        self,
        *,
        scope: str,
        session_id: int,
        statement: str,
        support_evidence_ids: list[int],
        contradiction_evidence_ids: list[int] | None = None,
        missing: list[str] | None = None,
    ) -> dict:
        statement = " ".join(statement.strip().split())
        if not statement:
            raise ValueError("claim statement is empty")
        evidence_map = {
            int(item["id"]): item
            for item in self.evidence(scope=scope, session_id=session_id, limit=500)
        }
        support = [
            evidence_map[eid]
            for eid in self._unique_ints(support_evidence_ids)
            if eid in evidence_map
        ]
        contradiction = [
            evidence_map[eid]
            for eid in self._unique_ints(contradiction_evidence_ids or [])
            if eid in evidence_map
        ]
        missing = [str(item).strip() for item in (missing or []) if str(item).strip()][:12]

        support_strength = self._combined_strength(
            [float(item["evidence_score"]) for item in support]
        )
        counter_strength = self._combined_strength(
            [float(item["evidence_score"]) for item in contradiction]
        )
        groups = {str(item["source_group"]) for item in support if item.get("source_group")}
        primary_groups = {group for group in groups if group != "derived_knowledge"}
        source_types = {str(item["source_type"]) for item in support}
        diversity = min(1.0, len(groups) / 3.0)
        volume = min(1.0, len(support) / 4.0)
        confidence = self._clamp(
            (0.60 * support_strength + 0.25 * diversity + 0.15 * volume)
            * (1.0 - 0.75 * counter_strength)
        )

        if contradiction:
            status = "conflicted"
        elif (
            len(support) >= self.TRUSTED_MIN_SUPPORT
            and len(groups) >= self.TRUSTED_MIN_GROUPS
            and len(primary_groups) >= self.TRUSTED_MIN_GROUPS
            and confidence >= self.TRUSTED_MIN_CONFIDENCE
            and support_strength >= 0.82
            and not missing
        ):
            status = "trusted"
        elif len(support) >= 2 and confidence >= 0.62:
            status = "supported"
        elif support:
            status = "candidate"
        else:
            status = "rejected"

        claim_key = self._hash(statement.casefold())
        with connect() as conn:
            previous = conn.execute(
                """SELECT * FROM research_claims
                   WHERE scope=? AND claim_key=?""",
                (scope, claim_key),
            ).fetchone()
            conn.execute(
                """INSERT INTO research_claims(
                       scope, claim_key, session_id, statement, status,
                       confidence, weighted_support, weighted_contradiction,
                       support_count, contradiction_count,
                       independent_groups, source_diversity,
                       support_evidence_json, contradiction_evidence_json,
                       missing_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope, claim_key) DO UPDATE SET
                       session_id=excluded.session_id,
                       statement=excluded.statement,
                       status=excluded.status,
                       confidence=excluded.confidence,
                       weighted_support=excluded.weighted_support,
                       weighted_contradiction=excluded.weighted_contradiction,
                       support_count=excluded.support_count,
                       contradiction_count=excluded.contradiction_count,
                       independent_groups=excluded.independent_groups,
                       source_diversity=excluded.source_diversity,
                       support_evidence_json=excluded.support_evidence_json,
                       contradiction_evidence_json=excluded.contradiction_evidence_json,
                       missing_json=excluded.missing_json,
                       updated_at=CURRENT_TIMESTAMP,
                       rejected_at=CASE
                         WHEN excluded.status='rejected' THEN CURRENT_TIMESTAMP
                         ELSE research_claims.rejected_at
                       END""",
                (
                    scope, claim_key, session_id, statement, status, confidence,
                    support_strength, counter_strength, len(support),
                    len(contradiction), len(groups), len(source_types),
                    json.dumps([int(item["id"]) for item in support]),
                    json.dumps([int(item["id"]) for item in contradiction]),
                    json.dumps(missing, ensure_ascii=False),
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM research_claims WHERE scope=? AND claim_key=?",
                (scope, claim_key),
            ).fetchone()

        claim = self._decode_claim(dict(row))
        if contradiction:
            self._record_contradictions(
                scope, session_id, int(claim["id"]), support, contradiction
            )

        was_promoted = bool(previous and previous["promoted_memory_id"])
        if status == "trusted" and not was_promoted:
            self._promote_claim(scope, claim, support)
        elif status != "trusted" and was_promoted:
            self._event(
                scope,
                "research.claim.regressed",
                "claim",
                claim_key,
                confidence,
                {
                    "previous_status": previous["status"],
                    "status": status,
                    "promoted_memory_id": previous["promoted_memory_id"],
                    "requires_review": True,
                },
            )

        self._event(
            scope,
            "research.claim.evaluated",
            "claim",
            claim_key,
            confidence,
            {
                "status": status,
                "support_count": len(support),
                "contradiction_count": len(contradiction),
                "independent_groups": len(groups),
            },
        )
        return self.claim(int(claim["id"]), scope=scope) or claim

    def resolve_contradiction(
        self,
        contradiction_id: int,
        *,
        scope: str,
        resolution: str,
    ) -> dict:
        resolution = resolution.strip()
        if not resolution:
            raise ValueError("resolution is empty")
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_contradictions WHERE id=? AND scope=?",
                (contradiction_id, scope),
            ).fetchone()
            if row is None:
                raise ValueError("contradiction not found")
            conn.execute(
                """UPDATE research_contradictions
                   SET status='resolved', resolution=?,
                       resolved_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (resolution[:2000], contradiction_id, scope),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM research_contradictions WHERE id=? AND scope=?",
                (contradiction_id, scope),
            ).fetchone()
        self._refresh_state(scope)
        return dict(updated)

    def dashboard(
        self,
        *,
        scope: str,
        gap_limit: int = 60,
        session_limit: int = 40,
        claim_limit: int = 80,
        evidence_limit: int = 100,
        cycle_limit: int = 40,
    ) -> dict:
        self._ensure_state(scope)
        self._ensure_builtin_sources(scope)
        state = self._refresh_state(scope)
        gaps = self.gaps(scope=scope, status=None, limit=gap_limit)
        sessions = self.sessions(scope=scope, limit=session_limit)
        claims = self.claims(scope=scope, limit=claim_limit)
        evidence = self.recent_evidence(scope=scope, limit=evidence_limit)
        contradictions = self.contradictions(scope=scope, status=None, limit=100)
        sources = self.sources(scope=scope, limit=200)
        cycles = self.cycles(scope=scope, limit=cycle_limit)
        return {
            "version": self.VERSION,
            "formula_version": self.FORMULA_VERSION,
            "scope": scope,
            "summary": {
                **state,
                "open_gaps": sum(1 for item in gaps if item["status"] == "open"),
                "researching_gaps": sum(1 for item in gaps if item["status"] == "researching"),
                "trusted_claims": sum(1 for item in claims if item["status"] == "trusted"),
                "supported_claims": sum(1 for item in claims if item["status"] == "supported"),
                "conflicted_claims": sum(1 for item in claims if item["status"] == "conflicted"),
                "open_contradictions": sum(1 for item in contradictions if item["status"] == "open"),
                "enabled_sources": sum(1 for item in sources if item["enabled"]),
                "external_connectors_enabled": sum(
                    1 for item in sources
                    if item["source_type"] == "external_connector" and item["enabled"]
                ),
            },
            "gaps": gaps,
            "sessions": sessions,
            "claims": claims,
            "evidence": evidence,
            "contradictions": contradictions,
            "sources": sources,
            "cycles": cycles,
            "principles": [
                "Model synthesis is never evidence; every evidence row points to a persisted source.",
                "Memory and semantic retrieval share one independence group and cannot double-count as two independent sources.",
                "Trusted promotion requires multiple independent primary source groups and zero counter-evidence.",
                "A conflicted claim is never promoted automatically.",
                "External network research stays disabled until an explicit connector adapter is implemented.",
                "Project files are auto-read only when explicitly registered and read_local_context permission allows it.",
                "Promoted research knowledge keeps provenance through claim and evidence IDs.",
                "Research confidence measures local evidence support; it is not universal truth.",
            ],
        }

    def prompt_block(
        self,
        *,
        scope: str,
        session_id: int | None = None,
        question: str = "",
        limit: int = 8,
    ) -> str:
        if session_id is None:
            evidence = self.recent_evidence(scope=scope, limit=limit)
            claims = self.claims(scope=scope, limit=limit)
        else:
            evidence = self.evidence(scope=scope, session_id=session_id, limit=limit)
            claims = self.claims(scope=scope, session_id=session_id, limit=limit)
        lines = [
            "Autonomous Research Intelligence.",
            "Use only the evidence ledger below as research evidence.",
            "Model-generated claims are not evidence by themselves.",
            "If evidence is insufficient or conflicted, preserve uncertainty.",
        ]
        if question:
            lines.append(f"Research question: {question[:600]}")
        if evidence:
            lines.append("Evidence ledger:")
            for item in evidence[:limit]:
                lines.append(
                    f"- E{item['id']} [{item['source_type']}/{item['source_group']}; "
                    f"score={float(item['evidence_score']):.2f}] {item['content'][:420]}"
                )
        if claims:
            lines.append("Research claims:")
            for item in claims[:limit]:
                lines.append(
                    f"- C{item['id']} [{item['status']}; "
                    f"confidence={float(item['confidence']):.2f}] {item['statement'][:500]}"
                )
        if not evidence:
            lines.append("- Research evidence not found.")
        return "\n".join(lines)

    def sources(self, *, scope: str, limit: int = 100) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM research_sources
                   WHERE scope=? ORDER BY enabled DESC, id ASC LIMIT ?""",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["enabled"] = bool(item["enabled"])
            item["auto_read"] = bool(item["auto_read"])
            item["metadata"] = self._json(item.pop("metadata_json"), {})
            result.append(item)
        return result

    def gaps(
        self,
        *,
        scope: str,
        status: str | None = "open",
        limit: int = 100,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        with connect() as conn:
            if status:
                rows = conn.execute(
                    """SELECT * FROM research_gaps
                       WHERE scope=? AND status=?
                       ORDER BY priority DESC, uncertainty DESC, id DESC LIMIT ?""",
                    (scope, status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM research_gaps
                       WHERE scope=?
                       ORDER BY CASE status
                         WHEN 'researching' THEN 0
                         WHEN 'open' THEN 1
                         WHEN 'resolved' THEN 2
                         ELSE 3 END,
                         priority DESC, id DESC LIMIT ?""",
                    (scope, limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def sessions(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_sessions WHERE scope=? ORDER BY id DESC LIMIT ?",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["plan"] = self._json(item.pop("plan_json"), {})
            item["source_plan"] = self._json(item.pop("source_plan_json"), [])
            item["synthesis_used"] = bool(item["synthesis_used"])
            result.append(item)
        return result

    def evidence(self, *, scope: str, session_id: int, limit: int = 100) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM research_evidence
                   WHERE scope=? AND session_id=?
                   ORDER BY evidence_score DESC, id ASC LIMIT ?""",
                (scope, session_id, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._decode_evidence(dict(row)) for row in rows]

    def recent_evidence(self, *, scope: str, limit: int = 100) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_evidence WHERE scope=? ORDER BY id DESC LIMIT ?",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._decode_evidence(dict(row)) for row in rows]

    def claim(self, claim_id: int, *, scope: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM research_claims WHERE id=? AND scope=?",
                (claim_id, scope),
            ).fetchone()
        return self._decode_claim(dict(row)) if row else None

    def claims(
        self,
        *,
        scope: str,
        session_id: int | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        where = ["scope=?"]
        params: list[Any] = [scope]
        if session_id is not None:
            where.append("session_id=?")
            params.append(session_id)
        if status:
            where.append("status=?")
            params.append(status)
        params.append(max(1, min(int(limit), 500)))
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM research_claims
                    WHERE {' AND '.join(where)}
                    ORDER BY CASE status
                      WHEN 'trusted' THEN 0
                      WHEN 'supported' THEN 1
                      WHEN 'conflicted' THEN 2
                      WHEN 'candidate' THEN 3
                      ELSE 4 END,
                      confidence DESC, id DESC LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [self._decode_claim(dict(row)) for row in rows]

    def contradictions(
        self,
        *,
        scope: str,
        session_id: int | None = None,
        status: str | None = "open",
        limit: int = 100,
    ) -> list[dict]:
        where = ["scope=?"]
        params: list[Any] = [scope]
        if session_id is not None:
            where.append("session_id=?")
            params.append(session_id)
        if status:
            where.append("status=?")
            params.append(status)
        params.append(max(1, min(int(limit), 500)))
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM research_contradictions
                    WHERE {' AND '.join(where)}
                    ORDER BY severity DESC, id DESC LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def cycles(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM research_cycles WHERE scope=? ORDER BY id DESC LIMIT ?",
                (scope, max(1, min(int(limit), 300))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["summary"] = self._json(item.pop("summary_json"), {})
            result.append(item)
        return result

    def state(self, *, scope: str) -> dict:
        self._ensure_state(scope)
        with connect() as conn:
            row = conn.execute("SELECT * FROM research_state WHERE scope=?", (scope,)).fetchone()
        return dict(row) if row else {}

    def _build_plan(
        self,
        scope: str,
        question: str,
        *,
        offline_only: bool = False,
    ) -> dict:
        sources = [
            item
            for item in self.sources(scope=scope, limit=300)
            if item["enabled"]
            and (
                not offline_only
                or item["source_type"] not in {
                    "semantic_memory",
                    "external_connector",
                }
            )
        ]
        return {
            "sources": sources,
            "policy": {
                "question": question,
                "network_research_sources": False,
                "offline_only": offline_only,
                "model_output_is_evidence": False,
                "minimum_trusted_groups": self.TRUSTED_MIN_GROUPS,
                "minimum_trusted_confidence": self.TRUSTED_MIN_CONFIDENCE,
            },
        }

    def _collect_evidence(
        self,
        scope: str,
        session_id: int,
        question: str,
        plan: dict,
    ) -> list[dict]:
        result: list[dict] = []
        for source in plan["sources"]:
            try:
                kind = source["source_type"]
                if kind == "memory":
                    result.extend(self._collect_memory(scope, session_id, question, source, False))
                elif kind == "semantic_memory":
                    result.extend(self._collect_memory(scope, session_id, question, source, True))
                elif kind == "knowledge_graph":
                    result.extend(self._collect_graph(scope, session_id, question, source))
                elif kind == "messages":
                    result.extend(self._collect_messages(scope, session_id, question, source))
                elif kind == "verification":
                    result.extend(self._collect_verification(scope, session_id, question, source))
                elif kind == "trusted_claims":
                    result.extend(self._collect_trusted_claims(scope, session_id, question, source))
                elif kind == "project_file":
                    result.extend(self._collect_project_file(scope, session_id, question, source))
                elif kind == "manual_reference":
                    result.extend(self._collect_manual_reference(scope, session_id, question, source))
            except Exception as exc:
                self._event(
                    scope,
                    "research.source.error",
                    "source",
                    str(source["source_key"]),
                    0.0,
                    {"error": str(exc)[:500]},
                )
        dedup: dict[str, dict] = {}
        for item in result:
            key = str(item["content_hash"])
            old = dedup.get(key)
            if old is None or float(item["evidence_score"]) > float(old["evidence_score"]):
                dedup[key] = item
        return sorted(dedup.values(), key=lambda x: float(x["evidence_score"]), reverse=True)

    def _collect_memory(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
        semantic: bool,
    ) -> list[dict]:
        items = (
            self.semantic.search(question, scope=scope, limit=14, min_similarity=0.20)
            if semantic
            else self.memory.recall(question, scope=scope, limit=16)
        )
        result = []
        for item in items:
            text = str(item.get("content") or "").strip()
            if not text:
                continue
            relevance = (
                float(item.get("semantic_similarity") or 0.0)
                if semantic
                else self._relevance(question, text)
            )
            if relevance < 0.12:
                continue
            trust = self._knowledge_trust(scope, "memory", int(item["id"]))
            reliability = max(
                float(source["trust_prior"]),
                float(item.get("confidence") or 0.0) * 0.82,
                trust,
            )
            result.append(
                self.add_evidence(
                    scope=scope,
                    session_id=session_id,
                    source_type=source["source_type"],
                    source_ref=str(item["id"]),
                    source_group=str(source["independent_group"]),
                    title=f"Memory #{item['id']}",
                    content=text,
                    reliability=reliability,
                    relevance=relevance,
                    freshness=self._freshness(item.get("updated_at"), 365.0),
                    independence=0.72 if semantic else 1.0,
                    metadata={
                        "kind": item.get("kind"),
                        "confidence": item.get("confidence"),
                        "retrieval": "semantic" if semantic else "lexical",
                    },
                )
            )
        return result

    def _collect_graph(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
    ) -> list[dict]:
        entities: dict[int, dict] = {}
        for token in sorted(self._tokens(question), key=len, reverse=True)[:8]:
            for item in self.graph.search(token, scope=scope, limit=8):
                entities[int(item["id"])] = item
        result = []
        for item in entities.values():
            content = (
                f"{item.get('entity_type')}: {item.get('canonical_name')}; "
                f"data={json.dumps(item.get('data') or {}, ensure_ascii=False)}"
            )
            relevance = self._relevance(question, content)
            if relevance < 0.10:
                continue
            result.append(
                self.add_evidence(
                    scope=scope,
                    session_id=session_id,
                    source_type="knowledge_graph",
                    source_ref=f"entity:{item['id']}",
                    source_group=str(source["independent_group"]),
                    title=f"Graph entity: {item.get('canonical_name')}",
                    content=content,
                    reliability=float(source["trust_prior"]),
                    relevance=relevance,
                    freshness=self._freshness(item.get("updated_at"), 540.0),
                    metadata={"entity_id": item["id"]},
                )
            )
        entity_ids = set(entities)
        for rel in self.graph.relations(scope=scope, limit=500):
            if int(rel["source_id"]) not in entity_ids and int(rel["target_id"]) not in entity_ids:
                continue
            content = (
                f"{rel['source_name']} --{rel['relation_type']}--> "
                f"{rel['target_name']}; evidence={rel.get('evidence') or ''}"
            )
            trust = self._knowledge_trust(scope, "relation", int(rel["id"]))
            result.append(
                self.add_evidence(
                    scope=scope,
                    session_id=session_id,
                    source_type="knowledge_graph_relation",
                    source_ref=f"relation:{rel['id']}",
                    source_group=str(source["independent_group"]),
                    title=f"Graph relation #{rel['id']}",
                    content=content,
                    reliability=max(
                        float(source["trust_prior"]),
                        float(rel.get("confidence") or 0.0) * 0.85,
                        trust,
                    ),
                    relevance=max(0.12, self._relevance(question, content)),
                    freshness=self._freshness(rel.get("created_at"), 540.0),
                    metadata={"relation_type": rel["relation_type"]},
                )
            )
        return result

    def _collect_messages(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
    ) -> list[dict]:
        tokens = list(self._tokens(question))[:10]
        if not tokens:
            return []
        where = " OR ".join(["LOWER(content) LIKE ?" for _ in tokens])
        params = [f"%{token.casefold()}%" for token in tokens]
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT * FROM messages
                    WHERE scope=? AND ({where})
                    ORDER BY id DESC LIMIT 18""",
                (scope, *params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            text = str(item["content"] or "").strip()
            relevance = self._relevance(question, text)
            if relevance < 0.14:
                continue
            result.append(
                self.add_evidence(
                    scope=scope,
                    session_id=session_id,
                    source_type="message",
                    source_ref=str(item["id"]),
                    source_group=str(source["independent_group"]),
                    title=f"Message #{item['id']} · {item['role']}",
                    content=text,
                    reliability=float(source["trust_prior"]) * (1.08 if item["role"] == "user" else 0.82),
                    relevance=relevance,
                    freshness=self._freshness(item.get("created_at"), 240.0),
                    metadata={"role": item["role"]},
                )
            )
        return result

    def _collect_verification(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
    ) -> list[dict]:
        q_tokens = self._tokens(question)
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM verification_runs WHERE scope=? ORDER BY id DESC LIMIT 50",
                (scope,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            findings = self._json(item.get("findings_json"), [])
            unresolved = self._json(item.get("unresolved_json"), [])
            searchable = " ".join(
                [str(item.get("query") or "")]
                + [str(v) for v in findings]
                + [str(v) for v in unresolved]
            )
            if q_tokens and not (q_tokens & self._tokens(searchable)):
                continue
            content = (
                f"Verification query: {item.get('query') or ''}\n"
                f"Findings: {json.dumps(findings, ensure_ascii=False)}\n"
                f"Unresolved: {json.dumps(unresolved, ensure_ascii=False)}"
            )
            result.append(
                self.add_evidence(
                    scope=scope,
                    session_id=session_id,
                    source_type="verification",
                    source_ref=str(item["id"]),
                    source_group=str(source["independent_group"]),
                    title=f"Verification #{item['id']}",
                    content=content,
                    reliability=float(source["trust_prior"]),
                    relevance=max(0.30, self._relevance(question, searchable)),
                    freshness=self._freshness(item.get("created_at"), 180.0),
                    metadata={
                        "final_status": item.get("final_status"),
                        "unresolved_count": len(unresolved),
                    },
                )
            )
        return result

    def _collect_trusted_claims(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM research_claims
                   WHERE scope=? AND status='trusted'
                   ORDER BY confidence DESC, updated_at DESC LIMIT 80""",
                (scope,),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            statement = str(item["statement"] or "")
            relevance = self._relevance(question, statement)
            if relevance < 0.18:
                continue
            result.append(
                self.add_evidence(
                    scope=scope,
                    session_id=session_id,
                    source_type="trusted_claim",
                    source_ref=str(item["id"]),
                    source_group="derived_knowledge",
                    title=f"Trusted claim #{item['id']}",
                    content=statement,
                    reliability=min(float(source["trust_prior"]), float(item["confidence"] or 0.0)),
                    relevance=relevance,
                    freshness=self._freshness(item.get("updated_at"), 270.0),
                    independence=0.65,
                    metadata={"claim_id": item["id"], "derived": True},
                )
            )
        return result

    def _collect_project_file(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
    ) -> list[dict]:
        if not source["auto_read"]:
            return []
        if self.tools.permissions.mode("read_local_context") != "allow":
            return []
        path = str(source.get("locator") or "").strip()
        if not path:
            return []
        tool_result = self.tools.invoke(
            "project.read_text",
            scope=scope,
            arguments={"path": path},
            dry_run=False,
            approved=False,
        )
        if tool_result.get("status") != "success":
            return []
        output = tool_result.get("output") or {}
        text = str(output.get("content") or "")
        relevance = self._relevance(question, text)
        if relevance < 0.08:
            return []
        return [
            self.add_evidence(
                scope=scope,
                session_id=session_id,
                source_type="project_file",
                source_ref=path,
                source_group=str(source["independent_group"]),
                title=str(source["label"]),
                content=text[:12000],
                reliability=float(source["trust_prior"]),
                relevance=relevance,
                metadata={
                    "path": output.get("path"),
                    "sha256": output.get("sha256"),
                    "registered_source_id": source["id"],
                },
            )
        ]

    def _collect_manual_reference(
        self,
        scope: str,
        session_id: int,
        question: str,
        source: dict,
    ) -> list[dict]:
        text = str((source.get("metadata") or {}).get("content") or "").strip()
        if not text:
            return []
        relevance = self._relevance(question, text)
        if relevance < 0.08:
            return []
        return [
            self.add_evidence(
                scope=scope,
                session_id=session_id,
                source_type="manual_reference",
                source_ref=str(source["source_key"]),
                source_group=str(source["independent_group"]),
                title=str(source["label"]),
                content=text[:12000],
                reliability=float(source["trust_prior"]),
                relevance=relevance,
                metadata={"registered_source_id": source["id"], "manual_reference": True},
            )
        ]

    def _synthesize_claims(
        self,
        scope: str,
        session_id: int,
        question: str,
        evidence: list[dict],
    ) -> tuple[list[dict], bool]:
        compact = [
            {
                "id": int(item["id"]),
                "source_type": item["source_type"],
                "source_group": item["source_group"],
                "score": round(float(item["evidence_score"]), 4),
                "content": item["content"][:1800],
            }
            for item in evidence[:24]
        ]
        system = """Ты Evidence Synthesis Engine проекта Aishin.
Работай ТОЛЬКО с переданным evidence ledger.
Твоя формулировка claim НЕ является доказательством.
Не используй внешние знания и не достраивай отсутствующие факты.
Верни только JSON:
{
  "claims": [
    {
      "statement": "краткое проверяемое утверждение",
      "support_evidence_ids": [1,2],
      "contradiction_evidence_ids": [],
      "missing": []
    }
  ]
}
Если evidence недостаточно, верни {"claims":[]}.
Если источники расходятся, перечисли counter-evidence.
Не объединяй разные факты в один широкий claim."""
        reply = self.ai.chat(
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": question, "evidence": compact},
                        ensure_ascii=False,
                    ),
                }
            ],
        )
        if not reply.available:
            return [], False
        data = self._parse_json(reply.text)
        raw = data.get("claims") if isinstance(data, dict) else []
        if not isinstance(raw, list):
            return [], True
        claims = []
        for item in raw[:8]:
            if not isinstance(item, dict):
                continue
            statement = str(item.get("statement") or "").strip()
            if not statement:
                continue
            claims.append(
                self.evaluate_claim(
                    scope=scope,
                    session_id=session_id,
                    statement=statement,
                    support_evidence_ids=self._unique_ints(item.get("support_evidence_ids") or []),
                    contradiction_evidence_ids=self._unique_ints(item.get("contradiction_evidence_ids") or []),
                    missing=[str(v) for v in item.get("missing") or []],
                )
            )
        return claims, True

    def _promote_claim(self, scope: str, claim: dict, support: list[dict]) -> None:
        if claim["status"] != "trusted" or claim["contradiction_count"]:
            return
        primary_groups = {
            item["source_group"]
            for item in support
            if item["source_group"] != "derived_knowledge"
        }
        if len(primary_groups) < self.TRUSTED_MIN_GROUPS:
            return
        claim_id = int(claim["id"])
        provenance = {
            "research_claim_id": claim_id,
            "research_session_id": int(claim["session_id"]),
            "support_evidence_ids": claim["support_evidence_ids"],
            "source_groups": sorted({str(item["source_group"]) for item in support}),
            "confidence": float(claim["confidence"]),
        }
        decision = self.memory.consolidate(
            MemoryCandidate(
                content=str(claim["statement"]),
                kind="researched_knowledge",
                scope=scope,
                confidence=min(0.97, float(claim["confidence"])),
                importance=0.78,
                tags=("research", "evidence_grounded", "provenance"),
                memory_key=f"research_claim:{claim['claim_key']}",
            ),
            source=f"autonomous_research:claim:{claim_id}",
        )
        entity_id = self.graph.entity(
            scope=scope,
            entity_type="research_claim",
            name=f"Claim {claim_id}",
            data={
                "statement": claim["statement"],
                "status": "trusted",
                "confidence": float(claim["confidence"]),
                "provenance": provenance,
            },
            evidence=json.dumps(provenance, ensure_ascii=False),
        )
        with connect() as conn:
            conn.execute(
                """UPDATE research_claims
                   SET promoted_memory_id=?, promoted_entity_id=?,
                       promoted_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (decision.memory_id, entity_id, claim_id, scope),
            )
            conn.commit()
        self.events.emit(
            "research.knowledge.promoted",
            scope=scope,
            payload={
                "claim_id": claim_id,
                "memory_id": decision.memory_id,
                "entity_id": entity_id,
                "confidence": claim["confidence"],
                "support_evidence_ids": claim["support_evidence_ids"],
            },
            importance=0.75,
        )

    def _record_contradictions(
        self,
        scope: str,
        session_id: int,
        claim_id: int,
        support: list[dict],
        contradiction: list[dict],
    ) -> None:
        left_id = int(support[0]["id"]) if support else None
        with connect() as conn:
            existing = {
                (
                    int(row["left_evidence_id"]) if row["left_evidence_id"] is not None else None,
                    int(row["right_evidence_id"]) if row["right_evidence_id"] is not None else None,
                )
                for row in conn.execute(
                    """SELECT left_evidence_id, right_evidence_id
                       FROM research_contradictions
                       WHERE scope=? AND session_id=? AND claim_id=?""",
                    (scope, session_id, claim_id),
                ).fetchall()
            }
            for item in contradiction:
                pair = (left_id, int(item["id"]))
                if pair in existing:
                    continue
                conn.execute(
                    """INSERT INTO research_contradictions(
                           scope, session_id, claim_id,
                           left_evidence_id, right_evidence_id,
                           contradiction_type, severity
                       ) VALUES (?, ?, ?, ?, ?, 'claim_counter_evidence', ?)""",
                    (
                        scope, session_id, claim_id, left_id, int(item["id"]),
                        max(0.50, float(item["evidence_score"])),
                    ),
                )
            conn.commit()

    def _refresh_state(self, scope: str) -> dict:
        self._ensure_state(scope)
        with connect() as conn:
            gap_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM research_gaps WHERE scope=? GROUP BY status",
                (scope,),
            ).fetchall()
            session_rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM research_sessions WHERE scope=? GROUP BY status",
                (scope,),
            ).fetchall()
            evidence_rows = conn.execute(
                "SELECT evidence_score FROM research_evidence WHERE scope=? ORDER BY id DESC LIMIT 300",
                (scope,),
            ).fetchall()
            claim_rows = conn.execute(
                "SELECT status, confidence FROM research_claims WHERE scope=?",
                (scope,),
            ).fetchall()
            contradiction_rows = conn.execute(
                "SELECT status FROM research_contradictions WHERE scope=?",
                (scope,),
            ).fetchall()

        gaps = {str(row["status"]): int(row["n"]) for row in gap_rows}
        sessions = {str(row["status"]): int(row["n"]) for row in session_rows}
        total_gaps = sum(gaps.values())
        coverage = gaps.get("resolved", 0) / total_gaps if total_gaps else 0.0
        evidence_quality = self._average([float(row["evidence_score"] or 0.0) for row in evidence_rows])
        total_c = len(contradiction_rows)
        resolved_c = sum(1 for row in contradiction_rows if row["status"] == "resolved")
        contradiction_resolution = resolved_c / total_c if total_c else (1.0 if claim_rows else 0.0)
        trusted = [row for row in claim_rows if row["status"] == "trusted"]
        conflicted = [row for row in claim_rows if row["status"] == "conflicted"]
        rejected = [row for row in claim_rows if row["status"] == "rejected"]
        evaluated = len(trusted) + len(conflicted) + len(rejected)
        precision = len(trusted) / evaluated if evaluated else 0.0
        if trusted:
            precision = 0.65 * precision + 0.35 * self._average(
                [float(row["confidence"] or 0.0) for row in trusted]
            )
        completed_sessions = sum(
            value for key, value in sessions.items()
            if key in {"completed", "evidence_only", "insufficient"}
        )
        volume = self._saturation(
            completed_sessions + len(evidence_rows) / 8.0 + len(claim_rows) * 1.5,
            30.0,
        )
        base = (
            0.28 * coverage
            + 0.30 * evidence_quality
            + 0.20 * contradiction_resolution
            + 0.22 * precision
        )
        research_score = 100.0 * base * (0.42 + 0.58 * volume)
        with connect() as conn:
            conn.execute(
                """UPDATE research_state
                   SET research_score=?, coverage_score=?,
                       evidence_quality=?, contradiction_resolution=?,
                       knowledge_precision=?, open_gap_count=?,
                       active_session_count=?, trusted_claim_count=?,
                       conflicted_claim_count=?,
                       last_cycle_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (
                    round(research_score, 2),
                    round(coverage * 100.0, 2),
                    round(evidence_quality * 100.0, 2),
                    round(contradiction_resolution * 100.0, 2),
                    round(precision * 100.0, 2),
                    gaps.get("open", 0) + gaps.get("researching", 0),
                    sessions.get("running", 0),
                    len(trusted),
                    len(conflicted),
                    scope,
                ),
            )
            conn.commit()
        return self.state(scope=scope)

    def _session_quality(
        self,
        evidence: list[dict],
        claims: list[dict],
        contradictions: list[dict],
    ) -> float:
        ev = self._average([float(item["evidence_score"]) for item in evidence])
        claim_q = self._average(
            [
                float(item["confidence"])
                for item in claims
                if item["status"] in {"trusted", "supported"}
            ]
        )
        trusted = sum(1 for item in claims if item["status"] == "trusted")
        return self._clamp(
            0.55 * ev + 0.30 * claim_q + 0.15 * min(1.0, trusted / 2.0)
            - min(0.45, 0.12 * len(contradictions))
        )

    def _ensure_state(self, scope: str) -> None:
        with connect() as conn:
            conn.execute(
                "INSERT INTO research_state(scope) VALUES (?) ON CONFLICT(scope) DO NOTHING",
                (scope,),
            )
            conn.commit()

    def _ensure_builtin_sources(self, scope: str) -> None:
        with connect() as conn:
            for key, source_type, label, group, trust in self.BUILTIN_SOURCES:
                conn.execute(
                    """INSERT INTO research_sources(
                           scope, source_key, source_type, label,
                           independent_group, trust_prior, enabled, auto_read
                       ) VALUES (?, ?, ?, ?, ?, ?, 1, 1)
                       ON CONFLICT(scope, source_key) DO UPDATE SET
                           label=excluded.label,
                           source_type=excluded.source_type,
                           independent_group=excluded.independent_group,
                           trust_prior=excluded.trust_prior,
                           enabled=1,
                           updated_at=CURRENT_TIMESTAMP""",
                    (scope, key, source_type, label, group, trust),
                )
            conn.commit()

    def _knowledge_trust(self, scope: str, subject_type: str, subject_id: int) -> float:
        with connect() as conn:
            row = conn.execute(
                """SELECT trust_score FROM knowledge_trust
                   WHERE scope=? AND subject_type=? AND subject_id=?""",
                (scope, subject_type, subject_id),
            ).fetchone()
        return float(row["trust_score"] or 0.0) if row else 0.0

    @staticmethod
    def _decode_evidence(item: dict) -> dict:
        item["metadata"] = AutonomousResearchEngine._json(item.pop("metadata_json"), {})
        return item

    @staticmethod
    def _decode_claim(item: dict) -> dict:
        item["support_evidence_ids"] = AutonomousResearchEngine._json(
            item.pop("support_evidence_json"), []
        )
        item["contradiction_evidence_ids"] = AutonomousResearchEngine._json(
            item.pop("contradiction_evidence_json"), []
        )
        item["missing"] = AutonomousResearchEngine._json(item.pop("missing_json"), [])
        return item

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if value in (None, ""):
            return default
        try:
            return json.loads(str(value))
        except Exception:
            return default

    @staticmethod
    def _parse_json(text: str) -> dict:
        raw = (text or "").strip()
        marker = chr(96) * 3
        if raw.startswith(marker):
            raw = re.sub(r"^.{3}(?:json)?\s*", "", raw, count=1)
            raw = re.sub(r"\s*.{3}$", "", raw, count=1)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            start, end = raw.find("{"), raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end + 1])
                    return data if isinstance(data, dict) else {}
                except Exception:
                    pass
        return {}

    @staticmethod
    def _hash(*parts: Any) -> str:
        return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()

    @staticmethod
    def _tokens(text: str) -> set[str]:
        stop = {"котор", "этого", "этот", "это", "для", "как", "что", "или", "если", "при", "the", "and", "with", "from"}
        return {
            token.casefold()
            for token in _TOKEN_RE.findall(text or "")
            if token.casefold() not in stop
        }

    @classmethod
    def _relevance(cls, query: str, content: str) -> float:
        q = cls._tokens(query)
        c = cls._tokens(content)
        if not q or not c:
            return 0.0
        overlap = len(q & c)
        recall = overlap / max(1, len(q))
        precision = overlap / max(1, min(len(c), 30))
        return cls._clamp(0.78 * recall + 0.22 * precision)

    @classmethod
    def _freshness(cls, value: Any, half_life_days: float) -> float:
        if not value:
            return 0.72
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            try:
                dt = datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except Exception:
                return 0.72
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = max(
            0.0,
            (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 86400.0,
        )
        decay = math.exp(-math.log(2.0) * age / max(1.0, half_life_days))
        return cls._clamp(0.45 + 0.55 * decay, 0.45, 1.0)

    @staticmethod
    def _combined_strength(values: list[float]) -> float:
        if not values:
            return 0.0
        remaining = 1.0
        for value in values:
            remaining *= 1.0 - min(0.95, max(0.0, value)) * 0.72
        return 1.0 - remaining

    @staticmethod
    def _unique_ints(values: list[Any]) -> list[int]:
        result, seen = [], set()
        for value in values:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number not in seen:
                seen.add(number)
                result.append(number)
        return result

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _saturation(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(1.0, 1.0 - math.exp(-max(0.0, float(value)) / target))

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    def _event(
        self,
        scope: str,
        event_type: str,
        subject_type: str,
        subject_key: str,
        score: float | None,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO research_events(
                       scope, event_type, subject_type,
                       subject_key, score, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope, event_type, subject_type, subject_key, score,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
        try:
            self.events.emit(
                event_type,
                scope=scope,
                payload={
                    "subject_type": subject_type,
                    "subject_key": subject_key,
                    "score": score,
                    **details,
                },
                importance=max(0.15, min(0.85, float(score or 0.25))),
            )
        except Exception:
            pass
