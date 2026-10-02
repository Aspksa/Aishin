# Aishin 00.00.06 — Cognitive Intelligence

## Назначение

Версия 00.00.06 превращает накопленный опыт Aishin в адаптивную когнитивную систему.

Предыдущие этапы:

- 00.00.04 — Live Brain: наблюдаемость реальных когнитивных контуров;
- 00.00.05 — Long-Term Growth: долговременные навыки, специализации, trust и freshness;
- 00.00.06 — Cognitive Intelligence: измеримые когнитивные способности и реальное использование подтверждённого опыта при обработке нового запроса.

Cognitive Intelligence не является IQ, психометрическим тестом или оценкой человеческого интеллекта. Это технический индекс способности локальной системы Aishin понимать контекст, принимать решения, использовать память, учиться, планировать, перепроверять себя, адаптироваться и переносить проверенный опыт.

## Основные компоненты

### CognitiveIntelligenceEngine

Файл:

app/core/cognitive_intelligence.py

Версия:

aishin-cognitive-intelligence-v1

Формула:

cognitive-intelligence-8d-v1

### Adaptive Skill Router

Перед Verification/Logic pipeline Aishin:

1. классифицирует тип задачи;
2. получает только долговременные навыки lifecycle established/mastered;
3. получает specialization developing/strong/mastered;
4. получает только knowledge trust levels trusted/supported;
5. проверяет тематическую релевантность;
6. анализирует успешный опыт этого task family;
7. проверяет доказанный перенос выбранного навыка между типами задач;
8. предлагает адаптивный режим;
9. добавляет operational experience в технический контекст;
10. после выполнения получает outcome и сохраняет результат.

Router не может понижать VERIFY или DIAGNOSE.

Permission Gate не изменяется.

Verification Engine имеет приоритет над adaptive experience.

## Типы задач

Базовая deterministic-классификация:

- documents;
- fuel;
- vehicles;
- timesheet;
- software;
- diagnostics;
- planning;
- analysis;
- knowledge;
- general.

Классификатор является маршрутизатором, а не утверждением о содержании мира.

## Relevance Gate

Высокий mastery сам по себе недостаточен для выбора навыка.

Skill/Specialization/Knowledge проходит в контекст только при:

- token overlap с текущим запросом; или
- совпадении предметной task family.

Для general task family совпадение family не считается достаточным: нужен реальный text overlap.

Это защищает Router от подключения нерелевантного сильного навыка.

## Mode Adaptation

Базовый режим выбирает Logic Engine.

Adaptive Router может:

- сохранить режим;
- повысить FAST до PLAN;
- повысить FAST до DEEP;
- повысить FAST до VERIFY.

Router не может:

- VERIFY -> FAST;
- VERIFY -> DEEP;
- DIAGNOSE -> FAST;
- DIAGNOSE -> DEEP;
- автоматически ослабить Verification;
- изменить Permission Gate.

Основные причины повышения режима:

- low metacognitive confidence;
- needs_verification;
- insufficient_data;
- transfer learning;
- высокая сложность при слабом подтверждённом опыте;
- action + planning family.

## Adaptive Context Budget

ContextBudgeter теперь поддерживает budget_multiplier.

Диапазон:

0.85 .. 1.35

Практические значения Router:

- FAST около 0.95;
- PLAN около 1.08;
- DEEP около 1.15;
- VERIFY около 1.24;
- DIAGNOSE около 1.24;
- transfer learning может добавить небольшой дополнительный budget.

В отчёте context_budget_reports сохраняются:

- base token budget;
- фактический token budget;
- budget multiplier;
- trimmed chars;
- history before/after.

## Outcome Loop

После завершения запроса Router получает:

- Decision Quality;
- Self Reflection Quality;
- provider availability;
- unresolved count.

Outcome:

0.45 * decision_quality
+ 0.35 * reflection_quality
+ 0.20 * provider_signal
- unresolved_penalty

Successful route:

- outcome >= 0.72;
- unresolved_count == 0.

Эта метрика не используется как доказательство истинности фактов. Она оценивает техническое качество завершённого когнитивного маршрута.

## Transfer Learning

Перенос опыта считается подтверждённым только тогда, когда:

1. один и тот же durable skill был реально выбран Router;
2. маршрут завершился successful;
3. тот же skill затем успешно применён в другой task family.

Только после этого skill входит в transfer map.

Само сходство текстов не считается успешным переносом.

## Восемь измерений интеллекта

### 1. Understanding — Понимание

Источники:

- metacognitive_assessments.confidence;
- metacognitive_assessments.evidence_score;
- contradiction frequency;
- объём накопленных metacognitive samples.

