from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import mimetypes
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from docx import Document as DocxDocument
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader

from ..ai import AIManager
from ..db import DATA_DIR, connect
from .events import EventBus
from .graph import KnowledgeGraph
from .semantic import cosine_similarity


_SPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[\wА-Яа-яЁё-]{3,}", re.UNICODE)
_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[\.\)]?\s+)?[A-ZА-ЯЁ][^\n]{2,100}$"
)
_KEY_VALUE_RE = re.compile(
    r"^\s*([A-Za-zА-Яа-яЁё0-9№][^:\n—–]{1,78}?)\s*(?::|—|–)\s*(.{2,500})\s*$"
)
_YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2}|21\d{2})\b")
_VERSION_RE = re.compile(
    r"(?:\b(?:ver|version|версия|редакция|rev)\s*[\._-]?\s*)"
    r"(\d+(?:[\._-]\d+){0,3})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(
    r"\b([0-3]?\d[./-][01]?\d[./-](?:19|20|21)?\d{2})\b"
)
_MONEY_RE = re.compile(
    r"\b(\d[\d\s]*(?:[.,]\d{1,2})?)\s*"
    r"(руб(?:\.|лей|ля)?|₽|RUB|USD|\$|EUR|€)\b",
    re.IGNORECASE,
)
_PERCENT_RE = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*%\b")
_EMAIL_RE = re.compile(
    r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)


@dataclass
class ParsedDocument:
    parser: str
    parser_version: str
    pages: list[dict]
    sections: list[dict]
    metadata: dict
    warnings: list[str]
    ocr_required: bool = False


@dataclass
class IngestionResult:
    document_id: int
    status: str
    duplicate: bool
    sha256: str
    quality_score: float
    extraction_coverage: float
    page_count: int
    section_count: int
    chunk_count: int
    fact_count: int
    contradiction_count: int
    ocr_required: bool
    semantic_indexed: int
    warnings: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


