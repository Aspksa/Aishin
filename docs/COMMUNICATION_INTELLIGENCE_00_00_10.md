# Aishin 00.00.10 — Communication Intelligence

## Назначение

Версия 00.00.10 делает общение отдельным измеряемым когнитивным контуром.

Цепочка:

User Message
→ Communication Signals
→ Intent / Need
→ Dialogue Strategy
→ Depth / Tone / Explanation Style
→ Persona Runtime
→ Response
→ Next User Reaction / Explicit Feedback
→ Communication Outcome
→ Communication Skills
→ Evolution Curriculum

Главное правило: качество общения нельзя оценивать только самой моделью. Основной outcome появляется из следующей реакции пользователя или явного feedback.

## Версии

Aishin Core: 0.0.10

Database schema: 22

Communication Engine: aishin-communication-intelligence-v1

Formula: adaptive-dialogue-quality-v1

Live Brain Export: 8

## Source of Truth личности

Communication Intelligence не создаёт вторую личность.

Канонический источник:

app/data/AISHIN_PERSONALITY_PROFILE.json

Загрузка и validation:

app/personality.py

Persona Runtime использует канонические identity, personality traits, speech style, emotional behavior, care, humor и runtime personality priorities.

Communication learning может адаптировать форму ответа, но не переписывает personality canon.

## Dialogue Signals

Движок извлекает только наблюдаемые текстовые сигналы:

- confusion_signal;
- positive_signal;
- frustration_signal;
- urgency_signal;
- fatigue_signal;
- personal_signal;
- risk_signal;
- expert_depth_signal;
- simple_explanation_signal;
- continuation_signal.

Это не диагноз эмоций пользователя.

Если confusion_signal активен, positive_signal подавляется. Поэтому слово «непонятно» не считается позитивным только из-за подстроки «понятно».

## Communication Intent

Отдельно от бизнес-intent определяется коммуникационная задача:

- general;
- personal;
- clarification;
- explanation;
- continuation;
- comparison;
- verification;
- action.

## User Need

Возможные потребности формы ответа:

- answer;
- next_step;
- simpler_explanation;
- recover_understanding;
- personal_connection;
- correction;
- risk_clarity;
- execution_or_plan;
- understanding.

User Need влияет только на форму ответа и не заменяет фактический intent системы.

## Response Strategy

Поддерживаются direct, teach, clarification_recovery, compare, collaborate, investigate, respectful_correction, proactive_warning и personal_warmth.

После отрицательного outcome clarification_needed следующий ответ автоматически переключается на simple_after_clarification.

## Adaptive Depth

Уровни:

- micro;
- standard;
- deep;
- expert.

«Что дальше?» ведёт к короткому ответу, а явные маркеры «профессионально», «максимально подробно», «архитектурно» — к expert depth.

## Persona Runtime

Persisted Communication Plan хранит безопасные параметры:

- calmness;
- accuracy_priority;
- warmth;
- directness;
- playfulness_allowed;
- loyalty_style;
- disagreement_style;
- address_policy;
- depth;
- strategy.

Это технические параметры формирования ответа, а не hidden chain-of-thought.

Канонические инварианты: точность выше желания понравиться; поддержка без слепого согласия; уважительное несогласие с evidence; отсутствие лести ради одобрения; забота без опеки; отсутствие манипуляции, ревности и зависимости; окончательное решение остаётся пользователю.

## Address Policy и Anti-Repetition

Вместо постоянного «Господин» используются policy avoid, rare и moderate.

Сохраняются opener, opener hash, repetition score и recent openers. Persona Runtime получает недавние начала ответов и запрещает их механическое повторение.

## Communication Outcome

Outcome не считается автоматически успешным.

Состояния:

- pending;
- useful;
- clarification_needed;
- correction_needed;
- too_long;
- too_short;
- style_mismatch;
- repetitive.

Следующая реплика пользователя может закрыть предыдущий pending turn. Например «Не понял» → clarification_needed; «Теперь понял» → useful.

## Explicit Feedback

Поддерживаются useful, clear, too_long, too_short, misunderstood, wrong, cold и repetitive.

Если explicit feedback меняет уже оценённый turn, skills не получают второй sample. Статистика навыков детерминированно пересчитывается из канонических communication_turn outcomes.

## Communication Preferences

Persisted preferences создаются только из наблюдаемого или явного evidence.

Примеры: preferred_depth=concise, preferred_depth=detailed, language=ru-RU, address=avoid, address=contextual.

## Communication Skills

Отдельные обучаемые навыки:

- concise_answer;
- complex_explanation;
- clarification_recovery;
- respectful_correction;
- uncertainty_communication;
- project_collaboration;
- personal_warmth;
- proactive_warning.

Для каждого сохраняются sample_count, success_count, failure_count, average_score, recent_score, baseline_score, trend, mastery, stability, freshness и last_evidence_at.

Один удачный диалог не может создать mastery 100%.

## Evolution Integration

Если sample_count >= 3 и наблюдается low mastery, negative trend или repeated failures, Evolution Engine создаёт curriculum target communication_skill.

Bounded adaptation может затрагивать только response depth, explanation style, address frequency и tone selection.

Запрещено менять факты, ослаблять Verification, обходить safety и переписывать personality canon.

## Communication Score

Это не IQ, не любовь и не «человечность».

Компоненты: understanding 34%, adaptation 23%, persona stability 22%, response-opening diversity 21%. Итог дополнительно умножается на evidence-volume factor.

## Database

Schema 22.

Новые таблицы:

- communication_state;
- communication_turns;
- communication_preferences;
- communication_skills;
- communication_feedback;
- communication_events.

## API

GET /api/assistant/communication

GET /api/assistant/communication/turns

GET /api/assistant/communication/skills

GET /api/assistant/communication/preferences

POST /api/assistant/communication/turns/{turn_id}/feedback

Feedback endpoint local-only.

## UI — «Общение Айшин»

Новый модуль расположен сразу после основного Assistant.

Экран показывает Communication Score, Understanding, Adaptation, Persona Stability, Diversity, Explanation Success, evaluated evidence, Dialogue Trace, Communication Skills, current Persona Runtime, Preferences, Learning Events и Safety & Character principles.

Для завершённых turn доступны feedback-кнопки: Полезно, Не поняла меня, Слишком длинно, Слишком коротко, Повторяется.

## Live Brain

Live Brain получает communication.summary, communication.turns, communication.skills, communication.preferences и communication.events.

Pulse содержит communication_score, communication_understanding, communication_adaptation, communication_persona_stability, communication_explanation_success и communication_attention.

Live Brain Export version: 8.

Количество базовых 24 когнитивных каналов не меняется. Communication Intelligence является мета-контуром формы взаимодействия.

## Development Metrics

Формула общего Development Score не изменяется задним числом.

Добавляются реальные counters:

- communication_score;
- communication_understanding;
- communication_adaptation;
- communication_persona_stability;
- communication_diversity;
- communication_explanation_success;
- communication_evaluated_turns;
- communication_skills;
- communication_preferences;
- communication_clarifications.

## Проверяемые инварианты

Runtime smoke обязан доказать:

1. schema 22 применяется;
2. новый UI присутствует;
3. communication API возвращает state/skills;
4. negative cue «не понял» не активирует positive_signal;
5. expert request выбирает expert depth;
6. feedback меняет outcome;
7. повторный override feedback не удваивает sample_count;
8. clarification outcome меняет следующий plan на clarification_recovery;
9. Live Brain содержит communication section;
10. Live Brain export имеет format_version 8;
11. 24 базовых cognitive channels сохранены;
12. Windows launcher остаётся рабочим.
