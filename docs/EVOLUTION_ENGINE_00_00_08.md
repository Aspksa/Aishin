# Aishin 00.00.08 — Evolution Engine / Self-Learning 2.0

## Цель релиза

00.00.08 превращает накопление опыта в управляемый мета-обучающийся контур.

Айшин теперь различает:

1. данные;
2. знания;
3. навыки;
4. стратегии;
5. качество выполнения;
6. пробелы обучения;
7. экспериментальные политики;
8. подтверждённые champion-политики;
9. регрессии;
10. перенос опыта между областями.

Главная идея:

**Айшин должна учиться не только на задачах, но и на том, какие способы обучения и решения действительно улучшают измеряемый результат.**

Это bounded evolution.

Evolution Engine не переписывает исходный код, не меняет веса внешней AI-модели и не получает новый путь для выполнения опасных действий.

---

## Версии

Aishin Core: 0.0.8

Database schema: 20

Evolution Engine: aishin-evolution-engine-v1

Evolution formula: bounded-meta-learning-v1

Live Brain runtime: aishin-live-brain-v3

Live Brain Export: 6

---

## Место в архитектуре

До этого существовали:

- Continuous Learning;
- Learning Quality Gate;
- Self Reflection;
- Learning Planner;
- Safe Experiments;
- Long-Term Growth;
- Cognitive Intelligence;
- Proactive Intelligence.

00.00.08 добавляет над ними мета-контур:

Outcome Evidence
→ Capability Fitness
→ Learning Gap
→ Curriculum
→ Challenger Policy
→ Shadow / Limited Traffic
→ Conservative Evidence Gate
→ Champion
→ Regression Watch
→ Rollback
→ New Generation

---

## Что считается эволюцией

Эволюция — это не рост количества записей.

Она фиксируется только тогда, когда система может показать:

- какой capability изменился;
- на каких completed routes это основано;
- какая политика была baseline;
- какой challenger проверялся;
- сколько evidence набрано;
- какой outcome получен;
- вырос или снизился unresolved rate;
- почему произошёл promotion или rollback.

---

## Capability Fitness

Для каждой task family строится отдельный профиль.

Поддерживаемые family:

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

Каждая capability хранит:

- sample_count;
- success_rate;
- unresolved_rate;
- average_outcome;
- recent_outcome;
- baseline_outcome;
- trend;
- confidence;
- learning_gap;
- fitness;
- last_evidence_at.

Fitness рассчитывается из реальных завершённых Cognitive Intelligence routes.

Сама формула не является IQ и не утверждает человеческую интеллектуальную способность.

---

## Learning Gap

Learning Gap показывает, насколько измеренная область требует дополнительного развития.

Gap растёт при:

- низком fitness;
- отрицательном recent trend;
- высоком unresolved rate;
- слабой evidence confidence.

Gap используется для Curriculum, но не для автоматического изменения фактов в памяти.

---

## Self Curriculum

Evolution Engine автоматически создаёт curriculum из измеренных слабых мест.

Источники:

### Task-family gaps

Если накоплено достаточно samples и наблюдается:

- слабый fitness;
- отрицательный trend;
- высокий unresolved rate,

создаётся curriculum item.

Типовые цели:

- повысить outcome quality;
- снизить unresolved rate;
- стабилизировать recent outcome;
- проверить более надёжную routing policy.

### Skill gaps

Для growth skills учитываются:

- lifecycle=fading;
- mastery;
- reliability;
- freshness;
- evidence_count.

Curriculum никогда не повышает mastery сам по себе.

Он формирует направление обучения.

Высокоприоритетные curriculum items зеркалируются в существующий Learning Planner через target_metric вида:

evolution:<item_key>

Таким образом новый слой не создаёт вторую изолированную систему планов.

---

## Champion / Challenger

Для task family может существовать:

- baseline;
- challenger;
- champion;
- retired;
- rolled_back.

### Baseline

Поведение Cognitive Intelligence без новой эволюционной политики.

### Challenger

Новая bounded runtime-policy.

Challenger не получает весь трафик.

По умолчанию:

traffic_fraction = 0.25

Assignment детерминирован по request_id.