class DocumentIntelligenceEngine:
    """Structured ingestion with provenance and guarded extraction."""

    VERSION = "aishin-document-intelligence-v1"
    PARSER_VERSION = "document-parser-v1"
    FORMULA_VERSION = "document-quality-provenance-v1"
    QUALITY_GATE = 0.70
    COVERAGE_GATE = 0.60
    MAX_FILE_BYTES = 80 * 1024 * 1024
    CHUNK_TARGET = 1400
    CHUNK_OVERLAP = 180

    SUPPORTED_EXTENSIONS = {
        ".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md",
        ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp",
        ".tif", ".tiff", ".bmp",
    }
    IMAGE_EXTENSIONS = {
        ".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"
    }

    def __init__(
        self,
        *,
        ai: AIManager,
        graph: KnowledgeGraph,
        research: Any,
        events: EventBus,
        root: Path | None = None,
    ) -> None:
        self.ai = ai
        self.graph = graph
        self.research = research
        self.events = events
        self.root = Path(root or DATA_DIR / "documents")
        self.root.mkdir(parents=True, exist_ok=True)

    def bootstrap(self, *, scope: str) -> dict:
        self._ensure_state(scope)
        self._rebuild_all_lineage(scope=scope)
        return self._refresh_state(scope)

    def ingest_bytes(
        self,
        *,
        scope: str,
        filename: str,
        data: bytes,
        media_type: str = "",
        trigger: str = "upload",
        enrich_with_ai: bool = True,
        build_semantic_index: bool = True,
    ) -> IngestionResult:
        started = time.perf_counter()
        scope = (scope or "personal").strip() or "personal"
        filename = self._safe_filename(filename)
        if not data:
            raise ValueError("document is empty")
        if len(data) > self.MAX_FILE_BYTES:
            raise ValueError(
                f"document exceeds {self.MAX_FILE_BYTES // (1024 * 1024)} MB limit"
            )

        extension = Path(filename).suffix.casefold()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                "unsupported document extension: "
                + (extension or "<none>")
            )

        sha = hashlib.sha256(data).hexdigest()
        existing = self._document_by_sha(scope=scope, sha256=sha)
        if existing:
            self._event(
                scope=scope,
                document_id=int(existing["id"]),
                event_type="document.duplicate.exact",
                score=1.0,
                details={"filename": filename, "sha256": sha},
            )
            return IngestionResult(
                document_id=int(existing["id"]),
                status=str(existing["status"]),
                duplicate=True,
                sha256=sha,
                quality_score=float(existing["quality_score"] or 0.0),
                extraction_coverage=float(
                    existing["extraction_coverage"] or 0.0
                ),
                page_count=int(existing["page_count"] or 0),
                section_count=int(existing["section_count"] or 0),
                chunk_count=int(existing["chunk_count"] or 0),
                fact_count=int(existing["fact_count"] or 0),
                contradiction_count=self._contradiction_count(
                    scope=scope,
                    document_id=int(existing["id"]),
                ),
                ocr_required=bool(existing["ocr_required"]),
                semantic_indexed=self._vector_count(
                    scope=scope,
                    document_id=int(existing["id"]),
                ),
                warnings=["exact_duplicate_sha256"],
            )

        storage_path = self._store_original(
            scope=scope,
            sha256=sha,
            filename=filename,
            data=data,
        )
        family_key = self._family_key(filename)
        version_label, version_rank = self._version_info(filename)
        media_type = (
            media_type.strip()
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        previous = self._previous_family_document(
            scope=scope,
            family_key=family_key,
            version_rank=version_rank,
        )

        with connect() as conn:
            cur = conn.execute(
                """INSERT INTO documents(
                       scope, sha256, filename, media_type, extension,
                       size_bytes, storage_path, status, parser_version,
                       document_type, family_key, version_label,
                       version_rank, previous_version_id
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, 'processing', ?, ?, ?, ?, ?, ?)""",
                (
                    scope, sha, filename, media_type, extension, len(data),
                    str(storage_path.relative_to(DATA_DIR.parent)),
                    self.PARSER_VERSION, self._document_type(extension),
                    family_key, version_label, version_rank,
                    int(previous["id"]) if previous else None,
                ),
            )
            document_id = int(cur.lastrowid)
            run = conn.execute(
                """INSERT INTO document_ingestion_runs(
                       scope, document_id, trigger, status
                   ) VALUES (?, ?, ?, 'running')""",
                (scope, document_id, trigger),
            )
            run_id = int(run.lastrowid)
            conn.commit()

        warnings: list[str] = []
        try:
            parsed = self._parse(
                filename=filename,
                data=data,
                extension=extension,
            )
            warnings.extend(parsed.warnings)
            quality, coverage = self._quality(parsed)
            pages = self._persist_pages(
                scope=scope,
                document_id=document_id,
                parsed=parsed,
            )
            sections = self._persist_sections(
                scope=scope,
                document_id=document_id,
                parsed=parsed,
            )
            chunks = self._persist_chunks(
                scope=scope,
                document_id=document_id,
                pages=pages,
                sections=sections,
                base_quality=quality,
            )

            near_duplicate_id = self._detect_near_duplicate(
                scope=scope,
                document_id=document_id,
                family_key=family_key,
                chunks=chunks,
            )
            if near_duplicate_id:
                warnings.append(
                    f"near_duplicate_of_document:{near_duplicate_id}"
                )

            self._extract_deterministic_facts(
                scope=scope,
                document_id=document_id,
                chunks=chunks,
                quality=quality,
                coverage=coverage,
                ocr_required=parsed.ocr_required,
            )

            ai_counts: dict[str, Any] = {
                "facts": 0, "entities": 0, "relations": 0,
            }
            if (
                enrich_with_ai
                and not parsed.ocr_required
                and quality >= self.QUALITY_GATE
                and chunks
            ):
                ai_counts = self._ai_enrich(
                    scope=scope,
                    document_id=document_id,
                    chunks=chunks,
                    document_quality=quality,
                )
                if ai_counts.get("warning"):
                    warnings.append(str(ai_counts["warning"]))

            contradictions = self._detect_contradictions(
                scope=scope,
                document_id=document_id,
                family_key=family_key,
            )
            graph_entity_id = self._index_graph(
                scope=scope,
                document_id=document_id,
                filename=filename,
                family_key=family_key,
                version_label=version_label,
                quality=quality,
                previous=previous,
                sections=sections,
                sha256=sha,
            )
            research_source = self._register_research_source(
                scope=scope,
                document_id=document_id,
                filename=filename,
                sha256=sha,
                quality=quality,
                duplicate_of_id=near_duplicate_id,
                graph_entity_id=graph_entity_id,
            )

            semantic = (
                self.ensure_semantic_index(
                    scope=scope,
                    document_id=document_id,
                    batch_size=24,
                )
                if build_semantic_index
                else {"indexed": 0, "available": False, "reason": "disabled"}
            )
            if not semantic.get("available"):
                reason = str(semantic.get("reason") or "")
                if reason not in {"disabled", "not_configured", "up_to_date"}:
                    warnings.append(f"semantic_index:{reason}")

            status = (
                "needs_ocr"
                if parsed.ocr_required
                else (
                    "studied"
                    if quality >= self.QUALITY_GATE
                    and coverage >= self.COVERAGE_GATE
                    else "quality_hold"
                )
            )
            facts_count = self._fact_count(
                scope=scope,
                document_id=document_id,
            )
            duration_ms = int((time.perf_counter() - started) * 1000)
            with connect() as conn:
                conn.execute(
                    """UPDATE documents
                       SET status=?, parser=?, parser_version=?,
                           duplicate_of_id=?,
                           quality_score=?, extraction_coverage=?,
                           ocr_required=?, page_count=?, section_count=?,
                           chunk_count=?, fact_count=?, warning_count=?,
                           metadata_json=?, studied_at=CASE
                             WHEN ?='studied' THEN CURRENT_TIMESTAMP
                             ELSE studied_at END,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND scope=?""",
                    (
                        status, parsed.parser, parsed.parser_version,
                        near_duplicate_id, quality, coverage,
                        1 if parsed.ocr_required else 0,
                        len(pages), len(sections), len(chunks),
                        facts_count, len(warnings),
                        json.dumps(
                            {
                                **parsed.metadata,
                                "graph_entity_id": graph_entity_id,
                                "research_source_key": (
                                    research_source.get("source_key")
                                    if research_source else None
                                ),
                                "ai_enrichment": ai_counts,
                            },
                            ensure_ascii=False,
                        ),
                        status, document_id, scope,
                    ),
                )
                conn.execute(
                    """UPDATE document_ingestion_runs
                       SET status='completed', parser=?,
                           pages_extracted=?, sections_extracted=?,
                           chunks_created=?, facts_created=?,
                           contradictions_found=?, embeddings_created=?,
                           duration_ms=?, warnings_json=?,
                           completed_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        parsed.parser, len(pages), len(sections), len(chunks),
                        facts_count, contradictions,
                        int(semantic.get("indexed") or 0), duration_ms,
                        json.dumps(warnings, ensure_ascii=False), run_id,
                    ),
                )
                conn.commit()

            self._rebuild_family_lineage(
                scope=scope,
                family_key=family_key,
            )
            self._refresh_state(scope)
            self._event(
                scope=scope,
                document_id=document_id,
                event_type="document.ingested",
                score=quality,
                details={
                    "status": status,
                    "pages": len(pages),
                    "sections": len(sections),
                    "chunks": len(chunks),
                    "facts": facts_count,
                    "contradictions": contradictions,
                    "ocr_required": parsed.ocr_required,
                    "semantic_indexed": int(semantic.get("indexed") or 0),
                },
            )
            return IngestionResult(
                document_id=document_id,
                status=status,
                duplicate=bool(near_duplicate_id),
                sha256=sha,
                quality_score=quality,
                extraction_coverage=coverage,
                page_count=len(pages),
                section_count=len(sections),
                chunk_count=len(chunks),
                fact_count=facts_count,
                contradiction_count=contradictions,
                ocr_required=parsed.ocr_required,
                semantic_indexed=int(semantic.get("indexed") or 0),
                warnings=warnings,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            with connect() as conn:
                conn.execute(
                    """UPDATE documents
                       SET status='failed', error_text=?,
                           updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND scope=?""",
                    (str(exc)[:2000], document_id, scope),
                )
                conn.execute(
                    """UPDATE document_ingestion_runs
                       SET status='failed', error_text=?, duration_ms=?,
                           warnings_json=?, completed_at=CURRENT_TIMESTAMP
                       WHERE id=?""",
                    (
                        str(exc)[:2000], duration_ms,
                        json.dumps(warnings, ensure_ascii=False), run_id,
                    ),
                )
                conn.commit()
            self._refresh_state(scope)
            self._event(
                scope=scope,
                document_id=document_id,
                event_type="document.ingestion.failed",
                score=0.0,
                details={"error": str(exc)[:1000]},
            )
            raise

    def reprocess(
        self,
        document_id: int,
        *,
        scope: str,
        enrich_with_ai: bool = True,
        build_semantic_index: bool = True,
    ) -> IngestionResult:
        doc = self.document(document_id, scope=scope)
        if doc is None:
            raise ValueError("document not found")
        path = DATA_DIR.parent / str(doc["storage_path"])
        if not path.is_file():
            raise ValueError("document original is missing")
        data = path.read_bytes()

        with connect() as conn:
            conn.execute(
                "DELETE FROM document_chunk_vectors WHERE chunk_id IN "
                "(SELECT id FROM document_chunks WHERE document_id=?)",
                (document_id,),
            )
            conn.execute(
                "DELETE FROM document_contradictions "
                "WHERE left_fact_id IN (SELECT id FROM document_facts WHERE document_id=?) "
                "OR right_fact_id IN (SELECT id FROM document_facts WHERE document_id=?)",
                (document_id, document_id),
            )
            conn.execute(
                "DELETE FROM document_facts WHERE document_id=?",
                (document_id,),
            )
            conn.execute(
                "DELETE FROM document_chunks WHERE document_id=?",
                (document_id,),
            )
            conn.execute(
                "DELETE FROM document_sections WHERE document_id=?",
                (document_id,),
            )
            conn.execute(
                "DELETE FROM document_pages WHERE document_id=?",
                (document_id,),
            )
            conn.execute(
                """UPDATE documents SET status='processing',
                   duplicate_of_id=NULL, quality_score=0,
                   extraction_coverage=0, ocr_required=0,
                   page_count=0, section_count=0, chunk_count=0,
                   fact_count=0, warning_count=0, error_text='',
                   updated_at=CURRENT_TIMESTAMP WHERE id=?""",
                (document_id,),
            )
            run = conn.execute(
                """INSERT INTO document_ingestion_runs(
                       scope, document_id, trigger, status
                   ) VALUES (?, ?, 'reprocess', 'running')""",
                (scope, document_id),
            )
            run_id = int(run.lastrowid)
            conn.commit()

        return self._process_existing(
            scope=scope,
            document_id=document_id,
            run_id=run_id,
            filename=str(doc["filename"]),
            data=data,
            enrich_with_ai=enrich_with_ai,
            build_semantic_index=build_semantic_index,
        )

    def _process_existing(
        self,
        *,
        scope: str,
        document_id: int,
        run_id: int,
        filename: str,
        data: bytes,
        enrich_with_ai: bool,
        build_semantic_index: bool,
    ) -> IngestionResult:
        started = time.perf_counter()
        doc = self.document(document_id, scope=scope)
        if doc is None:
            raise ValueError("document not found")
        parsed = self._parse(
            filename=filename,
            data=data,
            extension=str(doc["extension"]),
        )
        warnings = list(parsed.warnings)
        quality, coverage = self._quality(parsed)
        pages = self._persist_pages(
            scope=scope, document_id=document_id, parsed=parsed
        )
        sections = self._persist_sections(
            scope=scope, document_id=document_id, parsed=parsed
        )
        chunks = self._persist_chunks(
            scope=scope,
            document_id=document_id,
            pages=pages,
            sections=sections,
            base_quality=quality,
        )
        near_duplicate_id = self._detect_near_duplicate(
            scope=scope,
            document_id=document_id,
            family_key=str(doc["family_key"]),
            chunks=chunks,
        )
        if near_duplicate_id:
            warnings.append(
                f"near_duplicate_of_document:{near_duplicate_id}"
            )
        self._extract_deterministic_facts(
            scope=scope,
            document_id=document_id,
            chunks=chunks,
            quality=quality,
            coverage=coverage,
            ocr_required=parsed.ocr_required,
        )
        if (
            enrich_with_ai
            and not parsed.ocr_required
            and quality >= self.QUALITY_GATE
        ):
            self._ai_enrich(
                scope=scope,
                document_id=document_id,
                chunks=chunks,
                document_quality=quality,
            )
        contradictions = self._detect_contradictions(
            scope=scope,
            document_id=document_id,
            family_key=str(doc["family_key"]),
        )
        previous = self._previous_family_document(
            scope=scope,
            family_key=str(doc["family_key"]),
            version_rank=(
                int(doc["version_rank"])
                if doc.get("version_rank") is not None
                else None
            ),
        )
        graph_entity_id = self._index_graph(
            scope=scope,
            document_id=document_id,
            filename=filename,
            family_key=str(doc["family_key"]),
            version_label=str(doc.get("version_label") or ""),
            quality=quality,
            previous=previous,
            sections=sections,
            sha256=str(doc["sha256"]),
        )
        research_source = self._register_research_source(
            scope=scope,
            document_id=document_id,
            filename=filename,
            sha256=str(doc["sha256"]),
            quality=quality,
            duplicate_of_id=near_duplicate_id,
            graph_entity_id=graph_entity_id,
        )
        semantic = (
            self.ensure_semantic_index(
                scope=scope,
                document_id=document_id,
                batch_size=24,
            )
            if build_semantic_index
            else {"indexed": 0, "available": False, "reason": "disabled"}
        )
        status = (
            "needs_ocr"
            if parsed.ocr_required
            else (
                "studied"
                if quality >= self.QUALITY_GATE
                and coverage >= self.COVERAGE_GATE
                else "quality_hold"
            )
        )
        facts_count = self._fact_count(
            scope=scope, document_id=document_id
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        with connect() as conn:
            conn.execute(
                """UPDATE documents SET status=?, parser=?,
                   duplicate_of_id=?,
                   quality_score=?, extraction_coverage=?,
                   ocr_required=?, page_count=?, section_count=?,
                   chunk_count=?, fact_count=?, warning_count=?,
                   metadata_json=?, studied_at=CASE
                     WHEN ?='studied' THEN CURRENT_TIMESTAMP
                     ELSE studied_at END,
                   updated_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (
                    status, parsed.parser, near_duplicate_id,
                    quality, coverage, 1 if parsed.ocr_required else 0,
                    len(pages), len(sections), len(chunks),
                    facts_count, len(warnings),
                    json.dumps(
                        {
                            **parsed.metadata,
                            "graph_entity_id": graph_entity_id,
                            "research_source_key": (
                                research_source.get("source_key")
                                if research_source else None
                            ),
                        },
                        ensure_ascii=False,
                    ),
                    status, document_id, scope,
                ),
            )
            conn.execute(
                """UPDATE document_ingestion_runs SET status='completed',
                   parser=?, pages_extracted=?, sections_extracted=?,
                   chunks_created=?, facts_created=?,
                   contradictions_found=?, embeddings_created=?,
                   duration_ms=?, warnings_json=?,
                   completed_at=CURRENT_TIMESTAMP WHERE id=?""",
                (
                    parsed.parser, len(pages), len(sections), len(chunks),
                    facts_count, contradictions,
                    int(semantic.get("indexed") or 0), duration_ms,
                    json.dumps(warnings, ensure_ascii=False), run_id,
                ),
            )
            conn.commit()
        self._rebuild_family_lineage(
            scope=scope,
            family_key=str(doc["family_key"]),
        )
        self._refresh_state(scope)
        return IngestionResult(
            document_id=document_id,
            status=status,
            duplicate=bool(near_duplicate_id),
            sha256=str(doc["sha256"]),
            quality_score=quality,
            extraction_coverage=coverage,
            page_count=len(pages),
            section_count=len(sections),
            chunk_count=len(chunks),
            fact_count=facts_count,
            contradiction_count=contradictions,
            ocr_required=parsed.ocr_required,
            semantic_indexed=int(semantic.get("indexed") or 0),
            warnings=warnings,
        )

    def _parse(
        self,
        *,
        filename: str,
        data: bytes,
        extension: str,
    ) -> ParsedDocument:
        if extension == ".pdf":
            return self._parse_pdf(data)
        if extension == ".docx":
            return self._parse_docx(data)
        if extension == ".xlsx":
            return self._parse_xlsx(data)
        if extension == ".csv":
            return self._parse_csv(data)
        if extension in {".html", ".htm"}:
            return self._parse_html(data)
        if extension in {".txt", ".md"}:
            return self._parse_text(data, extension=extension)
        if extension in self.IMAGE_EXTENSIONS:
            return self._parse_image(data, filename=filename)
        raise ValueError(f"unsupported parser for {extension}")

    def _parse_pdf(self, data: bytes) -> ParsedDocument:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        warnings = []
        nonempty = 0
        for index, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "").strip()
            except Exception as exc:
                text = ""
                warnings.append(f"pdf_page_{index}:{str(exc)[:180]}")
            if text:
                nonempty += 1
            pages.append(
                {"number": index, "text": text, "method": "pypdf_text"}
            )
        ocr_required = bool(pages) and (
            nonempty == 0
            or sum(len(p["text"]) for p in pages)
            < max(80, len(pages) * 20)
        )
        if ocr_required:
            warnings.append("pdf_text_layer_insufficient_ocr_required")
        return ParsedDocument(
            parser="pypdf",
            parser_version=self.PARSER_VERSION,
            pages=pages,
            sections=self._sections_from_pages(pages),
            metadata={
                "pdf_metadata": {
                    str(k): str(v)
                    for k, v in (reader.metadata or {}).items()
                }
            },
            warnings=warnings,
            ocr_required=ocr_required,
        )

    def _parse_docx(self, data: bytes) -> ParsedDocument:
        doc = DocxDocument(io.BytesIO(data))
        sections = []
        blocks = []
        current_heading = ""
        ordinal = 0
        for paragraph in doc.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            style = str(paragraph.style.name or "")
            if style.casefold().startswith("heading"):
                current_heading = text
                ordinal += 1
                level_match = re.search(r"(\d+)", style)
                sections.append(
                    {
                        "heading": text,
                        "level": int(level_match.group(1))
                        if level_match else 1,
                        "ordinal": ordinal,
                        "text": "",
                        "page_start": None,
                        "page_end": None,
                    }
                )
            else:
                blocks.append((current_heading, text))

        for table_index, table in enumerate(doc.tables, start=1):
            rows = []
            for row in table.rows:
                cells = [
                    _SPACE_RE.sub(" ", cell.text.strip())
                    for cell in row.cells
                ]
                if any(cells):
                    rows.append(" | ".join(cells))
            if rows:
                table_text = "\n".join(rows)
                blocks.append((f"Таблица {table_index}", table_text))
                ordinal += 1
                sections.append(
                    {
                        "heading": f"Таблица {table_index}",
                        "level": 2,
                        "ordinal": ordinal,
                        "text": table_text,
                        "page_start": None,
                        "page_end": None,
                    }
                )

        page_text = "\n\n".join(text for _, text in blocks)
        if not sections and page_text:
            sections = self._sections_from_text(page_text)
        return ParsedDocument(
            parser="python-docx",
            parser_version=self.PARSER_VERSION,
            pages=[
                {
                    "number": 1,
                    "text": page_text,
                    "method": "python_docx",
                }
            ],
            sections=sections,
            metadata={
                "paragraphs": len(doc.paragraphs),
                "tables": len(doc.tables),
            },
            warnings=[] if page_text else ["docx_no_extractable_text"],
        )

    def _parse_xlsx(self, data: bytes) -> ParsedDocument:
        book = load_workbook(
            io.BytesIO(data), read_only=True, data_only=True
        )
        pages = []
        sections = []
        warnings = []
        for index, sheet in enumerate(book.worksheets, start=1):
            rows = []
            for row in sheet.iter_rows(values_only=True):
                values = [
                    "" if value is None else str(value)
                    for value in row
                ]
                if any(value.strip() for value in values):
                    rows.append(" | ".join(values))
            text = "\n".join(rows)
            pages.append(
                {"number": index, "text": text, "method": "openpyxl"}
            )
            sections.append(
                {
                    "heading": sheet.title,
                    "level": 1,
                    "ordinal": index,
                    "text": text,
                    "page_start": index,
                    "page_end": index,
                }
            )
            if not text:
                warnings.append(f"sheet_empty:{sheet.title}")
        return ParsedDocument(
            parser="openpyxl",
            parser_version=self.PARSER_VERSION,
            pages=pages,
            sections=sections,
            metadata={
                "sheets": [sheet.title for sheet in book.worksheets]
            },
            warnings=warnings,
        )

    def _parse_csv(self, data: bytes) -> ParsedDocument:
        text = self._decode_text(data)
        try:
            dialect = csv.Sniffer().sniff(text[:4096])
        except Exception:
            dialect = csv.excel
        rows = [
            " | ".join(cell.strip() for cell in row)
            for row in csv.reader(io.StringIO(text), dialect)
        ]
        cleaned = "\n".join(row for row in rows if row.strip(" |"))
        return ParsedDocument(
            parser="stdlib-csv",
            parser_version=self.PARSER_VERSION,
            pages=[{"number": 1, "text": cleaned, "method": "csv"}],
            sections=[
                {
                    "heading": "CSV",
                    "level": 1,
                    "ordinal": 1,
                    "text": cleaned,
                    "page_start": 1,
                    "page_end": 1,
                }
            ],
            metadata={"rows": len(rows)},
            warnings=[] if cleaned else ["csv_no_rows"],
        )

    def _parse_html(self, data: bytes) -> ParsedDocument:
        raw = self._decode_text(data)
        soup = BeautifulSoup(raw, "html.parser")
        for node in soup(["script", "style", "noscript"]):
            node.decompose()
        text = "\n".join(
            line.strip()
            for line in soup.get_text("\n").splitlines()
            if line.strip()
        )
        sections = []
        ordinal = 0
        for heading in soup.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6"]
        ):
            title = heading.get_text(" ", strip=True)
            if not title:
                continue
            ordinal += 1
            sections.append(
                {
                    "heading": title,
                    "level": int(heading.name[1]),
                    "ordinal": ordinal,
                    "text": "",
                    "page_start": 1,
                    "page_end": 1,
                }
            )
        return ParsedDocument(
            parser="beautifulsoup4",
            parser_version=self.PARSER_VERSION,
            pages=[
                {"number": 1, "text": text, "method": "html_text"}
            ],
            sections=sections or self._sections_from_text(text),
            metadata={
                "title": (
                    soup.title.get_text(" ", strip=True)
                    if soup.title else ""
                )
            },
            warnings=[] if text else ["html_no_visible_text"],
        )

    def _parse_text(
        self,
        data: bytes,
        *,
        extension: str,
    ) -> ParsedDocument:
        text = self._decode_text(data)
        return ParsedDocument(
            parser="plain-text",
            parser_version=self.PARSER_VERSION,
            pages=[
                {
                    "number": 1,
                    "text": text,
                    "method": extension.lstrip("."),
                }
            ],
            sections=self._sections_from_text(text),
            metadata={"extension": extension},
            warnings=[] if text.strip() else ["text_empty"],
        )

    def _parse_image(
        self,
        data: bytes,
        *,
        filename: str,
    ) -> ParsedDocument:
        with Image.open(io.BytesIO(data)) as image:
            metadata = {
                "width": image.width,
                "height": image.height,
                "mode": image.mode,
                "format": image.format,
                "filename": filename,
            }
        return ParsedDocument(
            parser="pillow-image-inspection",
            parser_version=self.PARSER_VERSION,
            pages=[
                {
                    "number": 1,
                    "text": "",
                    "method": "image_requires_ocr",
                }
            ],
            sections=[],
            metadata=metadata,
            warnings=[
                "ocr_required_no_local_ocr_adapter_configured"
            ],
            ocr_required=True,
        )

    def _persist_pages(
        self,
        *,
        scope: str,
        document_id: int,
        parsed: ParsedDocument,
    ) -> list[dict]:
        result = []
        with connect() as conn:
            for page in parsed.pages:
                text = str(page.get("text") or "")
                quality = self._page_quality(text)
                provenance = {
                    "document_id": document_id,
                    "page": int(page["number"]),
                    "parser": parsed.parser,
                    "method": page.get("method"),
                }
                cur = conn.execute(
                    """INSERT INTO document_pages(
                           scope, document_id, page_number, text_content,
                           char_count, quality_score, extraction_method,
                           provenance_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        scope, document_id, int(page["number"]), text,
                        len(text), quality, str(page.get("method") or ""),
                        json.dumps(provenance, ensure_ascii=False),
                    ),
                )
                result.append(
                    {
                        "id": int(cur.lastrowid),
                        "number": int(page["number"]),
                        "text": text,
                        "quality": quality,
                        "provenance": provenance,
                    }
                )
            conn.commit()
        return result

    def _persist_sections(
        self,
        *,
        scope: str,
        document_id: int,
        parsed: ParsedDocument,
    ) -> list[dict]:
        result = []
        with connect() as conn:
            for index, section in enumerate(parsed.sections, start=1):
                provenance = {
                    "document_id": document_id,
                    "heading": section.get("heading") or "",
                    "page_start": section.get("page_start"),
                    "page_end": section.get("page_end"),
                }
                cur = conn.execute(
                    """INSERT INTO document_sections(
                           scope, document_id, heading, level, ordinal,
                           page_start, page_end, text_content,
                           provenance_json
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        scope, document_id,
                        str(section.get("heading") or ""),
                        max(1, int(section.get("level") or 1)),
                        int(section.get("ordinal") or index),
                        section.get("page_start"),
                        section.get("page_end"),
                        str(section.get("text") or ""),
                        json.dumps(provenance, ensure_ascii=False),
                    ),
                )
                result.append(
                    {
                        "id": int(cur.lastrowid),
                        **section,
                        "provenance": provenance,
                    }
                )
            conn.commit()
        return result

    def _persist_chunks(
        self,
        *,
        scope: str,
        document_id: int,
        pages: list[dict],
        sections: list[dict],
        base_quality: float,
    ) -> list[dict]:
        result = []
        ordinal = 0
        with connect() as conn:
            for page in pages:
                for text in self._chunk_text(page["text"]):
                    ordinal += 1
                    section = self._section_for_page(
                        sections, page["number"]
                    )
                    content_hash = self._hash(text)
                    key = (
                        f"p{page['number']}:c{ordinal}:"
                        f"{content_hash[:12]}"
                    )
                    provenance = {
                        "document_id": document_id,
                        "page": page["number"],
                        "section_id": (
                            section.get("id") if section else None
                        ),
                        "heading": (
                            section.get("heading") if section else ""
                        ),
                        "chunk_ordinal": ordinal,
                    }
                    quality = min(
                        1.0,
                        0.70 * float(page["quality"])
                        + 0.30 * base_quality,
                    )
                    cur = conn.execute(
                        """INSERT INTO document_chunks(
                               scope, document_id, page_id, section_id,
                               ordinal, chunk_key, text_content,
                               token_estimate, quality_score, content_hash,
                               provenance_json
                           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            scope, document_id, int(page["id"]),
                            int(section["id"]) if section else None,
                            ordinal, key, text, max(1, len(text) // 4),
                            quality, content_hash,
                            json.dumps(provenance, ensure_ascii=False),
                        ),
                    )
                    result.append(
                        {
                            "id": int(cur.lastrowid),
                            "document_id": document_id,
                            "page_id": int(page["id"]),
                            "page": page["number"],
                            "section_id": (
                                int(section["id"]) if section else None
                            ),
                            "heading": (
                                section.get("heading") if section else ""
                            ),
                            "ordinal": ordinal,
                            "text": text,
                            "quality": quality,
                            "content_hash": content_hash,
                            "provenance": provenance,
                        }
                    )
            conn.commit()
        return result

    def _extract_deterministic_facts(
        self,
        *,
        scope: str,
        document_id: int,
        chunks: list[dict],
        quality: float,
        coverage: float,
        ocr_required: bool,
    ) -> int:
        grounded = (
            not ocr_required
            and quality >= self.QUALITY_GATE
            and coverage >= self.COVERAGE_GATE
        )
        status = "grounded" if grounded else "candidate"
        created = 0
        for chunk in chunks:
            candidates: list[dict] = []
            for line in chunk["text"].splitlines():
                clean = _SPACE_RE.sub(" ", line.strip())
                if not clean:
                    continue
                match = _KEY_VALUE_RE.match(clean)
                if match:
                    candidates.append(
                        {
                            "subject": match.group(1).strip(),
                            "predicate": "has_value",
                            "value": match.group(2).strip(),
                            "fact_type": "key_value",
                        }
                    )
            for value in _DATE_RE.findall(chunk["text"]):
                candidates.append(
                    {
                        "subject": "document",
                        "predicate": "mentions_date",
                        "value": value,
                        "fact_type": "date",
                    }
                )
            for amount, currency in _MONEY_RE.findall(chunk["text"]):
                candidates.append(
                    {
                        "subject": "document",
                        "predicate": "mentions_amount",
                        "value": f"{amount.strip()} {currency}",
                        "fact_type": "money",
                    }
                )
            for value in _PERCENT_RE.findall(chunk["text"]):
                candidates.append(
                    {
                        "subject": "document",
                        "predicate": "mentions_percent",
                        "value": value.replace(",", ".") + "%",
                        "fact_type": "percent",
                    }
                )
            for value in _EMAIL_RE.findall(chunk["text"]):
                candidates.append(
                    {
                        "subject": "document",
                        "predicate": "mentions_email",
                        "value": value,
                        "fact_type": "email",
                    }
                )
            for value in _URL_RE.findall(chunk["text"]):
                candidates.append(
                    {
                        "subject": "document",
                        "predicate": "mentions_url",
                        "value": value.rstrip(".,;"),
                        "fact_type": "url",
                    }
                )

            seen = set()
            for item in candidates[:80]:
                normalized = self._normalize_value(item["value"])
                fact_key = self._fact_key(
                    item["subject"], item["predicate"]
                )
                key = (fact_key, normalized)
                if not normalized or key in seen:
                    continue
                seen.add(key)
                provenance = {
                    **chunk["provenance"],
                    "chunk_id": chunk["id"],
                    "evidence_text": item["value"][:500],
                    "extraction": "deterministic",
                }
                if self._insert_fact(
                    scope=scope,
                    document_id=document_id,
                    chunk_id=int(chunk["id"]),
                    fact_key=fact_key,
                    subject=item["subject"],
                    predicate=item["predicate"],
                    value=item["value"],
                    normalized_value=normalized,
                    fact_type=item["fact_type"],
                    confidence=min(
                        0.96,
                        0.72 + 0.24 * float(chunk["quality"]),
                    ),
                    status=status,
                    provenance=provenance,
                ):
                    created += 1
        return created

    def _ai_enrich(
        self,
        *,
        scope: str,
        document_id: int,
        chunks: list[dict],
        document_quality: float,
    ) -> dict:
        selected = [
            {
                "chunk_id": int(item["id"]),
                "page": item["page"],
                "heading": item["heading"],
                "text": item["text"][:2200],
            }
            for item in chunks[:18]
            if len(item["text"].strip()) >= 40
        ]
        if not selected:
            return {"facts": 0, "entities": 0, "relations": 0}

        system = """Ты модуль структурного извлечения Aishin Document Intelligence.
Работай ТОЛЬКО с переданными chunks.
Верни только JSON:
{
 "entities":[{"name":"...", "type":"person|organization|vehicle|product|place|document_ref|other", "chunk_id":1, "evidence_quote":"точная цитата"}],
 "relations":[{"source":"...", "relation":"...", "target":"...", "chunk_id":1, "evidence_quote":"точная цитата", "confidence":0.8}],
 "facts":[{"subject":"...", "predicate":"...", "value":"...", "chunk_id":1, "evidence_quote":"точная цитата", "confidence":0.8}]
}
Каждый evidence_quote обязан дословно присутствовать в соответствующем chunk.
Не используй внешние знания. Не делай выводов, которых нет в тексте."""
        reply = self.ai.chat(
            system=system,
            messages=[
                {
                    "role": "user",
                    "content": json.dumps(
                        {"chunks": selected}, ensure_ascii=False
                    ),
                }
            ],
        )
        if not reply.available:
            return {
                "facts": 0,
                "entities": 0,
                "relations": 0,
                "warning": "ai_enrichment_unavailable",
            }

        payload = self._parse_json(reply.text)
        by_id = {int(item["id"]): item for item in chunks}
        entities: dict[str, int] = {}
        facts_created = 0
        entity_count = 0
        relation_count = 0

        for item in payload.get("entities") or []:
            if not isinstance(item, dict):
                continue
            chunk = by_id.get(self._as_int(item.get("chunk_id")))
            quote = str(item.get("evidence_quote") or "").strip()
            name = str(item.get("name") or "").strip()
            entity_type = str(item.get("type") or "other").strip()
            if (
                chunk is None
                or not name
                or not self._quote_grounded(quote, chunk["text"])
            ):
                continue
            provenance = {
                **chunk["provenance"],
                "chunk_id": chunk["id"],
                "evidence_quote": quote,
                "document_id": document_id,
                "extraction": "ai_grounded",
            }
            entity_id = self.graph.entity(
                scope=scope,
                entity_type=f"document_{entity_type}",
                name=name,
                data={
                    "document_id": document_id,
                    "provenance": provenance,
                },
                evidence=json.dumps(
                    provenance, ensure_ascii=False
                ),
            )
            entities[name.casefold()] = entity_id
            entity_count += 1

        for item in payload.get("facts") or []:
            if not isinstance(item, dict):
                continue
            chunk = by_id.get(self._as_int(item.get("chunk_id")))
            quote = str(item.get("evidence_quote") or "").strip()
            subject = str(item.get("subject") or "").strip()
            predicate = str(item.get("predicate") or "").strip()
            value = str(item.get("value") or "").strip()
            if (
                chunk is None
                or not subject
                or not predicate
                or not value
                or not self._quote_grounded(quote, chunk["text"])
            ):
                continue
            confidence = min(
                document_quality,
                self._clamp(item.get("confidence"), 0.0, 1.0),
                float(chunk["quality"]),
            )
            provenance = {
                **chunk["provenance"],
                "chunk_id": chunk["id"],
                "evidence_quote": quote,
                "extraction": "ai_grounded",
            }
            if self._insert_fact(
                scope=scope,
                document_id=document_id,
                chunk_id=int(chunk["id"]),
                fact_key=self._fact_key(subject, predicate),
                subject=subject,
                predicate=predicate,
                value=value,
                normalized_value=self._normalize_value(value),
                fact_type="ai_grounded",
                confidence=confidence,
                status=(
                    "grounded" if confidence >= 0.70
                    else "candidate"
                ),
                provenance=provenance,
            ):
                facts_created += 1

        for item in payload.get("relations") or []:
            if not isinstance(item, dict):
                continue
            chunk = by_id.get(self._as_int(item.get("chunk_id")))
            quote = str(item.get("evidence_quote") or "").strip()
            source_name = str(item.get("source") or "").strip()
            target_name = str(item.get("target") or "").strip()
            relation = str(item.get("relation") or "").strip()
            if (
                chunk is None
                or not source_name
                or not target_name
                or not relation
                or not self._quote_grounded(quote, chunk["text"])
            ):
                continue
            source_id = entities.get(source_name.casefold())
            target_id = entities.get(target_name.casefold())
            if source_id is None:
                source_id = self.graph.entity(
                    scope=scope,
                    entity_type="document_other",
                    name=source_name,
                    data={"document_id": document_id},
                    evidence=quote,
                )
            if target_id is None:
                target_id = self.graph.entity(
                    scope=scope,
                    entity_type="document_other",
                    name=target_name,
                    data={"document_id": document_id},
                    evidence=quote,
                )
            self.graph.relate(
                scope=scope,
                source_id=source_id,
                relation_type=self._relation_name(relation),
                target_id=target_id,
                confidence=min(
                    document_quality,
                    self._clamp(
                        item.get("confidence"), 0.0, 1.0
                    ),
                ),
                evidence=json.dumps(
                    {
                        **chunk["provenance"],
                        "chunk_id": chunk["id"],
                        "evidence_quote": quote,
                        "document_id": document_id,
                    },
                    ensure_ascii=False,
                ),
            )
            relation_count += 1

        return {
            "facts": facts_created,
            "entities": entity_count,
            "relations": relation_count,
        }

    def _insert_fact(
        self,
        *,
        scope: str,
        document_id: int,
        chunk_id: int | None,
        fact_key: str,
        subject: str,
        predicate: str,
        value: str,
        normalized_value: str,
        fact_type: str,
        confidence: float,
        status: str,
        provenance: dict,
    ) -> bool:
        if not normalized_value:
            return False
        with connect() as conn:
            before = conn.total_changes
            conn.execute(
                """INSERT OR IGNORE INTO document_facts(
                       scope, document_id, chunk_id, fact_key,
                       subject, predicate, value, normalized_value,
                       fact_type, confidence, status, provenance_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    scope, document_id, chunk_id, fact_key,
                    subject[:250], predicate[:120], value[:1500],
                    normalized_value[:1500], fact_type,
                    self._clamp(confidence, 0.0, 1.0), status,
                    json.dumps(provenance, ensure_ascii=False),
                ),
            )
            changed = conn.total_changes > before
            conn.commit()
        return changed

    def _detect_contradictions(
        self,
        *,
        scope: str,
        document_id: int,
        family_key: str,
    ) -> int:
        if not family_key:
            return 0
        with connect() as conn:
            current = conn.execute(
                """SELECT id, fact_key, normalized_value, confidence
                   FROM document_facts
                   WHERE scope=? AND document_id=?
                     AND status='grounded'
                     AND fact_type IN ('key_value','ai_grounded')""",
                (scope, document_id),
            ).fetchall()
            created = 0
            for fact in current:
                others = conn.execute(
                    """SELECT f.id, f.normalized_value, f.confidence
                       FROM document_facts f
                       JOIN documents d ON d.id=f.document_id
                       WHERE f.scope=? AND f.document_id<>?
                         AND f.fact_key=? AND f.status='grounded'
                         AND d.family_key=?""",
                    (
                        scope, document_id, fact["fact_key"],
                        family_key,
                    ),
                ).fetchall()
                for other in others:
                    if (
                        self._normalize_value(other["normalized_value"])
                        == self._normalize_value(fact["normalized_value"])
                    ):
                        continue
                    left_id, right_id = sorted(
                        (int(other["id"]), int(fact["id"]))
                    )
                    severity = min(
                        0.95,
                        0.55
                        + 0.20 * float(fact["confidence"] or 0.0)
                        + 0.20 * float(other["confidence"] or 0.0),
                    )
                    before = conn.total_changes
                    conn.execute(
                        """INSERT OR IGNORE INTO document_contradictions(
                               scope, family_key, fact_key,
                               left_fact_id, right_fact_id, severity
                           ) VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            scope, family_key, fact["fact_key"],
                            left_id, right_id, severity,
                        ),
                    )
                    if conn.total_changes > before:
                        created += 1
            conn.commit()
        if created:
            self.research.create_gap(
                scope=scope,
                question=(
                    f"Перепроверить {created} противоречий между версиями "
                    f"документов семейства {family_key}"
                ),
                origin="document_contradiction",
                origin_ref=f"document:{document_id}",
                priority=min(0.95, 0.62 + 0.06 * created),
                uncertainty=0.78,
                impact=min(0.90, 0.58 + 0.05 * created),
            )
        return created

    def _index_graph(
        self,
        *,
        scope: str,
        document_id: int,
        filename: str,
        family_key: str,
        version_label: str,
        quality: float,
        previous: dict | None,
        sections: list[dict],
        sha256: str,
    ) -> int:
        doc_entity = self.graph.entity(
            scope=scope,
            entity_type="document",
            name=f"Document {document_id}: {filename}",
            data={
                "document_id": document_id,
                "filename": filename,
                "family_key": family_key,
                "version_label": version_label,
                "quality_score": quality,
                "sha256": sha256,
            },
            evidence=f"document:{document_id}",
        )
        for section in sections[:60]:
            heading = str(section.get("heading") or "").strip()
            if not heading:
                continue
            sec_entity = self.graph.entity(
                scope=scope,
                entity_type="document_section",
                name=f"Document {document_id} · {heading[:180]}",
                data={
                    "document_id": document_id,
                    "section_id": section["id"],
                    "page_start": section.get("page_start"),
                    "page_end": section.get("page_end"),
                },
                evidence=json.dumps(
                    section.get("provenance") or {},
                    ensure_ascii=False,
                ),
            )
            self.graph.relate(
                scope=scope,
                source_id=doc_entity,
                relation_type="contains_section",
                target_id=sec_entity,
                confidence=quality,
                evidence=f"document:{document_id}",
            )
        if previous:
            candidates = self.graph.search(
                f"Document {int(previous['id'])}:",
                scope=scope,
                limit=10,
            )
            previous_entity = next(
                (
                    item for item in candidates
                    if int(
                        (item.get("data") or {}).get(
                            "document_id", -1
                        )
                    ) == int(previous["id"])
                ),
                None,
            )
            if previous_entity:
                self.graph.relate(
                    scope=scope,
                    source_id=doc_entity,
                    relation_type="supersedes_document",
                    target_id=int(previous_entity["id"]),
                    confidence=0.92,
                    evidence=(
                        f"family_key={family_key}; "
                        f"version={version_label}"
                    ),
                )
        return doc_entity

    def _register_research_source(
        self,
        *,
        scope: str,
        document_id: int,
        filename: str,
        sha256: str,
        quality: float,
        duplicate_of_id: int | None,
        graph_entity_id: int,
    ) -> dict | None:
        try:
            canonical_id = duplicate_of_id or document_id
            return self.research.register_source(
                scope=scope,
                source_key=f"document:{document_id}",
                source_type="document",
                label=filename,
                locator=str(document_id),
                independent_group=f"document:{canonical_id}",
                trust_prior=max(0.45, min(0.96, quality)),
                enabled=True,
                auto_read=True,
                metadata={
                    "document_id": document_id,
                    "sha256": sha256,
                    "quality_score": quality,
                    "graph_entity_id": graph_entity_id,
                    "duplicate_of_id": duplicate_of_id,
                },
            )
        except Exception as exc:
            self._event(
                scope=scope,
                document_id=document_id,
                event_type="document.research_source.failed",
                score=0.0,
                details={"error": str(exc)[:500]},
            )
            return None

    def ensure_semantic_index(
        self,
        *,
        scope: str,
        document_id: int | None = None,
        batch_size: int = 24,
    ) -> dict:
        health = self.ai.embedding_health()
        if not health.get("configured"):
            return {
                "indexed": 0,
                "available": False,
                "reason": "not_configured",
            }
        model = str(health.get("model") or "")
        with connect() as conn:
            rows = conn.execute(
                """SELECT c.id, c.text_content, c.content_hash
                   FROM document_chunks c
                   LEFT JOIN document_chunk_vectors v
                     ON v.chunk_id=c.id AND v.model=?
                   WHERE c.scope=?
                     AND (? IS NULL OR c.document_id=?)
                     AND (
                       v.chunk_id IS NULL
                       OR v.content_hash<>c.content_hash
                     )
                   ORDER BY c.id ASC LIMIT ?""",
                (
                    model, scope, document_id, document_id,
                    max(1, min(int(batch_size), 48)),
                ),
            ).fetchall()
        if not rows:
            return {
                "indexed": 0,
                "available": True,
                "reason": "up_to_date",
                "model": model,
            }
        reply = self.ai.embed(
            [str(row["text_content"]) for row in rows]
        )
        if not reply.available:
            return {
                "indexed": 0,
                "available": False,
                "reason": reply.error or "embedding_failed",
            }
        indexed = 0
        with connect() as conn:
            for row, vector in zip(rows, reply.vectors):
                conn.execute(
                    """INSERT INTO document_chunk_vectors(
                           chunk_id, scope, model, dimensions,
                           vector_json, content_hash
                       ) VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(chunk_id) DO UPDATE SET
                           scope=excluded.scope,
                           model=excluded.model,
                           dimensions=excluded.dimensions,
                           vector_json=excluded.vector_json,
                           content_hash=excluded.content_hash,
                           updated_at=CURRENT_TIMESTAMP""",
                    (
                        int(row["id"]), scope, reply.model,
                        len(vector), json.dumps(vector),
                        str(row["content_hash"]),
                    ),
                )
                indexed += 1
            conn.commit()
        return {
            "indexed": indexed,
            "available": True,
            "model": reply.model,
            "dimensions": reply.dimensions,
        }

    def search(
        self,
        query: str,
        *,
        scope: str,
        limit: int = 12,
    ) -> list[dict]:
        query = query.strip()
        if not query:
            return []
        semantic = self._semantic_search(
            query=query, scope=scope, limit=limit
        )
        if semantic:
            return semantic
        return self._lexical_search(
            query=query, scope=scope, limit=limit
        )

    def reasoning_evidence(
        self,
        query: str,
        *,
        scope: str,
        limit: int = 8,
    ) -> dict:
        """Return grounded document evidence for the reasoning controller.

        Document text is data, never instructions. Only studied documents are
        eligible because search() already filters the retrieval corpus.
        """
        chunks = self.search(query, scope=scope, limit=limit)
        document_ids = {
            int(item["document_id"])
            for item in chunks
            if item.get("document_id") is not None
        }
        evidence = []
        for item in chunks:
            quality = min(
                float(item.get("quality_score") or 0.0),
                float(item.get("document_quality") or 0.0),
            )
            evidence.append(
                {
                    "source": "document",
                    "document_id": int(item["document_id"]),
                    "chunk_id": int(item["chunk_id"]),
                    "filename": item.get("filename"),
                    "confidence": max(0.0, min(1.0, quality)),
                    "retrieval_score": float(item.get("score") or 0.0),
                    "content": str(item.get("text") or "")[:1200],
                    "provenance": item.get("provenance") or {},
                    "trust_boundary": "untrusted_document_data",
                }
            )

        contradictions = []
        if document_ids:
            for item in self.contradictions(
                scope=scope,
                status="open",
                limit=80,
            ):
                if (
                    int(item.get("left_document_id") or -1) in document_ids
                    or int(item.get("right_document_id") or -1) in document_ids
                ):
                    contradictions.append(
                        {
                            **item,
                            "source": "document",
                            "summary": (
                                f"Документы {item.get('left_document_id')} и "
                                f"{item.get('right_document_id')} содержат "
                                "разные grounded значения одного fact_key."
                            ),
                        }
                    )
        return {
            "chunks": chunks,
            "evidence": evidence,
            "contradictions": contradictions,
            "document_ids": sorted(document_ids),
        }

    def _semantic_search(
        self,
        *,
        query: str,
        scope: str,
        limit: int,
    ) -> list[dict]:
        self.ensure_semantic_index(scope=scope, batch_size=48)
        reply = self.ai.embed([query])
        if not reply.available or not reply.vectors:
            return []
        vector = reply.vectors[0]
        with connect() as conn:
            rows = conn.execute(
                """SELECT c.id, c.document_id, c.text_content,
                          c.quality_score, c.provenance_json,
                          d.filename, d.status,
                          d.quality_score AS document_quality,
                          v.vector_json
                   FROM document_chunk_vectors v
                   JOIN document_chunks c ON c.id=v.chunk_id
                   JOIN documents d ON d.id=c.document_id
                   WHERE c.scope=? AND v.model=?
                     AND d.status IN ('studied','quality_hold')
                   ORDER BY c.id DESC LIMIT 1200""",
                (scope, reply.model),
            ).fetchall()
        scored = []
        for row in rows:
            try:
                stored = json.loads(row["vector_json"])
            except Exception:
                continue
            similarity = cosine_similarity(vector, stored)
            if similarity < 0.22:
                continue
            scored.append(
                (
                    similarity,
                    self._chunk_result(
                        dict(row),
                        score=similarity,
                        method="semantic",
                    ),
                )
            )
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def _lexical_search(
        self,
        *,
        query: str,
        scope: str,
        limit: int,
    ) -> list[dict]:
        tokens = list(self._tokens(query))[:12]
        if not tokens:
            return []
        where = " OR ".join(
            ["LOWER(c.text_content) LIKE ?" for _ in tokens]
        )
        params = [f"%{token.casefold()}%" for token in tokens]
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT c.id, c.document_id, c.text_content,
                           c.quality_score, c.provenance_json,
                           d.filename, d.status,
                           d.quality_score AS document_quality
                    FROM document_chunks c
                    JOIN documents d ON d.id=c.document_id
                    WHERE c.scope=? AND ({where})
                      AND d.status IN ('studied','quality_hold')
                    ORDER BY c.quality_score DESC, c.id DESC
                    LIMIT 160""",
                (scope, *params),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            score = self._relevance(
                query, item["text_content"]
            )
            if score < 0.10:
                continue
            result.append(
                self._chunk_result(
                    item, score=score, method="lexical"
                )
            )
        result.sort(
            key=lambda item: item["score"], reverse=True
        )
        return result[:limit]

    def dashboard(
        self,
        *,
        scope: str,
        document_limit: int = 80,
        fact_limit: int = 80,
        contradiction_limit: int = 60,
        run_limit: int = 40,
    ) -> dict:
        state = self._refresh_state(scope)
        documents = self.documents(
            scope=scope, limit=document_limit
        )
        facts = self.facts(scope=scope, limit=fact_limit)
        contradictions = self.contradictions(
            scope=scope, status=None, limit=contradiction_limit
        )
        runs = self.runs(scope=scope, limit=run_limit)
        return {
            "version": self.VERSION,
            "formula_version": self.FORMULA_VERSION,
            "scope": scope,
            "summary": {
                **state,
                "documents": len(documents),
                "supported_extensions": sorted(
                    self.SUPPORTED_EXTENSIONS
                ),
                "quality_gate": self.QUALITY_GATE,
                "coverage_gate": self.COVERAGE_GATE,
            },
            "documents": documents,
            "facts": facts,
            "contradictions": contradictions,
            "runs": runs,
            "principles": [
                "Оригинал сохраняется неизменным; SHA-256 определяет точный дубликат.",
                "Документ не превращается целиком в долговременную память.",
                "Каждый chunk и fact хранит provenance до документа и страницы/раздела.",
                "AI extraction принимается только при дословно grounded evidence_quote.",
                "Скан без текстового слоя получает needs_ocr и не проходит Quality Gate.",
                "Дубликаты не считаются независимыми research-источниками.",
                "Противоречия версий не разрешаются автоматически и создают Research Gap.",
                "Semantic index работает только при доступном embedding provider и имеет lexical fallback.",
                "Quality score оценивает извлечение, а не истинность содержания документа.",
            ],
        }

    def document(
        self, document_id: int, *, scope: str
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE id=? AND scope=?",
                (document_id, scope),
            ).fetchone()
        return self._decode_document(dict(row)) if row else None

    def document_detail(
        self,
        document_id: int,
        *,
        scope: str,
        chunk_limit: int = 120,
    ) -> dict:
        doc = self.document(document_id, scope=scope)
        if doc is None:
            raise ValueError("document not found")
        with connect() as conn:
            pages = [
                self._decode_provenance(dict(row))
                for row in conn.execute(
                    "SELECT * FROM document_pages WHERE document_id=? ORDER BY page_number",
                    (document_id,),
                ).fetchall()
            ]
            sections = [
                self._decode_provenance(dict(row))
                for row in conn.execute(
                    "SELECT * FROM document_sections WHERE document_id=? ORDER BY ordinal",
                    (document_id,),
                ).fetchall()
            ]
            chunks = [
                self._decode_provenance(dict(row))
                for row in conn.execute(
                    "SELECT * FROM document_chunks WHERE document_id=? ORDER BY ordinal LIMIT ?",
                    (document_id, max(1, min(chunk_limit, 500))),
                ).fetchall()
            ]
        return {
            "document": doc,
            "pages": pages,
            "sections": sections,
            "chunks": chunks,
            "facts": self.facts(
                scope=scope, document_id=document_id, limit=300
            ),
            "contradictions": self.contradictions(
                scope=scope,
                document_id=document_id,
                status=None,
                limit=200,
            ),
        }

    def documents(
        self,
        *,
        scope: str,
        status: str | None = None,
        limit: int = 80,
    ) -> list[dict]:
        with connect() as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE scope=? AND status=? ORDER BY id DESC LIMIT ?",
                    (scope, status, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM documents WHERE scope=? ORDER BY id DESC LIMIT ?",
                    (scope, max(1, min(limit, 500))),
                ).fetchall()
        return [self._decode_document(dict(row)) for row in rows]

    def facts(
        self,
        *,
        scope: str,
        document_id: int | None = None,
        limit: int = 100,
    ) -> list[dict]:
        with connect() as conn:
            if document_id is None:
                rows = conn.execute(
                    """SELECT f.*, d.filename
                       FROM document_facts f
                       JOIN documents d ON d.id=f.document_id
                       WHERE f.scope=?
                       ORDER BY f.confidence DESC, f.id DESC LIMIT ?""",
                    (scope, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT f.*, d.filename
                       FROM document_facts f
                       JOIN documents d ON d.id=f.document_id
                       WHERE f.scope=? AND f.document_id=?
                       ORDER BY f.confidence DESC, f.id DESC LIMIT ?""",
                    (
                        scope, document_id,
                        max(1, min(limit, 500)),
                    ),
                ).fetchall()
        return [
            self._decode_provenance(dict(row))
            for row in rows
        ]

    def contradictions(
        self,
        *,
        scope: str,
        document_id: int | None = None,
        status: str | None = "open",
        limit: int = 80,
    ) -> list[dict]:
        where = ["c.scope=?"]
        params: list[Any] = [scope]
        if status:
            where.append("c.status=?")
            params.append(status)
        if document_id is not None:
            where.append("(lf.document_id=? OR rf.document_id=?)")
            params.extend([document_id, document_id])
        params.append(max(1, min(limit, 500)))
        with connect() as conn:
            rows = conn.execute(
                f"""SELECT c.*,
                           lf.document_id AS left_document_id,
                           lf.value AS left_value,
                           rf.document_id AS right_document_id,
                           rf.value AS right_value
                    FROM document_contradictions c
                    JOIN document_facts lf ON lf.id=c.left_fact_id
                    JOIN document_facts rf ON rf.id=c.right_fact_id
                    WHERE {' AND '.join(where)}
                    ORDER BY c.severity DESC, c.id DESC LIMIT ?""",
                tuple(params),
            ).fetchall()
        return [dict(row) for row in rows]

    def resolve_contradiction(
        self,
        contradiction_id: int,
        *,
        scope: str,
        resolution: str,
    ) -> dict:
        resolution = resolution.strip()
        if not resolution:
            raise ValueError("resolution is empty")
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM document_contradictions WHERE id=? AND scope=?",
                (contradiction_id, scope),
            ).fetchone()
            if row is None:
                raise ValueError("document contradiction not found")
            conn.execute(
                """UPDATE document_contradictions
                   SET status='resolved', resolution=?,
                       resolved_at=CURRENT_TIMESTAMP
                   WHERE id=? AND scope=?""",
                (resolution[:2000], contradiction_id, scope),
            )
            conn.commit()
            updated = conn.execute(
                "SELECT * FROM document_contradictions WHERE id=? AND scope=?",
                (contradiction_id, scope),
            ).fetchone()
        self._refresh_state(scope)
        return dict(updated)

    def runs(self, *, scope: str, limit: int = 50) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT r.*, d.filename
                   FROM document_ingestion_runs r
                   JOIN documents d ON d.id=r.document_id
                   WHERE r.scope=? ORDER BY r.id DESC LIMIT ?""",
                (scope, max(1, min(limit, 300))),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["warnings"] = self._json(
                item.pop("warnings_json"), []
            )
            result.append(item)
        return result

    def state(self, *, scope: str) -> dict:
        self._ensure_state(scope)
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM document_state WHERE scope=?",
                (scope,),
            ).fetchone()
        return dict(row) if row else {}

    def _refresh_state(self, scope: str) -> dict:
        self._ensure_state(scope)
        with connect() as conn:
            docs = conn.execute(
                """SELECT status, quality_score, extraction_coverage,
                          ocr_required, duplicate_of_id
                   FROM documents WHERE scope=?""",
                (scope,),
            ).fetchall()
            facts = conn.execute(
                "SELECT COUNT(*) AS n FROM document_facts WHERE scope=?",
                (scope,),
            ).fetchone()
            contradictions = conn.execute(
                """SELECT COUNT(*) AS n FROM document_contradictions
                   WHERE scope=? AND status='open'""",
                (scope,),
            ).fetchone()
            chunks = conn.execute(
                "SELECT COUNT(*) AS n FROM document_chunks WHERE scope=?",
                (scope,),
            ).fetchone()
            vectors = conn.execute(
                "SELECT COUNT(*) AS n FROM document_chunk_vectors WHERE scope=?",
                (scope,),
            ).fetchone()

        total = len(docs)
        studied = sum(1 for row in docs if row["status"] == "studied")
        queued = sum(
            1 for row in docs
            if row["status"] in {"queued", "processing"}
        )
        failed = sum(1 for row in docs if row["status"] == "failed")
        duplicates = sum(
            1 for row in docs if row["duplicate_of_id"] is not None
        )
        ocr = sum(1 for row in docs if bool(row["ocr_required"]))
        quality = self._average(
            [
                float(row["quality_score"] or 0.0)
                for row in docs if row["status"] != "failed"
            ]
        )
        coverage = self._average(
            [
                float(row["extraction_coverage"] or 0.0)
                for row in docs if row["status"] != "failed"
            ]
        )
        chunk_count = int(chunks["n"] or 0)
        vector_count = int(vectors["n"] or 0)
        semantic_coverage = (
            vector_count / chunk_count if chunk_count else 0.0
        )
        volume = self._sat(studied, 20.0)
        ingestion_score = 100.0 * (
            0.34 * (studied / total if total else 0.0)
            + 0.26 * quality
            + 0.22 * coverage
            + 0.18 * semantic_coverage
        ) * (0.42 + 0.58 * volume)

        with connect() as conn:
            conn.execute(
                """UPDATE document_state SET
                   ingestion_score=?, extraction_quality=?,
                   provenance_coverage=?, semantic_coverage=?,
                   studied_documents=?, queued_documents=?,
                   failed_documents=?, duplicate_documents=?,
                   ocr_required_documents=?, fact_count=?,
                   contradiction_count=?, updated_at=CURRENT_TIMESTAMP
                   WHERE scope=?""",
                (
                    round(ingestion_score, 2),
                    round(quality * 100.0, 2),
                    round(coverage * 100.0, 2),
                    round(semantic_coverage * 100.0, 2),
                    studied, queued, failed, duplicates, ocr,
                    int(facts["n"] or 0),
                    int(contradictions["n"] or 0),
                    scope,
                ),
            )
            conn.commit()
        return self.state(scope=scope)

    def _quality(
        self, parsed: ParsedDocument
    ) -> tuple[float, float]:
        pages = parsed.pages
        if not pages:
            return 0.0, 0.0
        nonempty = [
            page for page in pages
            if str(page.get("text") or "").strip()
        ]
        coverage = len(nonempty) / len(pages)
        chars = sum(
            len(str(page.get("text") or ""))
            for page in pages
        )
        volume = self._sat(
            chars, max(500.0, len(pages) * 600.0)
        )
        structure = min(
            1.0,
            0.35 + 0.12 * min(4, len(parsed.sections))
        )
        warning_penalty = min(0.35, 0.04 * len(parsed.warnings))
        quality = (
            0.46 * coverage
            + 0.34 * volume
            + 0.20 * structure
            - warning_penalty
        )
        if parsed.ocr_required:
            quality = min(quality, 0.28)
        return (
            round(self._clamp(quality), 4),
            round(self._clamp(coverage), 4),
        )

    def _page_quality(self, text: str) -> float:
        clean = text.strip()
        if not clean:
            return 0.0
        printable = sum(
            1 for char in clean
            if char.isprintable() and char != "\ufffd"
        )
        printable_ratio = printable / max(1, len(clean))
        volume = self._sat(len(clean), 700.0)
        return round(
            self._clamp(
                0.62 * printable_ratio + 0.38 * volume
            ),
            4,
        )

    def _detect_near_duplicate(
        self,
        *,
        scope: str,
        document_id: int,
        family_key: str,
        chunks: list[dict],
    ) -> int | None:
        current_tokens = self._tokens(
            " ".join(item["text"] for item in chunks[:40])
        )
        if not current_tokens:
            return None
        with connect() as conn:
            docs = conn.execute(
                """SELECT id FROM documents
                   WHERE scope=? AND id<>? AND family_key=?
                     AND status<>'failed'
                   ORDER BY id DESC LIMIT 12""",
                (scope, document_id, family_key),
            ).fetchall()
            for doc in docs:
                rows = conn.execute(
                    "SELECT text_content FROM document_chunks WHERE document_id=? ORDER BY ordinal LIMIT 40",
                    (int(doc["id"]),),
                ).fetchall()
                other_tokens = self._tokens(
                    " ".join(row["text_content"] for row in rows)
                )
                if not other_tokens:
                    continue
                jaccard = len(
                    current_tokens & other_tokens
                ) / max(1, len(current_tokens | other_tokens))
                if jaccard >= 0.96:
                    return int(doc["id"])
        return None

    def _rebuild_family_lineage(
        self,
        *,
        scope: str,
        family_key: str,
    ) -> None:
        if not family_key:
            return

        relation_pairs: list[tuple[int, int, int, int]] = []
        with connect() as conn:
            rows = conn.execute(
                """SELECT id, version_rank FROM documents
                   WHERE scope=? AND family_key=?
                     AND status<>'failed'
                     AND duplicate_of_id IS NULL
                     AND version_rank IS NOT NULL
                   ORDER BY version_rank ASC, id ASC""",
                (scope, family_key),
            ).fetchall()

            previous_id: int | None = None
            previous_rank: int | None = None
            lineage: list[tuple[int, int | None]] = []
            for row in rows:
                rank = int(row["version_rank"])
                expected_previous = (
                    previous_id
                    if previous_rank is not None and rank > previous_rank
                    else None
                )
                document_id = int(row["id"])
                conn.execute(
                    """UPDATE documents SET previous_version_id=?,
                       updated_at=CURRENT_TIMESTAMP
                       WHERE id=? AND scope=?""",
                    (expected_previous, document_id, scope),
                )
                lineage.append((document_id, expected_previous))
                if previous_rank is None or rank > previous_rank:
                    previous_id = document_id
                    previous_rank = rank

            entity_rows = conn.execute(
                """SELECT id, data_json FROM entities
                   WHERE scope=? AND entity_type='document'""",
                (scope,),
            ).fetchall()
            entity_by_document: dict[int, int] = {}
            family_entity_ids: list[int] = []
            for entity_row in entity_rows:
                data = self._json(entity_row["data_json"], {})
                if str(data.get("family_key") or "") != family_key:
                    continue
                document_id = data.get("document_id")
                if document_id is None:
                    continue
                entity_id = int(entity_row["id"])
                entity_by_document[int(document_id)] = entity_id
                family_entity_ids.append(entity_id)

            if family_entity_ids:
                placeholders = ",".join("?" for _ in family_entity_ids)
                conn.execute(
                    f"""DELETE FROM relations
                        WHERE scope=?
                          AND relation_type='supersedes_document'
                          AND (
                            source_entity_id IN ({placeholders})
                            OR target_entity_id IN ({placeholders})
                          )""",
                    (
                        scope,
                        *family_entity_ids,
                        *family_entity_ids,
                    ),
                )

            for document_id, previous_document_id in lineage:
                if previous_document_id is None:
                    continue
                source_entity = entity_by_document.get(document_id)
                target_entity = entity_by_document.get(previous_document_id)
                if source_entity and target_entity:
                    relation_pairs.append(
                        (
                            source_entity,
                            target_entity,
                            document_id,
                            previous_document_id,
                        )
                    )
            conn.commit()

        for (
            source_entity,
            target_entity,
            document_id,
            previous_document_id,
        ) in relation_pairs:
            self.graph.relate(
                scope=scope,
                source_id=source_entity,
                relation_type="supersedes_document",
                target_id=target_entity,
                confidence=0.96,
                evidence=(
                    f"family_key={family_key}; "
                    f"document={document_id}; previous={previous_document_id}; "
                    "rebuilt_lineage=true"
                ),
            )

        self._event(
            scope=scope,
            document_id=None,
            event_type="document.lineage.rebuilt",
            score=1.0,
            details={
                "family_key": family_key,
                "documents": len(relation_pairs) + (1 if rows else 0),
                "relations": len(relation_pairs),
            },
        )

    def _rebuild_all_lineage(self, *, scope: str) -> int:
        with connect() as conn:
            rows = conn.execute(
                """SELECT DISTINCT family_key FROM documents
                   WHERE scope=? AND family_key<>''
                     AND version_rank IS NOT NULL""",
                (scope,),
            ).fetchall()
        families = [
            str(row["family_key"])
            for row in rows
            if str(row["family_key"] or "").strip()
        ]
        for family_key in families:
            self._rebuild_family_lineage(
                scope=scope,
                family_key=family_key,
            )
        return len(families)

    def _previous_family_document(
        self,
        *,
        scope: str,
        family_key: str,
        version_rank: int | None,
    ) -> dict | None:
        if not family_key:
            return None
        with connect() as conn:
            if version_rank is not None:
                row = conn.execute(
                    """SELECT * FROM documents
                       WHERE scope=? AND family_key=?
                         AND status<>'failed'
                         AND version_rank IS NOT NULL
                         AND version_rank<?
                       ORDER BY version_rank DESC, id DESC LIMIT 1""",
                    (scope, family_key, version_rank),
                ).fetchone()
                return dict(row) if row is not None else None
            row = conn.execute(
                """SELECT * FROM documents
                   WHERE scope=? AND family_key=?
                     AND status<>'failed'
                     AND version_rank IS NULL
                   ORDER BY id DESC LIMIT 1""",
                (scope, family_key),
            ).fetchone()
        return dict(row) if row else None

    def _store_original(
        self,
        *,
        scope: str,
        sha256: str,
        filename: str,
        data: bytes,
    ) -> Path:
        scope_key = re.sub(
            r"[^A-Za-z0-9_.-]+", "_", scope
        )[:80] or "personal"
        folder = self.root / scope_key / sha256[:2] / sha256
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (
            "original" + Path(filename).suffix.casefold()
        )
        if not path.exists():
            path.write_bytes(data)
        return path

    def _sections_from_pages(
        self, pages: list[dict]
    ) -> list[dict]:
        result = []
        ordinal = 0
        for page in pages:
            headings = [
                line.strip()
                for line in str(page.get("text") or "").splitlines()
                if self._looks_heading(line.strip())
            ]
            for heading in headings[:12]:
                ordinal += 1
                result.append(
                    {
                        "heading": heading[:180],
                        "level": self._heading_level(heading),
                        "ordinal": ordinal,
                        "text": "",
                        "page_start": int(page["number"]),
                        "page_end": int(page["number"]),
                    }
                )
        return result

    def _sections_from_text(self, text: str) -> list[dict]:
        result = []
        ordinal = 0
        for line in text.splitlines():
            clean = line.strip()
            if not self._looks_heading(clean):
                continue
            ordinal += 1
            result.append(
                {
                    "heading": clean[:180],
                    "level": self._heading_level(clean),
                    "ordinal": ordinal,
                    "text": "",
                    "page_start": 1,
                    "page_end": 1,
                }
            )
        return result[:100]

    def _chunk_text(self, text: str) -> list[str]:
        clean = text.strip()
        if not clean:
            return []
        paragraphs = [
            _SPACE_RE.sub(" ", item.strip())
            for item in re.split(r"\n\s*\n|\r?\n", clean)
            if item.strip()
        ]
        chunks: list[str] = []
        current = ""
        for paragraph in paragraphs:
            if len(paragraph) > self.CHUNK_TARGET * 2:
                start = 0
                while start < len(paragraph):
                    piece = paragraph[
                        start : start + self.CHUNK_TARGET
                    ].strip()
                    if piece:
                        if current:
                            chunks.append(current.strip())
                            current = ""
                        chunks.append(piece)
                    start += max(
                        1,
                        self.CHUNK_TARGET - self.CHUNK_OVERLAP,
                    )
                continue
            candidate = (
                paragraph if not current
                else current + "\n" + paragraph
            )
            if len(candidate) <= self.CHUNK_TARGET:
                current = candidate
            else:
                if current:
                    chunks.append(current.strip())
                tail = (
                    current[-self.CHUNK_OVERLAP :]
                    if current else ""
                )
                current = (
                    (tail + "\n" + paragraph).strip()
                    if tail else paragraph
                )
        if current:
            chunks.append(current.strip())
        return [
            item for item in chunks if len(item) >= 20
        ]

    def _section_for_page(
        self,
        sections: list[dict],
        page_number: int,
    ) -> dict | None:
        candidates = [
            item for item in sections
            if item.get("page_start") is not None
            and int(item["page_start"]) <= page_number
            and (
                item.get("page_end") is None
                or int(item["page_end"]) >= page_number
            )
        ]
        return candidates[-1] if candidates else None

    def _document_by_sha(
        self,
        *,
        scope: str,
        sha256: str,
    ) -> dict | None:
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE scope=? AND sha256=?",
                (scope, sha256),
            ).fetchone()
        return dict(row) if row else None

    def _document_type(self, extension: str) -> str:
        return {
            ".pdf": "pdf",
            ".docx": "word",
            ".xlsx": "spreadsheet",
            ".csv": "table",
            ".txt": "text",
            ".md": "markdown",
            ".html": "web_archive",
            ".htm": "web_archive",
        }.get(
            extension,
            "image" if extension in self.IMAGE_EXTENSIONS
            else "generic",
        )

    def _family_key(self, filename: str) -> str:
        stem = Path(filename).stem.casefold().replace("ё", "е")
        stem = _VERSION_RE.sub(" ", stem)
        stem = _YEAR_RE.sub(" ", stem)
        stem = re.sub(
            r"\b(?:копия|copy|final|финал|new|новый|ред)\b",
            " ",
            stem,
            flags=re.IGNORECASE,
        )
        stem = re.sub(r"[^a-zа-я0-9]+", " ", stem)
        stem = _SPACE_RE.sub(" ", stem).strip()
        return stem[:180] or Path(filename).stem.casefold()[:180]

    def _version_info(
        self, filename: str
    ) -> tuple[str, int | None]:
        stem = Path(filename).stem
        version = _VERSION_RE.search(stem)
        year = _YEAR_RE.search(stem)
        if version:
            label = (
                version.group(1)
                .replace("_", ".")
                .replace("-", ".")
            )
            parts = [
                int(item)
                for item in label.split(".")
                if item.isdigit()
            ][:4]
            rank = 0
            for part in parts:
                rank = rank * 1000 + min(part, 999)
            return f"v{label}", rank
        if year:
            y = int(year.group(1))
            return str(y), y * 1_000_000
        return "", None

    def _fact_key(self, subject: str, predicate: str) -> str:
        base = (
            self._normalize_value(subject)
            + "|"
            + self._normalize_value(predicate)
        )
        return hashlib.sha256(
            base.encode("utf-8")
        ).hexdigest()[:24]

    def _normalize_value(self, value: Any) -> str:
        text = str(value or "").casefold().replace("ё", "е")
        text = re.sub(r"[“”\"']", "", text)
        text = _SPACE_RE.sub(" ", text)
        return text.strip(" \t\r\n.;,:")

    def _relation_name(self, value: str) -> str:
        text = self._normalize_value(value)
        text = re.sub(r"[^a-zа-я0-9]+", "_", text)
        return text[:80].strip("_") or "related_to"

    def _looks_heading(self, text: str) -> bool:
        if not text or len(text) > 120:
            return False
        if _HEADING_RE.match(text):
            return len(text.split()) <= 14
        return False

    def _heading_level(self, text: str) -> int:
        match = re.match(r"^(\d+(?:\.\d+)*)", text)
        if not match:
            return 1
        return min(6, match.group(1).count(".") + 1)

    def _decode_text(self, data: bytes) -> str:
        for encoding in (
            "utf-8-sig", "utf-8", "cp1251", "windows-1252"
        ):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    def _safe_filename(self, filename: str) -> str:
        name = Path(filename or "document").name.strip()
        name = re.sub(
            r"[\x00-\x1f<>:\"/\\|?*]+", "_", name
        )
        return name[:240] or "document"

    def _chunk_result(
        self,
        row: dict,
        *,
        score: float,
        method: str,
    ) -> dict:
        return {
            "chunk_id": int(row["id"]),
            "document_id": int(row["document_id"]),
            "filename": row["filename"],
            "text": row["text_content"],
            "score": round(float(score), 5),
            "method": method,
            "quality_score": float(
                row["quality_score"] or 0.0
            ),
            "document_quality": float(
                row["document_quality"] or 0.0
            ),
            "provenance": self._json(
                row["provenance_json"], {}
            ),
        }

    def _decode_document(self, item: dict) -> dict:
        item["ocr_required"] = bool(item["ocr_required"])
        item["metadata"] = self._json(
            item.pop("metadata_json"), {}
        )
        return item

    def _decode_provenance(self, item: dict) -> dict:
        if "provenance_json" in item:
            item["provenance"] = self._json(
                item.pop("provenance_json"), {}
            )
        return item

    def _fact_count(
        self,
        *,
        scope: str,
        document_id: int,
    ) -> int:
        with connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS n FROM document_facts
                   WHERE scope=? AND document_id=?""",
                (scope, document_id),
            ).fetchone()
        return int(row["n"] or 0)

    def _contradiction_count(
        self,
        *,
        scope: str,
        document_id: int,
    ) -> int:
        return len(
            self.contradictions(
                scope=scope,
                document_id=document_id,
                status=None,
                limit=1000,
            )
        )

    def _vector_count(
        self,
        *,
        scope: str,
        document_id: int,
    ) -> int:
        with connect() as conn:
            row = conn.execute(
                """SELECT COUNT(*) AS n
                   FROM document_chunk_vectors v
                   JOIN document_chunks c ON c.id=v.chunk_id
                   WHERE v.scope=? AND c.document_id=?""",
                (scope, document_id),
            ).fetchone()
        return int(row["n"] or 0)

    def _ensure_state(self, scope: str) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO document_state(scope)
                   VALUES (?) ON CONFLICT(scope) DO NOTHING""",
                (scope,),
            )
            conn.commit()

    def _event(
        self,
        *,
        scope: str,
        document_id: int | None,
        event_type: str,
        score: float | None,
        details: dict,
    ) -> None:
        with connect() as conn:
            conn.execute(
                """INSERT INTO document_events(
                       scope, document_id, event_type, score, details_json
                   ) VALUES (?, ?, ?, ?, ?)""",
                (
                    scope, document_id, event_type, score,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
        try:
            self.events.emit(
                event_type,
                scope=scope,
                payload={
                    "document_id": document_id,
                    "score": score,
                    **details,
                },
                importance=max(
                    0.16,
                    min(0.82, float(score or 0.25)),
                ),
            )
        except Exception:
            pass

    @staticmethod
    def _tokens(text: str) -> set[str]:
        stop = {
            "это", "как", "что", "для", "или", "при", "если",
            "the", "and", "with", "from", "document", "документ",
        }
        return {
            word.casefold().replace("ё", "е")
            for word in _WORD_RE.findall(text or "")
            if word.casefold() not in stop
        }

    @classmethod
    def _relevance(cls, query: str, text: str) -> float:
        q = cls._tokens(query)
        t = cls._tokens(text)
        if not q or not t:
            return 0.0
        overlap = len(q & t)
        return cls._clamp(
            0.80 * overlap / max(1, len(q))
            + 0.20 * overlap / max(1, min(40, len(t)))
        )

    @staticmethod
    def _quote_grounded(quote: str, text: str) -> bool:
        q = _SPACE_RE.sub(" ", quote.strip()).casefold()
        t = _SPACE_RE.sub(" ", text.strip()).casefold()
        return bool(q) and len(q) >= 4 and q in t

    @staticmethod
    def _parse_json(text: str) -> dict:
        raw = (text or "").strip()
        marker = chr(96) * 3
        if raw.startswith(marker):
            raw = re.sub(r"^.{3}(?:json)?\s*", "", raw, count=1)
            raw = re.sub(r"\s*.{3}$", "", raw, count=1)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(raw[start:end + 1])
                    return data if isinstance(data, dict) else {}
                except Exception:
                    pass
        return {}

    @staticmethod
    def _json(value: Any, default: Any) -> Any:
        if isinstance(value, (dict, list)):
            return value
        if value in (None, ""):
            return default
        try:
            return json.loads(str(value))
        except Exception:
            return default

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _average(values: list[float]) -> float:
        return sum(values) / len(values) if values else 0.0

    @staticmethod
    def _sat(value: float, target: float) -> float:
        if target <= 0:
            return 0.0
        return min(
            1.0,
            1.0 - math.exp(-max(0.0, float(value)) / target),
        )

    @staticmethod
    def _clamp(
        value: Any,
        low: float = 0.0,
        high: float = 1.0,
    ) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = 0.0
        return max(low, min(high, number))
