from __future__ import annotations

import json
from typing import Any, Dict, Generator, List, Optional

from app.services.claude_client import ClaudeClient, ClaudeClientFactory


class ExplanationService:
    """
    Generates a human-readable business explanation from query results.
    Single Responsibility: prompt construction + Claude call for explanation.
    Dependency injected: receives a ClaudeClient instance.
    """

    _SYSTEM_PROMPT = """\
You are an analytics assistant for BeastInsights, an e-commerce/subscription BI platform.

Rules:
- Be concise, business-focused, and analytical.
- Use the actual numbers from the query result. NEVER invent data.
- If the result is empty, say so and suggest likely reasons (date range, no data yet today, etc.).
- Highlight notable patterns: trends, outliers, large changes.
- Format currency with $ and commas (e.g., $12,345.67).
- Format percentages to 2 decimal places.
- Use bullet points for multi-metric answers.
- Keep the response under 300 words unless the data warrants more detail.
"""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._claude = claude_client

    @staticmethod
    def _truncate_rows(
        rows: List[Dict[str, Any]], max_rows: int = 50
    ) -> str:
        """Format rows for the prompt, truncating if too many."""
        if not rows:
            return "(no rows returned)"
        display = rows[:max_rows]
        result = json.dumps(display, indent=2, default=str)
        if len(rows) > max_rows:
            result += (
                f"\n... ({len(rows)} total rows, showing first {max_rows})"
            )
        return result

    def generate(
        self,
        question: str,
        columns: List[str],
        rows: List[Dict[str, Any]],
        view_table: str,
        sql: str,
    ) -> str:
        """Send query results to Claude for a business-focused explanation."""
        data_block = self._truncate_rows(rows)

        user_message = (
            f"User Question: {question}\n\n"
            f"Data Source: {view_table}\n"
            f"SQL Used: {sql}\n\n"
            f"Query Result ({len(rows)} rows):\n"
            f"Columns: {columns}\n"
            f"Data:\n{data_block}"
        )

        return self._claude.chat(
            system=self._SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1024,
        )

    def generate_stream(
        self,
        question: str,
        columns: List[str],
        rows: List[Dict[str, Any]],
        view_table: str,
        sql: str,
    ) -> Generator[str, None, None]:
        """Stream explanation tokens from Claude as they arrive."""
        data_block = self._truncate_rows(rows)

        user_message = (
            f"User Question: {question}\n\n"
            f"Data Source: {view_table}\n"
            f"SQL Used: {sql}\n\n"
            f"Query Result ({len(rows)} rows):\n"
            f"Columns: {columns}\n"
            f"Data:\n{data_block}"
        )

        yield from self._claude.chat_stream(
            system=self._SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1024,
        )


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (used by router)
# ---------------------------------------------------------------------------
_default_service: Optional[ExplanationService] = None


def _get_default() -> ExplanationService:
    global _default_service
    if _default_service is None:
        _default_service = ExplanationService(
            ClaudeClientFactory.get_default()
        )
    return _default_service


def generate_explanation(
    question: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
    view_table: str,
    sql: str,
) -> str:
    return _get_default().generate(question, columns, rows, view_table, sql)


def generate_explanation_stream(
    question: str,
    columns: List[str],
    rows: List[Dict[str, Any]],
    view_table: str,
    sql: str,
) -> Generator[str, None, None]:
    yield from _get_default().generate_stream(question, columns, rows, view_table, sql)
