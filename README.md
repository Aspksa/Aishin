# Aishin

Aishin — проект личной AI-помощницы Айшин (Айши).

## Версия
`0.0.3` — постоянное живое ядро с облачным AI-мозгом Cloud.ru.

## Что уже заложено
- ядро на Python/FastAPI;
- локальная SQLite-база данных;
- веб-интерфейс;
- Windows-запуск через `Aishin.bat`;
- модуль **Aishin Kitsune** — личная помощница;
- модуль **Личный кабинет**;
- модуль **Мобильное приложение**;
- модуль **Рабочее пространство**;
- нижний пункт **Система обновления** с обновлением через GitHub;
- полный машинно-читаемый профиль личности и «души» Айшин;
- канонический профиль `app/data/AISHIN_PERSONALITY_PROFILE.json` добавлен отдельно и не считается новой версией проекта;
- постоянное runtime-состояние и heartbeat;
- долговременная память с раздельными scope, типом, confidence, важностью, источником и тегами;
- история диалогов и постоянный журнал событий;
- когнитивный слой, который собирает личность + память + историю перед ответом;
- стабильная self-model: идентичность, ценности, цели, границы и политика ошибок;
- **Master Profile** — отдельный профиль Господина с источником и confidence;
- **Relationship Memory** — отдельная память совместной истории и договорённостей;
- **Personal Timeline** — личная хронология событий и изменений;
- **Memory Consolidation** — выделение важных фактов из разговора, проверка дублей, усиление повторно подтверждённой памяти, фиксация противоречий и замена устаревшего только при явном обновлении;
- **Semantic Memory** — embeddings Cloud.ru, постоянный векторный индекс в SQLite и гибридный поиск по словам и смыслу;
- **Knowledge Graph / карта мира** — сущности, связи, evidence, scope, журнал изменений и автоматическое построение из разговора;
- **Internal Planner** — цели, задачи, зависимости, приоритеты, сроки, блокировки, журнал изменений и автоматическое выделение явных задач из разговора;
- **Sensor Hub** — безопасные read-only сенсоры runtime, модулей, планировщика и файловой структуры проекта;
- **Tool Registry** — контролируемые инструменты с permission gate, dry-run, явным approval и журналом действий;
- **Proactive Decision Loop** — сенсоры → оценка → предложение → approval/reject → контролируемое выполнение;
- **Live Brain Visualization** — живой поток сенсоры → память → граф → планировщик → решение → инструмент с текущим фокусом, рабочей памятью и событиями;
- **Metacognition** — детерминированная оценка достаточности данных, confidence, evidence score, противоречий и необходимости перепроверки перед ответом;
- **Verification Engine** — автоматическая перепроверка памяти, semantic memory, Knowledge Graph, сенсоров и явно указанных файлов проекта с повторной оценкой confidence до финального ответа;
- permission gate для будущих автономных действий;
- пассивное самонаблюдение runtime;
- независимый слой AI Provider;
- Cloud.ru Evolution Foundation Models Adapter;
- автоматическая самодиагностика перед запуском;
- логотип Айшин, встроенный в интерфейс.

## Запуск
На Windows запустите `Aishin.bat`.

Первый запуск создаст локальное Python-окружение, установит зависимости, проверит обновления, выполнит самодиагностику и откроет:

`http://127.0.0.1:8765`

## Cloud.ru
Айшин использует Evolution Foundation Models через OpenAI-совместимый API Cloud.ru.

Базовый endpoint:

`https://foundation-models.api.cloud.ru/v1`

Поддерживаемые методы, которые использует ядро:
- `GET /models`
- `POST /chat/completions`

### Настройка
1. В Cloud.ru Evolution → Foundation Models создайте API key.
2. Скопируйте `.env.example` в локальный файл `.env`.
3. Запишите секрет только в локальный `.env`:

```env
AISHIN_AI_PROVIDER=cloudru
AISHIN_CLOUDRU_API_KEY=ВАШ_СЕКРЕТНЫЙ_КЛЮЧ
AISHIN_CLOUDRU_MODEL=ai-sage/GigaChat3-10B-A1.8B
AISHIN_CLOUDRU_EMBEDDING_MODEL=Qwen/Qwen3-Embedding-0.6B
AISHIN_CLOUDRU_EMBEDDING_DIMENSIONS=1024
AISHIN_CLOUDRU_URL=https://foundation-models.api.cloud.ru/v1
```

Файл `.env` исключён из Git и не должен попадать в репозиторий.

Модель можно заменить на любую доступную в вашем Cloud.ru Foundation Models API.

## Архитектурный принцип
Личность Айшин не принадлежит конкретной LLM. Характер, правила, история, состояние, память, граф связей и разрешения хранятся в собственном ядре проекта. Cloud.ru является внешним когнитивным двигателем, а не хранилищем личности Айшин.

Контур работы:

`восприятие → намерение → память → self-model → контекст → Cloud.ru AI → ответ → событие → обновление состояния`

## Безопасная автономность
Будущие действия проходят через централизованный permission gate. Чтение локального контекста и собственная память разрешены по умолчанию, а отправка сообщений, изменение файлов, установка программ и системные команды требуют разрешения. Удаление данных по умолчанию запрещено.

## Следующий слой
Context Budgeter для контроля размера системного контекста, затем усиление Cloud.ru resilience: health-cache, retries/backoff для 429/5xx и безопасная политика ошибок.


## Личная Айшин
Aishin проектируется не как многопользовательский сервис, а как одна личная Айшин для одного основного Господина.

Личный контур разделён на три постоянных слоя:
- `Master Profile` — только сохранённые сведения о Господине; отсутствующие сведения не выдумываются.
- `Relationship Memory` — совместные решения, договорённости и важная история.
- `Personal Timeline` — временная линия событий, изменений и завершённых этапов.

Проектная память хранится отдельно от личной и не должна автоматически смешиваться с ней. Перед ответом когнитивный слой собирает личность Айшин, self-model, личный контекст, релевантную память и только затем обращается к Cloud.ru.

Добавление этих слоёв является развитием текущей версии `0.0.3`, а не выпуском новой версии.


## Memory Consolidation
Айшин не должна сохранять каждую реплику как вечное воспоминание.

Консолидация работает так:
1. Сначала локальный фильтр определяет, есть ли в сообщении признаки устойчивого факта, предпочтения, правила, решения или совместной договорённости.
2. Если Cloud.ru доступен, модель предлагает до четырёх кандидатов памяти в структурированном JSON.
3. Каждый кандидат принимается только если содержит дословное evidence из сообщения пользователя.
4. Возможные секреты и ключи автоматически не сохраняются.
5. Дубли не создаются повторно: существующее воспоминание усиливается по confidence/importance.
6. При явном изменении старое воспоминание помечается как superseded и сохраняется новое.
7. Если новое значение конфликтует со старым, но пользователь не обозначил изменение, оба факта не сливаются: создаётся запись о противоречии.
8. Все изменения памяти записываются в `memory_changes` и доступны через `GET /api/assistant/memory-changes`.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Semantic Memory
Смысловая память использует embedding-модель Cloud.ru `Qwen/Qwen3-Embedding-0.6B` с ожидаемой размерностью 1024.

