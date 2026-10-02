from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass

from ..ai import AIManager
from ..db import add_verification_run, recent_verification_runs
from .graph import KnowledgeGraph
from .memory import MemorySystem
from .semantic import SemanticMemory
from .sensors import SensorHub
from .tools import ToolRegistry


_FILE_RE = re.compile(
    r"""(?:"|')?([\wА-Яа-яЁё./\\ -]+\.(?:txt|md|json|csv|log|py|js|ts|html|css|xml|yaml|yml))(?:"|')?""",
    re.IGNORECASE,
)


@dataclass
class VerificationReport:
    ran: bool
    initial_status: str
    checks: list[dict]
    findings: list[str]
    unresolved: list[str]
    expanded_memories: list[dict]
    consistency: dict

    def to_dict(self) -> dict:
        return asdict(self)


class VerificationEngine:
    """Grounded re-check loop for low-confidence or contradictory context."""

    TRIGGER_STATUSES = {"needs_verification"}

    def __init__(
        self,
        *,
        ai: AIManager,
        memory: MemorySystem,
        semantic: SemanticMemory,
        graph: KnowledgeGraph,
        sensors: SensorHub,
        tools: ToolRegistry,
    ) -> None:
        self.ai = ai
        self.memory = memory
        self.semantic = semantic
        self.graph = graph
        self.sensors = sensors
        self.tools = tools

    def should_run(self, *, intent: str, status: str) -> bool:
        if intent == "verification":
            return True
        if status in self.TRIGGER_STATUSES:
            return True
        return intent == "action" and status == "insufficient_data"

    def verify(
        self,
        query: str,
        *,
        scope: str,
        initial_status: str,
    ) -> VerificationReport:
        checks: list[dict] = []
        findings: list[str] = []
        unresolved: list[str] = []

        lexical = self.memory.recall(query, scope=scope, limit=12)
        semantic = self.semantic.search(query, scope=scope, limit=12)
        expanded = self._merge_memories(lexical, semantic, limit=16)
        checks.append(
            {
                "source": "memory",
                "status": "ok",
                "lexical": len(lexical),
                "semantic": len(semantic),
                "combined": len(expanded),
            }
        )
        if expanded:
            findings.append(
                f"Расширенный поиск памяти дал {len(expanded)} релевантных записей."
            )
        else:
            unresolved.append("Расширенный поиск памяти не дал подтверждений.")

        graph_hits = self.graph.search(query, scope=scope, limit=20)
        checks.append(
            {
                "source": "knowledge_graph",
                "status": "ok",
                "matches": len(graph_hits),
            }
        )
        if graph_hits:
            findings.append(
                f"Knowledge Graph дал совпадений сущностей: {len(graph_hits)}."
            )
        else:
            unresolved.append("Knowledge Graph не дал прямого совпадения по запросу.")

        sensors = self.sensors.scan(scope=scope, persist=False)
        attention = [
            item
            for item in sensors
            if item.get("status") not in {"ok"}
        ]
        checks.append(
            {
                "source": "sensors",
                "status": "attention" if attention else "ok",
                "channels": len(sensors),
                "attention": len(attention),
            }
        )
        if attention:
            findings.append(
                f"Сенсоры сообщили состояний attention: {len(attention)}."
            )

        file_evidence = self._verify_explicit_files(query, scope=scope)
        checks.extend(file_evidence["checks"])
        findings.extend(file_evidence["findings"])
        unresolved.extend(file_evidence["unresolved"])

        consistency = self._consistency_check(
            query=query,
            memories=expanded,
            graph_hits=graph_hits,
            file_snippets=file_evidence["snippets"],
        )
        checks.append(
            {
                "source": "cloudru_consistency",
                "status": (
                    "ok"
                    if consistency.get("available")
                    else "unavailable"
                ),
                "conflicts": len(consistency.get("conflicts", [])),
            }
        )

        for item in consistency.get("confirmed", [])[:6]:
            findings.append(f"Согласованность: {item}")
        for item in consistency.get("conflicts", [])[:6]:
            unresolved.append(f"Противоречие: {item}")
        for item in consistency.get("missing", [])[:6]:
            unresolved.append(f"Не хватает: {item}")

        return VerificationReport(
            ran=True,
            initial_status=initial_status,
            checks=checks,
            findings=self._unique(findings),
            unresolved=self._unique(unresolved),
            expanded_memories=expanded,
            consistency=consistency,
        )

    def record(
        self,
        report: VerificationReport,
        *,
        scope: str,
        query: str,
        final_status: str,
    ) -> int:
        return add_verification_run(
            scope=scope,
            query=query[:1000],
            initial_status=report.initial_status,
            final_status=final_status,
            checks=report.checks,
            findings=report.findings,
            unresolved=report.unresolved,
        )

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        return recent_verification_runs(scope, limit=limit)

    @staticmethod
    def prompt_block(report: VerificationReport) -> str:
        if not report.ran:
            return "Verification Engine: дополнительная проверка не требовалась."

        lines = [
            "Verification Engine выполнил дополнительную перепроверку.",
            f"Исходный статус: {report.initial_status}.",
        ]
        if report.findings:
            lines.append("Что удалось подтвердить или уточнить:")
            for item in report.findings[:8]:
                lines.append(f"- {item}")
        if report.unresolved:
            lines.append("Что осталось нерешённым:")
            for item in report.unresolved[:8]:
                lines.append(f"- {item}")
        lines.append(
            "Используй проверенные данные как дополнительную опору. "
            "Не называй Cloud.ru независимым источником истины: его роль здесь — "
            "проверка согласованности уже собранных свидетельств."
        )
        return "\n".join(lines)

    def _verify_explicit_files(self, query: str, *, scope: str) -> dict:
        checks: list[dict] = []
        findings: list[str] = []
        unresolved: list[str] = []
        snippets: list[dict] = []

        paths = []
        for match in _FILE_RE.findall(query):
            path = match.strip().replace("\\", "/")
            if path and path not in paths:
                paths.append(path)

        for path in paths[:3]:
            result = self.tools.invoke(
                "project.read_text",
                scope=scope,
                arguments={"path": path},
                dry_run=False,
                approved=True,
            )
            status = result.get("status")
            output = result.get("output") or {}
            checks.append(
                {
                    "source": "project_file",
                    "path": path,
                    "status": status,
                }
            )

            if status != "success":
                unresolved.append(
                    f"Файл «{path}» не удалось проверить: "
                    f"{output.get('error', status)}."
                )
                continue

            content = str(output.get("content") or "")
            snippets.append(
                {
                    "path": path,
                    "snippet": content[:3000],
                }
            )
            findings.append(
                f"Файл «{path}» прочитан для проверки, размер текста: {len(content)} символов."
            )

        return {
            "checks": checks,
            "findings": findings,
            "unresolved": unresolved,
            "snippets": snippets,
        }

    def _consistency_check(
        self,
        *,
        query: str,
        memories: list[dict],
        graph_hits: list[dict],
        file_snippets: list[dict],
    ) -> dict:
        evidence = {
            "memories": [
                {
                    "id": item.get("id"),
                    "content": item.get("content"),
                    "confidence": item.get("confidence"),
                    "kind": item.get("kind"),
                }
                for item in memories[:10]
            ],
            "graph": [
                {
                    "id": item.get("id"),
                    "type": item.get("entity_type"),
                    "name": item.get("canonical_name"),
                    "data": item.get("data"),
                }
                for item in graph_hits[:10]
            ],
            "files": file_snippets[:3],
        }

        if not any(evidence.values()):
            return {
                "available": False,
                "confirmed": [],
                "conflicts": [],
                "missing": ["Нет локальных свидетельств для проверки согласованности."],
            }

        system = """Ты модуль проверки согласованности данных Aishin.
Работай ТОЛЬКО с переданными свидетельствами. Не используй внешние знания.
Верни только JSON:
{
  "confirmed":["что согласуется"],
  "conflicts":["что противоречит друг другу"],
  "missing":["чего не хватает для ответа"]
}
Не называй отсутствие данных подтверждением. Не придумывай факты."""
        prompt = json.dumps(
            {
                "query": query,
                "evidence": evidence,
            },
            ensure_ascii=False,
        )

        reply = self.ai.chat(
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if not reply.available:
            return {
                "available": False,
                "confirmed": [],
                "conflicts": [],
                "missing": ["Cloud.ru недоступен для проверки согласованности."],
            }

        raw = reply.text.strip()
        fence = chr(96) * 3
        if raw.startswith(fence):
            raw = re.sub(r"^.{3}(?:json)?\s*", "", raw, count=1)
            raw = re.sub(r"\s*.{3}$", "", raw, count=1)

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {
                "available": False,
                "confirmed": [],
                "conflicts": [],
                "missing": ["Cloud.ru вернул неструктурированный результат проверки."],
            }

        return {
            "available": True,
            "confirmed": self._string_list(data.get("confirmed")),
            "conflicts": self._string_list(data.get("conflicts")),
            "missing": self._string_list(data.get("missing")),
        }

    @staticmethod
    def _merge_memories(
        lexical: list[dict],
        semantic: list[dict],
        *,
        limit: int,
    ) -> list[dict]:
        merged: dict[int, dict] = {}
        for item in lexical + semantic:
            try:
                key = int(item["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if key not in merged:
                merged[key] = dict(item)
            else:
                merged[key].update(
                    {
                        key_name: value
                        for key_name, value in item.items()
                        if value is not None
                    }
                )
        ranked = sorted(
            merged.values(),
            key=lambda item: (
                float(item.get("retrieval_score", 0.0)),
                float(item.get("confidence", 0.0)),
                float(item.get("importance", 0.0)),
            ),
            reverse=True,
        )
        return ranked[:limit]

    @staticmethod
    def _string_list(value) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ][:10]

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for item in items:
            key = item.casefold()
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result