Это позволяет:

- воспроизводить распределение;
- не менять поведение всех задач сразу;
- сравнивать результат постепенно.

### Champion

Challenger становится champion только после Evidence Gate.

### Retired

Политика проиграла либо была заменена.

### Rolled Back

Champion показал подтверждённую регрессию и был автоматически снят.

---

## Какие параметры разрешено эволюционировать

Только bounded runtime-политики:

- preferred_mode;
- context_multiplier;
- verification_bias;
- traffic_fraction;
- evidence thresholds.

Не разрешено автоматически менять:

- Python source;
- JavaScript source;
- database schema;
- Permission Gate;
- destructive permissions;
- tool capabilities;
- API keys;
- user data;
- system files;
- веса Cloud.ru или другой внешней модели.

---

## Safety Bounds

Mode order:

FAST < PLAN < DEEP < VERIFY < DIAGNOSE

Evolution Engine может повысить rigor.

Он не может его понизить.

Особые инварианты:

### VERIFY

Если base mode = VERIFY, итоговая evolution policy обязана оставить VERIFY.

### DIAGNOSE

Если base mode = DIAGNOSE, итоговая evolution policy обязана оставить DIAGNOSE.

### Context multiplier

Допустимый policy multiplier:

0.90 .. 1.20

Для high-complexity request снижение контекста ниже baseline запрещено.

Для VERIFY и DIAGNOSE снижение контекста запрещено.

---

## Candidate Policy Generation

Новая policy строится только из измеренного состояния family.

### High unresolved rate

Предлагается:

preferred_mode = VERIFY

verification_bias = true

context_multiplier ≈ 1.12

### Negative recent trend

Предлагается:

preferred_mode = DEEP

context_multiplier ≈ 1.10

### Low family fitness

Предлагается усиленный mode на основе evidence по family.

### Stable high-quality family

Разрешается осторожный efficiency trial:

context_multiplier ≈ 0.95

Но только когда:

- fitness высокий;
- unresolved почти отсутствует;
- trend стабилен.

---

## Conservative Evidence Gate

00.00.08 специально не делает promotion по одному среднему числу.

Минимальный challenger evidence:

8 samples

Фактически policy по умолчанию требует больше при сомнительной статистике.

Проверяются:

- mean gain;
- lower confidence bound gain;
- win rate;
- lower confidence bound win rate;
- unresolved rate.

Для conservative gate используется one-sided bound.

Он предназначен как инженерный safety gate.

Это не утверждение о научно доказанной причинности.

Promotion по умолчанию требует:

- mean gain >= 0.04;
- gain lower bound >= 0.01;
- win rate >= 0.65;
- win lower bound >= 0.50;
- unresolved rate <= 0.12.

Таким образом несколько случайно удачных ответов не должны становиться новой глобальной стратегией.

---

## Anti Self-Confirmation

Evolution outcome является runtime quality signal.

Он НЕ становится автоматически новым фактом или trusted knowledge.

Knowledge lifecycle остаётся под:

- evidence;
- Learning Quality Gate;
- trust;
- contradiction handling;
- freshness.

Evolution policy оптимизирует обработку.

Она не определяет истинность содержимого.

---

## Outcome Observation

Каждый Cognitive Intelligence route после завершения передаёт Evolution Engine:

- request_id;
- family;
- outcome_score;
- successful;
- unresolved_count;
- assigned variant.

Assignment хранится отдельно.

Это позволяет отличать:

- baseline;
- champion;
- challenger.

---

## Automatic Evolution Cycles

Cycle запускается:

- на startup;
- вручную из Evolution UI;
- автоматически после каждого пятого completed evolution assignment.

Cycle выполняет:

1. refresh Learning Quality;
2. refresh Long-Term Growth;
3. пересчёт capabilities;
4. пересчёт curriculum;
5. пересчёт transfer map;
6. создание challengers;
7. promotion/retirement;
8. regression detection;
9. rollback;
10. пересчёт evolution state.

---

## Generation

Evolution State хранит generation.

Generation увеличивается, если произошёл:

- promotion;
- rollback.

Это позволяет видеть не просто дату, а изменение adaptive lineage.

