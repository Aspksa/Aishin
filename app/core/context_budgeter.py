from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from ..db import connect


@dataclass
class ContextBudgetReport:
    request_id: str
    mode: str
    token_budget: int
    estimated_tokens_before: int
    estimated_tokens_after: int
    trimmed_chars: int
    history_before: int
    history_after: int
    report_id: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ContextBudgeter:
    """Final safety budget applied immediately before the provider call."""

    TOKEN_BUDGETS = {
        "FAST": 7000,
        "DEEP": 11000,
        "VERIFY": 13000,
        "PLAN": 11000,
        "DIAGNOSE": 13000,
    }
    RESERVED_OUTPUT_TOKENS = 1800
    CHARS_PER_TOKEN = 3.6

    def budget_for(self, mode: str) -> int:
        return self.TOKEN_BUDGETS.get(mode, self.TOKEN_BUDGETS["FAST"])

    def fit(
        self,
        *,
        request_id: str,
        scope: str,
        mode: str,
        system_prompt: str,
        messages: list[dict],
    ) -> tuple[str, list[dict], ContextBudgetReport]:
        total_budget = self.budget_for(mode)
        input_budget = max(1500, total_budget - self.RESERVED_OUTPUT_TOKENS)
        before = self._estimate(system_prompt, messages)
        original_chars = len(system_prompt) + sum(
            len(str(x.get("content") or "")) for x in messages
        )
        fitted_messages = [dict(x) for x in messages]

        while len(fitted_messages) > 2 and self._estimate(
            system_prompt, fitted_messages
        ) > input_budget:
            fitted_messages.pop(0)

        fitted_system = system_prompt
        if self._estimate(fitted_system, fitted_messages) > input_budget:
            message_tokens = self._estimate("", fitted_messages)
            allowed_system_tokens = max(800, input_budget - message_tokens)
            allowed_chars = max(
                2400,
                int(allowed_system_tokens * self.CHARS_PER_TOKEN),
            )
            if len(fitted_system) > allowed_chars:
                head = int(allowed_chars * 0.72)
                tail = max(0, allowed_chars - head - 160)
                fitted_system = (
                    fitted_system[:head]
                    + "\n\n[Context Budgeter: часть низкоприоритетного "
                      "контекста сокращена.]\n\n"
                    + (fitted_system[-tail:] if tail else "")
                )

        after = self._estimate(fitted_system, fitted_messages)
        fitted_chars = len(fitted_system) + sum(
            len(str(x.get("content") or "")) for x in fitted_messages
        )
        report = ContextBudgetReport(
            request_id=request_id,
            mode=mode,
            token_budget=total_budget,
            estimated_tokens_before=before,
            estimated_tokens_after=after,
            trimmed_chars=max(0, original_chars - fitted_chars),
            history_before=len(messages),
            history_after=len(fitted_messages),
        )
        report.report_id = self._record(scope=scope, report=report)
        return fitted_system, fitted_messages, report

    def recent(self, *, scope: str, limit: int = 30) -> list[dict]:
        with connect() as conn:
            rows = conn.execute(
                """SELECT * FROM context_budget_reports
                   WHERE scope=? ORDER BY id DESC LIMIT ?""",
                (scope, limit),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    @classmethod
    def _estimate(cls, system_prompt: str, messages: list[dict]) -> int:
        chars = len(system_prompt) + sum(
            len(str(x.get("content") or "")) for x in messages
        )
        overhead = 24 + (len(messages) * 8)
        return int(math.ceil(chars / cls.CHARS_PER_TOKEN)) + overhead

    @staticmethod
    def _record(*, scope: str, report: ContextBudgetReport) -> int:
        details = {
            "history_before": report.history_before,
            "history_after": report.history_after,
            "reserved_output_tokens": ContextBudgeter.RESERVED_OUTPUT_TOKENS,
        }
        with connect() as conn:
            cur = conn.execute(
                """INSERT OR REPLACE INTO context_budget_reports(
                       request_id, scope, mode, token_budget,
                       estimated_tokens_before, estimated_tokens_after,
                       trimmed_chars, details_json
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.request_id,
                    scope,
                    report.mode,
                    report.token_budget,
                    report.estimated_tokens_before,
                    report.estimated_tokens_after,
                    report.trimmed_chars,
                    json.dumps(details, ensure_ascii=False),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)
