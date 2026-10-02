# Aishin 00.00.04 — Live Brain Runtime

## Назначение

Версия 00.00.04 превращает существующий «Технический мозг Айшин» из набора отдельных диагностических карточек в единый наблюдаемый когнитивный контур.

Главный принцип: интерфейс показывает только реально существующие данные локального проекта Aishin. Внешний AI-провайдер не создаёт искусственные баллы развития и не подменяет память, события, граф знаний или историю обучения Айшин.

## Новые части

### LiveBrainRuntime

Файл: app/core/live_brain.py

Runtime агрегирует без изменения исходных данных:

- persistent event journal;
- активную память;
- knowledge graph;
- planner;
- Logic Engine;
- Context Orchestrator;
- Causal Reasoning;
- Hypothesis Manager;
- Logic Learning;
- Counterfactual Reasoning;
- Decision Quality;
- Action Selection;
- Execution Coordinator;
- Performance History;
- Continuous Learning;
- Metacognition;
- Verification Engine;
- Cognitive Request Traces;
- Tool Registry history;
- Self Reflection;
- Learning Planner;
- Safe Experiments;
- Development Metrics.

Runtime не генерирует скрытые рассуждения и не пытается реконструировать chain-of-thought.

### 24 наблюдаемых контура

1. Восприятие
2. Память
3. Связи
4. Планы
5. Логика
6. Контекст
7. Причины
8. Гипотезы
9. Опыт
10. Альтернативы
11. Качество
12. Выбор
13. Разрешение
14. Скорость
15. Самообучение
16. Самопроверка
17. Перепроверка
18. Решение
19. Действие
20. Самоанализ
21. План обучения
22. Эксперимент
23. Проверка обучения
24. Закрепление

Состояния контура: idle, active, attention.

### Реальные фазовые события

Во время обработки сообщения ядро пишет cognition.phase:

input -> memory -> graph -> planner -> context -> logic -> decision -> provider -> reflection -> learning -> completed

Эти события являются наблюдаемой технической телеметрией, а не текстовым описанием скрытого мышления модели.

## API

GET /api/assistant/live-brain

Параметры:

- scope;
- event_limit;
- graph_limit.

Основные разделы ответа:

- runtime_version;
- integrity;
- pulse;
- channels;
- safe_trace;
- event_stream;
- knowledge_graph;
- development;
- quality;
- provenance.

GET /api/assistant/live-brain/export

Возвращает полный машиночитаемый JSON-срез для диагностики и передачи в другой чат или инструмент анализа.

Формат:

AISHIN_LIVE_BRAIN_EXPORT

Версия формата:

2

## Safe Trace

safe_trace содержит только наблюдаемые сведения:

- request ID;
- trace ID;
- статус;
- выбранный режим Logic Engine;
- численную confidence, если она реально сохранена;
- количество источников памяти;
- количество evidence items;
- число противоречий;
- число unresolved-сигналов;
- факт запуска Verification Engine;
- Decision Quality;
- provider/model;
- измеренную latency;
- total runtime;
- bottleneck;
- budget status.

Safe Trace намеренно не содержит скрытую цепочку рассуждений модели.

## Event telemetry

EventBus расширен двумя функциями:

- scoped recent events;
- агрегированная статистика по scope.

Статистика включает:

- общее число событий;
- события за 5 минут;
- события за 1 час;
- события высокой важности за 1 час;
- среднюю importance.

## UI

Новый интерфейс подключён отдельными файлами:

- app/static/live_brain.css;
- app/static/live_brain.js.

Нейронная обсерватория показывает:

- ядро Айшин;
- статус целостности;
- текущую фазу;
- 24 когнитивных контура;
- поток событий;
- живой фрагмент графа знаний;
- safe trace;
- события за 5 минут и час;
- число активных каналов;
- память;
- сущности и связи;
- реальный Development Score;
- точки внимания и ошибки подсистем.

Существующий старый блок «Внутренние контуры» не удалён. Live Brain синхронизирует его состояния и пояснения с новым runtime.

## Экспорт из интерфейса

Кнопка «Экспорт JSON» доступна в Live Brain.

В настройках также появляется карточка «Диагностика мозга Айшин» с загрузкой полного отчёта.

Файл создаётся локально в браузере из ответа API. Секреты Cloud.ru в этот отчёт не добавляются самим LiveBrainRuntime.

## Отказоустойчивость

Snapshot использует изолированный сбор данных. Если одна подсистема не отвечает, весь endpoint не должен падать: ошибка попадает в integrity.errors, а остальные контуры продолжают отображаться.

Это позволяет отличить:

- healthy — ошибок и нерешённых сигналов нет;
- attention — есть ошибки подсистем, unresolved или важные события;
- initializing — проект ещё не накопил наблюдаемую историю.

## Автотесты

Runtime smoke проверяет:

- HTTP 200 для live-brain;
- ровно 24 контура;
- наличие политики Safe Trace;
- корректный список knowledge graph entities;
- endpoint экспорта;
- формат AISHIN_LIVE_BRAIN_EXPORT;
- format_version 2.

GitHub Actions дополнительно проверяет синтаксис app/static/live_brain.js.

## Версия

FastAPI: 0.0.4

UI: Aishin Core 0.0.4

Live Brain Runtime: aishin-live-brain-v2
