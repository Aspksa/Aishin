# Aishin 00.00.11 — Knowledge Ingestion & Document Intelligence

## Назначение

Версия 00.00.11 превращает загруженные файлы в управляемые источники знаний с точным provenance.

Основной pipeline:

Original File
→ SHA-256
→ Parser
→ Pages / Sections / Tables
→ Chunks
→ Quality Gate
→ Facts / Entities / Relations
→ Version & Duplicate Intelligence
→ Research Source
→ Semantic / Lexical Retrieval
→ Evidence-grounded Answer

Документ не превращается целиком в долговременную память.

## Версии

Aishin Core: 0.0.11

Database schema: 23

Document Intelligence Engine: aishin-document-intelligence-v1

Parser: document-parser-v1

Quality formula: document-quality-provenance-v1

Live Brain Export: 9

## Поддерживаемые форматы

Текст реально извлекается из:

- PDF с текстовым слоем — pypdf;
- DOCX — python-docx;
- XLSX — openpyxl;
- CSV — stdlib csv;
- TXT;
- Markdown;
- HTML / HTM — BeautifulSoup.

Изображения:

- PNG;
- JPG / JPEG;
- WEBP;
- TIF / TIFF;
- BMP.

Для изображений 00.00.11 выполняет только техническую инспекцию через Pillow.

Изображение не объявляется изученным без OCR.

Статус:

needs_ocr

Quality Gate блокирует создание grounded knowledge из такого файла.

PDF без достаточного текстового слоя также получает:

needs_ocr

Это намеренная защита от ложного обучения.

## Immutable Original

При загрузке:

1. проверяется размер;
2. проверяется расширение;
3. вычисляется SHA-256;
4. определяется точный дубль;
5. оригинал сохраняется без преобразования.

Хранилище:

data/documents/<scope>/<sha-prefix>/<sha>/original.<ext>

Максимальный размер одного файла:

80 MB

Повторная обработка использует сохранённый оригинал.

## Exact Duplicate

Уникальность:

scope + sha256

Если тот же бинарный файл загружен снова:

- новый document row не создаётся;
- возвращается существующий document_id;
- duplicate=true;
- создаётся техническое событие document.duplicate.exact.

Это не создаёт дополнительный независимый Research source.

## Near Duplicate

Внутри одного family_key сравнивается token Jaccard первых chunks.

Порог near duplicate:

0.96

Near duplicate получает duplicate_of_id.

В Research Intelligence он использует independence=0.55 и ту же canonical source group.

Таким образом скан/копия одного содержания не может искусственно повысить Evidence Gate.

## Document Family

family_key строится из имени файла после удаления:

- version/revision markers;
- года;
- copy/копия;
- final/финал;
- new/новый;
- служебных разделителей.

Пример:

Регламент ГСМ 2025.txt
Регламент ГСМ 2026.txt

относятся к одному family_key.

## Version Intelligence

Поддерживаются:

- version;
- ver;
- версия;
- редакция;
- rev;
- YYYY в имени файла.

Хранятся:

- version_label;
- version_rank;
- previous_version_id.

Если новая версия имеет предыдущую, Knowledge Graph получает отношение:

new document
--supersedes_document-->
previous document

## Pages

Каждая страница хранит:

- page_number;
- text_content;
- char_count;
- quality_score;
- extraction_method;
- provenance.

PDF page = реальная PDF page.

XLSX sheet трактуется как page-like source unit.

DOCX/TXT/HTML в первой версии используют логическую страницу 1, потому что стандартные parsers не дают надёжной физической пагинации DOCX.

Это ограничение не скрывается.

## Sections

Sections хранят:

- heading;
- level;
- ordinal;
- page_start;
- page_end;
- text;
- provenance.

DOCX использует Heading styles.

XLSX использует worksheet names.

HTML использует h1..h6.

PDF/TXT/Markdown используют conservative heading detection.

## Tables

DOCX tables преобразуются в структурированные строки с разделителем | и сохраняются как отдельные sections.

XLSX rows сохраняются внутри section соответствующего листа.

Это позволяет retrieval и fact extraction видеть таблицу, а не только цельный неструктурированный текст.

## Chunks

Chunk создаётся только как retrieval unit.

Он не является долговременной памятью.

Каждый chunk хранит:

- document_id;
- page_id;
- section_id;
- ordinal;
- text;
- token estimate;
- quality;
- content hash;
- provenance.

Target:

1400 characters

Overlap:

180 characters

Provenance включает минимум:

- document_id;
- page;
- section_id;
- heading;
- chunk_ordinal.

## Quality Gate

Document quality использует:

- extraction coverage;
- text volume;
- detected structure;
- warning penalty.

Quality Gate:

0.70

Coverage Gate:

0.60

Это качество извлечения текста.

Это НЕ оценка истинности содержания документа.

Статусы:

### studied

Quality >= 0.70
и coverage >= 0.60
и OCR не требуется.

### quality_hold

Текст извлечён, но качество ниже gate.

### needs_ocr

Нет надёжного текстового слоя.

### failed

Parser/processing завершился ошибкой.

## Deterministic Facts

