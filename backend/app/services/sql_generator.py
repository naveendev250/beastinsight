from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.exceptions import ClaudeAPIError, SQLGenerationError
from app.services.claude_client import ClaudeClient, ClaudeClientFactory
from app.utils.date_helpers import DateHelper

logger = logging.getLogger(__name__)


class SQLGenerator:
    """
    Converts a natural-language question into a validated PostgreSQL SELECT query.
    Single Responsibility: prompt construction + raw SQL extraction.
    Dependency injected: receives a ClaudeClient instance.
    """

    # Known enum values per column to help Claude generate correct filters
    _ENUM_HINTS: Dict[str, str] = {
        "sales_type": "Values: 'Initials', 'Rebills', 'Straight Sales'",
        "health_tag": "Values: 'healthy', 'at-risk', 'critical', 'inactive'",
        "refund_type": "Values: 'Refund Alert', 'Refund CS'",
        "alert_type": (
            "Values: 'RDR', 'Ethoca', 'CDRN', 'Direct', "
            "'Order Insight', 'Order Insight 3.0'"
        ),
        "decline_group": (
            "Values: 'Insufficient Funds', 'Expired Card', 'CVV Mismatch', "
            "'Fraudulent', 'Gateway Network Issue', 'Issuer Decline', "
            "'Customer Account Issue', etc."
        ),
        "near_capacity": "Values: text flag",
        "inactive": "Values: text flag",
        "decline_spike": "Values: text flag",
    }

    _SQL_SYSTEM_PROMPT = """\
You are a PostgreSQL SQL generator for a BI analytics platform.

STRICT RULES:
1. Output ONLY the raw SQL query. No markdown fences, no explanations, no comments.
2. Generate exactly ONE SELECT statement.
3. NEVER use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE.
4. NEVER include semicolons.
5. Only query the single table provided below.
6. Only reference columns listed below.
7. Prefer aggregated results (SUM, AVG, COUNT, GROUP BY) over raw row dumps.
8. If returning non-aggregated rows, always add LIMIT 100.
9. Always apply date filters when the question implies a time range.
10. Use CURRENT_DATE for today-relative calculations when helpful.
11. For rate calculations: rate = numerator / NULLIF(denominator, 0).
12. For percentage change: ((new - old) / NULLIF(old, 0)) * 100.
13. Round numeric results to 2 decimal places with ROUND().
14. Order results meaningfully (by date, by value DESC, etc.).

PERFORMANCE (CRITICAL):
- Some tables have MILLIONS of rows. ALWAYS include a WHERE clause with a date filter.
- Even for "all time" questions, limit to the last 12 months unless explicitly asked otherwise.
- For "today" questions use: date = CURRENT_DATE
- For "yesterday" use: date = CURRENT_DATE - 1
- For "this month" use: date >= DATE_TRUNC('month', CURRENT_DATE)
- For 'mid_summary_10042' table, use TO_DATE(month_year, 'Mon YYYY') column for date filtering.
- For hourly_revenue table, no date filter is needed (only 24 rows).
- NEVER do SELECT * — always select only the columns you need.
- Always add LIMIT to non-aggregated queries, max LIMIT 200.

For table mid_summary_10042 AND COLUMN LIST CONTAINING month_year: 
  - The column month_year is TEXT formatted as 'Mon YYYY' (e.g., 'Feb 2026').
  - month_year MUST NEVER be compared directly as a string.
  - ANY filtering, ordering, grouping, or comparison based on month_year MUST use:
        TO_DATE(month_year, 'Mon YYYY')
  - Example (correct):
        WHERE TO_DATE(month_year, 'Mon YYYY') >= DATE_TRUNC('month', CURRENT_DATE)
  - Example (WRONG – never allowed):
        WHERE month_year >= 'Feb 2026'
        ORDER BY month_year DESC

CONTEXT FOLLOW-UPS:
- Previous messages may be shown for context. The user may say "What about last month?" or "Compare to last week".
- In such cases, generate ONE query that answers the LATEST question only.
- NEVER output two queries. Output exactly ONE SELECT statement.
"""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._claude = claude_client

    def _build_prompt(
        self,
        question: str,
        view_schema: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, List[Dict[str, str]]]:
        """Build (system_prompt, messages) for Claude SQL generation."""
        table_name = view_schema["table_name"]
        description = view_schema.get("description", "")
        columns = view_schema["columns"]

        # Column list with enum hints
        col_lines = []
        for col in columns:
            hint = self._ENUM_HINTS.get(col, "")
            col_lines.append(
                f"  - {col}  ({hint})" if hint else f"  - {col}"
            )
        col_block = "\n".join(col_lines)

        date_ctx = DateHelper.get_date_context()

        system = (
            f"{self._SQL_SYSTEM_PROMPT}\n"
            f"TABLE: {table_name}\n"
            f"DESCRIPTION: {description}\n\n"
            f"COLUMNS:\n{col_block}\n\n"
            f"{date_ctx}"
        )

        # Conversation history for context
        messages: List[Dict[str, str]] = []
        if history:
            for msg in history[-6:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    messages.append({"role": "user", "content": content})
                    messages.append(
                        {"role": "assistant", "content": "(previous response)"}
                    )
            if messages and messages[-1]["content"] == "(previous response)":
                messages.pop()

        messages.append({"role": "user", "content": question})
        return system, messages

    @staticmethod
    def _clean_response(raw: str) -> str:
        """
        Strip markdown code fences, extra whitespace, and
        handle cases where Claude emits multiple statements (keep the last one).
        """
        text = raw.strip()
        # Remove ```sql ... ``` or ``` ... ```
        text = re.sub(r"^```(?:sql)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        text = text.strip().rstrip(";").strip()

        # If Claude generated multiple top-level statements, keep the last one.
        blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
        top_selects = [b for b in blocks if b.lower().startswith("select")]
        if len(top_selects) > 1:
            text = top_selects[-1]

        return text

    def generate(
        self,
        question: str,
        view_schema: Dict[str, Any],
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate a SQL query for the given question via Claude."""
        system, messages = self._build_prompt(question, view_schema, history)
        try:
            raw = self._claude.chat(
                system=system, messages=messages, max_tokens=800
            )
        except ClaudeAPIError:
            raise
        except Exception as exc:
            logger.error("SQL generation unexpected error: %s", exc)
            raise SQLGenerationError(
                "Failed to generate SQL query",
                detail=str(exc),
            ) from exc

        cleaned = self._clean_response(raw)
        if not cleaned or not cleaned.lower().startswith("select"):
            logger.warning("Claude returned non-SQL response: %s", raw[:200])
            raise SQLGenerationError(
                "AI did not return a valid SQL query — please rephrase your question",
                detail=f"Raw response: {raw[:200]}",
            )
        return cleaned


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions (used by router)
# ---------------------------------------------------------------------------
_default_generator: Optional[SQLGenerator] = None


def _get_default() -> SQLGenerator:
    global _default_generator
    if _default_generator is None:
        _default_generator = SQLGenerator(ClaudeClientFactory.get_default())
    return _default_generator


def generate_sql(
    question: str,
    view_schema: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    return _get_default().generate(question, view_schema, history)
