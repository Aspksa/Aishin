from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..db import connect


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_./:+#%-]+", re.UNICODE)


@dataclass
class GroundingClaim:
    text: str
    support_score: float
    status: str
    source_keys: list[str] = field(default_factory=list)
    provenance_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResponseGroundingResult:
    request_id: str
    status: str
    applicable: bool
    overall: float | None
    claim_coverage: float | None
    provenance_coverage: float | None
    source_diversity: float | None
    contradiction_handling: float | None
    claims_total: int
    claims_supported: int
    claims_partial: int
    claims_unsupported: int
    source_groups: int
    source_types: list[str]
    warnings: list[str]
    claims: list[GroundingClaim]
    grounding_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ResponseGroundingScorer:
    """Deterministic post-response evidence-grounding audit.

    The scorer does not decide whether an answer is objectively true. It only
    checks whether contentful claims in the produced answer can be matched to
    evidence that was actually available to this request.
    """

    VERSION = "aishin-response-grounding-v1"

    STOP_WORDS = {
        "это", "этот", "эта", "эти", "того", "также", "как", "что", "чтобы",
        "для", "при", "если", "или", "но", "уже", "ещё", "его", "ее", "её",
        "их", "мы", "вы", "я", "он", "она", "они", "быть", "есть", "был",
        "была", "были", "будет", "можно", "нужно", "надо", "the", "and",
        "for", "with", "from", "this", "that", "are", "was", "were", "will",
    }

    UNCERTAINTY_MARKERS = (
        "противореч",
        "не подтверж",
        "недостаточно",
        "не удалось подтвердить",
        "требует проверки",
        "нужно проверить",
        "неясно",
        "неизвестно",
        "уверенность",
        "вероятно",
        "возможно",
        "по имеющимся данным",
    )

    NON_CLAIM_PREFIXES = (
        "спасибо",
        "хорошо",
        "готово",
        "я рядом",
        "господин",
    )

    def assess(
        self,
        *,
        request_id: str,
        scope: str,
        mode: str,
        response: str,
        evidence: list[dict],
        tool_result: dict | None = None,
        contradictions: list[dict] | None = None,
    ) -> ResponseGroundingResult:
        sources = self._normalize_sources(
            evidence=evidence,
            tool_result=tool_result or {},
        )
        claims = self._claims(response)

        if not claims:
            result = ResponseGroundingResult(
                request_id=request_id,
                status="not_applicable_no_claims",
                applicable=False,
                overall=None,
                claim_coverage=None,
                provenance_coverage=None,
                source_diversity=None,
                contradiction_handling=None,
                claims_total=0,
                claims_supported=0,
                claims_partial=0,
                claims_unsupported=0,
                source_groups=len({item["group"] for item in sources}),
                source_types=sorted({item["source_type"] for item in sources}),
                warnings=[],
                claims=[],
            )
            result.grounding_id = self._record(
                scope=scope,
                mode=mode,
                result=result,
            )
            return result

        if not sources:
            result = ResponseGroundingResult(
                request_id=request_id,
                status="unscored_no_evidence",
                applicable=False,
                overall=None,
                claim_coverage=None,
                provenance_coverage=None,
                source_diversity=None,
                contradiction_handling=None,
                claims_total=len(claims),
                claims_supported=0,
                claims_partial=0,
                claims_unsupported=len(claims),
                source_groups=0,
                source_types=[],
                warnings=["no_grounding_evidence_available"],
                claims=[
                    GroundingClaim(
                        text=claim[:500],
                        support_score=0.0,
                        status="unscored",
                    )
                    for claim in claims[:24]
                ],
            )
            result.grounding_id = self._record(
                scope=scope,
                mode=mode,
                result=result,
            )
            return result

        evaluated: list[GroundingClaim] = []
        supporting_groups: set[str] = set()
        supported_with_provenance = 0

        for claim in claims[:24]:
            ranked = sorted(
                (
                    (
                        self._support_score(claim, source["content"])
                        * source["quality"],
                        source,
                    )
                    for source in sources
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            best_score = ranked[0][0] if ranked else 0.0
            matched = [
                source
                for score, source in ranked[:4]
                if score >= 0.22
            ]
            source_keys = list(dict.fromkeys(
                source["key"] for source in matched
            ))
            provenance_count = sum(
                1 for source in matched
                if source["has_provenance"]
            )
            if best_score >= 0.44:
                claim_status = "supported"
                supporting_groups.update(
                    source["group"] for source in matched
                    if source["group"]
                )
                if provenance_count:
                    supported_with_provenance += 1
            elif best_score >= 0.24:
                claim_status = "partial"
                supporting_groups.update(
                    source["group"] for source in matched
                    if source["group"]
                )
            else:
                claim_status = "unsupported"

            evaluated.append(
                GroundingClaim(
                    text=claim[:500],
                    support_score=round(best_score, 4),
                    status=claim_status,
                    source_keys=source_keys[:4],
                    provenance_count=provenance_count,
                )
            )

        total = len(evaluated)
        supported = sum(item.status == "supported" for item in evaluated)
        partial = sum(item.status == "partial" for item in evaluated)
        unsupported = sum(item.status == "unsupported" for item in evaluated)

        claim_coverage = (
            supported + 0.5 * partial
        ) / max(1, total)
        provenance_coverage = supported_with_provenance / max(1, supported)
        all_groups = {item["group"] for item in sources if item["group"]}
        source_diversity = min(
            1.0,
            len(supporting_groups) / 3.0,
        )

        contradictions = contradictions or []
        contradiction_handling: float | None = None
        if contradictions:
            text = response.casefold().replace("ё", "е")
            acknowledged = any(
                marker in text
                for marker in self.UNCERTAINTY_MARKERS
            )
            contradiction_handling = 1.0 if acknowledged else 0.0

        weighted = [
            (claim_coverage, 0.58),
            (provenance_coverage, 0.24),
            (source_diversity, 0.18),
        ]
        if contradiction_handling is not None:
            weighted = [
                (claim_coverage, 0.50),
                (provenance_coverage, 0.20),
                (source_diversity, 0.15),
                (contradiction_handling, 0.15),
            ]
        total_weight = sum(weight for _, weight in weighted)
        overall = sum(value * weight for value, weight in weighted) / total_weight

        warnings: list[str] = []
        if unsupported:
            warnings.append("unsupported_claims_present")
        if claim_coverage < 0.55:
            warnings.append("low_claim_evidence_coverage")
        if supported and provenance_coverage < 0.60:
            warnings.append("low_provenance_coverage")
        if contradictions and contradiction_handling == 0.0:
            warnings.append("contradictions_not_acknowledged")

        status = (
            "strong"
            if overall >= 0.78 and not warnings
            else "mixed"
            if overall >= 0.52
            else "weak"
        )

        result = ResponseGroundingResult(
            request_id=request_id,
            status=status,
            applicable=True,
            overall=round(overall, 4),
            claim_coverage=round(claim_coverage, 4),
            provenance_coverage=round(provenance_coverage, 4),
            source_diversity=round(source_diversity, 4),
            contradiction_handling=(
                round(contradiction_handling, 4)
                if contradiction_handling is not None
                else None
            ),
            claims_total=total,
            claims_supported=supported,
            claims_partial=partial,
            claims_unsupported=unsupported,
            source_groups=len(all_groups),
            source_types=sorted({item["source_type"] for item in sources}),
            warnings=warnings,
            claims=evaluated,
        )
        result.grounding_id = self._record(
            scope=scope,
            mode=mode,
            result=result,
        )
        return result

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM response_grounding_runs
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 300))),
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["applicable"] = bool(item["applicable"])
            item["source_types"] = json.loads(
                item.pop("source_types_json") or "[]"
            )
            item["warnings"] = json.loads(
                item.pop("warnings_json") or "[]"
            )
            item["claims"] = json.loads(
                item.pop("claims_json") or "[]"
            )
            result.append(item)
        return result

    def summary(self, *, scope: str, limit: int = 100) -> dict:
        rows = [
            item
            for item in self.recent(scope=scope, limit=limit)
            if item.get("applicable") and item.get("overall") is not None
        ]
        if not rows:
            return {
                "samples": 0,
                "average_grounding": None,
                "average_claim_coverage": None,
                "average_provenance_coverage": None,
                "unsupported_claims": 0,
            }
        return {
            "samples": len(rows),
            "average_grounding": round(
                sum(float(item["overall"]) for item in rows) / len(rows),
                4,
            ),
            "average_claim_coverage": round(
                sum(float(item["claim_coverage"]) for item in rows) / len(rows),
                4,
            ),
            "average_provenance_coverage": round(
                sum(float(item["provenance_coverage"]) for item in rows)
                / len(rows),
                4,
            ),
            "unsupported_claims": sum(
                int(item["claims_unsupported"]) for item in rows
            ),
        }

    @classmethod
    def _claims(cls, response: str) -> list[str]:
        claims: list[str] = []
        for raw in _SENTENCE_RE.split(response or ""):
            text = " ".join(raw.strip(" -\t•*").split())
            if not text or len(text) < 12:
                continue
            lowered = text.casefold().replace("ё", "е")
            if lowered.startswith(cls.NON_CLAIM_PREFIXES) and len(text) < 80:
                continue
            tokens = cls._tokens(text)
            if len(tokens) < 3 and not any(ch.isdigit() for ch in text):
                continue
            claims.append(text[:800])
        return list(dict.fromkeys(claims))[:24]

    @classmethod
    def _tokens(cls, text: str) -> set[str]:
        values: set[str] = set()
        for token in _TOKEN_RE.findall(text or ""):
            normalized = token.casefold().replace("ё", "е").strip(".,;:()[]{}")
            if not normalized or normalized in cls.STOP_WORDS:
                continue
            if (
                len(normalized) <= 2
                and normalized not in {"не"}
                and not any(ch.isdigit() for ch in normalized)
            ):
                continue
            values.add(cls._stem(normalized))
        return values

    @staticmethod
    def _stem(token: str) -> str:
        if any(ch.isdigit() for ch in token) or "/" in token or "." in token:
            return token
        suffixes = (
            "иями", "ями", "ами", "ого", "ему", "ому", "ыми", "ими",
            "ение", "ений", "ость", "ности", "овать", "ировать",
            "ая", "яя", "ое", "ее", "ый", "ий", "ой", "ые", "ие",
            "ами", "ями", "ах", "ях", "ов", "ев", "ом", "ем",
            "ам", "ям", "а", "я", "ы", "и", "е", "у", "ю",
        )
        for suffix in suffixes:
            if len(token) - len(suffix) >= 4 and token.endswith(suffix):
                return token[: -len(suffix)]
        return token

    @classmethod
    def _support_score(cls, claim: str, source: str) -> float:
        claim_tokens = cls._tokens(claim)
        source_tokens = cls._tokens(source)
        if not claim_tokens or not source_tokens:
            return 0.0
        overlap = len(claim_tokens & source_tokens)
        coverage = overlap / len(claim_tokens)
        precision = overlap / max(1, min(len(source_tokens), len(claim_tokens) * 3))
        numeric_claim = {
            token for token in claim_tokens
            if any(ch.isdigit() for ch in token)
        }
        numeric_source = {
            token for token in source_tokens
            if any(ch.isdigit() for ch in token)
        }
        numeric_bonus = 0.0
        numeric_match = 1.0
        if numeric_claim:
            numeric_match = (
                len(numeric_claim & numeric_source) / len(numeric_claim)
            )
            numeric_bonus = 0.18 * numeric_match
            if numeric_match == 0.0:
                numeric_bonus -= 0.18

        raw_score = max(
            0.0,
            min(
                1.0,
                0.76 * coverage
                + 0.24 * precision
                + numeric_bonus,
            ),
        )

        # Exact details must not be "supported" by a source containing a
        # different number/version. A partial numeric match may remain partial.
        if numeric_claim and numeric_match < 1.0:
            raw_score = min(
                raw_score,
                0.38 if numeric_match > 0.0 else 0.22,
            )

        negative_markers = {
            "не", "нет", "без", "запрещен", "запрещено",
            "отсутствует", "невозможно",
        }
        claim_negative = bool(claim_tokens & negative_markers)
        source_negative = bool(source_tokens & negative_markers)
        if claim_negative != source_negative:
            raw_score = min(raw_score, 0.22)

        return raw_score

    @classmethod
    def _normalize_sources(
        cls,
        *,
        evidence: list[dict],
        tool_result: dict,
    ) -> list[dict]:
        sources: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for index, item in enumerate(evidence[:32]):
            source_type = str(
                item.get("source_type")
                or item.get("source")
                or "evidence"
            )
            content = str(
                item.get("content")
                or item.get("finding")
                or item.get("message")
                or ""
            ).strip()
            if not content:
                continue

            if item.get("source_group"):
                group = str(item["source_group"])
            elif item.get("document_id") is not None:
                group = f"document:{item.get('document_id')}"
            elif source_type == "memory":
                group = f"memory:{item.get('id') or index}"
            else:
                group = f"{source_type}:{item.get('source_ref') or index}"

            if item.get("document_id") is not None:
                key = (
                    f"document:{item.get('document_id')}:"
                    f"chunk:{item.get('chunk_id')}"
                )
            elif source_type == "memory":
                key = f"memory:{item.get('id') or index}"
            else:
                key = f"{source_type}:{item.get('source_ref') or index}"

            fingerprint = (key, content[:500])
            if fingerprint in seen:
                continue
            seen.add(fingerprint)

            confidence = item.get("confidence")
            if confidence is None:
                confidence = item.get("retrieval_score")
            try:
                quality = max(
                    0.35,
                    min(
                        1.0,
                        float(
                            0.65 if confidence is None else confidence
                        ),
                    ),
                )
            except (TypeError, ValueError):
                quality = 0.65

            provenance = item.get("provenance") or {}
            has_provenance = bool(
                provenance
                or item.get("document_id") is not None
                or item.get("id") is not None
                or item.get("source_ref")
            )
            sources.append(
                {
                    "key": key,
                    "group": group,
                    "source_type": source_type,
                    "content": content[:5000],
                    "quality": quality,
                    "has_provenance": has_provenance,
                }
            )

        if tool_result:
            output = tool_result.get("output") or tool_result
            content = str(output.get("content") or "").strip()
            if content:
                tool = str(
                    tool_result.get("tool")
                    or tool_result.get("tool_name")
                    or "tool"
                )
                path = str(output.get("path") or "")
                sources.append(
                    {
                        "key": f"tool:{tool}:{path}",
                        "group": f"tool:{tool}:{path or 'result'}",
                        "source_type": "tool_result",
                        "content": content[:8000],
                        "quality": 0.82,
                        "has_provenance": True,
                    }
                )

        return sources[:40]

    @staticmethod
    def _record(
        *,
        scope: str,
        mode: str,
        result: ResponseGroundingResult,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT OR REPLACE INTO response_grounding_runs(
                       request_id, scope, mode, status, applicable, overall,
                       claim_coverage, provenance_coverage, source_diversity,
                       contradiction_handling, claims_total, claims_supported,
                       claims_partial, claims_unsupported, source_groups,
                       source_types_json, warnings_json, claims_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result.request_id,
                    scope,
                    mode,
                    result.status,
                    int(result.applicable),
                    result.overall,
                    result.claim_coverage,
                    result.provenance_coverage,
                    result.source_diversity,
                    result.contradiction_handling,
                    result.claims_total,
                    result.claims_supported,
                    result.claims_partial,
                    result.claims_unsupported,
                    result.source_groups,
                    json.dumps(result.source_types, ensure_ascii=False),
                    json.dumps(result.warnings, ensure_ascii=False),
                    json.dumps(
                        [item.to_dict() for item in result.claims],
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
