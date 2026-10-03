# Aishin 00.00.14 — Knowledge Lifecycle & Hypothesis Validation

## Цель

00.00.14 превращает разрозненные evidence, hypothesis runs, verification и response grounding в долговременный доказательный жизненный цикл. Новый слой отвечает на пять практических вопросов:

1. Что Айшин сейчас считает известным?
2. Из каких источников это известно?
3. Насколько знание подтверждено независимыми evidence groups?
4. Что изменилось, оказалось противоречивым или было отвергнуто?
5. Какие гипотезы реально подтверждены, а какие только проверяются?

## Жёсткая граница доверия

Текст ответа AI provider никогда не является источником knowledge claim.

В Knowledge Lifecycle могут поступать только evidence, уже находившиеся в reasoning path до генерации ответа: Memory/Verification/Research/Documents/Knowledge Graph/Tool evidence и иные явно маркированные источники.

Response Grounding используется только как сигнал качества ответа. Он может создать learning event о слабом grounding, но не повышает factual claim до verified.

Это предотвращает self-confirmation loop: Айшин не может написать утверждение, затем считать собственный текст доказательством и «научиться» ему как факту.

## Knowledge Claim Lifecycle

Состояния:

- `observed` — claim встретился в evidence, но независимой опоры недостаточно;
- `supported` — claim поддержан минимум двумя независимыми source groups с достаточным качеством;
- `verified` — есть независимая поддержка и clean Verification либо три сильных независимых source groups;
- `contradicted` — найдено сильное связанное counter-evidence;
- `rejected` — opposing evidence доминирует;
- `superseded` — состояние зарезервировано для явной замены старого знания новым без уничтожения истории.

Ни один state не означает абсолютную истину. Это технический уровень доказательной опоры.

## Hypothesis Lifecycle

Долговременный registry отделён от ephemeral `hypothesis_runs`.

Состояния:

- `candidate`;
- `testing`;
- `supported`;
- `confirmed`;
- `rejected`.

Высокий confidence сам по себе не подтверждает гипотезу.

Для `confirmed` нужны одновременно:

- достаточный confidence;
- минимум три независимых support groups;
- отсутствие opposing groups;
- хотя бы один clean Verification pass.

Таким образом, нормализованный score Hypothesis Manager остаётся приоритетом проверки, а не доказательством истины.

## Source independence

Повтор одного и того же документа не считается независимыми подтверждениями.

Independence определяется через `source_group`:

- document:<id>;
- research/manual source group;
- memory/source reference;
- другой provenance group.

Evidence дедуплицируется по subject + group + stance + content hash.

## Audit trail

Каждое изменение claim сохраняется в `knowledge_transitions`.

Каждое изменение долговременной гипотезы сохраняется в `hypothesis_transitions`.

История не стирается при изменении текущего state.

События обучения сохраняются в `knowledge_learning_events`:

- `knowledge_verified`;
- `error_detected`;
- `correction_confirmed`;
- `hypothesis_confirmed`;
- `hypothesis_rejected`;
- `response_grounding_ok`;
- `response_grounding_risk`.

## Schema 25

Добавлены таблицы:

- `knowledge_claims`;
- `knowledge_evidence`;
- `knowledge_transitions`;
- `hypothesis_registry`;
- `hypothesis_evidence`;
- `hypothesis_transitions`;
- `knowledge_learning_events`.

Все основные таблицы имеют scope и индексированы для scoped dashboard/read paths.

## Engine integration

Порядок в request pipeline:

`Logic evidence → Causal → Hypothesis Manager → Knowledge Lifecycle → Counterfactual/Decision → generation → Response Grounding → lifecycle quality event`

Knowledge Lifecycle prompt block передаёт модели только текущие verified/supported claims и предупреждение по contradicted knowledge.

## Development Metrics v2

`aishin-development-v2` больше не использует placeholder confirmed_hypotheses=0.

Knowledge dimension учитывает:

- реальное количество lifecycle claims;
- verified knowledge;
- average confidence supported/verified knowledge;
- memory confidence;
- diversity entity types.

Analytics dimension учитывает реальные confirmed hypotheses.

Это делает рост шкалы зависимым от persisted evidence, а не от декоративного процента.

## Live Brain

Technical Brain получает:

- verified knowledge;
- contradicted knowledge;
- confirmed hypotheses;
- rejected hypotheses;
- errors detected;
- corrections confirmed.

В UI добавлена отдельная карточка «Жизненный цикл знаний».

Safe Trace показывает только эти технические счётчики и не раскрывает hidden chain-of-thought.

## Scope isolation

`personal` и `project:aishin` хранятся и читаются раздельно.

Все lifecycle API требуют/принимают scope и не должны объединять данные разных областей.

## API

- `GET /api/assistant/knowledge-lifecycle`
- `GET /api/assistant/knowledge-lifecycle/claims`
- `GET /api/assistant/knowledge-lifecycle/hypotheses`
- `GET /api/assistant/knowledge-lifecycle/transitions`
- `GET /api/assistant/knowledge-lifecycle/learning-events`

## Validation contract

Runtime smoke обязан проверять:

- один source group не становится verified;
- две независимые evidence + clean Verification могут стать verified;
- связанное strong contradiction переводит claim в contradicted;
- высокий hypothesis confidence без independent evidence не создаёт confirmed;
- audit transitions сохраняются;
- API работает;
- project scope изолирован;
- Live Brain включает Knowledge Lifecycle;
- schema = 25;
- health version = 0.0.14;
- Ubuntu + Windows проходят полный Runtime Check;
- Linux дополнительно проходит настоящий headless Chrome;
- Windows проходит `Aishin.bat --check-only`.

## Что 00.00.14 намеренно не делает

- не считает AI-generated text evidence;
- не выполняет скрытое fine-tuning модели;
- не объявляет lifecycle state абсолютной истиной;
- не удаляет историю ошибочных знаний;
- не объединяет personal/project scopes;
- не auto-confirm hypothesis только из-за confidence;
- не заменяет Verification, Research, Documents или Response Grounding.