Без AI извлекаются:

- Key: Value / Key — Value;
- даты;
- суммы и валюты;
- проценты;
- email;
- URL.

Fact хранит:

- fact_key;
- subject;
- predicate;
- value;
- normalized_value;
- fact_type;
- confidence;
- status;
- provenance.

Если документ прошёл gate:

status = grounded

Иначе:

status = candidate

## AI Grounded Extraction

При явном включении AI enrichment модель получает только выбранные chunks.

Можно извлекать:

- entities;
- relations;
- facts.

Но каждый item обязан вернуть:

chunk_id
+
evidence_quote

evidence_quote должен дословно присутствовать в указанном chunk.

Если quote отсутствует — extraction отбрасывается.

Model output без grounded quote не является знанием.

AI enrichment в UI по умолчанию выключен.

## Knowledge Graph

Для изученного документа создаётся entity:

document

Sections получают entity:

document_section

Связь:

document --contains_section--> section

AI-grounded сущности создаются с типами:

document_person
document_organization
document_vehicle
document_product
document_place
document_document_ref
document_other

Relations всегда содержат evidence/provenance.

## Inter-document Contradictions

Сравниваются grounded key/value и AI-grounded facts внутри одного family_key.

Если fact_key совпадает, а normalized_value отличается:

создаётся document_contradiction.

Хранятся:

- left_fact_id;
- right_fact_id;
- severity;
- status;
- resolution.

Contradiction не разрешается автоматически.

Одновременно создаётся Knowledge Gap в Research Intelligence.

## Research Intelligence Integration

Каждый обработанный document регистрируется как research source:

source_type = document

source_key = document:<id>

source group:

document:<canonical_id>

Research Engine может получить релевантные chunks этого документа как evidence.

Evidence содержит:

- document id;
- chunk id;
- page;
- heading;
- content hash;
- document quality;
- chunk quality.

Документы-дубликаты не считаются независимыми подтверждениями.

## Semantic Index

document_chunks имеют отдельный embedding index.

Таблица:

document_chunk_vectors

Используется настроенный embedding provider.

Если embeddings недоступны:

- ingestion не падает;
- document остаётся изученным;
- search использует lexical fallback.

Таким образом semantic provider не является обязательным для Document Intelligence.

## Retrieval in Normal Chat

При обычном сообщении Айшин выполняет:

Document Intelligence search

до вызова chat provider.

До 6 релевантных chunks могут попасть в system context.

Формат содержит:

- D<document_id>;
- C<chunk_id>;
- filename;
- page;
- retrieval score;
- document quality;
- source text.

Instruction запрещает утверждать больше, чем поддерживает fragment.

Retrieved chunks сохраняются в Cognitive Trace как document_context.

## UI — «Библиотека знаний»

Добавлен отдельный модуль:

Библиотека знаний

Показываются:

- Document Intelligence Score;
- studied documents;
- OCR queue;
- duplicates;
- facts;
- contradictions;
- extraction quality;
- semantic coverage;
- upload;
- AI enrichment toggle;
- semantic index toggle;
- registry документов;
- Quality Gate;
- document search;
- Fact Ledger;
- Version Intelligence;
- ingestion history;
- principles.

Карточка документа показывает:

- status;
- quality;
- extraction coverage;
- SHA-256;
- pages;
- sections;
- chunks;
- facts;
- chunk text;
- provenance.

## API

GET /api/assistant/documents

GET /api/assistant/documents/list

GET /api/assistant/documents/detail/{document_id}

POST /api/assistant/documents/upload

POST /api/assistant/documents/{document_id}/reprocess

GET /api/assistant/documents/search

GET /api/assistant/documents/facts

GET /api/assistant/documents/contradictions

POST /api/assistant/documents/contradictions/{id}/resolve

Mutating endpoints are local-only.

## Database

Schema 23 adds:

document_state

documents

document_pages

document_sections

document_chunks

document_chunk_vectors

document_facts

document_contradictions

document_ingestion_runs

document_events

## Live Brain

Live Brain includes:

documents.summary
documents.documents
documents.facts
documents.contradictions
documents.runs

Pulse includes:

document_ingestion_score

document_studied

document_ocr_required

document_duplicates

document_facts

document_contradictions

Failed documents or open document contradictions can set integrity=attention.

Live Brain Export:

version 9

Базовые 24 cognitive channels не меняются.

## Development Metrics

Основная формула Development Score не меняется.

Добавляются диагностические counters:

document_ingestion_score

document_extraction_quality

document_provenance_coverage

document_semantic_coverage

document_studied

document_ocr_required

document_duplicates

document_facts

document_contradictions

document_chunks

document_vectors

## Safety / Honesty Rules

1. File uploaded != knowledge learned.
2. OCR required != OCR completed.
3. Chunk != memory.
4. Document quality != truth.
5. Model output != grounded fact without exact evidence quote.
6. Duplicate document != independent evidence.
7. Conflicting versions stay visible until resolved.
8. Missing embeddings do not invalidate textual ingestion.
9. Long-term trusted knowledge still requires Research Evidence Gate.
10. Original file remains the provenance root.
