# Aishin 00.00.09 — Autonomous Knowledge & Research Intelligence

## Цель

00.00.09 добавляет доказательный исследовательский контур поверх Long-Term Growth, Cognitive Intelligence, Proactive Intelligence и Evolution Engine.

Главная цепочка:

Knowledge Gap
→ Research Plan
→ Evidence Ledger
→ Claim
→ Contradiction Check
→ Evidence Gate
→ Trusted Knowledge
→ Provenance
→ Long-Term Memory / Knowledge Graph

## Главный принцип

Найденные сведения и подтверждённое знание — разные состояния.

AI-модель может помочь сформулировать claim, но её текст не является evidence. Claim получает статус только по сохранённым evidence rows.

## Версии

Aishin Core: 0.0.9

Database schema: 21

Research Engine: aishin-autonomous-research-v1

Research formula: evidence-ledger-research-v1

Live Brain Export: 7

## Источники

Встроенные источники:

- долговременная память;
- semantic memory;
- Knowledge Graph;
- история диалога;
- Verification Engine;
- ранее подтверждённые research claims.

Дополнительно можно явно зарегистрировать:

- project_file;
- manual_reference;
- external_connector.

В 00.00.09 external_connector является декларацией источника, но не выполняет сетевой I/O. Для внешнего интернета нужен отдельный явный source adapter.

Project file автоматически читается только когда:

1. источник явно зарегистрирован;
2. auto_read=true;
3. PermissionGate read_local_context=allow;
4. ToolRegistry project.read_text успешно вернул файл.

## Независимость источников

Lexical Memory и Semantic Memory имеют одну independence group:

memory

Поэтому одна и та же память, найденная двумя способами, не считается двумя независимыми подтверждениями.

Derived research claims имеют группу:

derived_knowledge

Она не может сама по себе обеспечить trusted promotion.

## Knowledge Gaps

Research Engine обнаруживает пробелы из:

- unresolved Verification;
- verification conflicts;
- Proactive Intelligence incidents, требующих review;
- Evolution Curriculum;
- stale knowledge pool.

Каждый gap хранит:

- question;
- origin;
- origin_ref;
- priority;
- uncertainty;
- impact;
- status;
- attempts;
- last_session_id.

## Research Session

Каждая сессия сохраняет:

- question;
- trigger;
- research plan;
- source plan;
- evidence count;
- independent groups;
- contradiction count;
- claim count;
- synthesis_used;
- duration;
- status.

Статусы:

- planned;
- running;
- evidence_only;
- completed;
- insufficient.

## Evidence Ledger

Каждый evidence item хранит:

- source_type;
- source_ref;
- source_group;
- title;
- content;
- reliability;
- relevance;
- freshness;
- independence;
- evidence_score;
- content_hash;
- metadata.

Evidence score:

reliability × relevance factor × freshness × independence.

Это технический вес evidence внутри Aishin, а не вероятность истинности факта.

## Claim Lifecycle

Claim может быть:

- candidate;
- supported;
- trusted;
- conflicted;
- rejected.

### Trusted gate

Trusted promotion требует одновременно:

- минимум 2 support evidence;
- минимум 2 независимых source groups;
- минимум 2 primary groups, не derived_knowledge;
- confidence >= 0.82;
- combined support >= 0.82;
- отсутствие counter-evidence;
- отсутствие missing requirements.

Практически несколько сильных независимых источников значительно надёжнее одного повторённого источника.

## Contradiction Matrix

Если synthesis или ручная evaluation указывает counter-evidence:

- claim становится conflicted;
- создаётся research_contradiction;
- trusted promotion запрещается.

Если ранее trusted claim уже был записан в память, новая конфликтующая информация не удаляет память автоматически. Claim получает состояние conflicted и событие requires_review.

Это защищает систему от молчаливого переписывания истории.

## Promotion

Только trusted claim может попасть в долговременную память.

Memory:

kind = researched_knowledge

tags:

- research;
- evidence_grounded;
- provenance.

Memory key:

research_claim:<claim_hash>

Источник:

autonomous_research:claim:<claim_id>

Одновременно создаётся Knowledge Graph entity:

research_claim

Provenance содержит:

- research_claim_id;
- research_session_id;
- support_evidence_ids;
- source_groups;
- confidence.

