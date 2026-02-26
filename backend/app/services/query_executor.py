from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.db import DatabaseManager


class QueryExecutor:
    """
    Executes validated SQL against Postgres and serializes results.
    Single Responsibility: execution + type serialization.
    Dependency injected: receives a DatabaseManager instance.
    """

    MAX_ROWS = 500  # Safety net: never return more than this many rows

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager

    @staticmethod
    def _serialize_value(val: Any) -> Any:
        """Convert DB types to JSON-safe Python types."""
        if val is None:
            return None
        if isinstance(val, Decimal):
            return float(val)
        if isinstance(val, (date, datetime)):
            return val.isoformat()
        if isinstance(val, time):
            return val.strftime("%H:%M")
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="replace")
        return val

    def serialize_rows(
        self,
        columns: List[str],
        rows: List[Tuple[Any, ...]],
    ) -> List[Dict[str, Any]]:
        """Convert raw DB rows to a list of JSON-safe dicts."""
        return [
            {col: self._serialize_value(val) for col, val in zip(columns, row)}
            for row in rows
        ]

    def run(self, sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Execute query and return (columns, serialized_rows).
        Caps results at MAX_ROWS as a safety net.
        Raises on DB errors.
        """
        columns, raw_rows = self._db.execute_select(sql)
        raw_rows = raw_rows[: self.MAX_ROWS]
        rows = self.serialize_rows(columns, raw_rows)
        return columns, rows


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (used by router)
# ---------------------------------------------------------------------------
_default_executor: Optional[QueryExecutor] = None


def _get_default() -> QueryExecutor:
    global _default_executor
    if _default_executor is None:
        _default_executor = QueryExecutor(DatabaseManager.get_instance())
    return _default_executor


def run_query(sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    return _get_default().run(sql)
