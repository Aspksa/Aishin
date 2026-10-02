# Aishin 00.00.07 — Proactive Intelligence

## Назначение

Версия 00.00.07 добавляет ситуационную осведомлённость поверх Live Brain 00.00.04, Long-Term Growth 00.00.05, Cognitive Intelligence 00.00.06 и существующего безопасного ProactiveDecisionLoop.

Главный принцип:

Айши может сама заметить, связать, оценить риск, перепроверить и предложить следующий шаг, но наблюдение не становится выполненным действием.

## Архитектура

Новый движок: app/core/proactive_intelligence.py

Версия: aishin-proactive-intelligence-v1

Формула: situation-awareness-risk-v1

00.00.07 не заменяет ProactiveDecisionLoop. Новый слой строится поверх безопасной цепочки:

Situation Model -> Change Detection -> Signal Engine -> Risk -> Attention -> Incident -> Proposal

Существующая цепочка исполнения сохраняется:

наблюдение -> предложение -> одобрение -> revalidation -> исполнение

## Situation Model

Каждый scan создаёт persisted snapshot состояния.

Наблюдаются entities, relations, active memories, trusted/stale knowledge, goals, tasks, blocked/overdue tasks, verification, mastered/fading skills, cognitive routes, execution failures, pending proactive decisions и sensors.

Snapshot хранит object counts, state, delta к предыдущему snapshot, awareness score, trigger и timestamp.

Triggers: startup, heartbeat, message, manual.

## Change Detection

Между последовательными Situation Snapshots рассчитывается numeric delta.

Отдельные сигналы поднимаются при резком росте unresolved verification, execution failures и failed cognitive routes.

Само изменение счётчика не объявляется ошибкой. Оно остаётся наблюдаемым signal с confidence и evidence.

## Signal Engine

### Planner
- overdue task;
- blocked task;
- waiting dependencies;
- invalid due date;
- goal without open tasks;
- stale open task.

### Sensors
Любой SensorHub reading со статусом, отличным от ok.

### Verification
- unresolved verification;
- verified conflict signal.

### Execution Coordinator
- failed attempt;
- stale_or_blocked attempt;
- revalidation failure.

### Cognitive Intelligence
Регрессия task family: минимум 6 routes, recent window 3, baseline предыдущие до 7.

### Long-Term Growth
Fading skill с достаточным evidence.

### Knowledge Trust
Aggregate stale knowledge signal.

### Situation Delta
Резкие изменения технических показателей.

## Risk Model

Signal хранит severity, confidence, impact и urgency.

Формула:

risk = 0.30 * severity + 0.25 * confidence + 0.25 * impact + 0.20 * urgency

Все значения ограничены диапазоном 0..1.

Risk не означает доказанную ошибку.

Отдельно хранится verification_state:
- deterministic_confirmed;
- verification_observed;
- corroborated;
- grounded_observation;
- needs_review.

## Attention Score

Risk корректируется надёжностью источника.

Примеры:
- planner: 0.98;
- execution: 0.98;
- verification: 0.94;
- sensor: 0.92;
- learning: 0.90;
- cognitive intelligence: 0.88;
- knowledge: 0.82.

Далее Attention Manager применяет learned feedback modifier.

## Severity Labels

- critical: risk >= 0.84;
- high: risk >= 0.68;
- medium: risk >= 0.48;
- low: ниже 0.48.

Это категории приоритета UI, а не утверждение о реальном ущербе.

## Attention Manager

Начальный threshold: 0.48.

Безопасный диапазон калибровки: 0.36..0.70.

Feedback:
- useful;
- noisy;
- false_positive;
- handled;
- resolved;
- snooze.

Поведение:
- useful подтверждает полезность;
- handled/resolved закрывает incident;
- snooze подавляет на 24 часа;
- noisy подавляет на 7 дней;
- false_positive подавляет на 30 дней.

Большая доля noisy/false positive повышает threshold. Полезные и обработанные сигналы могут аккуратно его снижать.

## Incident Lifecycle

Статусы:
- active;
- snoozed;
- resolved;
- dismissed.

Condition не считается resolved только из-за изменения attention threshold.

