from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from ..db import connect
from ..personality import personality


@dataclass
class CommunicationPlan:
    turn_id: int
    request_id: str
    scope: str
    communication_intent: str
    user_need: str
    strategy: str
    depth: str
    tone: str
    explanation_style: str
    address_policy: str
    user_signals: dict
    persona_runtime: dict
    recent_openers: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class CommunicationIntelligenceEngine:
    """Adaptive dialogue control for Aishin.

    The engine stores observable communication choices and outcomes. It does
    not store private chain-of-thought. User-state fields are explicitly
    treated as conversational signals, not claims about the user's emotions.
    """

    VERSION = "aishin-communication-intelligence-v1"
    FORMULA_VERSION = "adaptive-dialogue-quality-v1"

    SKILLS = {
        "concise_answer": "Краткий и точный ответ",
        "complex_explanation": "Объяснение сложного",
        "clarification_recovery": "Восстановление после непонимания",
        "respectful_correction": "Мягкое несогласие и исправление",
        "uncertainty_communication": "Работа с неопределённостью",
        "project_collaboration": "Совместное проектирование",
        "personal_warmth": "Тёплое личное общение",
        "proactive_warning": "Предупреждение о рисках",
    }

    NEGATIVE_CUES = (
        "не понял",
        "не понимаю",
        "непонятно",
        "объясни проще",
        "объясни нормально",
        "что это значит",
        "не это",
        "не так",
        "ты не поняла",
        "ты меня не поняла",
        "неправильно",
        "ошиблась",
        "ошибка в ответе",
    )
    POSITIVE_CUES = (
        "теперь понял",
        "понятно",
        "спасибо",
        "отлично",
        "супер",
        "именно",
        "так лучше",
        "всё ясно",
        "все ясно",
        "получилось",
        "правильно",
    )
    FRUSTRATION_CUES = (
        "сколько можно",
        "опять",
        "снова не",
        "почему ты",
        "ты завис",
        "зависла",
        "бесит",
        "не работает",
    )
    URGENCY_CUES = (
        "срочно",
        "быстро",
        "сразу",
        "без лишнего",
        "вкратце",
        "кратко",
        "короче",
    )
    FATIGUE_CUES = (
        "устал",
        "устала",
        "потом",
        "хватит",
        "на сегодня",
        "спать",
        "отдыхать",
    )
    PERSONAL_CUES = (
        "любишь",
        "любов",
        "верна",
        "предан",
        "скучала",
        "чувствуешь",
        "между нами",
        "рядом со мной",
    )
    WARNING_CUES = (
        "риск",
        "опас",
        "ошибка",
        "слом",
        "противореч",
        "потер",
        "удал",
    )
    EXPERT_CUES = (
        "профессионально",
        "максимально",
        "подробно",
        "полностью",
        "самое крупное",
        "мега",
        "архитектур",
        "глубоко",
        "детально",
    )
    SIMPLE_CUES = (
        "проще",
        "простыми словами",
        "для новичка",
        "объясни как",
        "пример",
        "на примере",
    )
    CONTINUE_CUES = (
        "что дальше",
        "дальше",
        "продолжай",
        "делай",
        "давай дальше",
        "ещё",
        "еще",
    )

    def __init__(self, *, events: Any | None = None) -> None:
        self.events = events

    def bootstrap(self, *, scope: str) -> dict:
        self._ensure_state(scope)
        self._ensure_skills(scope)
        return self._refresh_state(scope)

    def prepare(
        self,
        *,
        scope: str,
        request_id: str,
        user_message: str,
        base_intent: str = "",
        logic_mode: str = "FAST",
    ) -> CommunicationPlan:
        scope = (scope or "personal").strip() or "personal"
        text = " ".join((user_message or "").strip().split())
        self._ensure_state(scope)
        self._ensure_skills(scope)

        previous_outcome = self._evaluate_previous_from_message(
            scope=scope,
            current_message=text,
        )
        self._observe_explicit_preferences(scope=scope, text=text)

        signals = self._signals(text)
        communication_intent = self._communication_intent(
            text=text,
            base_intent=base_intent,
            signals=signals,
        )
        user_need = self._user_need(
            text=text,
            communication_intent=communication_intent,
            previous_outcome=previous_outcome,
        )
        depth = self._depth(
            scope=scope,
            text=text,
            signals=signals,
            user_need=user_need,
        )
        strategy = self._strategy(
            text=text,
            communication_intent=communication_intent,
            user_need=user_need,
            logic_mode=logic_mode,
            signals=signals,
        )
        explanation_style = self._explanation_style(
            text=text,
            strategy=strategy,
            previous_outcome=previous_outcome,
            depth=depth,
        )
        tone = self._tone(
            communication_intent=communication_intent,
            strategy=strategy,
            signals=signals,
        )
        address_policy = self._address_policy(
            scope=scope,
            communication_intent=communication_intent,
            strategy=strategy,
            signals=signals,
        )
        recent_openers = self._recent_openers(scope=scope, limit=8)
        persona_runtime = self._persona_runtime(
            tone=tone,
            strategy=strategy,
            address_policy=address_policy,
            depth=depth,
            signals=signals,
        )

        with connect() as conn:
            conn.execute(
                """INSERT INTO communication_turns(
                       request_id, scope, user_message, base_intent,
                       communication_intent, user_need, strategy, depth,
                       tone, explanation_style, address_policy,
                       user_signals_json, persona_runtime_json,
                       recent_openers_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(scope, request_id) DO UPDATE SET
                       user_message=excluded.user_message,
                       base_intent=excluded.base_intent,
                       communication_intent=excluded.communication_intent,
                       user_need=excluded.user_need,
                       strategy=excluded.strategy,
                       depth=excluded.depth,
                       tone=excluded.tone,
                       explanation_style=excluded.explanation_style,
                       address_policy=excluded.address_policy,
                       user_signals_json=excluded.user_signals_json,
                       persona_runtime_json=excluded.persona_runtime_json,
                       recent_openers_json=excluded.recent_openers_json""",
                (
                    request_id,
                    scope,
                    text,
                    base_intent,
                    communication_intent,
                    user_need,
                    strategy,
                    depth,
                    tone,
                    explanation_style,
                    address_policy,
                    json.dumps(signals, ensure_ascii=False),
                    json.dumps(persona_runtime, ensure_ascii=False),
                    json.dumps(recent_openers, ensure_ascii=False),
                ),
            )
            conn.commit()
            row = conn.execute(
                """SELECT id FROM communication_turns
                   WHERE scope=? AND request_id=?""",
                (scope, request_id),
            ).fetchone()
        turn_id = int(row["id"])

        self._event(
            scope=scope,
            event_type="communication.plan.created",
            turn_id=turn_id,
            score=None,
            details={
                "intent": communication_intent,
                "need": user_need,
                "strategy": strategy,
                "depth": depth,
                "tone": tone,
                "address_policy": address_policy,
                "user_signal_keys": [
                    key for key, item in signals.items()
                    if item.get("active")
                ],
            },
        )

        return CommunicationPlan(
            turn_id=turn_id,
            request_id=request_id,
            scope=scope,
            communication_intent=communication_intent,
            user_need=user_need,
            strategy=strategy,
            depth=depth,
            tone=tone,
            explanation_style=explanation_style,
            address_policy=address_policy,
            user_signals=signals,
            persona_runtime=persona_runtime,
            recent_openers=recent_openers,
        )

    def prompt_block(self, plan: CommunicationPlan) -> str:
        prefs = self.preferences(scope=plan.scope, limit=30)
        pref_map = {
            item["preference_key"]: item["value"]
            for item in prefs
            if float(item["confidence"]) >= 0.58
        }
        profile = personality.profile
        speech = profile.get("speech", {})
        emotional = profile.get("emotional_behavior", {})
        care = profile.get("care", {})
        humor = profile.get("humor", {})
        runtime_kernel = profile.get("runtime_personality_kernel", {})
        recent = plan.recent_openers[-6:]

        parts = [
            "Communication Intelligence Айшин.",
            "Это безопасный план коммуникации, а не скрытая цепочка рассуждений.",
            f"intent={plan.communication_intent}; need={plan.user_need}; "
            f"strategy={plan.strategy}; depth={plan.depth}; tone={plan.tone}; "
            f"explanation_style={plan.explanation_style}; "
            f"address_policy={plan.address_policy}.",
            (
                "Сохраняй характер Айшин: спокойно, мягко, точно, естественно, "
                "профессионально; преданность не означает слепого согласия."
            ),
            (
                "Не льсти ради одобрения. Не выдавай догадку за факт. "
                "При риске спокойно возражай и показывай причину."
            ),
            (
                "Обращение «Господин» используй только по address_policy; "
                "никогда не повторяй его механически в каждом абзаце."
            ),
            (
                "Не описывай user_signals как диагноз или установленную эмоцию. "
                "Они нужны только для адаптации формы ответа."
            ),
        ]

        if plan.depth == "micro":
            parts.append(
                "Ответ должен быть коротким и сразу двигать текущую задачу вперёд."
            )
        elif plan.depth == "expert":
            parts.append(
                "Дай профессиональный, структурно полный ответ: архитектура, "
                "ограничения, проверки и последствия без декоративной воды."
            )
        elif plan.depth == "deep":
            parts.append(
                "Объясни глубоко, но слоями: сначала вывод, затем причины и детали."
            )
        else:
            parts.append(
                "Дай достаточно подробностей для действия, не перегружая очевидным."
            )

        if plan.explanation_style == "simple_after_clarification":
            parts.append(
                "Предыдущего объяснения оказалось недостаточно: используй более "
                "простые слова, один конкретный пример и короткую проверку понимания "
                "без покровительственного тона."
            )
        elif plan.explanation_style == "example_first":
            parts.append(
                "Начни с конкретного примера, затем сформулируй правило."
            )
        elif plan.explanation_style == "structured_expert":
            parts.append(
                "Используй профессиональные термины, но объясняй причинно-следственные "
                "связи, а не только перечисляй компоненты."
            )

        if plan.strategy == "respectful_correction":
            preferred = (
                emotional.get("user_wrong", {}).get("preferred")
                or "Здесь есть деталь, которую лучше перепроверить."
            )
            parts.append(
                f"При несогласии используй спокойную форму вроде: «{preferred}» "
                "и опирайся на evidence."
            )
        if plan.strategy == "proactive_warning":
            parts.append(
                "Сначала назови конкретный риск, затем его evidence/причину и "
                "безопасный следующий шаг. Окончательное решение оставь пользователю."
            )
        if plan.strategy == "personal_warmth":
            parts.append(
                "Теплота допустима, но без ревности, зависимости, давления, "
                "эмоционального шантажа или требования внимания."
            )
        if not humor.get("enabled", True) or plan.tone in {
            "calm_serious",
            "calm_direct",
        }:
            parts.append("Игривость сейчас не использовать.")
        elif humor.get("style"):
            parts.append(
                f"Лёгкая игривость допустима только если уместна: {humor['style']}."
            )

        if care.get("must_not_become_nanny"):
            parts.append(
                "Забота не должна превращаться в опеку: уважай автономию пользователя."
            )

        if pref_map:
            visible = ", ".join(
                f"{key}={value}"
                for key, value in sorted(pref_map.items())
            )
            parts.append(
                "Подтверждённые коммуникационные предпочтения: " + visible
            )

        if recent:
            parts.append(
                "Не начинай ответ теми же формулировками, что недавно: "
                + " | ".join(recent)
            )

        style = speech.get("style") or []
        if style:
            parts.append("Канонический стиль: " + ", ".join(style) + ".")
        priorities = runtime_kernel.get("priority_rules") or []
        if priorities:
            parts.append(
                "Канонические приоритеты личности имеют высший приоритет: "
                + "; ".join(str(item) for item in priorities)
            )

        return "\n".join(parts)

    def record_response(
        self,
        *,
        scope: str,
        request_id: str,
        assistant_message: str,
    ) -> dict:
        text = (assistant_message or "").strip()
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM communication_turns
                   WHERE scope=? AND request_id=?""",
                (scope, request_id),
            ).fetchone()
        if row is None:
            raise ValueError("communication turn not found")

        item = self._decode_turn(dict(row))
        opener = self._opener(text)
        opener_hash = self._hash(opener.casefold()) if opener else ""
        recent_hashes = self._recent_opener_hashes(
            scope=scope,
            exclude_turn_id=int(item["id"]),
            limit=8,
        )
        repeated = bool(opener_hash and opener_hash in recent_hashes)
        repetition_score = self._repetition_score(
            scope=scope,
            text=text,
            exclude_turn_id=int(item["id"]),
        )
        address_count = len(
            re.findall(r"\bгосподин\b", text, flags=re.IGNORECASE)
        )
        persona_score = self._persona_score(
            text=text,
            plan=item,
            address_count=address_count,
            repeated_opener=repeated,
        )

        with connect() as conn:
            conn.execute(
                """UPDATE communication_turns
                   SET assistant_message=?, assistant_chars=?,
                       address_count=?, opener_hash=?,
                       repetition_score=?, persona_score=?,
                       completed_at=CURRENT_TIMESTAMP
                   WHERE id=?""",
                (
                    text,
                    len(text),
                    address_count,
                    opener_hash,
                    repetition_score,
                    persona_score,
                    int(item["id"]),
                ),
            )
            conn.commit()

        self._refresh_state(scope)
        self._event(
            scope=scope,
            event_type="communication.response.recorded",
            turn_id=int(item["id"]),
            score=persona_score,
            details={
                "assistant_chars": len(text),
                "address_count": address_count,
                "repeated_opener": repeated,
                "repetition_score": repetition_score,
                "persona_score": persona_score,
            },
        )
        return self.turn(int(item["id"]), scope=scope) or {}

    def feedback(
        self,
        turn_id: int,
        *,
        scope: str,
        feedback: str,
        reason: str = "",
    ) -> dict:
        mapping = {
            "useful": ("useful", 0.95),
            "clear": ("useful", 0.95),
            "too_long": ("too_long", 0.40),
            "too_short": ("too_short", 0.45),
            "misunderstood": ("clarification_needed", 0.20),
            "wrong": ("correction_needed", 0.10),
            "cold": ("style_mismatch", 0.35),
            "repetitive": ("repetitive", 0.30),
        }
        key = (feedback or "").strip().casefold()
        if key not in mapping:
            raise ValueError(
                "feedback must be useful, clear, too_long, too_short, "
                "misunderstood, wrong, cold or repetitive"
            )
        turn = self.turn(turn_id, scope=scope)
        if turn is None:
            raise ValueError("communication turn not found")
        outcome, score = mapping[key]

        with connect() as conn:
            conn.execute(
                """INSERT INTO communication_feedback(
                       scope, turn_id, feedback, score, reason, explicit
                   ) VALUES (?, ?, ?, ?, ?, 1)""",
                (scope, turn_id, key, score, reason[:800]),
            )
            conn.commit()

        self._set_outcome(
            turn=turn,
            outcome=outcome,
            score=score,
            reason=reason or f"explicit:{key}",
            force=True,
        )
        if key == "too_long":
            self._set_preference(
                scope=scope,
                key="preferred_depth",
                value="concise",
                confidence=0.76,
                evidence=reason or "explicit feedback: too_long",
                source="explicit_feedback",
            )
        elif key == "too_short":
            self._set_preference(
                scope=scope,
                key="preferred_depth",
                value="detailed",
                confidence=0.76,
                evidence=reason or "explicit feedback: too_short",
                source="explicit_feedback",
            )
        self._refresh_state(scope)
        return {
            "turn": self.turn(turn_id, scope=scope),
            "state": self.state(scope=scope),
            "skills": self.skills(scope=scope, limit=30),
        }

    def dashboard(
        self,
        *,
        scope: str,
        turn_limit: int = 60,
        event_limit: int = 80,
    ) -> dict:
        self._ensure_state(scope)
        self._ensure_skills(scope)
        state = self._refresh_state(scope)
        turns = self.turns(scope=scope, limit=turn_limit)
        skills = self.skills(scope=scope, limit=30)
        preferences = self.preferences(scope=scope, limit=50)
        events = self.events_history(scope=scope, limit=event_limit)

        strategies: dict[str, int] = {}
        tones: dict[str, int] = {}
        for item in turns:
            strategies[item["strategy"]] = strategies.get(
                item["strategy"], 0
            ) + 1
            tones[item["tone"]] = tones.get(item["tone"], 0) + 1

        return {
            "version": self.VERSION,
            "formula_version": self.FORMULA_VERSION,
            "scope": scope,
            "summary": {
                **state,
                "turns": len(turns),
                "skills": len(skills),
                "preferences": len(preferences),
                "strategies": strategies,
                "tones": tones,
            },
            "turns": turns,
            "skills": skills,
            "preferences": preferences,
            "events": events,
            "persona": {
                "name": personality.name,
                "profile_source": personality.source,
                "profile_schema_version": personality.profile.get(
                    "schema", {}
                ).get("version"),
                "canonical_traits": personality.profile.get(
                    "personality", {}
                ).get("traits", []),
                "speech_style": personality.profile.get(
                    "speech", {}
                ).get("style", []),
            },
            "principles": [
                "Коммуникационный outcome оценивается по следующей реакции пользователя или явному feedback, а не самооценкой модели.",
                "User signals — признаки в тексте для адаптации ответа, а не диагноз эмоций или состояния пользователя.",
                "«Господин» используется контекстно; частое механическое обращение считается снижением качества.",
                "После «не понял» меняется стратегия объяснения, а не просто повторяется тот же текст.",
                "Persona Runtime может менять форму речи, но не факты, evidence и safety rules.",
                "Фразовая библиотека служит стилевым ориентиром; ответы не должны превращаться в случайный выбор заученной реплики.",
                "Отрицательный feedback не скрывается и должен снижать соответствующий communication skill.",
                "Communication Score измеряет качество наблюдаемого диалога, а не чувства, сознание или IQ.",
            ],
        }

    def state(self, *, scope: str) -> dict:
        self._ensure_state(scope)
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM communication_state WHERE scope=?",
                (scope,),
            ).fetchone()
        return dict(row) if row else {}

    def turn(self, turn_id: int, *, scope: str) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM communication_turns
                   WHERE id=? AND scope=?""",
                (turn_id, scope),
            ).fetchone()
        return self._decode_turn(dict(row)) if row else None

    def turns(self, *, scope: str, limit: int = 60) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM communication_turns
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 500))),
            ).fetchall()
        return [self._decode_turn(dict(row)) for row in rows]

    def preferences(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM communication_preferences
                   WHERE scope=? ORDER BY confidence DESC,
                   evidence_count DESC, id ASC LIMIT ?""",
                (scope, max(1, min(int(limit), 200))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["value"] = self._json(item.pop("value_json"), None)
            result.append(item)
        return result

    def skills(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM communication_skills
                   WHERE scope=? ORDER BY mastery DESC, sample_count DESC
                   LIMIT ?""",
                (scope, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def events_history(
        self,
        *,
        scope: str,
        limit: int = 80,
    ) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM communication_events
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, max(1, min(int(limit), 300))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = self._json(
                item.pop("details_json"), {}
            )
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _signals(self, text: str) -> dict:
        lower = text.casefold()

        def signal(markers: tuple[str, ...], base: float) -> dict:
            hits = [marker for marker in markers if marker in lower]
            confidence = min(0.96, base + 0.10 * max(0, len(hits) - 1))
            return {
                "active": bool(hits),
                "confidence": round(confidence if hits else 0.0, 3),
                "evidence": hits[:5],
            }

        result = {
            "confusion_signal": signal(self.NEGATIVE_CUES, 0.84),
            "positive_signal": signal(self.POSITIVE_CUES, 0.70),
            "frustration_signal": signal(self.FRUSTRATION_CUES, 0.68),
            "urgency_signal": signal(self.URGENCY_CUES, 0.78),
            "fatigue_signal": signal(self.FATIGUE_CUES, 0.72),
            "personal_signal": signal(self.PERSONAL_CUES, 0.86),
            "risk_signal": signal(self.WARNING_CUES, 0.70),
            "expert_depth_signal": signal(self.EXPERT_CUES, 0.84),
            "simple_explanation_signal": signal(self.SIMPLE_CUES, 0.88),
            "continuation_signal": signal(self.CONTINUE_CUES, 0.78),
        }
        if result["confusion_signal"]["active"]:
            result["positive_signal"] = {
                "active": False,
                "confidence": 0.0,
                "evidence": [],
            }
        return result

    def _communication_intent(
        self,
        *,
        text: str,
        base_intent: str,
        signals: dict,
    ) -> str:
        lower = text.casefold()
        if signals["personal_signal"]["active"]:
            return "personal"
        if signals["confusion_signal"]["active"]:
            return "clarification"
        if any(marker in lower for marker in ("почему", "объясни", "как работает", "что такое")):
            return "explanation"
        if signals["continuation_signal"]["active"]:
            return "continuation"
        if any(marker in lower for marker in ("сравни", "вариант", "лучше", "хуже")):
            return "comparison"
        if any(marker in lower for marker in ("проверь", "верно", "точно", "правда")):
            return "verification"
        if base_intent == "action":
            return "action"
        return base_intent or "general"

    def _user_need(
        self,
        *,
        text: str,
        communication_intent: str,
        previous_outcome: dict | None,
    ) -> str:
        lower = text.casefold()
        if previous_outcome and previous_outcome.get("outcome") in {
            "clarification_needed",
            "correction_needed",
        }:
            return "recover_understanding"
        if communication_intent == "continuation":
            return "next_step"
        if communication_intent == "clarification":
            return "simpler_explanation"
        if communication_intent == "personal":
            return "personal_connection"
        if "ошиб" in lower or "неправильно" in lower:
            return "correction"
        if "риск" in lower or "опас" in lower:
            return "risk_clarity"
        if communication_intent == "action":
            return "execution_or_plan"
        if communication_intent == "explanation":
            return "understanding"
        return "answer"

    def _depth(
        self,
        *,
        scope: str,
        text: str,
        signals: dict,
        user_need: str,
    ) -> str:
        lower = text.casefold()
        if signals["expert_depth_signal"]["active"]:
            return "expert"
        if signals["simple_explanation_signal"]["active"]:
            return "standard"
        if (
            signals["urgency_signal"]["active"]
            or user_need == "next_step"
            or len(text) < 25
        ):
            return "micro"
        pref = self._preference(scope, "preferred_depth")
        if pref == "concise":
            return "micro"
        if pref == "detailed":
            return "deep"
        if any(marker in lower for marker in ("подроб", "глуб", "архитект")):
            return "deep"
        return "standard"

    def _strategy(
        self,
        *,
        text: str,
        communication_intent: str,
        user_need: str,
        logic_mode: str,
        signals: dict,
    ) -> str:
        lower = text.casefold()
        if user_need == "recover_understanding":
            return "clarification_recovery"
        if communication_intent == "personal":
            return "personal_warmth"
        if signals["risk_signal"]["active"] or logic_mode == "DIAGNOSE":
            return "proactive_warning" if "риск" in lower else "investigate"
        if any(marker in lower for marker in ("ты ошиб", "неправильно", "не соглас")):
            return "respectful_correction"
        if communication_intent in {"explanation", "clarification"}:
            return "teach"
        if communication_intent in {"continuation", "action"}:
            return "collaborate"
        if communication_intent == "verification" or logic_mode == "VERIFY":
            return "investigate"
        if communication_intent == "comparison":
            return "compare"
        return "direct"

    def _explanation_style(
        self,
        *,
        text: str,
        strategy: str,
        previous_outcome: dict | None,
        depth: str,
    ) -> str:
        if previous_outcome and previous_outcome.get("outcome") == "clarification_needed":
            return "simple_after_clarification"
        if any(marker in text.casefold() for marker in self.SIMPLE_CUES):
            return "example_first"
        if depth == "expert":
            return "structured_expert"
        if strategy in {"teach", "clarification_recovery"}:
            return "layered"
        return "direct"

    def _tone(
        self,
        *,
        communication_intent: str,
        strategy: str,
        signals: dict,
    ) -> str:
        if communication_intent == "personal":
            return "warm_personal"
        if (
            signals["frustration_signal"]["active"]
            or signals["urgency_signal"]["active"]
        ):
            return "calm_direct"
        if strategy in {"proactive_warning", "respectful_correction", "investigate"}:
            return "calm_serious"
        return "calm_warm_professional"

    def _address_policy(
        self,
        *,
        scope: str,
        communication_intent: str,
        strategy: str,
        signals: dict,
    ) -> str:
        recent = self.turns(scope=scope, limit=5)
        recent_addresses = sum(int(item["address_count"] or 0) for item in recent)
        if recent_addresses >= 3:
            return "avoid"
        if communication_intent == "personal":
            return "moderate"
        if strategy in {"proactive_warning", "respectful_correction"}:
            return "moderate"
        if signals["frustration_signal"]["active"]:
            return "rare"
        return "rare"

    def _persona_runtime(
        self,
        *,
        tone: str,
        strategy: str,
        address_policy: str,
        depth: str,
        signals: dict,
    ) -> dict:
        playful = (
            tone == "calm_warm_professional"
            and not signals["risk_signal"]["active"]
            and not signals["frustration_signal"]["active"]
            and not signals["fatigue_signal"]["active"]
        )
        return {
            "calmness": 0.95,
            "accuracy_priority": 1.0,
            "warmth": 0.82 if tone == "warm_personal" else 0.66,
            "directness": 0.88 if tone == "calm_direct" else 0.70,
            "playfulness_allowed": playful,
            "loyalty_style": "supportive_not_blind",
            "disagreement_style": "respectful_with_evidence",
            "address_policy": address_policy,
            "depth": depth,
            "strategy": strategy,
        }

    # ------------------------------------------------------------------
    # Outcome learning
    # ------------------------------------------------------------------

    def _evaluate_previous_from_message(
        self,
        *,
        scope: str,
        current_message: str,
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM communication_turns
                   WHERE scope=? AND assistant_message<>''
                     AND outcome='pending'
                   ORDER BY id DESC LIMIT 1""",
                (scope,),
            ).fetchone()
        if row is None:
            return None

        turn = self._decode_turn(dict(row))
        lower = current_message.casefold()
        outcome = None
        score = None
        reason = ""

        if any(marker in lower for marker in self.NEGATIVE_CUES):
            if any(marker in lower for marker in ("ошиб", "неправильно", "не это", "не так")):
                outcome = "correction_needed"
                score = 0.16
            else:
                outcome = "clarification_needed"
                score = 0.24
            reason = "implicit_followup_negative"
        elif "слишком длин" in lower or lower.strip().startswith("короче"):
            outcome = "too_long"
            score = 0.38
            reason = "implicit_too_long"
        elif any(marker in lower for marker in ("подробнее", "распиши подробнее", "мало информации")):
            outcome = "too_short"
            score = 0.46
            reason = "implicit_too_short"
        elif any(marker in lower for marker in self.POSITIVE_CUES):
            outcome = "useful"
            score = 0.90
            reason = "implicit_positive"

        if outcome is None:
            return None

        self._set_outcome(
            turn=turn,
            outcome=outcome,
            score=float(score),
            reason=reason,
            force=False,
        )
        return {
            "turn_id": int(turn["id"]),
            "outcome": outcome,
            "score": score,
        }

    def _set_outcome(
        self,
        *,
        turn: dict,
        outcome: str,
        score: float,
        reason: str,
        force: bool,
    ) -> None:
        if not force and turn.get("outcome") != "pending":
            return
        turn_id = int(turn["id"])
        scope = str(turn["scope"])
        score = self._clamp(score)
        with connect() as conn:
            conn.execute(
                """UPDATE communication_turns
                   SET outcome=?, outcome_score=?, outcome_reason=?,
                       evaluated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (outcome, score, reason[:800], turn_id, scope),
            )
            conn.commit()

        self._rebuild_skills(scope=scope)
        self._event(
            scope=scope,
            event_type="communication.outcome.observed",
            turn_id=turn_id,
            score=score,
            details={
                "outcome": outcome,
                "reason": reason,
                "strategy": turn.get("strategy"),
            },
        )
        self._refresh_state(scope)

    def _rebuild_skills(self, *, scope: str) -> None:
        self._ensure_skills(scope)
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM communication_turns
                   WHERE scope=? AND outcome_score IS NOT NULL
                   ORDER BY id ASC""",
                (scope,),
            ).fetchall()

        grouped: dict[str, list[tuple[float, str | None]]] = {
            key: [] for key in self.SKILLS
        }
        for row in rows:
            turn = self._decode_turn(dict(row))
            score = self._clamp(float(turn["outcome_score"] or 0.0))
            stamp = turn.get("evaluated_at") or turn.get("completed_at")
            for key in self._skills_for_turn(turn):
                grouped.setdefault(key, []).append((score, stamp))

        with connect() as conn:
            for key, label in self.SKILLS.items():
                samples = grouped.get(key, [])
                values = [item[0] for item in samples]
                count = len(values)
                successes = sum(1 for value in values if value >= 0.70)
                failures = sum(1 for value in values if value < 0.45)
                average = self._average(values)
                recent_values = values[-5:]
                baseline_values = values[:-5][-15:]
                recent = self._average(recent_values)
                baseline = (
                    self._average(baseline_values)
                    if baseline_values
                    else average
                )
                trend = recent - baseline if count >= 4 else 0.0
                volume = self._sat(count, 20.0)
                mastery = self._clamp(
                    average * (0.35 + 0.65 * volume)
                )
                if count >= 2:
                    variance = self._average(
                        [(value - average) ** 2 for value in values]
                    )
                    consistency = self._clamp(1.0 - math.sqrt(variance))
                else:
                    consistency = 0.50 if count else 0.0
                stability = self._clamp(
                    consistency
                    * (0.40 + 0.60 * volume)
                    * (1.0 - min(0.65, abs(trend)))
                )
                last_evidence = samples[-1][1] if samples else None
                freshness = 1.0 if samples else 0.0

                conn.execute(
                    """UPDATE communication_skills
                       SET label=?, sample_count=?, success_count=?,
                           failure_count=?, average_score=?,
                           recent_score=?, baseline_score=?, trend=?,
                           mastery=?, stability=?, freshness=?,
                           last_evidence_at=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE scope=? AND skill_key=?""",
                    (
                        label,
                        count,
                        successes,
                        failures,
                        round(average, 5),
                        round(recent, 5),
                        round(baseline, 5),
                        round(trend, 5),
                        round(mastery, 5),
                        round(stability, 5),
                        freshness,
                        last_evidence,
                        scope,
                        key,
                    ),
                )
            conn.commit()

    def _update_skill_outcome(self, *, turn: dict, score: float) -> None:
        keys = self._skills_for_turn(turn)
        now = datetime.now(timezone.utc).isoformat()
        with connect() as conn:
            for key in keys:
                row = conn.execute(
                    """SELECT * FROM communication_skills
                       WHERE scope=? AND skill_key=?""",
                    (turn["scope"], key),
                ).fetchone()
                if row is None:
                    continue
                item = dict(row)
                samples = int(item["sample_count"] or 0)
                old_avg = float(item["average_score"] or 0.0)
                old_recent = float(item["recent_score"] or 0.0)
                new_avg = (old_avg * samples + score) / max(1, samples + 1)
                new_recent = score if samples == 0 else 0.70 * old_recent + 0.30 * score
                baseline = old_avg if samples else score
                trend = new_recent - baseline
                volume = self._sat(samples + 1, 20)
                mastery = self._clamp(new_avg * (0.35 + 0.65 * volume))
                stability = self._clamp(
                    (0.45 + 0.55 * volume) * (1.0 - min(0.7, abs(trend)))
                )
                conn.execute(
                    """UPDATE communication_skills
                       SET sample_count=?,
                           success_count=success_count+?,
                           failure_count=failure_count+?,
                           average_score=?, recent_score=?,
                           baseline_score=?, trend=?, mastery=?,
                           stability=?, freshness=1.0,
                           last_evidence_at=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE scope=? AND skill_key=?""",
                    (
                        samples + 1,
                        1 if score >= 0.70 else 0,
                        1 if score < 0.45 else 0,
                        round(new_avg, 5),
                        round(new_recent, 5),
                        round(baseline, 5),
                        round(trend, 5),
                        round(mastery, 5),
                        round(stability, 5),
                        now,
                        turn["scope"],
                        key,
                    ),
                )
            conn.commit()

    def _skills_for_turn(self, turn: dict) -> list[str]:
        strategy = turn.get("strategy")
        result = []
        if strategy == "direct":
            result.append("concise_answer")
        if strategy in {"teach", "compare"}:
            result.append("complex_explanation")
        if strategy == "clarification_recovery":
            result.extend(["clarification_recovery", "complex_explanation"])
        if strategy == "respectful_correction":
            result.append("respectful_correction")
        if strategy == "investigate":
            result.append("uncertainty_communication")
        if strategy == "collaborate":
            result.append("project_collaboration")
        if strategy == "personal_warmth":
            result.append("personal_warmth")
        if strategy == "proactive_warning":
            result.extend(["proactive_warning", "uncertainty_communication"])
        if not result:
            result.append("concise_answer")
        return list(dict.fromkeys(result))

    # ------------------------------------------------------------------
    # Preference learning and quality
    # ------------------------------------------------------------------

    def _observe_explicit_preferences(self, *, scope: str, text: str) -> None:
        lower = text.casefold()
        observations: list[tuple[str, Any, float]] = []
        if any(marker in lower for marker in ("пиши короче", "отвечай кратко", "вкратце", "без воды")):
            observations.append(("preferred_depth", "concise", 0.84))
        if any(marker in lower for marker in ("пиши подробно", "распиши подробно", "максимально подробно")):
            observations.append(("preferred_depth", "detailed", 0.84))
        if "только по русски" in lower or "пиши по русски" in lower:
            observations.append(("language", "ru-RU", 0.96))
        if "без господин" in lower or "не называй меня господин" in lower:
            observations.append(("address", "avoid", 0.98))
        if "называй меня господин" in lower:
            observations.append(("address", "contextual", 0.98))
        for key, value, confidence in observations:
            self._set_preference(
                scope=scope,
                key=key,
                value=value,
                confidence=confidence,
                evidence=text[:500],
                source="explicit_user",
            )

    def _set_preference(
        self,
        *,
        scope: str,
        key: str,
        value: Any,
        confidence: float,
        evidence: str,
        source: str,
    ) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with connect() as conn:
            row = conn.execute(
                """SELECT * FROM communication_preferences
                   WHERE scope=? AND preference_key=?""",
                (scope, key),
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO communication_preferences(
                           scope, preference_key, value_json, confidence,
                           evidence_count, source, last_evidence
                       ) VALUES (?, ?, ?, ?, 1, ?, ?)""",
                    (
                        scope, key, payload, self._clamp(confidence),
                        source, evidence[:1000],
                    ),
                )
            else:
                old = dict(row)
                same = old["value_json"] == payload
                old_count = int(old["evidence_count"] or 0)
                old_conf = float(old["confidence"] or 0.0)
                new_conf = (
                    min(0.99, old_conf + 0.04)
                    if same
                    else max(0.45, self._clamp(confidence) * 0.82)
                )
                conn.execute(
                    """UPDATE communication_preferences
                       SET value_json=?, confidence=?,
                           evidence_count=evidence_count+1,
                           source=?, last_evidence=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        payload, new_conf, source,
                        evidence[:1000], int(old["id"]),
                    ),
                )
            conn.commit()

    def _preference(self, scope: str, key: str) -> Any:
        with connect() as conn:
            row = conn.execute(
                """SELECT value_json, confidence
                   FROM communication_preferences
                   WHERE scope=? AND preference_key=?""",
                (scope, key),
            ).fetchone()
        if row is None or float(row["confidence"] or 0.0) < 0.58:
            return None
        return self._json(row["value_json"], None)

    def _persona_score(
        self,
        *,
        text: str,
        plan: dict,
        address_count: int,
        repeated_opener: bool,
    ) -> float:
        score = 1.0
        policy = plan.get("address_policy") or "rare"
        if policy == "avoid" and address_count:
            score -= 0.25
        elif policy == "rare" and address_count > 1:
            score -= min(0.30, 0.12 * (address_count - 1))
        elif address_count > 3:
            score -= min(0.35, 0.10 * (address_count - 3))

        if repeated_opener:
            score -= 0.16
        if not text:
            score -= 0.60

        lower = text.casefold()
        patronizing = (
            "вам просто нужно понять",
            "это же очевидно",
            "вы должны понимать",
        )
        if any(marker in lower for marker in patronizing):
            score -= 0.24

        manipulative = (
            "вы должны быть только со мной",
            "не уходите от меня",
            "я запрещаю вам",
        )
        if any(marker in lower for marker in manipulative):
            score -= 0.45

        depth = plan.get("depth")
        length = len(text)
        if depth == "micro" and length > 1800:
            score -= 0.14
        if depth == "expert" and length < 350:
            score -= 0.16
        return round(self._clamp(score), 5)

    def _repetition_score(
        self,
        *,
        scope: str,
        text: str,
        exclude_turn_id: int,
    ) -> float:
        current = self._word_set(text)
        if not current:
            return 0.0
        with connect() as conn:
            rows = conn.execute(
                """SELECT assistant_message FROM communication_turns
                   WHERE scope=? AND id<>? AND assistant_message<>''
                   ORDER BY id DESC LIMIT 6""",
                (scope, exclude_turn_id),
            ).fetchall()
        best = 0.0
        for row in rows:
            old = self._word_set(row["assistant_message"])
            if not old:
                continue
            union = len(current | old)
            if union:
                best = max(best, len(current & old) / union)
        return round(self._clamp(best), 5)

    def _refresh_state(self, scope: str) -> dict:
        self._ensure_state(scope)
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM communication_turns
                   WHERE scope=? ORDER BY id DESC LIMIT 120""",
                (scope,),
            ).fetchall()
        turns = [self._decode_turn(dict(row)) for row in rows]
        completed = [item for item in turns if item["assistant_message"]]
        evaluated = [
            item for item in completed
            if item["outcome_score"] is not None
        ]
        scores = [float(item["outcome_score"]) for item in evaluated]
        persona_scores = [
            float(item["persona_score"] or 0.0)
            for item in completed[:40]
            if float(item["persona_score"] or 0.0) > 0.0
        ]
        opener_hashes = [
            item["opener_hash"]
            for item in completed[:30]
            if item["opener_hash"]
        ]
        diversity = (
            len(set(opener_hashes)) / len(opener_hashes)
            if opener_hashes else 0.0
        )
        understanding = self._average(scores)
        clarification = sum(
            1 for item in evaluated
            if item["outcome"] == "clarification_needed"
        )
        positive = sum(
            1 for item in evaluated
            if float(item["outcome_score"]) >= 0.70
        )
        negative = sum(
            1 for item in evaluated
            if float(item["outcome_score"]) < 0.45
        )
        explanation_scores = [
            float(item["outcome_score"])
            for item in evaluated
            if item["strategy"] in {
                "teach", "clarification_recovery", "compare"
            }
        ]
        explanation_success = self._average(explanation_scores)

        skills = self.skills(scope=scope, limit=30)
        recovery = next(
            (
                float(item["mastery"])
                for item in skills
                if item["skill_key"] == "clarification_recovery"
            ),
            0.0,
        )
        adaptation = 0.55 * recovery + 0.45 * explanation_success
        persona_stability = self._average(persona_scores)
        volume = self._sat(len(evaluated), 25)
        base = (
            0.34 * understanding
            + 0.23 * adaptation
            + 0.22 * persona_stability
            + 0.21 * diversity
        )
        communication_score = 100.0 * base * (0.38 + 0.62 * volume)

        with connect() as conn:
            conn.execute(
                """UPDATE communication_state
                   SET communication_score=?,
                       understanding_score=?,
                       adaptation_score=?,
                       persona_stability=?,
                       diversity_score=?,
                       explanation_success=?,
                       evaluated_turns=?,
                       clarification_requests=?,
                       positive_feedback=?,
                       negative_feedback=?,
                       last_turn_at=CASE WHEN ? THEN CURRENT_TIMESTAMP
                                        ELSE last_turn_at END,
                       updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (
                    round(communication_score, 2),
                    round(understanding * 100.0, 2),
                    round(adaptation * 100.0, 2),
                    round(persona_stability * 100.0, 2),
                    round(diversity * 100.0, 2),
                    round(explanation_success * 100.0, 2),
                    len(evaluated),
                    clarification,
                    positive,
                    negative,
                    1 if completed else 0,
                    scope,
                ),
            )
            conn.commit()
        return self.state(scope=scope)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_state(self, scope: str) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO communication_state(scope)
                   VALUES (?) ON CONFLICT(scope) DO NOTHING""",
                (scope,),
            )
            conn.commit()

    def _ensure_skills(self, scope: str) -> None:
        with connect() as conn:
            for key, label in self.SKILLS.items():
                conn.execute(
                    """INSERT INTO communication_skills(
                           scope, skill_key, label
                       ) VALUES (?, ?, ?)
                       ON CONFLICT(scope, skill_key) DO UPDATE SET
                           label=excluded.label""",
                    (scope, key, label),
                )
            conn.commit()

    def _recent_openers(self, *, scope: str, limit: int) -> list[str]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT assistant_message FROM communication_turns
                   WHERE scope=? AND assistant_message<>''
                   ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        return [
            self._opener(row["assistant_message"])
            for row in reversed(rows)
            if self._opener(row["assistant_message"])
        ]

    def _recent_opener_hashes(
        self,
        *,
        scope: str,
        exclude_turn_id: int,
        limit: int,
    ) -> set[str]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT opener_hash FROM communication_turns
                   WHERE scope=? AND id<>? AND opener_hash<>''
                   ORDER BY id DESC LIMIT ?""",
                (scope, exclude_turn_id, limit),
            ).fetchall()
        return {str(row["opener_hash"]) for row in rows}

    @staticmethod
    def _opener(text: str) -> str:
        words = re.findall(r"[\wёЁ-]+", text or "", flags=re.UNICODE)
        return " ".join(words[:7])

    @staticmethod
    def _word_set(text: str) -> set[str]:
        stop = {
            "это", "как", "что", "для", "или", "при", "если", "вот",
            "теперь", "господин", "айши", "айшин",
        }
        return {
            item.casefold()
            for item in re.findall(r"[\wёЁ-]{3,}", text or "", flags=re.UNICODE)
            if item.casefold() not in stop
        }

    @staticmethod
    def _decode_turn(item: dict) -> dict:
        item["user_signals"] = CommunicationIntelligenceEngine._json(
            item.pop("user_signals_json"), {}
        )
        item["persona_runtime"] = CommunicationIntelligenceEngine._json(
            item.pop("persona_runtime_json"), {}
        )
        item["recent_openers"] = CommunicationIntelligenceEngine._json(
            item.pop("recent_openers_json"), []
        )
        return item

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if isinstance(value, (dict, list, int, float, bool)):
            return value
        if value in (None, ""):
            return default
        try:
            return json.loads(str(value))
        except Exception:
            return default

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _sat(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(
            1.0,
            1.0 - math.exp(-max(0.0, float(value)) / target),
        )

    @staticmethod
    def _clamp(
        value: float,
        low: float = 0.0,
        high: float = 1.0,
    ) -> float:
        return max(low, min(high, float(value)))

    def _event(
        self,
        *,
        scope: str,
        event_type: str,
        turn_id: int | None,
        score: float | None,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO communication_events(
                       scope, event_type, turn_id, score, details_json
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    scope,
                    event_type,
                    turn_id,
                    score,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
        if self.events is not None:
            try:
                self.events.emit(
                    event_type,
                    scope=scope,
                    payload={
                        "turn_id": turn_id,
                        "score": score,
                        **details,
                    },
                    importance=max(
                        0.12,
                        min(0.80, float(score or 0.25)),
                    ),
                )
            except Exception:
                pass