Векторы хранятся локально в SQLite в таблице `memory_vectors`. Сырые воспоминания и их scope остаются в собственной базе Aishin.

Поиск работает гибридно:
- лексический поиск находит точные слова и формулировки;
- semantic search сравнивает embedding запроса с embedding воспоминаний;
- результаты объединяются и ранжируются по смысловой близости, confidence и importance.

Если embedding API временно недоступен, Айшин не теряет память: когнитивный слой продолжает использовать лексический поиск.

API:
- `GET /api/assistant/semantic-search?query=...&scope=personal`
- `POST /api/assistant/semantic-index?scope=personal`

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Knowledge Graph
Айшин постепенно строит собственную карту мира из подтверждённых сущностей и связей.

Поддерживаемые сущности:
- person
- assistant
- project
- document
- organization
- vehicle
- place
- object
- task
- decision
- event

Связи создаются только при наличии evidence — дословного фрагмента сообщения пользователя, подтверждающего связь. Модель не должна дорисовывать связи без основания.

Граф разделён по scope. Личная карта, отношения и проектные области могут храниться отдельно.

При запуске создаётся базовый relationship-граф:
`Айшин → assists → Господин`
`Айшин → develops → Aishin`
`Господин → develops → Aishin`

Все изменения графа записываются в `graph_changes`.

API:
- `GET /api/assistant/graph/entities`
- `GET /api/assistant/graph/relations`
- `GET /api/assistant/graph/search`
- `GET /api/assistant/graph/stats`
- `GET /api/assistant/graph/changes`

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Internal Planner
Внутренний планировщик хранит цели, задачи, зависимости и незавершённые дела Айшин.

Основные правила:
- цель и задача всегда принадлежат конкретному `scope`;
- задача не может ссылаться на цель из другой области;
- зависимости между задачами не могут образовывать цикл;
- статус выполнения не считается завершённым, пока явно не установлен `completed`;
- автоматическое выделение задач из разговора принимается только при наличии дословного `evidence` из сообщения пользователя;
- сроки не выдумываются: дата сохраняется только если она была явно указана;
- планировщик может замечать просроченные, заблокированные задачи и незакрытые зависимости;
- heartbeat выполняет периодическую проверку и пишет `planner.attention` в журнал событий;
- планировщик сам по себе не выполняет внешние действия.

Разрешения:
- `manage_internal_plans=allow`
- `proactive_notice=allow`
- `execute_planned_action=ask`

API:
- `GET/POST /api/assistant/planner/goals`
- `POST /api/assistant/planner/goals/{goal_id}/status`
- `GET/POST /api/assistant/planner/tasks`
- `POST /api/assistant/planner/tasks/{task_id}/status`
- `POST /api/assistant/planner/dependencies`
- `GET /api/assistant/planner/notices`
- `GET /api/assistant/planner/changes`

Активные цели, задачи и предупреждения планировщика включаются в когнитивный контекст Айшин перед ответом.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Sensors & Tools
Айшин получила контролируемые «органы чувств» и «руки».

Sensor Hub работает только на чтение и собирает:
- runtime-состояние;
- состояние модулей;
- состояние планировщика;
- безопасную статистику файловой структуры проекта без чтения `.env`, `.git`, `.venv` и базы данных.

Снимки сенсоров могут сохраняться в `sensor_snapshots`. Heartbeat периодически запускает сенсоры и создаёт событие `sensors.attention`, если обнаружено состояние, требующее внимания.

Tool Registry сейчас содержит:
- `planner.create_task`
- `planner.set_task_status`
- `project.read_text`
- `project.write_text`

Каждый инструмент объявляет требуемую capability. Каждый вызов пишется в `tool_actions`.

Правила выполнения:
- `dry_run=true` показывает, что инструмент собирается сделать, без изменения данных;
- режим permission=`deny` полностью блокирует действие;
- режим permission=`ask` не выполняет реальное действие без `approved=true`;
- реальное выполнение и изменение permission через HTTP разрешены только локальному клиенту;
- доступ за пределы корня проекта запрещён;
- `.env`, `.git`, `.venv` и `aishin.db` закрыты для файловых инструментов;
- удаление файлов отдельным инструментом не добавлялось.

Сенсорный контекст и каталог доступных инструментов включаются в системный контекст Айшин. Она не должна утверждать, что действие выполнено, пока Tool Registry не вернул `status=success`.

API:
- `GET /api/assistant/sensors`
- `POST /api/assistant/sensors/scan`
- `GET /api/assistant/sensors/history`
- `GET /api/assistant/tools`
- `POST /api/assistant/tools/{tool_name}`
- `GET /api/assistant/tools/history`
- `POST /api/assistant/permissions/{capability}`

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Proactive Decision Loop
Проактивный контур связывает Sensor Hub, Internal Planner, Permission Gate и Tool Registry.

Поток:
`observe → evaluate → propose → pending → approve/reject → execute → audit`

Ключевые правила:
- обнаруженный сигнал не считается действием;
- предложение не считается выполненным действием;
- каждое предложение имеет source, rationale, priority, confidence, capability, tool и dry-run preview;
- одинаковые pending-решения дедуплицируются;
- если причина исчезла, planner-решение автоматически переводится в `dismissed` с причиной `underlying_condition_resolved`;
- информационные решения могут не иметь инструмента;
- решение с инструментом нельзя выполнить, пока оно не имеет status=`approved`;
- `execute_planned_action=deny` блокирует выполнение даже после approval;
- конкретный Tool Registry повторно проверяет собственную capability;
- approve/reject/execute и ручная evaluation доступны только локальному HTTP-клиенту;
- результат исполнения сохраняется в решении и в журнале Tool Registry.

Сейчас Decision Loop детерминированно реагирует на:
- просроченные задачи;
- заблокированные задачи;
- незакрытые зависимости;
- некорректные сроки;
- активные цели без открытых задач;
- sensor attention.

Для цели без задач Айшин может предложить создать внутреннюю задачу «Определить следующий шаг...», но она не создаётся до одобрения.

API:
- `POST /api/assistant/proactive/evaluate`
- `GET /api/assistant/proactive/pending`
- `GET /api/assistant/proactive/history`
- `POST /api/assistant/proactive/{decision_id}/approve`
- `POST /api/assistant/proactive/{decision_id}/reject`
- `POST /api/assistant/proactive/{decision_id}/execute`

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Approval Center
Главная страница Aishin содержит живой центр решений «Айшин заметила».

Интерфейс показывает:
- pending-решения проактивного контура;
- приоритет, confidence, источник и причину решения;
- предлагаемый Tool Registry инструмент;
- безопасный dry-run preview;
- отдельно одобренные, но ещё не выполненные действия;
- состояние сенсоров;
- количество открытых задач, сущностей графа и воспоминаний текущего контекста.

