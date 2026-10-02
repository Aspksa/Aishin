from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from ..db import connect


@dataclass
class Hypothesis:
    key: str
    title: str
    confidence: float
    supporting: list[str]
    opposing: list[str]
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HypothesisRun:
    mode: str
    hypotheses: list[Hypothesis]
    selected_test: dict
    stop_reason: str
    run_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "selected_test": self.selected_test,
            "stop_reason": self.stop_reason,
            "run_id": self.run_id,
        }


class HypothesisManager:
    """Maintain competing explanations without promoting one too early."""

    ACTIVE_MODES = {"VERIFY", "DIAGNOSE"}

    def evaluate(
        self,
        query: str,
        *,
        scope: str,
        mode: str,
        evidence: list[dict],
        contradictions: list[dict],
        verification: dict | None,
        causal: dict | None,
    ) -> HypothesisRun:
        if mode not in self.ACTIVE_MODES:
            run = HypothesisRun(
                mode=mode,
                hypotheses=[],
                selected_test={},
                stop_reason="mode_not_hypothesis_driven",
            )
            run.run_id = self._record(scope=scope, query=query, run=run)
            return run

        hypotheses = self._build_candidates(
            evidence=evidence,
            contradictions=contradictions,
            verification=verification,
            causal=causal,
        )
        hypotheses = self._normalize_confidence(hypotheses)

        stop_reason = self._stop_reason(hypotheses, verification=verification)
        selected_test = (
            {}
            if stop_reason
            else self._select_discriminating_test(
                hypotheses=hypotheses,
                evidence=evidence,
                verification=verification,
            )
        )

        run = HypothesisRun(
            mode=mode,
            hypotheses=hypotheses,
            selected_test=selected_test,
            stop_reason=stop_reason,
        )
        run.run_id = self._record(scope=scope, query=query, run=run)
        return run

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM hypothesis_runs
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()

        result = []
        for row in rows:
            item = dict(row)
            item["hypotheses"] = json.loads(
                item.pop("hypotheses_json") or "[]"
            )
            item["selected_test"] = json.loads(
                item.pop("selected_test_json") or "{}"
            )
            result.append(item)
        return result

    @staticmethod
    def prompt_block(run: HypothesisRun) -> str:
        if not run.hypotheses:
            return "Hypothesis Manager: конкурирующие гипотезы не требовались."

        lines = [
            "Hypothesis Manager.",
            "Не выбирай гипотезу как факт только потому, что у неё самый высокий score.",
        ]
        for item in run.hypotheses[:5]:
            lines.append(
                f"- {item.title}: confidence={item.confidence:.2f}, "
                f"status={item.status}"
            )

        if run.selected_test:
            lines.append(
                "Следующая наиболее полезная проверка: "
                f"{run.selected_test.get('title')} "
                f"(reason={run.selected_test.get('reason')})."
            )
        if run.stop_reason:
            lines.append(f"Stop rule: {run.stop_reason}.")

        return "\n".join(lines)

    def _build_candidates(
        self,
        *,
        evidence: list[dict],
        contradictions: list[dict],
        verification: dict | None,
        causal: dict | None,
    ) -> list[Hypothesis]:
        support_by_source: dict[str, list[str]] = {}
        for item in evidence:
            source = str(item.get("source") or "unknown")
            text = (
                item.get("content")
                or item.get("finding")
                or item.get("message")
                or ""
            )
            if isinstance(text, str) and text.strip():
                support_by_source.setdefault(source, []).append(text.strip()[:500])

        candidates: list[Hypothesis] = []

        source_templates = (
            ("memory", "Причина уже проявлялась в сохранённой памяти"),
            ("verification", "Проблема подтверждается результатами Verification"),
            ("planner", "Проблема связана с незавершённым планом или зависимостью"),
            ("knowledge_graph", "Проблема связана с известной структурой объектов/связей"),
        )

        for source, title in source_templates:
            support = support_by_source.get(source, [])
            if not support:
                continue
            candidates.append(
                Hypothesis(
                    key=f"source:{source}",
                    title=title,
                    confidence=min(0.75, 0.28 + 0.10 * len(support)),
                    supporting=support[:5],
                    opposing=[],
                    status="candidate",
                )
            )

        if causal:
            for index, claim in enumerate(causal.get("claims", [])[:4]):
                cause = str(claim.get("cause") or "").strip()
                effect = str(claim.get("effect") or "").strip()
                if not cause or not effect:
                    continue
                candidates.append(
                    Hypothesis(
                        key=f"causal:{index}",
                        title=f"{cause} могло привести к {effect}",
                        confidence=min(
                            0.80,
                            float(claim.get("confidence", 0.0)),
                        ),
                        supporting=[
                            str(item)[:500]
                            for item in claim.get("evidence", [])[:5]
                        ],
                        opposing=[],
                        status="candidate",
                    )
                )

        unresolved = []
        if verification:
            unresolved = [
                str(item).strip()
                for item in verification.get("unresolved", []) or []
                if str(item).strip()
            ]
        for index, item in enumerate(unresolved[:4]):
            candidates.append(
                Hypothesis(
                    key=f"unresolved:{index}",
                    title=f"Нерешённый фактор: {item[:180]}",
                    confidence=0.25,
                    supporting=[],
                    opposing=[],
                    status="candidate",
                )
            )

        if not candidates:
            candidates = [
                Hypothesis(
                    key="unknown:local",
                    title="Причина находится в локальном состоянии проекта",
                    confidence=0.34,
                    supporting=[],
                    opposing=[],
                    status="candidate",
                ),
                Hypothesis(
                    key="unknown:external",
                    title="Причина находится во внешней зависимости или провайдере",
                    confidence=0.33,
                    supporting=[],
                    opposing=[],
                    status="candidate",
                ),
                Hypothesis(
                    key="unknown:data",
                    title="Недостаточно данных или контекст интерпретирован неверно",
                    confidence=0.33,
                    supporting=[],
                    opposing=[],
                    status="candidate",
                ),
            ]

        contradiction_text = [
            str(item.get("summary") or "")[:500]
            for item in contradictions
            if str(item.get("summary") or "").strip()
        ]

        if contradiction_text:
            for candidate in candidates:
                candidate.opposing.extend(contradiction_text[:3])
                candidate.confidence = max(
                    0.05,
                    candidate.confidence - 0.08 * len(contradiction_text[:3]),
                )

        return candidates[:6]

    @staticmethod
    def _normalize_confidence(
        hypotheses: list[Hypothesis],
    ) -> list[Hypothesis]:
        total = sum(max(0.0, item.confidence) for item in hypotheses)
        if total <= 0:
            return hypotheses

        for item in hypotheses:
            item.confidence = round(
                max(0.0, min(1.0, item.confidence / total)),
                4,
            )
            if item.confidence >= 0.72 and not item.opposing:
                item.status = "leading"
            elif item.confidence <= 0.10:
                item.status = "weak"
            else:
                item.status = "candidate"

        hypotheses.sort(
            key=lambda item: item.confidence,
            reverse=True,
        )
        return hypotheses

    @staticmethod
    def _stop_reason(
        hypotheses: list[Hypothesis],
        *,
        verification: dict | None,
    ) -> str:
        if not hypotheses:
            return "no_hypotheses"

        leading = hypotheses[0]
        second = hypotheses[1] if len(hypotheses) > 1 else None
        unresolved = (
            len(verification.get("unresolved", []) or [])
            if verification
            else 0
        )

        if (
            leading.confidence >= 0.80
            and unresolved == 0
            and (second is None or leading.confidence - second.confidence >= 0.45)
        ):
            return "dominant_hypothesis_with_sufficient_margin"

        return ""

    @staticmethod
    def _select_discriminating_test(
        *,
        hypotheses: list[Hypothesis],
        evidence: list[dict],
        verification: dict | None,
    ) -> dict:
        sources = {str(item.get("source") or "") for item in evidence}
        checks = {
            str(item.get("source") or "")
            for item in (verification or {}).get("checks", []) or []
        }

        candidates = [
            {
                "key": "sensor_rescan",
                "title": "Повторно снять сенсоры и сравнить состояние",
                "reason": "Разделяет локальное runtime-состояние и устойчивую внешнюю причину.",
                "available_if": "sensors" not in checks,
                "gain": 0.72,
            },
            {
                "key": "graph_neighborhood",
                "title": "Проверить ближайшие связи Knowledge Graph",
                "reason": "Показывает, связана ли проблема с конкретным объектом или зависимостью.",
                "available_if": "knowledge_graph" not in sources,
                "gain": 0.62,
            },
            {
                "key": "memory_expansion",
                "title": "Расширить поиск похожих прошлых случаев",
                "reason": "Проверяет, повторяется ли известный паттерн.",
                "available_if": "memory" not in sources,
                "gain": 0.58,
            },
            {
                "key": "explicit_file_check",
                "title": "Проверить конкретный файл или конфигурацию",
                "reason": "Отделяет гипотезу о конфигурации от общей runtime-гипотезы.",
                "available_if": True,
                "gain": 0.66,
            },
        ]

        valid = [
            item for item in candidates
            if item.pop("available_if")
        ]
        if not valid:
            return {}

        valid.sort(key=lambda item: item["gain"], reverse=True)
        selected = valid[0]
        selected["competing_hypotheses"] = [
            item.key for item in hypotheses[:3]
        ]
        return selected

    @staticmethod
    def _record(
        *,
        scope: str,
        query: str,
        run: HypothesisRun,
    ) -> int:
        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO hypothesis_runs(
                       scope, query, mode, hypotheses_json,
                       selected_test_json, stop_reason
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    query[:1200],
                    run.mode,
                    json.dumps(
                        [item.to_dict() for item in run.hypotheses],
                        ensure_ascii=False,
                    ),
                    json.dumps(run.selected_test, ensure_ascii=False),
                    run.stop_reason,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
