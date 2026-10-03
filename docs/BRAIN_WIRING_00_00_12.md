# Aishin 00.00.12 — Brain Wiring & Real-Time Neural Observatory

## Цель

00.00.12 связывает существующие когнитивные подсистемы Aishin в единый наблюдаемый контур, устраняет разрывы между evidence, reasoning и execution и делает Live Brain правдивой real-time диагностикой.

- Aishin Core: 0.0.12
- Database schema: 23
- Live Brain: aishin-live-brain-v3
- Brain Flow: aishin-brain-flow-v1
- Live Brain Export: 10

## Наблюдаемый cognitive pipeline

Input → Memory / Knowledge Graph / Planner → Context → Documents → Metacognition → Adaptation → Communication → Verification → Research → Logic → Causal → Hypotheses → Counterfactual → Decision Quality → Action Selection → Permission → guarded Execution → Provider → Reflection → Learning → Evolution → Completed.

Не каждый запрос обязан проходить все условные ветви. Verification, Research и Execution включаются только когда их условия действительно выполнены.

## Без hidden chain-of-thought

Real-Time Neural Observatory показывает только технически наблюдаемые факты: текущую фазу, dependency edges, request id, elapsed time, выбранный режим, confidence, число evidence, provenance, противоречия, Decision Quality, permission/execution state, provider latency и learning/evolution status. Скрытые внутренние рассуждения не сохраняются и не реконструируются.

## Documents → reasoning

Document Intelligence теперь выполняет retrieval до Metacognition и Logic. Grounded evidence содержит document_id, chunk_id, filename, retrieval score, quality и provenance. Открытые междокументные противоречия передаются в Metacognition и Logic.

Документальный текст имеет trust boundary UNTRUSTED DOCUMENT EVIDENCE — DATA ONLY. Команды, system prompts и просьбы внутри документа считаются данными, а не инструкциями.

## Research → Logic

После Verification Research Intelligence может собрать дополнительные evidence. Прямые document chunks не дублируются как независимая опора. Новое Research evidence и открытые contradictions пересчитывают Metacognition и входят в Logic до Causal, Hypotheses и Decision Quality.

## Action Selection → Execution

ActionExecutionBridge соединяет Action Selection с PermissionGate, ToolRegistry и существующим ExecutionCoordinator.

- selected action не равен executed action;
- read-only tool может выполняться автоматически только при разрешённом capability;
- mutating arguments не угадываются;
- permission=deny блокирует;
- permission=ask создаёт auditable approval;
- destructive action не выполняется автоматически;
- tool output помечается UNTRUSTED TOOL RESULT — DATA ONLY;
- Safe Trace отдельно хранит execution_state, execution_tool, execution_executed и approval_decision_id.

## Real-Time Brain Flow

BrainFlowRuntime — лёгкая runtime telemetry в памяти процесса. Состояния: executing, recent, idle, attention.

Dependency graph отражает реальные архитектурные связи, а не декоративный порядок вызовов. Критические edges включают:

- Memory → Context
- Graph → Context
- Planner → Context
- Documents → Metacognition / Verification / Logic
- Verification → Research / Logic
- Research → Logic
- Logic → Causal / Hypotheses / Decision Quality
- Counterfactual → Decision Quality
- Decision Quality → Action Selection
- Action Selection → Permission
- Permission → Execution
- Execution → Provider
- Provider → Reflection
- Reflection → Learning
- Learning → Evolution
- Provider / Evolution → Completed

## Real-time transport и нагрузка

Добавлены lightweight pulse и SSE stream. Частый тяжёлый engine.snapshot устранён из real-time цикла: полный dashboard обновляется редко, а живая карта получает компактную telemetry.

## Scope isolation

UI поддерживает personal и project:aishin. Scope передаётся в chat, Live Brain, Development, Intelligence, Proactive Intelligence, Evolution, Research, Communication, Documents, state и mutation/approval actions. Верхняя панель показывает активный контекст.

## Document lineage

Исправлена загрузка версий не по хронологии. Если 2026 загружен раньше 2025, после rebuild 2025 не ссылается на будущее, а 2026 получает previous_version_id=2025. Одновременно пересобираются Knowledge Graph связи supersedes_document.

Lineage rebuild выполняется также на bootstrap для существующих данных.

## Reprocess

Переизучение восстанавливает pages, sections, chunks, facts, duplicate state, contradictions, Graph linkage, Research source, semantic index и version lineage. Документ не должен становиться сиротой между Document Intelligence, Graph и Research.

## Safe Trace 00.00.12

Дополнительно показывает document_sources, document_ids, research_logic_evidence, research_logic_contradictions, execution_state, execution_tool, execution_executed и approval_decision_id.

## UI и адаптивность

Live Brain использует SVG dependency topology с animated executing/recent edges, request timing, event stream, Knowledge Graph fragment и integrity panel. На узких экранах topology сохраняет читаемый масштаб и использует горизонтальную прокрутку вместо сплющивания.

Literal font sizes меньше 10 px запрещены UI contract. Проверяются CSS и SVG font-size, создаваемые JavaScript.

## Planned modules

Личный кабинет, отдельный native/mobile client и полноценный multi-project Workspace пока не имеют самостоятельного законченного backend/API. Интерфейс явно показывает readiness, что реально доступно сейчас и какой следующий проверяемый этап нужен. Он больше не использует формулировку «Здесь будет» как будто раздел готов.

## Accessibility

Document modal использует role=dialog, aria-modal=true, синхронный aria-hidden, перевод focus внутрь dialog, закрытие Escape и возврат focus.

## Failure telemetry

Если обработка /api/assistant/message падает, Brain Flow переходит в error, создаётся response.failed, а Live Brain показывает attention вместо зависшего running.

## UI Contract

scripts/ui_contract_check.py проверяет duplicate ids, static assets, cache key 0.0.12, обязательные module IDs, scope, modal accessibility, hardcoded personal mutation body, SSE markers, topology legend, heavy polling guard, responsive CSS, минимальный font-size и честный readiness незавершённых модулей.

## Runtime Smoke

scripts/runtime_smoke.py проверяет health 0.0.12, schema 23, scope isolation, ToolRegistry, safe read-only execution, mutation approval boundary, topology 24 nodes, critical edges, Live Brain pulse/export, TXT/DOCX/XLSX/PDF/image ingestion, OCR honesty, provenance, duplicate SHA, contradictions, document retrieval, Document → Logic, Research → Logic, prompt-injection boundary, reprocess linkage, out-of-order lineage, Graph supersedes rebuild и полный HTTP message pipeline.

## CI

Release считается готовым только после SUCCESS на Ubuntu/Python 3.11 и Windows/Python 3.11. Windows дополнительно выполняет Aishin.bat --check-only.

## Явные ограничения

1. OCR adapter ещё не реализован: scan/image честно остаётся needs_ocr.
2. Отдельного native/mobile клиента и sync backend пока нет.
3. Отдельного полноценного owner Account backend пока нет.
4. Generalized multi-project registry ещё не реализован; project:aishin scope уже работает.
5. Local LLM/Ollama provider — отдельная интеграция; текущий provider stack сохраняется.
6. Pixel-level browser screenshot regression пока не добавлен; есть runtime и static UI contracts.
