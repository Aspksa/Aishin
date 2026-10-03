# Aishin 00.00.15 — Canonical Facts & Evidence Fusion

## Цель

00.00.15 вводит отдельный слой строгой идентичности фактов поверх Document Intelligence, Autonomous Research, Memory, Knowledge Graph и Knowledge Lifecycle.

Слой отвечает на вопросы:

1. Какие записи действительно описывают один и тот же атомарный факт?
2. Какие значения у этого факта наблюдались?
3. Какие источники независимы, а какие являются производными копиями?
4. Какое значение актуально сейчас?
5. Что было заменено новой версией документа?
6. Где существует настоящий unresolved conflict?
7. Из каких конкретных source records состоит provenance?

## Базовый принцип

**Semantic similarity не является identity.**

Fusion Engine не объединяет утверждения по похожести текста, embedding similarity или LLM-оценке.

Автоматическое объединение разрешено только если присутствует:

- одинаковый строгий canonical key;
- либо доказуемая lineage-связь к уже существующему canonical fact.

Это защищает долговременную память от ложного слияния похожих, но разных фактов.

## Модель данных

`canonical_facts` хранит идентичность факта:

- scope;
- canonical_key;
- namespace;
- subject;
- predicate;
- fact_type;
- state;
- current value;
- confidence;
- число независимых групп;
- число активных evidence;
- число конфликтующих values.

`canonical_fact_values` хранит все наблюдавшиеся значения одного факта.

Состояния value:

- `observed`;
- `supported`;
- `verified`;
- `conflicted`;
- `superseded`.

`canonical_fact_evidence` — evidence ledger. Для каждой записи сохраняются:

- source_type;
- source_ref;
- source_group;
- independence_group;
- source_record_type / source_record_id;
- stance;
- is_independent;
- confidence;
- lineage_root;
- provenance;
- excerpt;
- active / historical state.

`canonical_fact_links` связывает canonical fact с Research Claim, Memory, Graph entity/relation, Knowledge Lifecycle claim и другими persisted records.

`canonical_fact_events` хранит immutable audit transitions.

## Document Facts

### Structured facts

Для `key_value` и `ai_grounded`, когда subject не равен generic `document`, canonical key строится из Document Intelligence `fact_key`.

Это позволяет двум независимым документам подтвердить один и тот же атомарный факт.

Пример:

- Document A: `Engine power → 100 kW`;
- Document B: `Engine power → 100 kW`.

Если их document families независимы, Fusion видит две independence groups.

### Generic metadata

`mentions_date`, `mentions_amount`, `mentions_percent`, email, URL и другие generic document-level facts не получают глобальную identity.

Их canonical key включает family/document identity.

Это предотвращает ложное объединение, например, всех дат из разных документов в один «факт даты».

## Independence

Количество строк evidence не равно количеству независимых подтверждений.

Для документов:

`document_family:<family_key>`

является independence group.

Несколько версий одного документа принадлежат одной группе и не повышают доказательность как независимые источники.

Для Research используется уже существующий `research_evidence.source_group`.

`derived_knowledge` не является независимым источником.

Promoted Memory и Knowledge Graph records не получают новый independent vote.

## Value scoring

Primary evidence агрегируется сначала внутри independence group: повтор одного источника не умножает его вес.

Value может стать:

- `verified`: минимум 3 независимые группы со средней confidence >= 0.72, либо минимум 2 группы со средней confidence >= 0.85;
- `supported`: минимум 2 группы со средней confidence >= 0.60, либо один сильный источник >= 0.85;
- `observed`: evidence есть, но порог support не достигнут;
- `conflicted`: есть сильная независимая opposing evidence;
- `superseded`: значение исторически заменено более новой версией.

Эти пороги измеряют evidence support, а не абсолютную истину.

## Document Version Lineage

Автоматическое supersession допустимо только когда:

- значения относятся к одному canonical fact;
- evidence относится к одной непустой document family;
- существует однозначно более новая версия через `version_rank` или `previous_version_id`.

При выполнении условий старое value получает:

- state=`superseded`;
- `superseded_by_value_id`;
- `superseded_at`;
- audit event `value_superseded_by_document_version`.

Старое значение не удаляется.

Если значения пришли из разных независимых families, Fusion не выбирает «победителя» автоматически — fact становится `conflicted`.

## Research

Research Claim получает canonical key:

`research:<claim_key>`

Сам claim не считается evidence самому себе.

Fusion импортирует underlying `research_evidence` из `support_evidence_json` и `contradiction_evidence_json`.

Если trusted claim был promoted в Memory и Knowledge Graph:

`Research Claim → Memory → Graph entity`