Кнопки:
- `Одобрить` переводит решение в approved, но не считает его выполненным;
- `Отклонить` сохраняет отказ в истории;
- `Выполнить` доступно для уже approved-решения и запускает Tool Registry через серверный permission gate.

После каждого действия интерфейс перечитывает фактическое состояние ядра. Автообновление выполняется без мутации состояния; ручная кнопка «Обновить» дополнительно запускает локальную proactive evaluation.

Карточки строятся через DOM API и пользовательский текст не вставляется как сырой HTML.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Live Brain Visualization
Главная страница показывает не декоративную схему, а фактическое состояние когнитивного контура Айшин.

Поток:
`Sensors → Working Memory → Knowledge Graph → Planner → Decision Loop → Tool Registry`

Каждый узел подсвечивается на основании текущего состояния ядра.

Интерфейс показывает:
- текущий runtime focus;
- сенсорные сигналы и состояния attention;
- реальную working memory последнего когнитивного прохода;
- количество сущностей и связей личного Knowledge Graph;
- открытые задачи и предупреждения Planner;
- pending/approved решения Proactive Decision Loop;
- последние Tool Registry действия;
- последние события ядра;
- rationale, source, priority, confidence, capability и tool выбранного решения.

`working_memory` в snapshot хранит только воспоминания, которые последний вызов `Cognition.build_context` действительно поднял для ответа. Это отличается от `recent_memories`, которые являются просто последними активными записями хранилища.

Карточку решения в Approval Center можно выбрать, чтобы увидеть её основание в блоке «Почему это решение».

Визуальный поток анимируется только как отражение активности данных и не означает, что скрытое действие было выполнено.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Metacognition
Перед генерацией ответа Cloud.ru ядро Aishin выполняет отдельную метакогнитивную оценку.

Статусы:
- `confident` — у контекста достаточно подтверждённой опоры;
- `cautious` — данные есть, но ответ должен быть осторожным;
- `needs_verification` — обнаружены противоречия, которые нельзя скрывать;
- `insufficient_data` — данных недостаточно для уверенного вывода.

Оценка учитывает:
- количество реально поднятых working-memory воспоминаний;
- confidence воспоминаний;
- retrieval score;
- использование semantic search;
- противоречивые memory kinds/tags;
- наличие данных Knowledge Graph;
- предупреждения Planner;
- состояния Sensor Hub;
- тип запроса: verification/action требует более сильной опоры.

Результат содержит:
- `status`;
- `confidence`;
- `evidence_score`;
- `contradiction_count`;
- `missing_data`;
- `reasons`.

Метакогнитивная оценка выполняется ДО обращения к Cloud.ru и добавляется в system prompt. Модель получает прямое правило не звучать увереннее, чем позволяет оценка ядра.

`confidence` здесь — техническая оценка опоры ответа на доступные данные Aishin. Это не измерение сознания, эмоций или субъективной уверенности.

Оценки сохраняются в `metacognitive_assessments` и доступны через:
- `GET /api/assistant/metacognition`

Live Brain содержит отдельный узел «Уверенность» и показывает последний metacognitive status.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Verification Engine
Если первичная Metacognition возвращает `needs_verification`, `insufficient_data` или пользователь явно просит «проверь», Aishin запускает отдельный Verification Engine до финального ответа.

Порядок:
1. Расширяет лексический поиск памяти.
2. Расширяет semantic search.
3. Сверяет Knowledge Graph.
4. Повторно снимает Sensor Hub.
5. Если пользователь явно указал безопасный текстовый файл внутри проекта — читает его через Tool Registry `project.read_text`.
6. Передаёт только собранные локальные свидетельства Cloud.ru для проверки их внутренней согласованности. Cloud.ru здесь не считается независимым источником истины.
7. Повторно запускает Metacognition с расширенной памятью, найденными конфликтами и нерешёнными пунктами.
8. Именно повторная оценка ограничивает уверенность финального ответа.

Verification Report содержит:
- `checks`;
- `findings`;
- `unresolved`;
- `expanded_memories`;
- `consistency`.

История сохраняется в `verification_runs`.

API:
- `GET /api/assistant/verification`

Live Brain содержит отдельный узел `Verification`, который показывает, выполнялась ли перепроверка и сколько пунктов осталось нерешёнными.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Надёжность ядра и миграции
Текущая версия проекта остаётся `0.0.3`.

Канонический профиль личности:
- основной источник: `app/data/AISHIN_PERSONALITY_PROFILE.json`;
- `app/personality.py` использует canonical-first загрузку;
- `app/data/aishin_personality.json` оставлен только как compatibility fallback;
- self-check аварийно завершает запуск, если активен не канонический профиль.

SQLite:
- добавлен `app/migrations.py`;
- таблица `schema_migrations` хранит применённые миграции;
- текущая версия схемы: `13`;
- `init_db()` автоматически применяет недостающие миграции;
- self-check проверяет schema version, `PRAGMA foreign_keys=ON` и `PRAGMA integrity_check`.

Runtime:
- `scripts/runtime_smoke.py` реально поднимает FastAPI через TestClient и проверяет ключевые endpoints;
- `Aishin.bat` требует Python 3.11+, исправлена нумерация этапов и перед запуском выполняются self-check + runtime smoke;
- добавлен GitHub Actions workflow `.github/workflows/runtime-check.yml`;
- workflow запускает compileall, core self-check и FastAPI runtime smoke на Windows и Ubuntu.

Во время первого реального CI были найдены и исправлены:
- буквальные `\\n` вместо переводов строк в `app/core/__init__.py` и `app/core/events.py`;
- Windows `UnicodeEncodeError` при печати русского JSON через cp1252.

Подтверждённый успешный CI:
- workflow run id: `36987889755`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success.

Это первый этап проекта, где runtime-проверка выполнена фактически в CI, а не только структурно по содержимому репозитория.


## Aishin Logic Engine v1
Logic Engine управляет способом обработки задачи до финального ответа Cloud.ru.

Динамические режимы:
- `FAST` — короткая линейная обработка простой задачи;
- `DEEP` — сравнение нескольких технически релевантных вариантов;
- `VERIFY` — приоритет доказательной перепроверки;
- `PLAN` — цель → зависимости → следующий шаг → критерий завершения;
- `DIAGNOSE` — симптомы → подтверждённые факты → гипотезы → проверки → причина.

Режим выбирается детерминированно по intent, сложности запроса, метакогнитивному confidence, противоречиям и состоянию Planner.

Компоненты:
- Reasoning Controller;
- Rule Engine;
- Evidence Chain;
- Contradiction Resolver;
- Dynamic Thinking Mode;
- Decision Journal.

Decision Journal сохраняет только техническую трассу: режим, сработавшие правила, evidence, противоречия, альтернативные стратегии, выбранную стратегию, unresolved и confidence. Скрытая chain-of-thought не сохраняется и не экспонируется.

Если Logic Engine выбирает `VERIFY` или `DIAGNOSE`, Verification Engine запускается принудительно до финального ответа. После Verification выполняется финальная Metacognition, затем фиксируется Logic Trace и только потом вызывается Cloud.ru.

