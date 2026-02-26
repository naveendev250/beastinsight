from __future__ import annotations

import logging
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.db import DatabaseManager
from app.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase E — Safety: common math helpers (division-safe, precision-safe)
# ---------------------------------------------------------------------------

def safe_divide(
    numerator: Any,
    denominator: Any,
    default: float = 0.0,
) -> float:
    """Division that handles None, zero, and type coercion safely."""
    try:
        num = float(numerator) if numerator is not None else 0.0
        den = float(denominator) if denominator is not None else 0.0
        if den == 0:
            return default
        return num / den
    except (TypeError, ValueError):
        return default


def safe_round(value: Any, decimals: int = 2) -> Optional[float]:
    """Round to N decimals, handling None and bad types."""
    if value is None:
        return None
    try:
        return round(float(value), decimals)
    except (TypeError, ValueError):
        return None


def pct_change(current: Any, previous: Any) -> Optional[float]:
    """Percentage change: ((current - previous) / previous) * 100."""
    try:
        cur = float(current) if current is not None else 0.0
        prev = float(previous) if previous is not None else 0.0
        if prev == 0:
            return None
        return round(((cur - prev) / prev) * 100, 2)
    except (TypeError, ValueError):
        return None


def detect_anomaly(
    current: Any,
    average: Any,
    threshold: float = 0.20,
) -> bool:
    """Flag if current deviates from average by more than threshold (20%)."""
    try:
        cur = float(current) if current is not None else 0.0
        avg = float(average) if average is not None else 0.0
        if avg == 0:
            return False
        return abs(cur - avg) / avg > threshold
    except (TypeError, ValueError):
        return False


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce to float safely."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Phase A — Base Repository: common data-fetch infrastructure
# ---------------------------------------------------------------------------

class BaseRepository:
    """
    Abstract base for insight repositories.
    Single Responsibility: provides safe SQL execution + row serialization.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        self._db = db_manager
        self._client_id = get_settings().client_id

    def _table(self, view_name: str) -> str:
        """Build fully-qualified table name with dynamic client_id."""
        return f"reporting.{view_name}_{self._client_id}"

    def _fetch(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """
        Execute predefined SQL and return serialized rows.
        Logs errors and returns empty list on failure (Phase E safety).
        """
        try:
            cols, raw_rows = self._db.execute_select(sql, params)
            return self._serialize(cols, raw_rows)
        except Exception as e:
            logger.error("Insight query failed: %s | SQL: %s", e, sql[:200])
            return []

    def _fetch_single(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> Dict[str, Any]:
        """Fetch a single-row result, return empty dict on failure."""
        rows = self._fetch(sql, params)
        return rows[0] if rows else {}

    @staticmethod
    def _serialize(
        cols: List[str], rows: List[Tuple[Any, ...]]
    ) -> List[Dict[str, Any]]:
        """Convert raw DB tuples to JSON-safe dicts."""

        def _conv(val: Any) -> Any:
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

        return [
            {col: _conv(v) for col, v in zip(cols, row)}
            for row in rows
        ]
