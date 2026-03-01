from __future__ import annotations

import json
from typing import Any, Dict, Generator, List, Optional, Union

from app.services.claude_client import ClaudeClient, ClaudeClientFactory
from app.services.visualization_prompt import VISUALIZATION_APPENDIX_PROMPT


class ExplanationService:
    """
    Generates a human-readable business explanation from query results.
    Single Responsibility: prompt construction + Claude call for explanation.
    Dependency injected: receives a ClaudeClient instance.
    """

    _SYSTEM_PROMPT = """\
You are an analytics assistant for BeastInsights, an e-commerce/subscription BI platform.

INSIGHT (required in every answer):
An insight is: a derived, contextualized conclusion from structured data that reduces uncertainty and informs action.
Every answer MUST include at least one clear insight — not just a summary of the numbers. Give a conclusion that helps the user decide what to do (e.g. what to watch, what to change, what is working or at risk).

Rules:
- Be concise, business-focused, and analytical.
- Use the actual numbers from the query result. NEVER invent data.
- The columns and data provided are query results for explanation only — do not use them to generate SQL. Use the actual numbers from the query result. NEVER invent data.
- If the result is empty, say so and suggest likely reasons (date range, no data yet today, etc.).
- Highlight notable patterns: trends, outliers, large changes.
- Format currency with $ and commas (e.g., $12,345.67).
- Format percentages to 2 decimal places.
- Use bullet points for multi-metric answers.
- Keep the response under 300 words unless the data warrants more detail.
"""

    _COMBINED_SYSTEM_PROMPT = """\
You are an analytics assistant for BeastInsights, an e-commerce/subscription BI platform.

You are answering from MULTIPLE data sources (several views and/or fixed insight reports).

INSIGHT (required in every answer):
An insight is: a derived, contextualized conclusion from structured data that reduces uncertainty and informs action.
Every answer MUST include at least one clear insight — not just a summary of the numbers. Give a conclusion that helps the user decide what to do (e.g. what to watch, what to change, what is working or at risk).

The structured data (including any column names) is for explanation only — do not use it to generate SQL.

STRICT RULES (like a report formatter):
1. ONLY use the numbers and facts provided in the structured data below. NEVER invent or estimate.
2. If the user refers to previous context (e.g. "what about that?", "compare to last time"), use the conversation history to interpret and answer.
3. Be concise, business-focused, and analytical. Highlight notable patterns, trends, and comparisons across sources.
4. Format currency with $ and commas. Format percentages to 2 decimal places.
5. Use bullet points and clear structure when multiple metrics or sources are involved.
6. If a section has no data or null values, say "Data not available" — do NOT guess.
7. Keep the response under 400 words unless the data warrants more detail.
"""

    _MARKER_START = "__VISUALIZATION_JSON_START__"
    _MARKER_END = "__VISUALIZATION_JSON_END__"

    @property
    def _system_prompt(self) -> str:
        return self._SYSTEM_PROMPT + "\n\n" + VISUALIZATION_APPENDIX_PROMPT

    @property
    def _combined_system_prompt(self) -> str:
        return self._COMBINED_SYSTEM_PROMPT + "\n\n" + VISUALIZATION_APPENDIX_PROMPT

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

    @staticmethod
    def _format_combined_data_for_prompt(
        combined_data: Dict[str, Any], max_rows_per_view: int = 50
    ) -> str:
        """Format aggregated multi-source data for the combined explanation prompt."""
        out: Dict[str, Any] = {"views": {}, "insights": combined_data.get("insights", {})}
        for view_key, block in combined_data.get("views", {}).items():
            rows = block.get("rows") or []
            display = rows[:max_rows_per_view]
            out["views"][view_key] = {
                "table_name": block.get("table_name"),
                "sql": block.get("sql"),
                "columns": block.get("columns"),
                "rows": display,
                "row_count": len(rows),
            }
            if len(rows) > max_rows_per_view:
                out["views"][view_key]["_truncated"] = (
                    f"Showing first {max_rows_per_view} of {len(rows)} rows"
                )
        return json.dumps(out, indent=2, default=str)

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
            f"Query Result ({len(rows)} rows). Columns and Data below are for explanation only (do not use for SQL):\n"
            f"Columns: {columns}\n"
            f"Data:\n{data_block}"
        )

        return self._claude.chat(
            system=self._system_prompt,
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
    ) -> Generator[Union[str, Dict[str, Any]], None, None]:
        """Stream explanation tokens from Claude; yields text or visualization payload."""
        data_block = self._truncate_rows(rows)

        user_message = (
            f"User Question: {question}\n\n"
            f"Data Source: {view_table}\n"
            f"SQL Used: {sql}\n\n"
            f"Query Result ({len(rows)} rows). Columns and Data below are for explanation only (do not use for SQL):\n"
            f"Columns: {columns}\n"
            f"Data:\n{data_block}"
        )

        buffer = ""
        json_buffer = ""
        inside_json = False

        for chunk in self._claude.chat_stream(
            system=self._system_prompt,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=1024,
        ):
            buffer += chunk

            if self._MARKER_START in buffer:
                before, _, after = buffer.partition(self._MARKER_START)
                if before:
                    yield before
                json_buffer = after
                buffer = ""
                inside_json = True
            elif inside_json:
                json_buffer += buffer
                buffer = ""
                if self._MARKER_END in json_buffer:
                    json_part, _, rest = json_buffer.partition(self._MARKER_END)
                    try:
                        parsed = json.loads(json_part.strip())
                        if isinstance(parsed, dict) and "visualizations" in parsed and isinstance(parsed["visualizations"], list):
                            for item in parsed["visualizations"]:
                                yield {"type": "visualization", "payload": item}
                        else:
                            yield {"type": "visualization", "payload": parsed}
                    except json.JSONDecodeError:
                        pass
                    json_buffer = rest
                    inside_json = False
            else:
                if len(buffer) > len(self._MARKER_START):
                    yield buffer[: -len(self._MARKER_START)]
                    buffer = buffer[-len(self._MARKER_START) :]
        if buffer and not inside_json:
            yield buffer

    def generate_combined(
        self,
        question: str,
        combined_data: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate a single explanation from aggregated multi-view/insight data. Uses prior context if provided."""
        data_block = self._format_combined_data_for_prompt(combined_data)
        user_content = (
            f"User Question: {question}\n\n"
            f"Structured Data (multiple sources):\n{data_block}"
        )
        messages: List[Dict[str, str]] = []
        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_content})
        return self._claude.chat(
            system=self._combined_system_prompt,
            messages=messages,
            max_tokens=1024,
        )

    def generate_combined_stream(
        self,
        question: str,
        combined_data: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Generator[Union[str, Dict[str, Any]], None, None]:
        """Stream combined explanation; yields text tokens and visualization payload. Uses prior context if provided."""
        data_block = self._format_combined_data_for_prompt(combined_data)
        user_content = (
            f"User Question: {question}\n\n"
            f"Structured Data (multiple sources):\n{data_block}"
        )
        messages: List[Dict[str, str]] = []
        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_content})

        buffer = ""
        json_buffer = ""
        inside_json = False

        for chunk in self._claude.chat_stream(
            system=self._combined_system_prompt,
            messages=messages,
            max_tokens=1024,
        ):
            buffer += chunk

            if self._MARKER_START in buffer:
                before, _, after = buffer.partition(self._MARKER_START)
                if before:
                    yield before
                json_buffer = after
                buffer = ""
                inside_json = True
            elif inside_json:
                json_buffer += buffer
                buffer = ""
                if self._MARKER_END in json_buffer:
                    json_part, _, rest = json_buffer.partition(self._MARKER_END)
                    try:
                        parsed = json.loads(json_part.strip())
                        if isinstance(parsed, dict) and "visualizations" in parsed and isinstance(parsed["visualizations"], list):
                            for item in parsed["visualizations"]:
                                yield {"type": "visualization", "payload": item}
                        else:
                            yield {"type": "visualization", "payload": parsed}
                    except json.JSONDecodeError:
                        pass
                    json_buffer = rest
                    inside_json = False
            else:
                if len(buffer) > len(self._MARKER_START):
                    yield buffer[: -len(self._MARKER_START)]
                    buffer = buffer[-len(self._MARKER_START) :]
        if buffer and not inside_json:
            yield buffer


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
) -> Generator[Union[str, Dict[str, Any]], None, None]:
    yield from _get_default().generate_stream(question, columns, rows, view_table, sql)


def generate_combined(
    question: str,
    combined_data: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """Generate explanation from aggregated multi-view/insight data; optional history for follow-up context."""
    return _get_default().generate_combined(question, combined_data, history)


def generate_combined_stream(
    question: str,
    combined_data: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> Generator[Union[str, Dict[str, Any]], None, None]:
    """Stream combined explanation; yields text and visualization payload; optional history for follow-up context."""
    yield from _get_default().generate_combined_stream(question, combined_data, history)