Memory и Graph сохраняются в `canonical_fact_links` как `derived_promotion`, но число independence groups не увеличивается.

## Memory

Memory с явным `memory_key` может стать отдельным canonical assertion.

Memory, созданная из trusted Research Claim, не создаёт новый fact и связывается обратно с:

`research:<claim_key>`

как derived lineage.

Memory без `memory_key` не подвергается автоматическому fuzzy fusion.

## Knowledge Graph

Graph relation получает отдельную canonical assertion identity.

Knowledge Graph рассматривается как derived world model, поэтому relation сама по себе:

- доступна через canonical ledger;
- сохраняет lineage/provenance;
- не считается независимым первичным доказательством;
- не может самостоятельно сделать fact verified.

## Knowledge Lifecycle projection

Canonical Facts является слоем evidence fusion; Knowledge Lifecycle — слоем жизненного цикла знания.

Чтобы избежать double scoring, Lifecycle не повторяет вычисление independence.

Canonical fact проецируется как `origin_type='canonical_fact'` с:

- canonical key;
- current normalized value;
- canonical state;
- confidence;
- provenance summary;
- underlying independence groups.

При смене текущего supported/verified canonical value старый canonical lifecycle claim получает `superseded`.

## Retrieval and Response Grounding

`reasoning_evidence()` выдаёт только `supported` и `verified` canonical facts, релевантные текущему запросу по детерминированному lexical overlap.

Для каждого canonical fact наружу возвращаются underlying primary independence groups.

Evidence получает trust boundary:

`derived_canonical_projection`

Таким образом:

- модель может использовать persisted canonical knowledge;
- Response Grounding видит реальную evidence-опору;
- canonical projection не создаёт новый независимый source group поверх первичных источников.

## Lazy-fresh synchronization

Fusion не пересчитывает все документы на каждый запрос.

Перед использованием вычисляется дешёвая source signature для:

- grounded Document Facts;
- Research Claims;
- active keyed Memory;
- Knowledge Graph relations;
- Research Claim graph entities.

Если signature не изменилась, используется существующий ledger.

Если изменилась — запускается sync.

Старые source evidence не удаляются: они получают `active=0`, после чего текущие persisted source records реактивируются. Это сохраняет историю и не позволяет удалённому/заменённому evidence продолжать влиять на текущий score.

## Scope isolation

Все facts, values, evidence, links и events имеют scope.

Fusion никогда не объединяет данные разных scopes.

`personal`, `project:aishin` и тестовые/будущие project scopes полностью разделены.

## API

Read:

- `GET /api/assistant/canonical-facts`
- `GET /api/assistant/canonical-facts/facts`
- `GET /api/assistant/canonical-facts/facts/{fact_id}`
- `GET /api/assistant/canonical-facts/history`

Mutation:

- `POST /api/assistant/canonical-facts/sync`

Manual sync остаётся local-only.

## Technical Brain

Live Brain v5 показывает:

- canonical facts total;
- verified canonical facts;
- conflicted canonical facts;
- superseded historical values;
- independent evidence groups.

24-node BrainFlow не увеличивается искусственно: Canonical Facts — persisted evidence layer, а не отдельная исполняемая reasoning phase.

## Development Metrics

`aishin-development-v2` сохраняется.

Canonical verified facts уже проецируются в Knowledge Lifecycle, поэтому повторно начислять за них отдельный вес означало бы double counting.

В counters добавляются canonical metrics только для прозрачности.

## Validation contract

Runtime smoke обязан доказать:

- два независимых document families могут подтвердить один structured fact;
- generic metadata разных документов не объединяется глобально;
- новая версия одной family создаёт audited value supersession;
- разные independent families с разными значениями остаются conflicted;
- Research underlying evidence сохраняет независимые groups;
- promoted Memory/Graph не добавляют ложные votes;
- Graph relation без primary evidence не self-confirms;
- verified canonical fact проецируется в Knowledge Lifecycle;
- reasoning evidence сохраняет underlying source groups;
- sync идемпотентен;
- scope isolation сохраняется;
- API и history доступны;
- mutation sync защищён local-only;
- Live Brain содержит Canonical Facts;
- schema = 26;
- health version = 0.0.15;
- Ubuntu/Windows runtime checks зелёные;
- Ubuntu проходит настоящий headless Chrome;
- Windows проходит `Aishin.bat --check-only`.

## Намеренно не реализовано в 0.0.15

- fuzzy/embedding auto-merge разных canonical keys;
- LLM-решение «эти два факта одинаковые» без явного ключа;
- автоматический выбор победителя между независимыми конфликтующими families;
- превращение Graph/Memory derived copies в независимые доказательства;
- уничтожение исторических values;
- второй самостоятельный вес canonical facts в Development Score.
