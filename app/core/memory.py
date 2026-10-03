from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable

from ..db import (
    active_memories_for_scope,
    add_memory,
    find_active_memory_by_key,
    find_memory_by_fingerprint,
    log_memory_change,
    recent_memories,
    recent_memory_changes,
    search_memories,
    supersede_memory,
    touch_memory,
    update_memory_strength,
)

_WORD_RE = re.compile(r"[\wА-Яа-яЁё-]{3,}", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_memory_text(text: str) -> str:
    text = text.strip().lower().replace("ё", "е")
    text = _SPACE_RE.sub(" ", text)
    return text


def fingerprint(text: str) -> str:
    normalized = normalize_memory_text(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def keywords(text: str, limit: int = 10) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for word in _WORD_RE.findall(text.lower()):
        if word in seen:
            continue
        seen.add(word)
        result.append(word)
        if len(result) >= limit:
            break
    return result


@dataclass
class MemoryCandidate:
    content: str
    kind: str = "context"
    scope: str = "personal"
    confidence: float = 0.7
    importance: float = 0.5
    tags: tuple[str, ...] = ()
    memory_key: str | None = None
    supersedes: bool = False


@dataclass
class ConsolidationDecision:
    action: str
    memory_id: int | None
    reason: str


class MemorySystem:
    """Long-term memory with scope, confidence, deduplication and audit history."""

    def remember(self, candidate: MemoryCandidate, *, source: str = "conversation") -> int:
        return add_memory(
            scope=candidate.scope,
            kind=candidate.kind,
            content=candidate.content,
            confidence=candidate.confidence,
            importance=candidate.importance,
            tags=list(candidate.tags),
            source=source,
            fingerprint=fingerprint(candidate.content),
            memory_key=candidate.memory_key,
        )

    def consolidate(
        self,
        candidate: MemoryCandidate,
        *,
        source: str = "conversation",
    ) -> ConsolidationDecision:
        clean = candidate.content.strip()
        if not clean:
            return ConsolidationDecision("ignored", None, "empty")

        candidate.content = clean
        fp = fingerprint(clean)

        exact = find_memory_by_fingerprint(candidate.scope, fp)
        if exact:
            new_confidence = max(float(exact["confidence"]), candidate.confidence)
            new_importance = max(float(exact["importance"]), candidate.importance)
            update_memory_strength(
                exact["id"],
                confidence=new_confidence,
                importance=new_importance,
            )
            log_memory_change(
                candidate.scope,
                exact["id"],
                "reinforced",
                "exact_duplicate",
                before=exact,
                after={
                    "confidence": new_confidence,
                    "importance": new_importance,
                },
            )
            return ConsolidationDecision("reinforced", exact["id"], "exact_duplicate")

        if candidate.memory_key:
            previous = find_active_memory_by_key(candidate.scope, candidate.memory_key)
            if previous:
                similarity = SequenceMatcher(
                    None,
                    normalize_memory_text(previous["content"]),
                    normalize_memory_text(clean),
                ).ratio()

                if similarity >= 0.90:
                    new_confidence = max(float(previous["confidence"]), candidate.confidence)
                    new_importance = max(float(previous["importance"]), candidate.importance)
                    update_memory_strength(
                        previous["id"],
                        confidence=new_confidence,
                        importance=new_importance,
                    )
                    log_memory_change(
                        candidate.scope,
                        previous["id"],
                        "reinforced",
                        f"same_memory_key_similarity={similarity:.3f}",
                        before=previous,
                        after={
                            "confidence": new_confidence,
                            "importance": new_importance,
                        },
                    )
                    return ConsolidationDecision(
                        "reinforced",
                        previous["id"],
                        "same_key_near_duplicate",
                    )

                if candidate.supersedes:
                    new_id = self.remember(candidate, source=source)
                    supersede_memory(previous["id"], new_id)
                    log_memory_change(
                        candidate.scope,
                        new_id,
                        "superseded",
                        "explicit_update_of_same_memory_key",
                        before=previous,
                        after={"id": new_id, "content": clean},
                    )
                    return ConsolidationDecision(
                        "superseded",
                        new_id,
                        "explicit_update",
                    )

                log_memory_change(
                    candidate.scope,
                    previous["id"],
                    "conflict_detected",
                    "same_memory_key_different_value",
                    before=previous,
                    after={"content": clean, "confidence": candidate.confidence},
                )
                candidate.tags = tuple({*candidate.tags, "contradiction"})
                candidate.kind = "contradictory_information"
                new_id = self.remember(candidate, source=source)
                return ConsolidationDecision(
                    "conflict_saved",
                    new_id,
                    "same_key_conflict",
                )

        near = self._find_near_duplicate(clean, scope=candidate.scope)
        if near:
            new_confidence = max(float(near["confidence"]), candidate.confidence)
            new_importance = max(float(near["importance"]), candidate.importance)
            update_memory_strength(
                near["id"],
                confidence=new_confidence,
                importance=new_importance,
            )
            log_memory_change(
                candidate.scope,
                near["id"],
                "reinforced",
                "near_duplicate",
                before=near,
                after={
                    "confidence": new_confidence,
                    "importance": new_importance,
                },
            )
            return ConsolidationDecision("reinforced", near["id"], "near_duplicate")

        new_id = self.remember(candidate, source=source)
        log_memory_change(
            candidate.scope,
            new_id,
            "created",
            "new_memory",
            after={
                "content": candidate.content,
                "kind": candidate.kind,
                "confidence": candidate.confidence,
                "importance": candidate.importance,
                "memory_key": candidate.memory_key,
            },
        )
        return ConsolidationDecision("created", new_id, "new_memory")

    def _find_near_duplicate(self, text: str, *, scope: str) -> dict | None:
        normalized = normalize_memory_text(text)
        for item in active_memories_for_scope(scope, limit=80):
            ratio = SequenceMatcher(
                None,
                normalize_memory_text(item["content"]),
                normalized,
            ).ratio()
            if ratio >= 0.94:
                return item
        return None

    def recall(self, query: str, *, scope: str = "personal", limit: int = 8) -> list[dict]:
        terms = keywords(query)
        memories = search_memories(terms=terms, scope=scope, limit=limit)
        for memory in memories:
            touch_memory(memory["id"])
        return memories

    def recent(self, *, scope: str = "personal", limit: int = 12) -> list[dict]:
        return recent_memories(scope=scope, limit=limit)

    def recent_changes(
        self,
        limit: int = 30,
        *,
        scope: str | None = None,
    ) -> list[dict]:
        return recent_memory_changes(limit=limit, scope=scope)

    def context_block(self, memories: Iterable[dict]) -> str:
        return "\n".join(
            f"- [{item['kind']}; confidence={item['confidence']:.2f}] {item['content']}"
            for item in memories
        )