Хранилище:
- `logic_decisions`;
- `logic_rule_events`;
- schema migration version `3`.

API:
- `GET /api/assistant/logic`

Live Brain содержит отдельный узел Logic Engine и отображает текущий mode/complexity.

Это развитие текущей версии `0.0.3`; номер версии не меняется.


## Context Orchestrator
Logic Engine выбирает, как думать; Context Orchestrator решает, какой объём данных попадёт в финальный prompt Cloud.ru.

Бюджеты по режимам:
- `FAST`: history=4, memories=4, graph=0, planner=2;
- `DEEP`: history=8, memories=8, graph=8, planner=5;
- `VERIFY`: history=6, memories=12, graph=12, verification=8;
- `PLAN`: history=6, memories=6, graph=6, planner=12;
- `DIAGNOSE`: history=8, memories=10, graph=8, verification=8, sensors=6.

Сначала Cognition собирает рабочий минимальный контекст для выбора Logic Mode. После Logic/Verification финальный system prompt пересобирается с нуля Context Orchestrator под выбранный mode. Исходные данные при этом не удаляются из памяти — ограничивается только конкретный prompt.

Каждая сборка сохраняется в `context_traces`: mode, budget, выбранные memory/entity/planner IDs и приблизительный размер prompt.

API:
- `GET /api/assistant/context-traces`

## Causal Reasoning
Causal Reasoning консервативно отделяет:
- `observed` — связь наблюдается;
- `temporal` — одно событие было раньше/позже другого;
- `contributory` — фактор мог способствовать;
- `causal_candidate` — есть явная причинная формулировка и evidence, но причинность ещё не доказана.

Причинный confidence ограничен сверху и снижается при противоречиях. Если evidence не поддерживает одновременно причину и следствие, система сохраняет это как гипотезу/неопределённость, а не как факт.

История сохраняется в `causal_assessments`.

API:
- `GET /api/assistant/causal`

Live Brain показывает отдельные узлы Context и Causal.

Schema migration: `4`.
Версия приложения остаётся `0.0.3`.


### Подтверждение Context + Causal runtime
Context Orchestrator и Causal Reasoning подтверждены GitHub Actions:
- run id: `36989908775`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.

Во время первого прогона CI обнаружил некорректные newline-литералы в `app/core/context_orchestrator.py`; файл был переписан безопасно и повторный cross-platform run прошёл полностью.


## Hypothesis Manager
В режимах `VERIFY` и `DIAGNOSE` Aishin теперь поддерживает несколько конкурирующих гипотез одновременно.

Правила:
- гипотеза не становится фактом только из-за самого высокого confidence;
- confidence нормализуется между конкурирующими кандидатами;
- противоречия понижают confidence;
- сохраняются supporting/opposing evidence;
- Stop Rule завершает перебор только при достаточном преимуществе и отсутствии unresolved;
- если остановка рано невозможна, выбирается следующая discriminating check — проверка, которая лучше разделит ведущие гипотезы.

История:
- `hypothesis_runs`

API:
- `GET /api/assistant/hypotheses`

## Logic Learning
Logic Learning не обучается на собственных ответах Айшин. Стратегия получает reinforcement только после явной последующей обратной связи Господина.

Положительные сигналы включают: `сработало`, `получилось`, `исправлено`, `решено`, `заработало`, `помогло`.

Отрицательные сигналы включают: `не сработало`, `не помогло`, `не работает`, `ошибка осталась`, `проблема осталась`, `стало хуже`.

Надёжность стратегии считается с Beta(2,2) prior, поэтому один успешный случай не превращает стратегию в абсолютное правило.

Хранилище:
- `logic_strategies`
- `logic_learning_events`

API:
- `GET /api/assistant/logic-learning`

Подтверждённые стратегии добавляются в prompt только как прошлый опыт с reliability, а не как обязательное правило.

Schema migration: `5`.
Версия приложения остаётся `0.0.3`.


### Подтверждение Hypothesis + Logic Learning runtime
Hypothesis Manager и Logic Learning подтверждены GitHub Actions:
- run id: `36990689777`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.


## Counterfactual Reasoning
Перед сложным решением Aishin может построить условные сценарии «что изменится, если сделать X».

Активные режимы:
- `DEEP`
- `PLAN`
- `VERIFY`
- `DIAGNOSE`

Каждый сценарий содержит:
- действие;
- возможные эффекты;
- риски;
- обратимость `high/medium/low`;
- confidence;
- evidence.

Ключевое правило: сценарий не является прогнозом. Если evidence недостаточно, эффект явно помечается как неподтверждённый сценарий. Temporal/correlation evidence не превращается автоматически в причинный прогноз.

Хранилище:
- `counterfactual_assessments`

API:
- `GET /api/assistant/counterfactual`

## Decision Quality Scoring
Decision Quality Scoring оценивает не «правильность решения», а качество его основания.

Компоненты:
- logic confidence;
- evidence quality;
- verification quality;
- uncertainty control;
- contradiction control;
- alternative coverage;
- reversibility.

Итоговые состояния:
- `evidence_sufficient_for_considered_action`;
- `proceed_cautiously_or_verify_remaining_risks`;
- `do_not_treat_as_ready_for_action`.

Низкая обратимость, слабая evidence-опора, нерешённые противоречия и большой остаток неопределённости снижают качество решения.

Хранилище:
- `decision_quality_scores`

API:
- `GET /api/assistant/decision-quality`

Live Brain показывает отдельные узлы Counterfactual и Decision Quality.

Schema migration: `6`.
Версия приложения остаётся `0.0.3`.


### Подтверждение Counterfactual + Decision Quality runtime
Counterfactual Reasoning и Decision Quality Scoring подтверждены GitHub Actions:
- run id: `36991246148`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.


## Action Selection / Expected Utility
Action Selector сравнивает безопасные кандидатные действия после Counterfactual Reasoning и Decision Quality Scoring.

Utility учитывает:
- ожидаемую пользу = scenario confidence × decision quality;
- risk penalty;
- reversibility penalty;
- permission penalty;
- unresolved/uncertainty penalty.

Action Selector сопоставляет понятный кандидат с Tool Registry, если это возможно, и читает актуальный Permission Gate:
- `allow` → кандидат может быть передан Tool Registry;
- `ask` → `approval_required`;
- `deny` → `blocked_by_permission`.

Критическое правило:
**Action Selection никогда сам не вызывает инструмент.**
Выбор кандидата не считается выполнением. Реальное действие возможно только через Tool Registry, который повторно проверяет permission и approval.

Хранилище:
- `action_selections`

API:
- `GET /api/assistant/action-selection`

Live Brain показывает отдельный узел Action Selection с utility и execution state.

Schema migration: `7`.
Версия приложения остаётся `0.0.3`.


### Подтверждение Action Selection runtime
Action Selection / Expected Utility подтверждён GitHub Actions:
- run id: `36991833619`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.

Action Selector не исполняет выбранное действие сам: реальное выполнение остаётся за Tool Registry и Permission Gate.


