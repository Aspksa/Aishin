# Aishin 00.00.05 — Long-Term Growth

## Цель

00.00.05 добавляет долговременное развитие поверх Live Brain 00.00.04.

Система отвечает не на вопрос «сколько событий произошло», а на более строгие вопросы:

- какие навыки действительно подтверждены повторяемым опытом;
- какие навыки стали устойчивыми;
- какие навыки можно считать освоенными;
- в каких областях сформировалась специализация;
- каким сохранённым знаниям можно доверять сильнее;
- какой опыт начал устаревать;
- почему конкретный показатель вырос или снизился.

## Главный принцип

Aishin не получает навык из текста модели или декларации «я научилась».

Навык может появиться только из уже сохранённых:

- learning_patterns;
- learning_pattern_quality;
- learning_evidence_metrics;
- logic_strategies;
- strategy_quality_state.

Cloud.ru или другой внешний провайдер не добавляет mastery напрямую.

## Новая миграция

Schema version: 17

Таблицы:

- growth_skills;
- knowledge_trust;
- growth_specializations;
- long_term_growth_snapshots;
- long_term_growth_events.

## Growth Skills

Каждый долговременный навык хранит:

- skill_key;
- source_type;
- source_id;
- category;
- title;
- lifecycle;
- mastery_score;
- reliability;
- evidence_count;
- successes;
- failures;
- freshness;
- stability;
- first_seen_at;
- last_evidence_at.

### Lifecycle

forming

Навык наблюдается, но evidence пока недостаточно.

established

Требуется одновременно:

- mastery >= 62;
- evidence >= 4;
- stability >= 0.56.

mastered

Требуется одновременно:

- mastery >= 80;
- evidence >= 8;
- stability >= 0.72.

fading

Навык переводится в fading, если исходный quality lifecycle deprecated либо свежесть становится ниже порога при уже накопленном evidence.

Никакой навык не становится mastered только из-за одной успешной операции.

## Freshness

Freshness рассчитывается по возрасту последнего подтверждающего сигнала.

Для pattern skill используется half-life 240 дней.

Для strategy skill используется half-life 180 дней.

Freshness ограничена нижним floor. История не удаляется и не обнуляется.

Идея:

старый опыт остаётся известным системе, но его влияние на текущий уровень мастерства постепенно уменьшается.

## Skill Mastery

Для learning pattern учитываются:

- effective_score;
- weighted evidence volume;
- success/failure ratio;
- contradiction rate;
- evidence confidence;
- stability;
- freshness.

Для logic strategy учитываются:

- effective reliability;
- evidence count;
- success/failure ratio;
- drift score;
- stability;
- freshness.

Итоговая mastery всегда ограничена диапазоном 0–100.

## Knowledge Trust

Доверие рассчитывается только для объектов, где в существующей модели данных имеется явный confidence-сигнал.

В версии 00.00.05:

- active memories;
- knowledge graph relations.

### Memory Trust

Учитываются:

- memory confidence;
- freshness;
- corroboration по совпадающему memory_key/fingerprint;
- importance.

### Relation Trust

Учитываются:

- relation confidence;
- freshness;
- наличие evidence.

### Trust levels

trusted

trust >= 0.84 и знание не stale.

supported

trust >= 0.68.

provisional

trust >= 0.50.

weak

trust < 0.50.

stale

Свежесть опустилась ниже установленного порога.

Trust не заменяет Verification Engine. Даже trusted knowledge может потребовать перепроверки для критического решения.

## Specializations

Специализация формируется только из реальных Growth Skills одной категории.

Для каждой специализации считаются:

- skill_count;
- mastered_skills;
- evidence_count;
- depth_score;
- breadth_score;
- trust_score;
- overall_score;
- level.

Уровни:

- forming;
- developing;
- strong;
- mastered.

High specialization score требует не только высокого качества, но и достаточного объёма evidence.

## Long-Term Growth Score

Отдельный показатель долговременного развития.

Он не заменяет Development Metrics 00.00.04.

В основе:

- среднее mastery навыков;
- средняя сила специализаций;
- среднее knowledge trust;
- volume factor по накопленному evidence.

Это защищает систему от ситуации, когда один хороший результат даёт искусственно высокий общий процент.

## История

long_term_growth_snapshots сохраняется не чаще одного раза в час.

Snapshot содержит:

- overall_score;
- durable_skills;
- mastered_skills;
- specializations;
- trusted_knowledge;
- stale_knowledge;
- average_trust;
- average_freshness;
- полный summary payload.

## Audit Events

long_term_growth_events фиксирует переходы:

- skill lifecycle;
- knowledge trust level;
- specialization level.

Переходы не переписывают историю задним числом.

## API

GET /api/assistant/growth

Полный срез:

- summary;
- skills;
- knowledge;
- specializations;
- history;
- events.

GET /api/assistant/growth/skills

Фильтр lifecycle поддерживается.

GET /api/assistant/growth/knowledge

Фильтр trust_level поддерживается.

GET /api/assistant/growth/specializations

GET /api/assistant/growth/history

POST /api/assistant/growth/refresh

Ручной локальный пересчёт.

## Live Brain

Live Brain export теперь содержит long_term_growth.

Версия export format повышена до 3.

Контур «Самообучение» показывает число устойчивых и освоенных навыков.

## Интерфейс

Новая карта отображается на странице «Развитие Айшин».

В ней есть:

- Long-Term Growth ring;
- устойчивые навыки;
- mastered skills;
- trusted knowledge;
- специализации;
- матрица навыков;
- mastery;
- evidence count;
- reliability;
- freshness;
- trust map;
- stale knowledge;
- история;
- правила честного роста.

## Ограничения

00.00.05 намеренно не:

- объявляет навык освоенным по одному ответу;
- использует скрытый chain-of-thought;
- считает provider/model брендом развития;
- удаляет старый опыт автоматически;
- превращает trust score в абсолютную истину;
- автоматически повышает разрешения на действия.

## Версии

Aishin Core: 0.0.5

Long-Term Growth Engine: aishin-long-term-growth-v1

Live Brain Export Format: 3

Database schema: 17