Если signal продолжает существовать, fingerprint остаётся активным.

Если condition реально исчезает:
- incident -> resolved;
- связанный pending decision -> dismissed.

## Deduplication

Signal и Incident используют deterministic SHA-256 fingerprint по source, signal type, subject identity и scope.

Повторный scan увеличивает occurrences вместо создания одинаковых карточек.

## Temporal Intelligence

Таблица proactive_expectations хранит временные ожидания.

00.00.07 автоматически создаёт:

### Task Due
expected_state = completed_or_reviewed_before_due

Статусы pending, overdue, resolved.

### Goal Next Step
Для активной цели без открытой задачи:
expected_state = has_open_task

Это фундамент для будущих domain-specific chains. 00.00.07 не выдумывает доменные цепочки без явных правил.

## Situation Awareness Score

Это не intelligence score и не качество решений.

Компоненты:
- source coverage: 50%;
- temporal coverage: 20%;
- evidence grounding: 20%;
- attention calibration: 10%.

Высокий awareness означает хорошее наблюдение, а не отсутствие проблем.

## Proactive Decisions

Новый engine создаёт только информационные proactive decisions:
- tool_name = None;
- capability = proactive_notice.

Новый путь исполнения инструментов не создаётся.

PermissionGate и ExecutionCoordinator остаются единственным путём изменяющих действий.

## Safety

Новый engine не может сам отправлять письма, менять файлы, удалять данные, менять task status, выполнять external tools, обходить Permission Gate или превращать suggestion в execution.

## Database Schema

Schema version: 19.

Новые таблицы:
- situation_snapshots;
- proactive_signals;
- proactive_incidents;
- proactive_expectations;
- proactive_attention_feedback;
- proactive_attention_profile;
- proactive_intelligence_runs.

Существующая proactive_conditions из schema 11 сохраняется.

## API

GET /api/assistant/proactive-intelligence

POST /api/assistant/proactive-intelligence/scan

GET /api/assistant/proactive-intelligence/incidents

GET /api/assistant/proactive-intelligence/expectations

GET /api/assistant/proactive-intelligence/signals

POST /api/assistant/proactive-intelligence/incidents/{id}/feedback

Изменяющие endpoints local-only.

## UI — «Айши заметила»

В левом меню добавлен модуль «Айши заметила».

Экран показывает Situation Awareness ring, observed objects, active incidents, requires attention, expectations, calibrated threshold, incident feed, severity filters, risk score, attention score, verification state, evidence count, suggested action, feedback, situation deltas, source health, Temporal Intelligence, Signal Stream, Attention Manager, scan history и safety principles.

На главной странице добавляется компактная карточка активных ситуаций и awareness score.

## Live Brain

Live Brain дополнен awareness score, active incidents, attention incidents и полным proactive intelligence snapshot.

Integrity становится attention, если есть incidents выше текущего threshold.

Live Brain Export version: 5.

## Heartbeat

Heartbeat остаётся 60 секунд.

Полный proactive scan выполняется на первом heartbeat и далее на каждом десятом heartbeat — примерно раз в 10 минут при работающем процессе.

Дополнительно scan выполняется на startup, после завершённого сообщения и вручную.

## Development Metrics

Формула общего развития не меняется задним числом.

Добавляются только counters:
- proactive_active_incidents;
- proactive_attention_incidents;
- proactive_critical_incidents;
- proactive_feedback_samples;
- proactive_intelligence_runs;
- situational_awareness.

## Honesty Rules

1. Observation != confirmed error.
2. Risk != probability that fact is true.
3. Awareness != absence of problems.
4. Suggestion != executed action.
5. High confidence must have visible source.
6. False-positive feedback suppresses recurrence.
7. Resolved condition closes its pending informational decision.
8. Hidden chain-of-thought is not stored or displayed.
9. External AI provider does not directly control risk or awareness scores.
10. Persisted local evidence remains the basis of Situation Model.

## Versions

Aishin Core: 0.0.7

Database schema: 19

Proactive Intelligence Engine: aishin-proactive-intelligence-v1

Situation Awareness Formula: situation-awareness-risk-v1

Live Brain Export: 5