## Approval / Execution Coordinator
Реальное выполнение planned/proactive действий теперь отделено от простого status=`approved`.

Ключевые свойства:
- approval одноразовый;
- TTL approval: 15 минут;
- approval привязан к decision id, tool, capability, arguments hash и dry-run preview hash;
- новое approval инвалидирует старое активное approval по той же decision;
- непосредственно перед исполнением повторно проверяются:
  - текущий status decision;
  - tool/capability;
  - Permission Gate;
  - глобальный `execute_planned_action`;
  - arguments hash;
  - текущий dry-run preview hash;
  - срок действия approval;
- если состояние изменилось, approval становится stale/invalidated, действие не выполняется, а решение возвращается в `pending` для нового одобрения;
- successful/failed execution consumes approval, поэтому повторно использовать его нельзя.

Для `project.write_text` dry-run включает состояние существующего файла и SHA-256. Перед перезаписью существующего файла создаётся локальный backup в `.aishin_backups/`; backup-папка исключена из Git. Tool result содержит rollback metadata и SHA-256 до/после. Для нового файла rollback metadata помечает удаление созданного файла как отдельное действие, требующее самостоятельного разрешения.

Хранилище:
- `execution_approvals`
- `execution_attempts`

API:
- `GET /api/assistant/execution/approvals`
- `GET /api/assistant/execution/attempts`

Live Brain содержит узел `Execution Guard`.

Schema migration: `8`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Approval / Execution runtime
Approval / Execution Coordinator подтверждён GitHub Actions:
- run id: `36992853640`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.

Во время интеграции CI обнаружил ошибочную раннюю передачу coordinator в PlannerBuilder; она была исправлена до итогового зелёного run.


## Cloud.ru Resilience
Cloud.ru provider теперь использует ограниченную сетевую устойчивость без бесконечных повторов.

Политика:
- retry только для временных состояний: HTTP `408`, `429`, `500`, `502`, `503`, `504`, timeout и сетевые ошибки;
- default `max_retries=2`, жёсткая верхняя граница `4`;
- exponential backoff с default base `0.5s` и max `4s`;
- `Retry-After` учитывается, но также ограничивается max backoff;
- timeout ограничен диапазоном 5–300 секунд;
- health `/models` кэшируется по умолчанию на 30 секунд;
- health cache защищён lock для параллельных запросов;
- HTTP body ошибки не выводится наружу, Authorization/API key не попадает в diagnostic error;
- AIReply и EmbeddingReply содержат attempts, latency_ms, error_code и безопасные metadata.

Переменные окружения:
- `AISHIN_CLOUDRU_TIMEOUT`
- `AISHIN_CLOUDRU_MAX_RETRIES`
- `AISHIN_CLOUDRU_BACKOFF_BASE`
- `AISHIN_CLOUDRU_MAX_BACKOFF`
- `AISHIN_CLOUDRU_HEALTH_TTL`

API:
- `GET /api/assistant/ai-diagnostics`

## Per-request Cognitive Trace Isolation
Глобальный mutable `last_cognitive_context` удалён.

Каждый `respond()` теперь:
1. создаёт уникальный `request_id`;
2. ведёт собственную рабочую cognitive trace;
3. после Cloud.ru/fallback сохраняет её отдельной строкой в SQLite;
4. возвращает `request_id` и `trace_id`;
5. `snapshot()` читает последнюю завершённую трассу по scope, а не общий Python-словарь.

Хранилище:
- `cognitive_request_traces`

Сохраняются:
- request_id;
- scope;
- query;
- trace status;
- working-memory trace JSON;
- provider runtime metadata;
- created_at.

API:
- `GET /api/assistant/cognitive-traces`

Это устраняет прежнюю гонку, при которой два параллельных запроса могли перезаписать один `last_cognitive_context`.

Schema migration: `9`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Cloud resilience + trace isolation runtime
Функциональный код подтверждён GitHub Actions:
- run id: `36994225453`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.

Первый итоговый run обнаружил порядок self-check: resilience-проверка обращалась к `engine` до его создания. Ошибка исправлена, повторный run прошёл полностью.


## Performance Observability / Latency Budget
Каждый `respond()` теперь измеряет время основных стадий и связывает замеры с тем же `request_id`, что и cognitive trace.

Измеряемые стадии:
- `input_setup`
- `memory_consolidation`
- `graph_builder`
- `planner_builder`
- `cognition`
- `sensors_metacognition`
- `verification`
- `logic_pipeline`
- `context_orchestrator`
- `cloud`
- `postprocess`

Soft budgets по умолчанию:
- memory consolidation: 500 ms
- graph builder: 500 ms
- planner builder: 500 ms
- cognition: 700 ms
- sensors + metacognition: 500 ms
- verification: 2500 ms
- logic pipeline: 1000 ms
- context orchestrator: 500 ms
- cloud: 5000 ms
- postprocess: 500 ms
- total: 8000 ms

Budget не прерывает ответ автоматически. Он только помечает `within_budget` / `over_budget`, сохраняет bottleneck и список превышенных стадий. Это позволяет оптимизировать систему по фактическим измерениям.

Хранилище:
- `performance_traces`

API:
- `GET /api/assistant/performance`

Live Brain содержит узел `Latency`, который показывает total ms и bottleneck последнего request.

## Verification trigger policy
Исправлена избыточная эскалация:
- обычный `conversation` без релевантной персональной памяти получает `cautious`, а не автоматически `insufficient_data`;
- отсутствие памяти в обычном разговоре само по себе не считается ошибкой данных;
- explicit `verification` всегда запускает Verification Engine;
- `needs_verification` всегда запускает Verification Engine;
- `action + insufficient_data` запускает Verification Engine;
- обычный `conversation + insufficient_data` сам по себе Verification не запускает.

Это уменьшает лишние повторные memory/graph/sensor/Cloud проверки на простых разговорах.

Schema migration: `10`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Performance + Verification policy runtime
Функциональный код подтверждён GitHub Actions:
- run id: `36994986756`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.


## Proactive Lifecycle Dedupe / Acknowledge
Проактивный контур теперь хранит состояние самого условия отдельно от карточки решения.

Правило:
- один активный fingerprint условия создаёт не более одной decision;
- `approved`, `rejected`, `acknowledged`, `executed` и `failed` не создают повторную карточку, пока исходное условие остаётся активным;
- когда условие реально исчезает, lifecycle становится `resolved`;
- если то же условие появится позже снова, увеличивается `generation`, очищается `last_decision_id`, и разрешается новая карточка.

Для информационных сигналов добавлен отдельный статус:
- `acknowledged` — «принято к сведению», без семантики reject.

Исполняемые решения нельзя acknowledge: для них остаются approve/reject и Execution Coordinator.

Хранилище:
- `proactive_conditions`

Поля состояния:
- scope
- fingerprint
- source
- active
- generation
- last_decision_id
- disposition
- last_seen_at
- resolved_at

API:
- `GET /api/assistant/proactive/conditions`
- `POST /api/assistant/proactive/{decision_id}/acknowledge`