UI показывает:

G1
G2
G3
...

---

## Challenger Iteration

Неудачный challenger не блокирует family навсегда.

Variant key включает:

- family;
- generation;
- attempt;
- policy fingerprint.

Если challenger retired, последующий cycle может создать новую попытку.

Это предотвращает замораживание evolution loop после одной ошибки.

---

## Champion Regression Watch

Champion продолжает наблюдаться после promotion.

Для recent window сравниваются:

- outcome score;
- unresolved rate;
- success rate;
- older champion evidence.

Rollback срабатывает при серьёзной регрессии, например:

- recent outcome существенно хуже older baseline;
- unresolved rate резко вырос;
- success rate провалился.

---

## Automatic Rollback

При regression:

champion → rolled_back

Если существует предыдущий подтверждённый champion:

previous retired champion → champion

Если безопасного предыдущего champion нет:

fallback → baseline

То есть система предпочитает потерять адаптацию, а не сохранять деградировавшую policy.

---

## Transfer Learning

00.00.08 строит отдельную таблицу подтверждённого переноса навыков.

Transfer key связывает:

source_family
→ target_family
→ skill_id

Хранятся:

- evidence_count;
- successes;
- failures;
- success_rate;
- confidence;
- status;
- route evidence.

Lifecycle:

candidate → observed → trusted

Trusted transfer требует повторяемого cross-family success.

Один удачный перенос недостаточен.

---

## Anti-Forgetting

Evolution Engine не заменяет Long-Term Growth.

Он использует:

- freshness;
- stability;
- mastery;
- lifecycle;
- evidence_count.

Fading skill автоматически может попасть в Curriculum.

Таким образом забывание становится наблюдаемым направлением восстановления, а не скрытым падением качества.

---

## Evolution State

Persisted state содержит:

- generation;
- evolution_score;
- stability_score;
- plasticity_score;
- learning_velocity;
- active_policy_count;
- challenger_count;
- rollback_count;
- last_cycle_at.

---

## Evolution Score

Evolution Score — здоровье adaptive learning loop.

Он НЕ является IQ.

Компоненты включают:

- capability fitness;
- stability;
- trusted transfer;
- evidence confidence;
- learning velocity.

Высокий score не означает «Айшин знает всё».

Он означает, что adaptive contour имеет устойчивое подтверждённое качество.

---

## Stability

Stability снижается при:

- negative capability trends;
- rollback events;
- подтверждённой деградации.

Высокая stability означает отсутствие измеренной недавней регрессии.

---

## Plasticity

Plasticity отражает способность системы безопасно адаптироваться.

Сигналы:

- challengers;
- open curriculum;
- trusted transfers.

Высокая plasticity не означает, что изменения автоматически хороши.

Качество отдельно проверяется Evidence Gate.

---

## Learning Velocity

Learning Velocity использует:

- positive capability trends;
- trusted transfer;
- curriculum dynamics.

Это измерение темпа подтверждённого улучшения, а не количества записанных событий.

---

## Database Schema 20

Новые таблицы:

### evolution_state

Текущее состояние Evolution Engine.

### evolution_capabilities

Измеренные способности task families.

### evolution_variants

Lineage policies.

### evolution_assignments

Фактическое распределение запросов между baseline/champion/challenger.

### evolution_curriculum

Self-generated learning curriculum.

### evolution_transfers

Cross-family transfer evidence.

### evolution_cycles

История evolution cycle.

### evolution_events

Audit trail:

- challenger_created;
- variant_promoted;
- variant_retired;
- champion_rolled_back;
- другие lifecycle events.

---

## API

### Dashboard

GET /api/assistant/evolution

Возвращает:

- state;
- capabilities;
- variants;
- curriculum;
- transfers;
- cycles;
- events;
- principles.

### Manual Cycle

POST /api/assistant/evolution/cycle

Local-only.

### Capabilities

GET /api/assistant/evolution/capabilities

### Variants

GET /api/assistant/evolution/variants

### Curriculum

GET /api/assistant/evolution/curriculum

### Transfers

GET /api/assistant/evolution/transfers

### Cycles

GET /api/assistant/evolution/cycles

