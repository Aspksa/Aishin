from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from typing import Any

from ..db import connect


@dataclass
class EvolutionCycleReport:
    scope: str
    trigger: str
    generation: int
    evolution_score: float
    stability_score: float
    plasticity_score: float
    learning_velocity: float
    variants_created: int = 0
    variants_promoted: int = 0
    variants_retired: int = 0
    variants_rolled_back: int = 0
    curriculum_created: int = 0
    transfers_updated: int = 0
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "trigger": self.trigger,
            "generation": self.generation,
            "evolution_score": self.evolution_score,
            "stability_score": self.stability_score,
            "plasticity_score": self.plasticity_score,
            "learning_velocity": self.learning_velocity,
            "variants_created": self.variants_created,
            "variants_promoted": self.variants_promoted,
            "variants_retired": self.variants_retired,
            "variants_rolled_back": self.variants_rolled_back,
            "curriculum_created": self.curriculum_created,
            "transfers_updated": self.transfers_updated,
            "duration_ms": self.duration_ms,
        }


class EvolutionEngine:
    """Evidence-grounded meta-learning and bounded runtime evolution.

    Evolution never rewrites Python source, bypasses permissions, or trains the
    external model. It evolves only local routing/context policies that remain
    auditable, reversible and bounded by safety invariants.
    """

    VERSION = "aishin-evolution-engine-v1"
    FORMULA_VERSION = "bounded-meta-learning-v1"

    MODE_ORDER = {
        "FAST": 0,
        "PLAN": 1,
        "DEEP": 2,
        "VERIFY": 3,
        "DIAGNOSE": 4,
    }

    FAMILY_LABELS = {
        "documents": "Документы",
        "fuel": "ГСМ и путевые листы",
        "vehicles": "Автотранспорт",
        "timesheet": "Табель и рабочее время",
        "software": "Разработка и система",
        "diagnostics": "Диагностика",
        "planning": "Планирование",
        "analysis": "Аналитика",
        "knowledge": "Память и знания",
        "general": "Общий контекст",
    }

    def __init__(
        self,
        *,
        growth: Any,
        continuous_learning: Any,
        events: Any | None = None,
    ) -> None:
        self.growth = growth
        self.continuous_learning = continuous_learning
        self.events = events

    @staticmethod
    def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
        return max(low, min(high, float(value)))

    @staticmethod
    def _sat(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(1.0, 1.0 - math.exp(-max(0.0, float(value)) / target))

    @staticmethod
    def _mean(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

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
    def _hash_key(*parts: Any) -> str:
        raw = "|".join(str(part).strip().casefold() for part in parts)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]

    def run_cycle(
        self,
        *,
        scope: str,
        trigger: str = "manual",
    ) -> EvolutionCycleReport:
        started = time.perf_counter()
        scope = (scope or "personal").strip() or "personal"
        self._ensure_state(scope=scope)

        quality = self.continuous_learning.quality_gate.refresh(scope=scope)
        growth = self.growth.refresh(
            scope=scope,
            persist_snapshot=False,
        )

        self._refresh_capabilities(scope=scope)
        curriculum_created = self._refresh_curriculum(scope=scope)
        transfers_updated = self._refresh_transfers(scope=scope)
        variants_created = self._generate_variants(scope=scope)
        promoted, retired, rolled_back = self._evaluate_variants(scope=scope)

        previous = self.state(scope=scope)
        generation = int(previous.get("generation") or 1)
        if promoted or rolled_back:
            generation += 1

        metrics = self._calculate_state(
            scope=scope,
            generation=generation,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)

        with connect() as conn:
            conn.execute(
                """UPDATE evolution_state
                   SET generation=?,
                       evolution_score=?,
                       stability_score=?,
                       plasticity_score=?,
                       learning_velocity=?,
                       active_policy_count=?,
                       challenger_count=?,
                       rollback_count=rollback_count+?,
                       last_cycle_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (
                    generation,
                    metrics["evolution_score"],
                    metrics["stability_score"],
                    metrics["plasticity_score"],
                    metrics["learning_velocity"],
                    metrics["active_policy_count"],
                    metrics["challenger_count"],
                    rolled_back,
                    scope,
                ),
            )
            conn.execute(
                """INSERT INTO evolution_cycles(
                       scope, trigger, generation, evolution_score,
                       stability_score, plasticity_score, learning_velocity,
                       variants_created, variants_promoted, variants_retired,
                       variants_rolled_back, curriculum_created,
                       transfers_updated, duration_ms, summary_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    trigger,
                    generation,
                    metrics["evolution_score"],
                    metrics["stability_score"],
                    metrics["plasticity_score"],
                    metrics["learning_velocity"],
                    variants_created,
                    promoted,
                    retired,
                    rolled_back,
                    curriculum_created,
                    transfers_updated,
                    duration_ms,
                    json.dumps(
                        {
                            "quality_gate": quality,
                            "growth_score": growth.get("overall_score"),
                            "capabilities": metrics["capabilities"],
                            "trusted_transfers": metrics["trusted_transfers"],
                            "open_curriculum": metrics["open_curriculum"],
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            conn.commit()

        self._emit(
            "evolution.cycle.completed",
            scope=scope,
            payload={
                "trigger": trigger,
                "generation": generation,
                "evolution_score": metrics["evolution_score"],
                "stability_score": metrics["stability_score"],
                "plasticity_score": metrics["plasticity_score"],
                "learning_velocity": metrics["learning_velocity"],
                "variants_created": variants_created,
                "variants_promoted": promoted,
                "variants_rolled_back": rolled_back,
                "curriculum_created": curriculum_created,
            },
            importance=0.42 if promoted or rolled_back else 0.18,
        )

        return EvolutionCycleReport(
            scope=scope,
            trigger=trigger,
            generation=generation,
            evolution_score=metrics["evolution_score"],
            stability_score=metrics["stability_score"],
            plasticity_score=metrics["plasticity_score"],
            learning_velocity=metrics["learning_velocity"],
            variants_created=variants_created,
            variants_promoted=promoted,
            variants_retired=retired,
            variants_rolled_back=rolled_back,
            curriculum_created=curriculum_created,
            transfers_updated=transfers_updated,
            duration_ms=duration_ms,
        )

    def routing_hint(
        self,
        *,
        scope: str,
        family: str,
        base_mode: str,
        request_id: str,
        base_complexity: float,
    ) -> dict:
        """Return one bounded policy hint and persist its assignment.

        Champion policies are always eligible. Challengers receive a
        deterministic traffic slice so experiments are reproducible.
        """
        scope = (scope or "personal").strip() or "personal"
        family = family if family in self.FAMILY_LABELS else "general"
        self._ensure_state(scope=scope)

        champion = self._variant_for_family(
            scope=scope,
            family=family,
            lifecycle="champion",
        )
        challenger = self._variant_for_family(
            scope=scope,
            family=family,
            lifecycle="challenger",
        )

        variant = champion
        assignment_type = "champion" if champion else "baseline"

        if champion is None and challenger is not None:
            policy = self._json(challenger["policy_json"], {})
            fraction = self._clamp(float(policy.get("traffic_fraction") or 0.25), 0.05, 0.40)
            bucket = int(
                hashlib.sha256(
                    f"{scope}|{family}|{request_id}".encode("utf-8")
                ).hexdigest()[:8],
                16,
            ) / 0xFFFFFFFF
            if bucket < fraction:
                variant = challenger
                assignment_type = "challenger"

        capability = self._capability(scope=scope, family=family)
        baseline_fitness = float(
            (capability or {}).get("fitness") or 0.0
        )

        if variant is None:
            hint = {
                "variant_id": None,
                "variant_key": None,
                "generation": int(self.state(scope=scope).get("generation") or 1),
                "assignment_type": "baseline",
                "preferred_mode": base_mode,
                "context_multiplier": 1.0,
                "verification_bias": False,
                "policy_applied": False,
                "reason": "no_active_evolution_policy",
            }
        else:
            raw_policy = self._json(variant["policy_json"], {})
            policy = self._sanitize_policy(
                raw_policy,
                base_mode=base_mode,
                base_complexity=base_complexity,
            )
            hint = {
                "variant_id": int(variant["id"]),
                "variant_key": variant["variant_key"],
                "generation": int(variant["generation"]),
                "assignment_type": assignment_type,
                "preferred_mode": policy["preferred_mode"],
                "context_multiplier": policy["context_multiplier"],
                "verification_bias": policy["verification_bias"],
                "policy_applied": True,
                "reason": str(variant["rationale"] or ""),
            }

        with connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO evolution_assignments(
                       request_id, scope, family, variant_id,
                       assignment_type, policy_json, baseline_fitness
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    request_id,
                    scope,
                    family,
                    hint["variant_id"],
                    hint["assignment_type"],
                    json.dumps(hint, ensure_ascii=False),
                    baseline_fitness,
                ),
            )
            conn.commit()

        return hint

    def observe_outcome(
        self,
        *,
        scope: str,
        request_id: str,
        outcome_score: float,
        successful: bool,
        unresolved_count: int,
    ) -> dict:
        score = self._clamp(outcome_score)
        unresolved = max(0, int(unresolved_count))
        with connect() as conn:
            assignment = conn.execute(
                """SELECT * FROM evolution_assignments
                   WHERE scope=? AND request_id=?""",
                (scope, request_id),
            ).fetchone()
            if assignment is None:
                return {
                    "observed": False,
                    "reason": "assignment_not_found",
                }

            item = dict(assignment)
            conn.execute(
                """UPDATE evolution_assignments
                   SET outcome_score=?, successful=?, unresolved_count=?,
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    score,
                    1 if successful else 0,
                    unresolved,
                    int(item["id"]),
                ),
            )

            variant_id = item.get("variant_id")
            if variant_id is not None:
                variant = conn.execute(
                    """SELECT * FROM evolution_variants WHERE id=?""",
                    (int(variant_id),),
                ).fetchone()
                if variant is not None:
                    v = dict(variant)
                    old_n = int(v["evidence_count"] or 0)
                    old_fitness = float(v["observed_fitness"] or 0.0)
                    new_fitness = (
                        old_fitness * old_n + score
                    ) / max(1, old_n + 1)
                    conn.execute(
                        """UPDATE evolution_variants
                           SET observed_fitness=?,
                               evidence_count=evidence_count+1,
                               wins=wins+?,
                               losses=losses+?,
                               unresolved_total=unresolved_total+?,
                               updated_at=CURRENT_TIMESTAMP
                           WHERE id=?""",
                        (
                            round(new_fitness, 5),
                            1 if successful else 0,
                            0 if successful else 1,
                            unresolved,
                            int(variant_id),
                        ),
                    )
            conn.commit()

        completed = self._completed_assignment_count(scope=scope)
        cycle = None
        if completed > 0 and completed % 5 == 0:
            cycle = self.run_cycle(
                scope=scope,
                trigger="outcome_batch",
            ).to_dict()

        return {
            "observed": True,
            "request_id": request_id,
            "outcome_score": round(score, 4),
            "successful": bool(successful),
            "unresolved_count": unresolved,
            "cycle": cycle,
        }

    def dashboard(
        self,
        *,
        scope: str,
        capability_limit: int = 30,
        variant_limit: int = 50,
        curriculum_limit: int = 50,
        transfer_limit: int = 50,
        cycle_limit: int = 60,
        refresh: bool = False,
    ) -> dict:
        if refresh:
            self.run_cycle(scope=scope, trigger="dashboard")

        state = self.state(scope=scope)
        capabilities = self.capabilities(
            scope=scope,
            limit=capability_limit,
        )
        variants = self.variants(
            scope=scope,
            limit=variant_limit,
        )
        curriculum = self.curriculum(
            scope=scope,
            limit=curriculum_limit,
        )
        transfers = self.transfers(
            scope=scope,
            limit=transfer_limit,
        )
        cycles = self.cycles(scope=scope, limit=cycle_limit)

        champions = [v for v in variants if v["lifecycle"] == "champion"]
        challengers = [v for v in variants if v["lifecycle"] == "challenger"]
        regressions = [
            item
            for item in capabilities
            if float(item["trend"] or 0.0) <= -0.08
        ]
        open_curriculum = [
            item
            for item in curriculum
            if item["status"] in {"open", "active"}
        ]
        trusted_transfers = [
            item
            for item in transfers
            if item["status"] == "trusted"
        ]

        return {
            "version": self.VERSION,
            "formula_version": self.FORMULA_VERSION,
            "scope": scope,
            "summary": {
                **state,
                "champions": len(champions),
                "challengers": len(challengers),
                "regressions": len(regressions),
                "open_curriculum": len(open_curriculum),
                "trusted_transfers": len(trusted_transfers),
            },
            "capabilities": capabilities,
            "variants": variants,
            "curriculum": curriculum,
            "transfers": transfers,
            "cycles": cycles,
            "events": self.events_history(scope=scope, limit=80),
            "principles": [
                "Эволюция меняет только локальные runtime-политики, а не исходный код и не веса внешней модели.",
                "Новая политика сначала challenger и получает только ограниченную долю задач.",
                "VERIFY и DIAGNOSE никогда не понижаются эволюционным контуром.",
                "Promotion разрешён только после достаточного outcome evidence и без роста unresolved.",
                "Деградация champion вызывает rollback; отсутствие безопасного предшественника возвращает baseline.",
                "Curriculum строится из измеренных пробелов, регрессий и fading-навыков, а не из самооценки без evidence.",
                "Transfer learning считается доверенным только после повторяемого успеха в другой task family.",
                "Эволюционный score — здоровье адаптивного контура, а не IQ и не абсолютная оценка интеллекта.",
            ],
        }

    def state(self, *, scope: str) -> dict:
        self._ensure_state(scope=scope)
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM evolution_state WHERE scope=?""",
                (scope,),
            ).fetchone()
        return dict(row) if row else {
            "scope": scope,
            "generation": 1,
            "evolution_score": 0.0,
            "stability_score": 1.0,
            "plasticity_score": 0.0,
            "learning_velocity": 0.0,
            "active_policy_count": 0,
            "challenger_count": 0,
            "rollback_count": 0,
        }

    def capabilities(
        self,
        *,
        scope: str,
        limit: int = 30,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM evolution_capabilities
                   WHERE scope=?
                   ORDER BY learning_gap DESC, confidence DESC, id ASC
                   LIMIT ?""",
                (scope, max(1, min(int(limit), 200))),
            ).fetchall()
        return [dict(row) for row in rows]

    def variants(
        self,
        *,
        scope: str,
        lifecycle: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        limit = max(1, min(int(limit), 300))
        with connect() as conn:
            if lifecycle:
                rows = conn.execute(
                    """SELECT * FROM evolution_variants
                       WHERE scope=? AND lifecycle=?
                       ORDER BY updated_at DESC, id DESC LIMIT ?""",
                    (scope, lifecycle, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM evolution_variants
                       WHERE scope=?
                       ORDER BY
                         CASE lifecycle
                           WHEN 'champion' THEN 0
                           WHEN 'challenger' THEN 1
                           WHEN 'shadow' THEN 2
                           WHEN 'rolled_back' THEN 3
                           ELSE 4
                         END,
                         updated_at DESC, id DESC
                       LIMIT ?""",
                    (scope, limit),
                ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["policy"] = self._json(item.pop("policy_json"), {})
            item["auto_promotable"] = bool(item["auto_promotable"])
            result.append(item)
        return result

    def curriculum(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM evolution_curriculum
                   WHERE scope=?
                   ORDER BY
                     CASE status WHEN 'active' THEN 0 WHEN 'open' THEN 1 ELSE 2 END,
                     priority DESC, id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 300))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["plan"] = self._json(item.pop("plan_json"), {})
            result.append(item)
        return result

    def transfers(
        self,
        *,
        scope: str,
        limit: int = 50,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM evolution_transfers
                   WHERE scope=?
                   ORDER BY
                     CASE status WHEN 'trusted' THEN 0 WHEN 'observed' THEN 1 ELSE 2 END,
                     confidence DESC, evidence_count DESC, id DESC
                   LIMIT ?""",
                (scope, max(1, min(int(limit), 300))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["evidence"] = self._json(item.pop("evidence_json"), [])
            result.append(item)
        return result

    def cycles(
        self,
        *,
        scope: str,
        limit: int = 60,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM evolution_cycles
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["summary"] = self._json(item.pop("summary_json"), {})
            result.append(item)
        return result

    def events_history(
        self,
        *,
        scope: str,
        limit: int = 80,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM evolution_events
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = self._json(item.pop("details_json"), {})
            result.append(item)
        return result

    def prompt_block(self, *, scope: str) -> str:
        champions = self.variants(
            scope=scope,
            lifecycle="champion",
            limit=10,
        )
        curriculum = [
            item
            for item in self.curriculum(scope=scope, limit=20)
            if item["status"] in {"open", "active"}
        ][:5]
        lines = [
            "Evolution Engine: локальное evidence-grounded мета-обучение.",
            "Не утверждай, что модель переобучила свои веса или переписала код.",
            "Champion-политики являются ограниченными runtime-подсказками; Verification и Permission Gate имеют приоритет.",
        ]
        if champions:
            lines.append("Действующие подтверждённые adaptive policies:")
            for item in champions:
                policy = item.get("policy") or {}
                lines.append(
                    f"- {item['family']}: mode={policy.get('preferred_mode')}, "
                    f"context={float(policy.get('context_multiplier') or 1.0):.2f}, "
                    f"evidence={int(item.get('evidence_count') or 0)}."
                )
        if curriculum:
            lines.append("Текущие измеренные направления развития:")
            for item in curriculum:
                lines.append(
                    f"- {item['title']} "
                    f"(gap={float(item['gap_score']):.2f}, "
                    f"priority={float(item['priority']):.2f})."
                )
        return "\n".join(lines)

    def _ensure_state(self, *, scope: str) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO evolution_state(scope)
                   VALUES (?)""",
                (scope,),
            )
            conn.commit()

    def _refresh_capabilities(self, *, scope: str) -> int:
        changed = 0
        with connect() as conn:
            all_rows = conn.execute(
                """SELECT task_family, outcome_score, successful,
                          unresolved_count, completed_at
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND outcome_score IS NOT NULL
                   ORDER BY id DESC LIMIT 1200""",
                (scope,),
            ).fetchall()

        grouped: dict[str, list[dict]] = {
            family: [] for family in self.FAMILY_LABELS
        }
        for row in all_rows:
            item = dict(row)
            family = str(item.get("task_family") or "general")
            grouped.setdefault(family, []).append(item)

        for family, label in self.FAMILY_LABELS.items():
            rows = grouped.get(family, [])
            outcomes = [float(row["outcome_score"] or 0.0) for row in rows]
            sample_count = len(rows)
            successes = sum(int(row["successful"] or 0) for row in rows)
            unresolved_cases = sum(
                1 for row in rows if int(row["unresolved_count"] or 0) > 0
            )
            success_rate = (
                successes / sample_count if sample_count else 0.0
            )
            unresolved_rate = (
                unresolved_cases / sample_count if sample_count else 0.0
            )
            average = self._mean(outcomes)

            recent_rows = rows[: min(5, sample_count)]
            baseline_rows = rows[
                min(5, sample_count): min(20, sample_count)
            ]
            recent = self._mean(
                [float(row["outcome_score"] or 0.0) for row in recent_rows]
            )
            baseline = (
                self._mean(
                    [
                        float(row["outcome_score"] or 0.0)
                        for row in baseline_rows
                    ]
                )
                if baseline_rows
                else average
            )
            trend = recent - baseline if sample_count >= 4 else 0.0
            confidence = self._sat(sample_count, 12.0)
            raw_fitness = self._clamp(
                0.55 * average
                + 0.27 * success_rate
                + 0.18 * (1.0 - unresolved_rate)
            )
            fitness = raw_fitness * (0.65 + 0.35 * confidence)
            gap = self._clamp(
                1.0
                - fitness
                + max(0.0, -trend) * 0.35
                + unresolved_rate * 0.15
            )
            last_evidence = (
                rows[0].get("completed_at") if rows else None
            )

            with connect() as conn:
                old = conn.execute(
                    """SELECT fitness, trend, learning_gap
                       FROM evolution_capabilities
                       WHERE scope=? AND capability_key=?""",
                    (scope, f"family:{family}"),
                ).fetchone()
                conn.execute(
                    """INSERT INTO evolution_capabilities(
                           scope, capability_key, label, family,
                           sample_count, success_rate, unresolved_rate,
                           average_outcome, recent_outcome, baseline_outcome,
                           trend, confidence, learning_gap, fitness,
                           last_evidence_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(scope, capability_key) DO UPDATE SET
                           label=excluded.label,
                           family=excluded.family,
                           sample_count=excluded.sample_count,
                           success_rate=excluded.success_rate,
                           unresolved_rate=excluded.unresolved_rate,
                           average_outcome=excluded.average_outcome,
                           recent_outcome=excluded.recent_outcome,
                           baseline_outcome=excluded.baseline_outcome,
                           trend=excluded.trend,
                           confidence=excluded.confidence,
                           learning_gap=excluded.learning_gap,
                           fitness=excluded.fitness,
                           last_evidence_at=excluded.last_evidence_at,
                           updated_at=CURRENT_TIMESTAMP""",
                    (
                        scope,
                        f"family:{family}",
                        label,
                        family,
                        sample_count,
                        round(success_rate, 5),
                        round(unresolved_rate, 5),
                        round(average, 5),
                        round(recent, 5),
                        round(baseline, 5),
                        round(trend, 5),
                        round(confidence, 5),
                        round(gap, 5),
                        round(fitness, 5),
                        last_evidence,
                    ),
                )
                conn.commit()

            if old is None or abs(
                float(old["fitness"] or 0.0) - fitness
            ) >= 0.03 or abs(
                float(old["trend"] or 0.0) - trend
            ) >= 0.05:
                changed += 1

        return changed

    def _refresh_curriculum(self, *, scope: str) -> int:
        active_keys: set[str] = set()
        created = 0
        capabilities = self.capabilities(scope=scope, limit=100)

        for item in capabilities:
            samples = int(item["sample_count"] or 0)
            gap = float(item["learning_gap"] or 0.0)
            trend = float(item["trend"] or 0.0)
            unresolved = float(item["unresolved_rate"] or 0.0)
            if samples < 3:
                continue
            if gap < 0.28 and trend > -0.06 and unresolved < 0.12:
                continue

            family = str(item["family"])
            key = f"family:{family}"
            active_keys.add(key)
            priority = self._clamp(
                0.48 * gap
                + 0.27 * float(item["confidence"] or 0.0)
                + 0.15 * min(1.0, unresolved * 3.0)
                + 0.10 * min(1.0, max(0.0, -trend) * 4.0)
            )
            plan = {
                "family": family,
                "objectives": [
                    "увеличить outcome quality на подтверждённых задачах",
                    "снизить unresolved rate",
                    "стабилизировать recent outcome относительно baseline",
                ],
                "recommended_actions": self._curriculum_actions(item),
                "completion": {
                    "fitness_gte": 0.78,
                    "unresolved_rate_lte": 0.10,
                    "negative_trend_gt": -0.04,
                },
            }
            if self._upsert_curriculum(
                scope=scope,
                item_key=key,
                target_type="task_family",
                target_key=family,
                title=f"Укрепить область «{item['label']}»",
                reason=(
                    f"fitness={float(item['fitness']):.2f}, "
                    f"gap={gap:.2f}, trend={trend:+.2f}, "
                    f"unresolved={unresolved:.2f}"
                ),
                priority=priority,
                gap_score=gap,
                expected_metric="family_fitness",
                progress=self._clamp(float(item["fitness"] or 0.0)),
                evidence_count=samples,
                plan=plan,
            ):
                created += 1
            self._mirror_learning_plan(
                scope=scope,
                item_key=key,
                title=f"Evolution · {item['label']}",
                reason=(
                    f"Measured family gap {gap:.2f}; "
                    f"trend {trend:+.2f}; unresolved {unresolved:.2f}"
                ),
                priority=priority,
                evidence={
                    "family": family,
                    "fitness": item["fitness"],
                    "sample_count": samples,
                    "trend": trend,
                },
            )

        with connect() as conn:
            skills = conn.execute(
                """SELECT id, skill_key, title, lifecycle, mastery_score,
                          reliability, evidence_count, freshness, stability
                   FROM growth_skills
                   WHERE scope=?
                     AND evidence_count >= 3
                     AND (
                       lifecycle='fading'
                       OR mastery_score < 62
                       OR freshness < 0.55
                     )
                   ORDER BY mastery_score ASC, evidence_count DESC
                   LIMIT 80""",
                (scope,),
            ).fetchall()

        for row in skills:
            skill = dict(row)
            key = f"skill:{skill['skill_key']}"
            active_keys.add(key)
            mastery = self._clamp(
                float(skill["mastery_score"] or 0.0) / 100.0
            )
            freshness = self._clamp(float(skill["freshness"] or 0.0))
            reliability = self._clamp(float(skill["reliability"] or 0.0))
            gap = self._clamp(
                0.50 * (1.0 - mastery)
                + 0.30 * (1.0 - freshness)
                + 0.20 * (1.0 - reliability)
            )
            priority = self._clamp(0.45 + 0.45 * gap)
            plan = {
                "skill_id": int(skill["id"]),
                "skill_key": skill["skill_key"],
                "objectives": [
                    "получить новое подтверждённое evidence",
                    "проверить переносимость навыка",
                    "восстановить freshness без искусственного повышения mastery",
                ],
                "completion": {
                    "mastery_gte": 70,
                    "freshness_gte": 0.65,
                    "lifecycle_in": ["established", "mastered"],
                },
            }
            if self._upsert_curriculum(
                scope=scope,
                item_key=key,
                target_type="skill",
                target_key=str(skill["skill_key"]),
                title=f"Укрепить навык «{skill['title']}»",
                reason=(
                    f"lifecycle={skill['lifecycle']}, "
                    f"mastery={float(skill['mastery_score']):.1f}, "
                    f"freshness={freshness:.2f}"
                ),
                priority=priority,
                gap_score=gap,
                expected_metric="skill_mastery_and_freshness",
                progress=self._clamp(
                    0.60 * mastery + 0.40 * freshness
                ),
                evidence_count=int(float(skill["evidence_count"] or 0.0)),
                plan=plan,
            ):
                created += 1

        with connect() as conn:
            rows = conn.execute(
                """SELECT id, item_key FROM evolution_curriculum
                   WHERE scope=? AND status IN ('open','active')""",
                (scope,),
            ).fetchall()
            for row in rows:
                key = str(row["item_key"])
                if key in active_keys:
                    continue
                conn.execute(
                    """UPDATE evolution_curriculum
                       SET status='completed', progress=1.0,
                           completed_at=CURRENT_TIMESTAMP,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (int(row["id"]),),
                )
            conn.commit()

        return created

    def _upsert_curriculum(
        self,
        *,
        scope: str,
        item_key: str,
        target_type: str,
        target_key: str,
        title: str,
        reason: str,
        priority: float,
        gap_score: float,
        expected_metric: str,
        progress: float,
        evidence_count: int,
        plan: dict,
    ) -> bool:
        with connect() as conn:
            old = conn.execute(
                """SELECT id, status FROM evolution_curriculum
                   WHERE scope=? AND item_key=?""",
                (scope, item_key),
            ).fetchone()
            conn.execute(
                """INSERT INTO evolution_curriculum(
                       scope, item_key, target_type, target_key, title,
                       reason, priority, gap_score, expected_metric,
                       status, plan_json, progress, evidence_count
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                   ON CONFLICT(scope, item_key) DO UPDATE SET
                       target_type=excluded.target_type,
                       target_key=excluded.target_key,
                       title=excluded.title,
                       reason=excluded.reason,
                       priority=excluded.priority,
                       gap_score=excluded.gap_score,
                       expected_metric=excluded.expected_metric,
                       status=CASE
                         WHEN evolution_curriculum.status='completed'
                         THEN 'open'
                         ELSE evolution_curriculum.status
                       END,
                       plan_json=excluded.plan_json,
                       progress=excluded.progress,
                       evidence_count=excluded.evidence_count,
                       completed_at=NULL,
                       updated_at=CURRENT_TIMESTAMP""",
                (
                    scope,
                    item_key,
                    target_type,
                    target_key,
                    title,
                    reason,
                    round(priority, 5),
                    round(gap_score, 5),
                    expected_metric,
                    json.dumps(plan, ensure_ascii=False),
                    round(progress, 5),
                    int(evidence_count),
                ),
            )
            conn.commit()
        return old is None or str(old["status"]) == "completed"

    def _mirror_learning_plan(
        self,
        *,
        scope: str,
        item_key: str,
        title: str,
        reason: str,
        priority: float,
        evidence: dict,
    ) -> None:
        if priority < 0.58:
            return
        metric = f"evolution:{item_key}"
        with connect() as conn:
            existing = conn.execute(
                """SELECT id FROM learning_plans
                   WHERE scope=? AND target_metric=? AND status='open'
                   ORDER BY id DESC LIMIT 1""",
                (scope, metric),
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE learning_plans
                       SET priority=?, rationale=?, evidence_json=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        round(priority, 5),
                        reason,
                        json.dumps([evidence], ensure_ascii=False),
                        int(existing["id"]),
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO learning_plans(
                           scope, topic, rationale, priority, status,
                           target_metric, evidence_json
                       ) VALUES (?, ?, ?, ?, 'open', ?, ?)""",
                    (
                        scope,
                        title,
                        reason,
                        round(priority, 5),
                        metric,
                        json.dumps([evidence], ensure_ascii=False),
                    ),
                )
            conn.commit()

    def _refresh_transfers(self, *, scope: str) -> int:
        with connect() as conn:
            rows = conn.execute(
                """SELECT id, task_family, selected_skill_ids_json,
                          transfer_used, transfer_skill_ids_json,
                          outcome_score, successful, unresolved_count,
                          completed_at
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND outcome_score IS NOT NULL
                   ORDER BY id ASC LIMIT 2000""",
                (scope,),
            ).fetchall()

        source_map: dict[int, set[str]] = {}
        for row in rows:
            if not int(row["successful"] or 0):
                continue
            family = str(row["task_family"] or "general")
            for skill_id in self._json(
                row["selected_skill_ids_json"],
                [],
            ):
                try:
                    sid = int(skill_id)
                except (TypeError, ValueError):
                    continue
                source_map.setdefault(sid, set()).add(family)

        aggregated: dict[str, dict] = {}
        for row in rows:
            if not int(row["transfer_used"] or 0):
                continue
            target = str(row["task_family"] or "general")
            transfer_ids = self._json(
                row["transfer_skill_ids_json"],
                [],
            )
            for raw_id in transfer_ids:
                try:
                    skill_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                sources = sorted(
                    family
                    for family in source_map.get(skill_id, set())
                    if family != target
                )
                for source in sources:
                    key = f"{source}->{target}:skill:{skill_id}"
                    item = aggregated.setdefault(
                        key,
                        {
                            "source": source,
                            "target": target,
                            "skill_id": skill_id,
                            "evidence": 0,
                            "successes": 0,
                            "failures": 0,
                            "rows": [],
                        },
                    )
                    item["evidence"] += 1
                    if int(row["successful"] or 0):
                        item["successes"] += 1
                    else:
                        item["failures"] += 1
                    if len(item["rows"]) < 8:
                        item["rows"].append(
                            {
                                "route_id": int(row["id"]),
                                "outcome_score": float(
                                    row["outcome_score"] or 0.0
                                ),
                                "successful": bool(row["successful"]),
                                "unresolved_count": int(
                                    row["unresolved_count"] or 0
                                ),
                            }
                        )

        updated = 0
        for key, item in aggregated.items():
            evidence = int(item["evidence"])
            successes = int(item["successes"])
            failures = int(item["failures"])
            success_rate = successes / max(1, evidence)
            confidence = self._clamp(
                self._sat(evidence, 6.0)
                * (0.55 + 0.45 * success_rate)
            )
            if evidence >= 6 and success_rate >= 0.78:
                status = "trusted"
            elif evidence >= 2:
                status = "observed"
            else:
                status = "candidate"
            with connect() as conn:
                old = conn.execute(
                    """SELECT evidence_count, status, success_rate
                       FROM evolution_transfers
                       WHERE scope=? AND transfer_key=?""",
                    (scope, key),
                ).fetchone()
                conn.execute(
                    """INSERT INTO evolution_transfers(
                           scope, transfer_key, source_family, target_family,
                           skill_id, confidence, evidence_count, successes,
                           failures, success_rate, status, evidence_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(scope, transfer_key) DO UPDATE SET
                           source_family=excluded.source_family,
                           target_family=excluded.target_family,
                           skill_id=excluded.skill_id,
                           confidence=excluded.confidence,
                           evidence_count=excluded.evidence_count,
                           successes=excluded.successes,
                           failures=excluded.failures,
                           success_rate=excluded.success_rate,
                           status=excluded.status,
                           evidence_json=excluded.evidence_json,
                           updated_at=CURRENT_TIMESTAMP""",
                    (
                        scope,
                        key,
                        item["source"],
                        item["target"],
                        item["skill_id"],
                        round(confidence, 5),
                        evidence,
                        successes,
                        failures,
                        round(success_rate, 5),
                        status,
                        json.dumps(item["rows"], ensure_ascii=False),
                    ),
                )
                conn.commit()
            if old is None or int(old["evidence_count"] or 0) != evidence or str(old["status"]) != status:
                updated += 1
        return updated

    def _generate_variants(self, *, scope: str) -> int:
        created = 0
        generation = int(self.state(scope=scope).get("generation") or 1)
        capabilities = self.capabilities(scope=scope, limit=100)

        with connect() as conn:
            mode_rows = conn.execute(
                """SELECT task_family, adapted_mode,
                          COUNT(*) AS samples,
                          AVG(outcome_score) AS avg_outcome,
                          AVG(CASE WHEN successful=1 THEN 1.0 ELSE 0.0 END)
                              AS success_rate,
                          AVG(CASE WHEN unresolved_count>0 THEN 1.0 ELSE 0.0 END)
                              AS unresolved_rate
                   FROM cognitive_intelligence_routes
                   WHERE scope=? AND outcome_score IS NOT NULL
                   GROUP BY task_family, adapted_mode""",
                (scope,),
            ).fetchall()

        mode_stats: dict[str, list[dict]] = {}
        for row in mode_rows:
            mode_stats.setdefault(
                str(row["task_family"] or "general"),
                [],
            ).append(dict(row))

        for cap in capabilities:
            family = str(cap["family"])
            samples = int(cap["sample_count"] or 0)
            if samples < 4:
                continue
            if self._variant_for_family(
                scope=scope,
                family=family,
                lifecycle="challenger",
            ) is not None:
                continue

            policy = self._candidate_policy(
                capability=cap,
                modes=mode_stats.get(family, []),
            )
            if policy is None:
                continue

            variant_key = (
                f"{family}:"
                + self._hash_key(
                    family,
                    json.dumps(policy, sort_keys=True),
                    generation,
                )
            )
            baseline = float(cap["fitness"] or 0.0)
            with connect() as conn:
                old = conn.execute(
                    """SELECT id FROM evolution_variants
                       WHERE scope=? AND variant_key=?""",
                    (scope, variant_key),
                ).fetchone()
                if old:
                    continue
                conn.execute(
                    """INSERT INTO evolution_variants(
                           scope, family, variant_key, generation,
                           parent_variant_id, lifecycle, policy_json,
                           rationale, baseline_fitness, auto_promotable
                       ) VALUES (?, ?, ?, ?, ?, 'challenger', ?, ?, ?, 1)""",
                    (
                        scope,
                        family,
                        variant_key,
                        generation,
                        self._champion_id(scope=scope, family=family),
                        json.dumps(policy, ensure_ascii=False),
                        policy["rationale"],
                        round(baseline, 5),
                    ),
                )
                conn.commit()
            created += 1
            self._record_event(
                scope=scope,
                event_type="challenger_created",
                subject_type="variant",
                subject_key=variant_key,
                generation=generation,
                score=baseline,
                details={
                    "family": family,
                    "policy": policy,
                    "baseline_fitness": baseline,
                },
            )
        return created

    def _candidate_policy(
        self,
        *,
        capability: dict,
        modes: list[dict],
    ) -> dict | None:
        fitness = float(capability["fitness"] or 0.0)
        unresolved = float(capability["unresolved_rate"] or 0.0)
        trend = float(capability["trend"] or 0.0)
        average = float(capability["average_outcome"] or 0.0)

        preferred_mode = None
        verification_bias = False
        context_multiplier = 1.0
        reasons: list[str] = []

        best_mode = None
        eligible = [
            item
            for item in modes
            if int(item.get("samples") or 0) >= 3
        ]
        if eligible:
            eligible.sort(
                key=lambda item: (
                    float(item.get("avg_outcome") or 0.0)
                    + 0.15 * float(item.get("success_rate") or 0.0)
                    - 0.12 * float(item.get("unresolved_rate") or 0.0)
                ),
                reverse=True,
            )
            best_mode = str(eligible[0].get("adapted_mode") or "FAST")

        if unresolved >= 0.18:
            preferred_mode = "VERIFY"
            verification_bias = True
            context_multiplier = 1.12
            reasons.append("high_unresolved_rate")
        elif trend <= -0.08:
            preferred_mode = "DEEP"
            context_multiplier = 1.10
            reasons.append("negative_recent_trend")
        elif fitness < 0.64 or average < 0.68:
            preferred_mode = (
                best_mode
                if best_mode in {"DEEP", "VERIFY", "DIAGNOSE"}
                else "DEEP"
            )
            context_multiplier = 1.08
            reasons.append("low_family_fitness")
        elif (
            fitness >= 0.82
            and unresolved <= 0.04
            and trend >= -0.02
        ):
            preferred_mode = None
            context_multiplier = 0.95
            reasons.append("stable_high_quality_efficiency_trial")
        else:
            return None

        return {
            "preferred_mode": preferred_mode,
            "verification_bias": verification_bias,
            "context_multiplier": round(context_multiplier, 3),
            "traffic_fraction": 0.25,
            "min_samples": 6,
            "max_unresolved_rate": 0.12,
            "min_gain": 0.04,
            "rationale": ",".join(reasons),
        }

    def _evaluate_variants(
        self,
        *,
        scope: str,
    ) -> tuple[int, int, int]:
        promoted = 0
        retired = 0
        rolled_back = 0
        variants = self.variants(scope=scope, limit=300)

        for item in variants:
            lifecycle = str(item["lifecycle"])
            evidence = int(item["evidence_count"] or 0)
            if lifecycle == "challenger":
                policy = item.get("policy") or {}
                min_samples = max(5, int(policy.get("min_samples") or 6))
                if evidence < min_samples:
                    continue
                observed = float(item["observed_fitness"] or 0.0)
                baseline = float(item["baseline_fitness"] or 0.0)
                wins = int(item["wins"] or 0)
                unresolved_total = int(item["unresolved_total"] or 0)
                win_rate = wins / max(1, evidence)
                unresolved_rate = unresolved_total / max(1, evidence)
                gain = observed - baseline
                min_gain = float(policy.get("min_gain") or 0.04)
                max_unresolved = float(
                    policy.get("max_unresolved_rate") or 0.12
                )

                if (
                    bool(item["auto_promotable"])
                    and gain >= min_gain
                    and win_rate >= 0.65
                    and unresolved_rate <= max_unresolved
                ):
                    self._promote_variant(
                        scope=scope,
                        variant=item,
                        gain=gain,
                        win_rate=win_rate,
                        unresolved_rate=unresolved_rate,
                    )
                    promoted += 1
                elif (
                    gain <= -0.05
                    or unresolved_rate >= 0.25
                    or (evidence >= min_samples * 2 and win_rate < 0.55)
                ):
                    self._retire_variant(
                        scope=scope,
                        variant=item,
                        reason="challenger_underperformed",
                        score=observed,
                    )
                    retired += 1

            elif lifecycle == "champion" and evidence >= 6:
                regression = self._champion_regression(
                    scope=scope,
                    variant_id=int(item["id"]),
                )
                if regression["should_rollback"]:
                    self._rollback_champion(
                        scope=scope,
                        variant=item,
                        regression=regression,
                    )
                    rolled_back += 1

        return promoted, retired, rolled_back

    def _promote_variant(
        self,
        *,
        scope: str,
        variant: dict,
        gain: float,
        win_rate: float,
        unresolved_rate: float,
    ) -> None:
        family = str(variant["family"])
        with connect() as conn:
            conn.execute(
                """UPDATE evolution_variants
                   SET lifecycle='retired', retired_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=? AND family=? AND lifecycle='champion'
                     AND id<>?""",
                (scope, family, int(variant["id"])),
            )
            conn.execute(
                """UPDATE evolution_variants
                   SET lifecycle='champion',
                       promoted_at=CURRENT_TIMESTAMP,
                       retired_at=NULL,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (int(variant["id"]),),
            )
            conn.commit()
        self._record_event(
            scope=scope,
            event_type="variant_promoted",
            subject_type="variant",
            subject_key=str(variant["variant_key"]),
            generation=int(variant["generation"]),
            score=float(variant["observed_fitness"] or 0.0),
            details={
                "family": family,
                "gain": round(gain, 5),
                "win_rate": round(win_rate, 5),
                "unresolved_rate": round(unresolved_rate, 5),
            },
        )

    def _retire_variant(
        self,
        *,
        scope: str,
        variant: dict,
        reason: str,
        score: float,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """UPDATE evolution_variants
                   SET lifecycle='retired',
                       retired_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (int(variant["id"]),),
            )
            conn.commit()
        self._record_event(
            scope=scope,
            event_type="variant_retired",
            subject_type="variant",
            subject_key=str(variant["variant_key"]),
            generation=int(variant["generation"]),
            score=score,
            details={"reason": reason, "family": variant["family"]},
        )

    def _champion_regression(
        self,
        *,
        scope: str,
        variant_id: int,
    ) -> dict:
        with connect() as conn:
            rows = conn.execute(
                """SELECT outcome_score, successful, unresolved_count
                   FROM evolution_assignments
                   WHERE scope=? AND variant_id=?
                     AND outcome_score IS NOT NULL
                   ORDER BY id DESC LIMIT 20""",
                (scope, variant_id),
            ).fetchall()
        if len(rows) < 6:
            return {
                "should_rollback": False,
                "samples": len(rows),
            }

        recent = rows[:5]
        older = rows[5:15]
        recent_score = self._mean(
            [float(row["outcome_score"] or 0.0) for row in recent]
        )
        older_score = (
            self._mean(
                [float(row["outcome_score"] or 0.0) for row in older]
            )
            if older
            else recent_score
        )
        recent_unresolved = sum(
            1 for row in recent if int(row["unresolved_count"] or 0) > 0
        ) / len(recent)
        recent_success = sum(
            int(row["successful"] or 0) for row in recent
        ) / len(recent)

        return {
            "should_rollback": (
                recent_score <= older_score - 0.10
                or recent_unresolved >= 0.30
                or recent_success <= 0.40
            ),
            "samples": len(rows),
            "recent_score": round(recent_score, 5),
            "older_score": round(older_score, 5),
            "recent_unresolved_rate": round(recent_unresolved, 5),
            "recent_success_rate": round(recent_success, 5),
        }

    def _rollback_champion(
        self,
        *,
        scope: str,
        variant: dict,
        regression: dict,
    ) -> None:
        family = str(variant["family"])
        with connect() as conn:
            previous = conn.execute(
                """SELECT id, variant_key FROM evolution_variants
                   WHERE scope=? AND family=? AND lifecycle='retired'
                     AND promoted_at IS NOT NULL
                     AND id<>?
                   ORDER BY promoted_at DESC, id DESC LIMIT 1""",
                (scope, family, int(variant["id"])),
            ).fetchone()
            conn.execute(
                """UPDATE evolution_variants
                   SET lifecycle='rolled_back',
                       retired_at=CURRENT_TIMESTAMP,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (int(variant["id"]),),
            )
            restored = None
            if previous is not None:
                conn.execute(
                    """UPDATE evolution_variants
                       SET lifecycle='champion',
                           retired_at=NULL,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (int(previous["id"]),),
                )
                restored = str(previous["variant_key"])
            conn.commit()

        self._record_event(
            scope=scope,
            event_type="champion_rolled_back",
            subject_type="variant",
            subject_key=str(variant["variant_key"]),
            generation=int(variant["generation"]),
            score=float(variant["observed_fitness"] or 0.0),
            details={
                "family": family,
                "regression": regression,
                "restored_variant": restored,
                "fallback": "baseline" if restored is None else "previous_champion",
            },
        )

    def _calculate_state(
        self,
        *,
        scope: str,
        generation: int,
    ) -> dict:
        capabilities = self.capabilities(scope=scope, limit=100)
        variants = self.variants(scope=scope, limit=300)
        curriculum = self.curriculum(scope=scope, limit=300)
        transfers = self.transfers(scope=scope, limit=300)

        confident = [
            item
            for item in capabilities
            if int(item["sample_count"] or 0) >= 3
        ]
        avg_fitness = self._mean(
            [float(item["fitness"] or 0.0) for item in confident]
        )
        if not confident:
            avg_fitness = 0.0

        negative_trends = [
            abs(min(0.0, float(item["trend"] or 0.0)))
            for item in confident
        ]
        avg_regression = self._mean(negative_trends)
        champion_count = sum(
            1 for item in variants if item["lifecycle"] == "champion"
        )
        challenger_count = sum(
            1 for item in variants if item["lifecycle"] == "challenger"
        )
        rollback_recent = sum(
            1
            for item in self.events_history(scope=scope, limit=40)
            if item["event_type"] == "champion_rolled_back"
        )
        stability = self._clamp(
            1.0
            - min(0.55, avg_regression * 2.4)
            - min(0.25, rollback_recent * 0.04)
        )

        open_curriculum = [
            item
            for item in curriculum
            if item["status"] in {"open", "active"}
        ]
        curriculum_progress = self._mean(
            [float(item["progress"] or 0.0) for item in open_curriculum]
        ) if open_curriculum else 1.0

        trusted_transfers = sum(
            1 for item in transfers if item["status"] == "trusted"
        )
        transfer_signal = self._sat(trusted_transfers, 8.0)
        plasticity = self._clamp(
            0.35 * self._sat(challenger_count, 4.0)
            + 0.35 * self._sat(len(open_curriculum), 10.0)
            + 0.30 * transfer_signal
        )

        positive_trend = self._mean(
            [max(0.0, float(item["trend"] or 0.0)) for item in confident]
        )
        learning_velocity = self._clamp(
            0.60 * min(1.0, positive_trend * 5.0)
            + 0.25 * transfer_signal
            + 0.15 * (1.0 - curriculum_progress)
        )

        evidence_confidence = self._mean(
            [float(item["confidence"] or 0.0) for item in confident]
        )
        evolution_score = 100.0 * self._clamp(
            0.42 * avg_fitness
            + 0.24 * stability
            + 0.14 * transfer_signal
            + 0.12 * evidence_confidence
            + 0.08 * learning_velocity
        )

        return {
            "generation": generation,
            "evolution_score": round(evolution_score, 1),
            "stability_score": round(stability * 100.0, 1),
            "plasticity_score": round(plasticity * 100.0, 1),
            "learning_velocity": round(learning_velocity * 100.0, 1),
            "active_policy_count": champion_count,
            "challenger_count": challenger_count,
            "capabilities": len(capabilities),
            "trusted_transfers": trusted_transfers,
            "open_curriculum": len(open_curriculum),
        }

    def _sanitize_policy(
        self,
        policy: dict,
        *,
        base_mode: str,
        base_complexity: float,
    ) -> dict:
        base_mode = (
            base_mode if base_mode in self.MODE_ORDER else "FAST"
        )
        preferred = policy.get("preferred_mode")
        if preferred not in self.MODE_ORDER:
            preferred = base_mode

        # Evolution may never reduce reasoning rigor.
        if self.MODE_ORDER[preferred] < self.MODE_ORDER[base_mode]:
            preferred = base_mode

        verification_bias = bool(policy.get("verification_bias"))
        if verification_bias and base_mode != "DIAGNOSE":
            if self.MODE_ORDER[preferred] < self.MODE_ORDER["VERIFY"]:
                preferred = "VERIFY"

        if base_mode in {"VERIFY", "DIAGNOSE"}:
            preferred = base_mode

        multiplier = self._clamp(
            float(policy.get("context_multiplier") or 1.0),
            0.90,
            1.20,
        )
        if base_complexity >= 0.75:
            multiplier = max(multiplier, 1.0)
        if base_mode in {"VERIFY", "DIAGNOSE"}:
            multiplier = max(multiplier, 1.0)

        return {
            "preferred_mode": preferred,
            "context_multiplier": round(multiplier, 3),
            "verification_bias": verification_bias,
        }

    def _variant_for_family(
        self,
        *,
        scope: str,
        family: str,
        lifecycle: str,
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM evolution_variants
                   WHERE scope=? AND family=? AND lifecycle=?
                   ORDER BY updated_at DESC, id DESC LIMIT 1""",
                (scope, family, lifecycle),
            ).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["policy"] = self._json(item["policy_json"], {})
        return item

    def _champion_id(self, *, scope: str, family: str) -> int | None:
        item = self._variant_for_family(
            scope=scope,
            family=family,
            lifecycle="champion",
        )
        return int(item["id"]) if item else None

    def _capability(self, *, scope: str, family: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM evolution_capabilities
                   WHERE scope=? AND capability_key=?""",
                (scope, f"family:{family}"),
            ).fetchone()
        return dict(row) if row else None

    def _completed_assignment_count(self, *, scope: str) -> int:
        with connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS total FROM evolution_assignments
                   WHERE scope=? AND completed_at IS NOT NULL""",
                (scope,),
            ).fetchone()
        return int(row["total"] or 0) if row else 0

    @staticmethod
    def _curriculum_actions(capability: dict) -> list[str]:
        actions = []
        if float(capability["unresolved_rate"] or 0.0) >= 0.12:
            actions.append(
                "усилить Verification и evidence coverage для этой family"
            )
        if float(capability["trend"] or 0.0) <= -0.06:
            actions.append(
                "сравнить последние маршруты с историческим baseline"
            )
        if float(capability["success_rate"] or 0.0) < 0.70:
            actions.append(
                "проверить стратегии с лучшим подтверждённым outcome"
            )
        if not actions:
            actions.append(
                "накапливать новые outcome samples без искусственной promotion"
            )
        return actions

    def _record_event(
        self,
        *,
        scope: str,
        event_type: str,
        subject_type: str,
        subject_key: str,
        generation: int,
        score: float | None,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO evolution_events(
                       scope, event_type, subject_type, subject_key,
                       generation, score, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope,
                    event_type,
                    subject_type,
                    subject_key,
                    generation,
                    score,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
        self._emit(
            f"evolution.{event_type}",
            scope=scope,
            payload={
                "subject_type": subject_type,
                "subject_key": subject_key,
                "generation": generation,
                "score": score,
                **details,
            },
            importance=0.55 if "promoted" in event_type or "rollback" in event_type else 0.28,
        )

    def _emit(
        self,
        event_type: str,
        *,
        scope: str,
        payload: dict,
        importance: float,
    ) -> None:
        if self.events is None:
            return
        try:
            self.events.emit(
                event_type,
                scope=scope,
                payload=payload,
                importance=importance,
            )
        except Exception:
            return