UI:
- для информационного pending-сигнала показывается кнопка «Принято»;
- после acknowledge он не появляется снова при каждом heartbeat, пока условие не исчезнет и не возникнет заново.

Дополнительно устранена race в создании pending proactive decision: при конкурентном INSERT уникальный индекс остаётся последней защитой, а код после SQLite IntegrityError возвращает уже созданную pending-карточку вместо создания дубля.

Schema migration: `11`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Proactive lifecycle runtime
Функциональный код подтверждён GitHub Actions:
- run id: `36995834519`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.


## Knowledge Graph Merge / Audit Suppression
Knowledge Graph upsert теперь сохраняет накопленные свойства сущности вместо полной замены `data_json`.

Merge policy:
- вложенные object/dict объединяются рекурсивно;
- list объединяются без дублей;
- новые непустые scalar-значения обновляют соответствующее поле;
- `null` не стирает существующее значение;
- пустая строка не стирает существующее непустое значение;
- удаление знания не происходит неявно через обычный upsert.

Audit policy:
- `graph_changes` создаётся только если entity/relation действительно создана или изменилась;
- повторный startup seed с теми же сущностями и связями не создаёт ложные audit-события;
- неизменившийся entity не получает искусственный `updated_at`;
- relation audit также подавляется, если confidence/evidence не изменились.

Действия audit теперь различаются:
- `entity_create`
- `entity_update`
- `relation_create`
- `relation_update`

Поиск Knowledge Graph исправлен для Unicode/кириллицы:
SQLite `LOWER()` не обеспечивал корректный case-insensitive поиск русского текста. Поиск теперь использует Python `casefold()` и проверяет canonical name + сериализованные data.

Это исправило случай, когда существующая сущность `Айшин` не находилась запросом после нормализации регистра.

Verification-compatible shape подтверждён:
- `canonical_name`
- `entity_type`
- `data` как dict

Новых таблиц для этого этапа не потребовалось.
Schema остаётся `11`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Knowledge Graph runtime
Функциональный код подтверждён GitHub Actions:
- run id: `36996825381`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.

Первый усиленный self-check обнаружил старую Unicode-проблему поиска кириллицы. После замены SQLite LOWER-поиска на Unicode-safe casefold повторный run прошёл полностью.


## Tool Registry Atomic Write Hardening
`project.write_text` теперь пишет файлы атомарно.

Write pipeline:
1. проверяется текущий SHA-256 / отсутствие файла;
2. при наличии `expected_sha256` состояние должно совпасть;
3. для существующего файла создаётся backup;
4. backup записывается атомарно и его SHA-256 сверяется с исходным файлом;
5. новое содержимое записывается во временный файл в той же директории;
6. temp file получает `flush + fsync`;
7. выполняется `os.replace()`;
8. директория fsync-ится там, где ОС это поддерживает;
9. итоговый SHA-256 сверяется с записанными байтами.

Execution Coordinator дополнительно передаёт внутренний `_expected_sha256` из свежего pre-execution preview. Поэтому изменение файла даже в узком окне между revalidation и записью блокирует write.

Для нового файла используется специальный precondition `__missing__`: если файл успел появиться после проверки, запись отменяется.

### Rollback hardening
В Tool Registry добавлен destructive tool:
- `project.rollback_write`

Он всегда требует новое явное approval перед реальным выполнением, даже если capability `modify_files` когда-либо будет переведена в `allow`.

Rollback существующего файла:
- target должен всё ещё иметь `after_sha256` исходной операции;
- backup должен находиться строго внутри `.aishin_backups/`;
- backup SHA-256 должен совпасть с сохранённым `backup_sha256`;
- восстановление выполняется атомарно;
- итоговый SHA-256 проверяется повторно.

Rollback нового файла:
- удаление разрешено только если текущий SHA-256 совпадает с `after_sha256`;
- если файл был изменён позже, rollback блокируется;
- после unlink выполняется fsync директории там, где поддерживается.

API:
- `POST /api/assistant/execution/attempts/{attempt_id}/rollback`

Первый вызов с `approved=false` возвращает preview / `approval_required`.
Реальный rollback выполняется только отдельным запросом с новым `approved=true`, и Permission Gate проверяется заново непосредственно Tool Registry.

Обычный доступ к `.aishin_backups/` остаётся запрещён; rollback использует отдельную внутреннюю проверку пути только для backup metadata.

Новых таблиц не потребовалось.
Schema остаётся `11`.
Версия приложения остаётся `0.0.3`.

### Подтверждение atomic write / rollback runtime
Функциональный код подтверждён GitHub Actions:
- run id: `36998386131`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.

Self-check во временной директории подтвердил:
- atomic replace;
- expected SHA-256 guard;
- backup integrity;
- rollback restore;
- destructive rollback tool.

Первый runtime smoke ожидал HTTP 400 для нелокального rollback-теста, но local-only guard корректно вернул 403. Тест был исправлен так, чтобы 403 считался правильной защитой.


## Continuous Learning Engine
Aishin получила постоянный фоновый контур самообучения вокруг основной модели.

Worker автоматически стартует вместе с FastAPI lifecycle и корректно останавливается при завершении приложения. Ручного переключателя режимов нет.

Автоматические режимы:
- `REALTIME` — пользователь активен; обрабатывается только небольшой batch, чтобы обучение не мешало разговору;
- `BACKGROUND` — есть накопленная очередь и пользователь не активен;
- `IDLE` — обучающей работы нет;
- `MAINTENANCE` — длительный простой + пришло время обслуживания.

Текущая политика выбора:
- активность пользователя за последние ~45 секунд → `REALTIME`;
- idle >= 30 минут и maintenance overdue → `MAINTENANCE`;
- есть очередь → `BACKGROUND`;
- иначе → `IDLE`.

Источники обучения:
- EventBus events;
- performance traces;
- explicit Logic Learning feedback;
- memory_changes;
- graph_changes;
- execution_attempts.

Continuous Learning не использует hidden chain-of-thought и не считает собственные ответы доказательством успеха.

### Что именно изучается
Локальный Pattern Learner агрегирует:
- повторяющиеся bottleneck stages;
- успешность/ошибки Tool Registry;
- подтверждённые outcomes Logic Learning;
- частоту типов memory/graph changes;
- системные event patterns.

Паттерны хранят observations, successes, failures, score и ограниченную evidence history.

В будущий prompt попадают только накопленные operational patterns с достаточным числом наблюдений. Они маркируются как опыт системы, а не как факты о мире, и не имеют права обходить Verification, Permission Gate или текущие evidence.

### 24/7 поведение
Worker проверяет режим примерно раз в 15 секунд, но не создаёт пустую audit-строку на каждом цикле.

Cycle history пишется только:
- при смене режима;
- при наличии/обработке очереди;
- во время maintenance;
- либо как редкий heartbeat примерно раз в 5 минут.

Это предотвращает бессмысленный рост SQLite при круглосуточной работе.

Maintenance:
- возвращает зависшие `processing` items обратно в очередь;
- удаляет завершённые queue items старше 7 дней;
- не удаляет пользовательскую память.