Высокая оценка требует качества и достаточного количества evidence.

### 2. Logic — Логика

Источники:

- decision_quality_scores.overall;
- metacognitive evidence;
- trusted logic strategies;
- объём реальных decision samples.

### 3. Memory — Память

Источники:

- active memories;
- average memory confidence;
- knowledge_trust;
- trusted knowledge ratio;
- объём памяти и trust records.

### 4. Learning — Обучение

Источники:

- growth_skills;
- average mastery;
- durable skills;
- mastered skills;
- weighted skill evidence;
- growth_specializations.

### 5. Planning — Планирование

Источники:

- goals;
- tasks;
- completion status;
- action selections;
- decision quality of action selection.

Если реального planner evidence нет, score не заполняется искусственно.

### 6. Self Check — Самопроверка

Источники:

- self_reflection_runs;
- reflection quality;
- reflection confidence;
- Verification Engine;
- unresolved rate;
- metacognition;
- correction signals.

### 7. Adaptation — Адаптация

Источники:

- cognitive_intelligence_routes;
- route outcomes;
- success rate;
- route confidence;
- доля маршрутов с реальным skill routing;
- объём накопленного adaptive experience.

### 8. Transfer — Перенос опыта

Источники:

- successful adaptive routes;
- один skill;
- несколько task families;
- число подтверждённых transfer routes;
- breadth по разным task families.

## Веса общего Cognitive Intelligence Score

- Understanding: 16%;
- Logic: 18%;
- Memory: 14%;
- Learning: 14%;
- Planning: 10%;
- Self Check: 12%;
- Adaptation: 10%;
- Transfer: 6%.

Сумма:

100%.

Каждая dimension дополнительно использует volume factor. Поэтому несколько хороших результатов не должны быстро давать высокий общий процент.

## Новая схема базы данных

Schema version:

18

### cognitive_intelligence_routes

Хранит:

- request_id;
- task_family;
- intent;
- base_mode;
- adapted_mode;
- route_confidence;
- context_multiplier;
- selected skill IDs;
- selected specialization IDs;
- selected knowledge IDs;
- transfer_used;
- transfer skill IDs;
- rationale;
- outcome_score;
- successful;
- unresolved_count;
- timestamps.

### cognitive_intelligence_snapshots

Хранит:

- formula_version;
- overall_score;
- dimensions;
- evidence;
- route stats;
- timestamp.

Snapshot создаётся не чаще одного раза в час.

## API

GET /api/assistant/intelligence

Возвращает:

- current;
- strengths;
- growth_priorities;
- routes;
- latest_route;
- transfer_map;
- history.

GET /api/assistant/intelligence/routes

GET /api/assistant/intelligence/history

GET /api/assistant/intelligence/transfer

## Live Brain

Live Brain теперь содержит:

cognitive_intelligence.current

cognitive_intelligence.latest_route

Safe Trace дополнен:

- task_family;
- base_mode;
- adapted_mode;
- route_confidence;
- adaptive_skill_count;
- adaptive_knowledge_count;
- transfer_used;
- intelligence_outcome.

Live Brain Export Format:

4

Скрытый chain-of-thought по-прежнему не экспортируется.

## UI

Новый экран «Интеллект Айши» находится внутри «Развитие Айшин».

Он показывает:

- общий Cognitive Intelligence Score;
- radar chart из 8 способностей;
- отдельную карточку каждой способности;
- вес способности;
- Why/объяснение score;
- Adaptive Skill Router последнего запроса;
- task family;
- base mode -> adapted mode;
- context multiplier;
- outcome;
- transfer flag;
- сильные стороны;
- точки роста;
- Transfer Learning Map;
- последние adaptive routes;
- историю Cognitive Intelligence;
- правила защиты от накрутки.

Live Brain дополнительно показывает intelligence score и последний Router state.

## Принципы безопасности и честности

1. Cognitive Intelligence не является IQ.
2. Неизмеренные способности не заполняются выдуманными числами.
3. Provider/model не добавляет intelligence points напрямую.
4. High mastery не даёт Router права использовать нерелевантный skill.
5. Router не ослабляет Verification.
6. Router не изменяет Permission Gate.
7. Transfer засчитывается только после успешного применения одного skill в разных task families.
8. Hidden chain-of-thought не сохраняется и не реконструируется.
9. Current evidence имеет приоритет над накопленным operational experience.
10. Любой score должен иметь техническое объяснение Why.

## Версии

Aishin Core: 0.0.6

Database schema: 18

Cognitive Intelligence Engine: aishin-cognitive-intelligence-v1

Cognitive Intelligence Formula: cognitive-intelligence-8d-v1

Live Brain Export Format: 4
