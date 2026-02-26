from __future__ import annotations

import re
from typing import List

from app.exceptions import SQLValidationError


class SQLValidator:
    """
    Strict SQL safety validator.
    Single Responsibility: ensures only a single SELECT against one allowed table.
    Open/Closed: forbidden keywords list can be extended without modifying validate().
    """

    _DEFAULT_FORBIDDEN: List[str] = [
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "execute",
        "copy",
    ]

    def __init__(self, extra_forbidden: List[str] | None = None) -> None:
        self._forbidden = list(self._DEFAULT_FORBIDDEN)
        if extra_forbidden:
            self._forbidden.extend(extra_forbidden)

    def validate(self, sql: str, allowed_table: str) -> None:
        """
        Validate the SQL statement.
        Raises SQLValidationError on any violation.
        """
        if not sql or not isinstance(sql, str):
            raise SQLValidationError("Empty or invalid SQL")

        lowered = sql.strip().lower()

        if not lowered.startswith("select"):
            raise SQLValidationError("Only SELECT queries are allowed")

        for kw in self._forbidden:
            if re.search(rf"\b{kw}\b", lowered):
                raise SQLValidationError(f"Forbidden keyword detected: {kw}")

        if ";" in lowered:
            raise SQLValidationError(
                "Semicolons are not allowed (single statement only)"
            )

        if re.search(r"^\s*with\b", lowered):
            raise SQLValidationError("CTEs (WITH ...) are not allowed in v1")

        blocks = [b.strip() for b in re.split(r"\n\s*\n", lowered) if b.strip()]
        top_selects = [b for b in blocks if b.startswith("select")]
        if len(top_selects) > 1:
            raise SQLValidationError(
                "Multiple SELECT statements detected — only one is allowed"
            )

        table_clean = allowed_table.lower().replace('"', "")
        if table_clean not in lowered:
            raise SQLValidationError(
                f"Query must reference the allowed table: {allowed_table}"
            )

        other_tables = re.findall(r"reporting\.\w+", lowered)
        for t in other_tables:
            if t != table_clean:
                raise SQLValidationError(f"Unauthorized table reference: {t}")


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (used by router)
# ---------------------------------------------------------------------------
_default_validator = SQLValidator()


def validate_sql(sql: str, allowed_table: str) -> None:
    _default_validator.validate(sql, allowed_table)