Cloud.ru для фонового самообучения v1 не вызывается постоянно: `cloud_used=false`. Основной learning loop локальный, поэтому 24/7 режим не создаёт постоянную стоимость API.

Хранилище:
- `continuous_learning_state`
- `continuous_learning_queue`
- `learning_patterns`
- `continuous_learning_cycles`

API:
- `GET /api/assistant/continuous-learning/status`
- `GET /api/assistant/continuous-learning/cycles`
- `GET /api/assistant/continuous-learning/patterns`
- `GET /api/assistant/continuous-learning/queue`

Live Brain содержит узел `Continuous Learning` с текущим mode, pending queue и learned patterns.

Важно: Continuous Learning работает постоянно, пока запущен процесс Aishin. Для работы после перезагрузки Windows нужен отдельный OS autostart/service слой.

Schema migration: `12`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Continuous Learning runtime
Функциональный код подтверждён GitHub Actions:
- run id: `37000341016`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.


## Learning Quality Gate / Strategy Evolution / Drift & Decay
Continuous Learning больше не использует любой накопленный pattern сразу.

Каждый learned pattern проходит lifecycle:
- `candidate` — слишком мало наблюдений;
- `observed` — повторяется, но доверия ещё недостаточно;
- `trusted` — достаточно повторных evidence, эффективный score стабилен, противоречивость приемлема;
- `deprecated` — паттерн устарел или стабильно показывает низкое качество.

### Pattern Quality Gate
Для каждого pattern рассчитываются:
- raw score;
- effective score после decay;
- decay factor;
- contradiction rate;
- age in days;
- lifecycle reason.

Default pattern half-life: 30 дней.
После длительного отсутствия свежих evidence score постепенно тянется к нейтральному 0.5.
После 120 дней без свежего подтверждения pattern может стать `deprecated`.

`trusted` pattern требует повторных наблюдений и достаточного effective score.
Высокая противоречивость блокирует promotion в trusted.

В cognition попадают только `trusted` operational patterns из разрешённых категорий.
`candidate`, `observed` и `deprecated` не выдаются модели как подтверждённый опыт.

### Strategy Evolution
Logic Learning теперь использует отдельный quality state для каждой strategy.

Рассчитываются:
- raw reliability;
- effective reliability;
- evidence count;
- decay factor;
- recent drift score;
- lifecycle;
- rank внутри Logic Mode.

Default strategy half-life: 45 дней.

Положительная стратегия может стать `trusted` только после достаточного числа explicit user feedback outcomes.
Сильный recent negative drift снимает доверие и возвращает strategy в `observed`.
Стабильно слабая или сильно устаревшая strategy становится `deprecated`.

`LogicLearning.recommend()`:
- исключает deprecated strategies;
- сначала предпочитает trusted;
- затем observed;
- затем candidate;
- внутри группы сортирует по effective reliability и подтверждённым outcomes.

Таким образом старая когда-то успешная стратегия не остаётся «лучшей навсегда».

### Drift
Drift сравнивает последние explicit feedback outcomes strategy с её историческим failure rate.

Если последние результаты заметно хуже долгосрочной истории:
- drift_score растёт;
- promotion блокируется;
- trusted strategy может потерять приоритет.

Assistant-generated ответы по-прежнему не считаются success feedback.

### Хранилище
- `learning_pattern_quality`
- `strategy_quality_state`
- `learning_quality_events`

Quality events записываются при изменении lifecycle, поэтому можно видеть promotion/deprecation history.

API:
- `GET /api/assistant/continuous-learning/quality`
- `GET /api/assistant/continuous-learning/strategies`
- `GET /api/assistant/continuous-learning/quality-events`

Live Brain теперь показывает число именно `trusted` patterns, а не просто всё накопленное обучение.

Quality Gate работает внутри Continuous Learning worker и также освежается непосредственно перед повторным использованием Logic Learning strategies.

No-op quality refresh не пишет строки в SQLite каждые 15 секунд: запись происходит только при существенном изменении score/drift/rank/lifecycle.

Schema migration: `13`.
Версия приложения остаётся `0.0.3`.

### Подтверждение Learning Quality runtime
Функциональный код подтверждён GitHub Actions:
- run id: `37001952014`;
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall, self-check и FastAPI runtime smoke: success.


## Windows launcher diagnostics
`Aishin.bat` больше не закрывается молча при ошибке запуска.

Launcher:
- проверяет Python 3.11+;
- обнаруживает повреждённую `.venv` и пересоздаёт её;
- проверяет зависимости;
- запускает self-check и runtime smoke;
- проверяет порт `127.0.0.1:8765`;
- если Айшин уже запущена, открывает существующий экземпляр;
- если порт занят другим процессом, показывает понятную ошибку;
- проверяет exit code uvicorn и оставляет окно открытым при сбое;
- пишет диагностический лог в `logs/launcher.log`.

Для CI поддерживается:
`Aishin.bat --check-only`

Windows launcher preflight подтверждён GitHub Actions run `37003479979`.


## Chat-first interface redesign
Главная страница Aishin полностью переработана в chat-first интерфейс.

Новый порядок:
- Айшин и чат находятся на первом экране и являются главным рабочим пространством;
- справа показывается только краткое состояние: память, задачи, знания, решения и самообучение;
- блок «Как я сейчас думаю» сокращён до понятных стадий: понимаю → вспоминаю → проверяю → отвечаю;
- «Айшин заметила» оставлена отдельным блоком только для действительно требующих внимания решений;
- все 19 внутренних cognitive nodes, события, сенсоры, latency, execution guard и техническая диагностика перенесены в сворачиваемый «Технический мозг Айшин»;
- пользовательская часть переведена с внутренних терминов типа IDLE, queue, trusted, claims, confidence на понятные русские статусы;
- чат получил полноценные bubbles и аватар Айшин.

UI больше не дублирует «Мозг Айшин» на главном экране и не заставляет пользователя читать внутреннюю телеметрию до начала разговора.

CI теперь дополнительно выполняет:
- `node --check app/static/app.js`;
- UI structure smoke test для chat form, compact status, technical brain и approval center.

Подтверждено GitHub Actions run `37004855074`:
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success.


## Cloud.ru settings + Live Technical Brain + ZIP updater
Добавлен полноценный локальный раздел `Настройки → Cloud.ru`.

Cloud.ru settings:
- API-ключ вводится в password-поле;
- сохраняется только в локальный `.env`;
- `.env` остаётся исключённым из Git;
- API никогда не возвращает значение ключа обратно в браузер;
- после сохранения поле очищается;
- AIManager и связанные cognitive компоненты перезагружают provider settings без ручного редактирования файла;
- кнопка «Проверить подключение» выполняет реальный health-check Cloud.ru.

API:
- `GET /api/settings/cloudru`
- `POST /api/settings/cloudru`
- `POST /api/settings/cloudru/test`

### Live Technical Brain
Сворачиваемый «Технический мозг Айшин» сохранён.

