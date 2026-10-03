# Aishin 00.00.13 — Response Grounding

## Цель

00.00.13 добавляет отдельный контур доказательности финального ответа Айшин. Он не объявляет ответ объективной истиной и не заменяет Verification Engine. Его задача — проверять, насколько фактические утверждения ответа опираются на evidence, реально доступные текущему запросу.

## Архитектура

Контур состоит из двух частей:

1. Generation-time policy — перед обращением к AI provider в system context добавляется строгая политика:
   - не придумывать даты, суммы, версии, номера и количества;
   - не считать отрицание эквивалентным противоположному утверждению;
   - при недостаточной или противоречивой evidence явно обозначать неопределённость;
   - не придумывать provenance, документы, память или результаты инструментов.

2. Deterministic post-response audit — после генерации ResponseGroundingScorer:
   - выделяет содержательные claims;
   - сопоставляет их с evidence текущего request;
   - учитывает provenance и source groups;
   - отдельно контролирует числовые расхождения;
   - отдельно контролирует несовпадение отрицания;
   - учитывает наличие противоречий;
   - сохраняет безопасную трассу в SQLite.

## Статусы

- strong — высокая доказательная опора без предупреждений;
- mixed — частичная опора;
- weak — слабая опора;
- unscored_no_evidence — внешняя evidence отсутствует, поэтому система не рисует фальшивый ноль или 100%;
- not_applicable_no_claims — содержательных проверяемых claims нет.

Важно: score измеряет grounding, а не абсолютную истинность.

## Хранение

Database schema: 24.

Таблица:
- response_grounding_runs

Сохраняются:
- request_id;
- scope;
- logic mode;
- applicable;
- overall;
- claim coverage;
- provenance coverage;
- source diversity;
- contradiction handling;
- число supported / partial / unsupported claims;
- типы источников;
- warnings;
- безопасное описание claims.

Raw content результата ToolRegistry не сохраняется в persistent execution trace. Для read-only file content сохраняется только размер content_bytes.

## Интеграция

Response Grounding подключён к:
- AishinEngine;
- Self Reflection;
- Continuous Learning;
- Live Brain;
- Safe Trace;
- scoped diagnostics API;
- Runtime Smoke;
- UI Contract.

API:
- GET /api/assistant/response-grounding?scope=personal&limit=30

Live Brain показывает:
- общий grounding score;
- статус;
- supported claims;
- partial claims;
- unsupported claims;
- число source groups;
- attention при слабом grounding.

## Scope isolation

Все записи grounding привязаны к scope. personal и project:aishin не смешиваются.

## Safety boundary

Response Grounding не раскрывает hidden chain-of-thought. Он хранит и показывает только наблюдаемые технические признаки: claims, score, provenance identifiers, source groups и итоговые предупреждения.

## Проверки релиза

Runtime Smoke обязан проверить:
- прямую документальную опору;
- несовпадающее число;
- противоположное отрицание;
- отсутствие evidence;
- diagnostics API;
- отсутствие raw tool content в persistent execution trace;
- Live Brain export format 11.

UI Contract обязан проверить:
- cache key 0.0.13;
- Grounding metric в Live Brain;
- AISHIN 00.00.13 marker;
- сохранение всех accessibility/scope/browser contracts 00.00.12.

Релиз считается закрытым только после зелёного Aishin Runtime Check на Ubuntu/Python 3.11 и Windows/Python 3.11, включая headless Chrome и Aishin.bat --check-only.