## Model Synthesis

AI получает только Evidence Ledger текущей сессии.

System instruction запрещает:

- использовать внешние знания;
- достраивать отсутствующие факты;
- считать собственный ответ evidence;
- скрывать counter-evidence.

Ожидаемый JSON:

{
  "claims": [
    {
      "statement": "...",
      "support_evidence_ids": [1, 2],
      "contradiction_evidence_ids": [],
      "missing": []
    }
  ]
}

Если provider недоступен, Research Engine сохраняет evidence и завершает session как evidence_only. Он не придумывает claim.

## Автоматическое исследование в запросе

Если Verification Engine оставил unresolved/conflicts, Aishin:

1. создаёт Knowledge Gap;
2. запускает исследование по доступным локальным источникам;
3. собирает Evidence Ledger;
4. при доступном AI делает constrained synthesis;
5. добавляет research evidence в system context текущего ответа;
6. сохраняет run в Cognitive Trace.

Research не заменяет Verification — он расширяет доказательную базу.

## Research Cycles

Manual/background research cycle:

1. обнаруживает gaps;
2. сортирует по priority;
3. берёт только gaps >= 0.62;
4. запускает ограниченное число sessions;
5. пересчитывает Research State.

Автоматический cycle по умолчанию может работать без synthesis, чтобы не расходовать provider на фоновом сканировании.

## Research State

Persisted показатели:

- research_score;
- coverage_score;
- evidence_quality;
- contradiction_resolution;
- knowledge_precision;
- open_gap_count;
- active_session_count;
- trusted_claim_count;
- conflicted_claim_count.

Research Score — здоровье исследовательского контура, а не IQ и не абсолютная истинность базы знаний.

## API

GET /api/assistant/research

POST /api/assistant/research/query

POST /api/assistant/research/cycle

GET /api/assistant/research/gaps

GET /api/assistant/research/sessions

GET /api/assistant/research/claims

GET /api/assistant/research/evidence

GET /api/assistant/research/sources

POST /api/assistant/research/sources

GET /api/assistant/research/contradictions

POST /api/assistant/research/contradictions/{id}/resolve

Mutating research endpoints local-only.

## UI

Новый модуль:

Исследования Айши

Экран показывает:

- Research Score;
- open knowledge gaps;
- trusted/conflicted claims;
- open contradictions;
- enabled sources;
- evidence quality;
- ручной research query;
- Knowledge Gaps;
- Evidence Gate;
- Evidence Ledger;
- Claim Ledger;
- Contradiction Matrix;
- Source Registry;
- Research Sessions;
- Research History;
- anti-self-confirmation principles.

## Live Brain

Live Brain включает:

research.summary

research.gaps

research.sessions

research.claims

research.evidence

research.contradictions

research.sources

research.cycles

Pulse показывает:

- research_score;
- research_open_gaps;
- research_trusted_claims;
- research_conflicted_claims;
- research_open_contradictions.

Open contradiction переводит integrity в attention.

Live Brain Export: version 7.

Количество базовых когнитивных контуров остаётся 24 — Research Intelligence показывается как надстройка, чтобы не ломать существующую topology telemetry.

## Development Metrics

00.00.09 не меняет существующую формулу общего Development Score.

Добавлены только реальные counters:

- research_score;
- research_open_gaps;
- research_sessions;
- research_evidence;
- research_trusted_claims;
- research_supported_claims;
- research_conflicted_claims;
- research_open_contradictions;
- research_sources.

## Безопасность

Research Engine не:

- переписывает source code;
- меняет Permission Gate;
- выполняет внешний web search самостоятельно;
- считает AI provider источником истины;
- повышает claim до trusted по одному источнику;
- удаляет старое знание при первом противоречии;
- выполняет destructive actions;
- скрывает конфликтующие evidence.

## Anti Self-Confirmation Rules

1. Model output != evidence.
2. Same source via lexical + semantic retrieval != independent confirmation.
3. Derived claim != primary independent source.
4. Conflict blocks promotion.
5. Missing evidence blocks trusted status.
6. Promotion requires provenance.
7. Previously promoted knowledge is not silently deleted on regression.
8. External network remains disabled without explicit adapter.
9. Confidence is local evidence support, not universal truth.
10. Every promoted knowledge item must be traceable back to evidence IDs.