Внутри добавлена живая SVG-сеть:
- линии связывают cognitive nodes;
- активные связи анимируются как поток сигнала;
- attention paths визуально выделяются;
- активные узлы пульсируют;
- при открытом Technical Brain dashboard обновляется примерно каждые 3 секунды;
- при закрытом блоке polling снижается примерно до 20 секунд;
- блок по-прежнему можно открыть и закрыть обычным `details/summary`.

Визуализация основана на фактическом runtime state, а не является декоративной имитацией скрытого chain-of-thought.

### ZIP-safe updater
Исправлена ошибка:
`git fetch origin main returned non-zero exit status 128`

Updater теперь сам выбирает режим:
- если проект является Git checkout → `git fetch + git pull --ff-only`;
- если проект скачан ZIP и папки `.git` нет → безопасное обновление из GitHub main ZIP.

ZIP mode сохраняет локальные данные:
- `.env`;
- `.git`;
- `.venv`;
- `.aishin_backups`;
- `data/`;
- `logs/`.

API:
- `GET /api/system/update/status`
- `POST /api/system/update`

После обновления UI сообщает, нужен ли перезапуск Aishin.bat.

CI дополнительно проверяет:
- отсутствие API key в Cloud settings response;
- updater mode `git|zip`;
- JavaScript syntax;
- Windows launcher;
- Cloud settings/updater modules.

Подтверждено GitHub Actions run `37006308613`:
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success.


## Self-Reflection Metrics + Learning Planner + Safe Experiment Manager + Context Budgeter

Следующий слой самообучения реализован поверх Continuous Learning и Learning Quality Gate без повышения версии приложения.

### Self-Reflection Metrics
После каждого фактического ответа ядро детерминированно оценивает наблюдаемые сигналы качества:
- доступность AI-провайдера;
- confidence Metacognition;
- Decision Quality;
- unresolved evidence и contradictions;
- latency/budget status;
- явные пользовательские сигналы повторного исправления.

Self-Reflection не просит LLM «оценить саму себя» и не считает собственный ответ доказательством успеха.

Хранилище:
- `self_reflection_runs`

API:
- `GET /api/assistant/self-reflection`

### Learning Planner
Learning Planner агрегирует повторяющиеся слабые места Self-Reflection и создаёт отдельные learning objectives только после накопления измеряемых сигналов.

Примеры целей:
- уменьшение пользовательских исправлений;
- повышение evidence/confidence;
- снижение reasoning latency;
- повышение устойчивости к сбоям провайдера;
- повышение средней измеряемой response quality.

Хранилище:
- `learning_plans`
- `learning_plan_events`

API:
- `GET /api/assistant/learning-plans`

### Safe Experiment Manager
Эксперименты работают только в `shadow`-режиме:
- активная логика не заменяется автоматически;
- baseline и candidate сравниваются отдельно;
- требуется минимум накопленных наблюдений;
- promising candidate получает только статус `ready_for_review`;
- автоматическое promotion запрещено.

Хранилище:
- `safe_experiments`
- `experiment_observations`

API:
- `GET /api/assistant/safe-experiments`

### Context Budgeter
Финальный бюджет применяется непосредственно перед вызовом Cloud.ru, то есть после сборки personality, memory, graph, planner, verification, logic и остальных динамических блоков.

Budgeter:
- имеет отдельный token budget для FAST/DEEP/VERIFY/PLAN/DIAGNOSE;
- резервирует место для ответа модели;
- сначала удаляет старую историю;
- затем при необходимости сокращает низкоприоритетную часть system context;
- сохраняет отчёт до/после для диагностики;
- не удаляет исходные данные из долговременной памяти.

Хранилище:
- `context_budget_reports`

API:
- `GET /api/assistant/context-budget`

Schema migration: `14`.
Версия приложения остаётся `0.0.3`.

### Подтверждение runtime
GitHub Actions run `37008371575`:
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall: success;
- self-check: success;
- FastAPI runtime smoke: success;
- Windows launcher check-only: success.



## Reflective Learning Technical Brain UI

«Технический мозг Айшин» расширен живым циклом развития:
`Самоанализ → План обучения → Эксперимент → Проверка → Закрепление`.

Новые узлы работают от фактического runtime state:
- **Самоанализ** — показывает quality score и слабые места Self-Reflection;
- **План обучения** — показывает активные learning objectives и их приоритет;
- **Эксперимент** — показывает shadow experiments, число наблюдений и baseline/candidate;
- **Проверка** — выделяет experiments со статусом `ready_for_review`;
- **Закрепление** — показывает число действительно `trusted` learning patterns.

Добавлена отдельная панель «Цикл развития» с:
- качеством последнего/среднего ответа;
- списком слабых мест;
- текущими целями обучения;
- состоянием безопасных экспериментов;
- фактическим Context Budget до/после сокращения.

Нейронные SVG-связи дополнены отдельным контуром развития. Визуализация использует сохранённые runtime-метрики и не отображает скрытый chain-of-thought.

Подтверждено GitHub Actions run `37009020927`:
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- JavaScript syntax: success;
- self-check: success;
- FastAPI runtime smoke: success;
- Windows launcher check-only: success.

Версия приложения остаётся `0.0.3`. Schema остаётся `14`.


## Weighted Evidence Self-Learning

Continuous Learning усилен системой веса доказательств.

Новые источники обучения:
- Self-Reflection Metrics;
- Context Budget reports;
- Safe Experiment observations;
- прежние sources: explicit Logic Learning feedback, execution results, performance, memory/graph changes and events.

Каждый сигнал теперь имеет evidence weight:
- explicit user success/failure feedback: 1.00;
- real tool execution outcome: 0.95;
- Self-Reflection: 0.85;
- performance: 0.70;
- Context Budget pressure: 0.60;
- memory/graph changes: 0.55/0.50;
- ordinary events: 0.35;
- shadow experiment observation: 0.35.

Добавлена таблица `learning_evidence_metrics`:
- weighted_observations;
- weighted_successes;
- weighted_failures;
- evidence_confidence;
- source_types_json;
- last_signal_weight.

Learning Quality Gate теперь учитывает не только число повторов, но и доказательную массу. Паттерн не может стать `trusted` только потому, что слабая телеметрия повторилась много раз.

Для `trusted` pattern теперь требуются:
- минимум 5 обычных observations;
- weighted evidence strength >= 3.5;
- evidence confidence >= 0.62;
- effective score >= 0.62;
- отсутствие чрезмерных противоречий и staleness.

Shadow experiments не дают success/failure reinforcement и не могут подтверждать сами себя.

Self-check содержит отдельный regression test:
- 6 слабых event-signals остаются ниже `trusted`;
- 6 сильных explicit-feedback signals достигают `trusted`.

Schema migration: `15`.
Версия приложения остаётся `0.0.3`.

Подтверждено GitHub Actions run `37010233186`:
- Ubuntu / Python 3.11: success;
- Windows / Python 3.11: success;
- compileall: success;
- JavaScript syntax: success;
- self-check: success;
- FastAPI runtime smoke: success;
- Windows launcher check-only: success.