---

## UI — «Эволюция Айшин»

В левом меню добавлен самостоятельный модуль.

Hero показывает:

- Evolution Score;
- Generation;
- Stability;
- Plasticity;
- Learning Velocity;
- Champions;
- Challengers;
- Rollback count.

Далее:

### Capability Fitness

По каждой family:

- fitness;
- learning gap;
- trend;
- confidence;
- samples;
- unresolved.

### Champion / Challenger

Для каждой policy:

- generation;
- lifecycle;
- preferred mode;
- context multiplier;
- verification bias;
- evidence;
- wins;
- losses;
- unresolved;
- gain against baseline.

### Self Curriculum

Показывает:

- приоритет;
- gap;
- progress;
- evidence;
- target metric;
- причину обучения.

### Transfer Learning

Показывает:

source family → target family

и:

- skill id;
- status;
- confidence;
- success rate;
- evidence.

### Evolution History

График:

- evolution score;
- stability.

### Evolution Events

Показываются promotion и rollback.

### Safety Invariants

В UI явно отображаются правила, ограничивающие самоизменение.

---

## Home

На главной появляется компактная Evolution card:

- generation;
- score;
- champions.

Она ведёт прямо в Evolution workspace.

---

## Live Brain

Live Brain runtime:

aishin-live-brain-v3

Добавлены:

- evolution_generation;
- evolution_score;
- evolution_stability;
- evolution_champions;
- evolution_challengers;
- evolution_regressions.

Live Brain Export:

version 6

Provenance явно показывает таблицы Evolution Engine.

Количество исторических cognitive channels остаётся 24.

Evolution является мета-слоем над ними, а не заменой старых каналов.

---

## Development Metrics

Формула старого Development Score не переписывается задним числом.

Добавлены прозрачные counters:

- evolution_generation;
- evolution_score;
- evolution_stability;
- evolution_plasticity;
- evolution_learning_velocity;
- evolution_champions;
- evolution_challengers;
- evolution_rollbacks;
- evolution_open_curriculum;
- evolution_trusted_transfers.

Это позволяет сравнивать старую историю развития без искусственного скачка score.

---

## Основные safety invariants

1. Evolution != source-code self modification.
2. Evolution != external-model weight training.
3. Runtime policy != knowledge truth.
4. Challenger != champion.
5. Average improvement alone != sufficient promotion evidence.
6. VERIFY cannot be downgraded.
7. DIAGNOSE cannot be downgraded.
8. High-complexity context cannot be reduced by evolution.
9. Destructive permissions cannot be changed by Evolution Engine.
10. Permission Gate remains authoritative.
11. Tool execution path remains authoritative.
12. Regression can remove a champion automatically.
13. Absence of a safe previous champion means fallback to baseline.
14. Transfer is trusted only after repeated cross-family evidence.
15. Curriculum is based on measured gaps.
16. Skill mastery is not increased merely because curriculum exists.
17. Evolution Score is not IQ.
18. Hidden chain-of-thought is not stored or exposed.
19. Audit events are persisted.
20. Every adaptive assignment can be traced to a generation and policy.

---

## Runtime Test Contract

00.00.08 runtime smoke uses an isolated evolution scope.

Test flow:

weak software capability
→ challenger creation
→ conservative evidence
→ promotion
→ champion
→ forced regression
→ automatic rollback

Additionally tested:

- Evolution score ranges;
- stability ranges;
- plasticity ranges;
- API structure;
- capability construction from real route rows;
- VERIFY preservation;
- DIAGNOSE preservation;
- context multiplier safety bounds;
- generation increment;
- UI markers;
- Live Brain Evolution integration;
- Live Brain Export v6;
- prohibition of source-code self modification.

---

## Итоговая цепочка развития

00.00.05 Long-Term Growth:
«Что я действительно закрепила?»

00.00.06 Cognitive Intelligence:
«Какой опыт использовать для этой задачи?»

00.00.07 Proactive Intelligence:
«Что изменилось вокруг меня и что важно заметить?»

00.00.08 Evolution Engine:
«Какой способ решения и обучения действительно становится лучше — и когда его нужно откатить?»
