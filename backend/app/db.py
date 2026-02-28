from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

import psycopg

from app.config import get_settings
from app.exceptions import DatabaseConnectionError, DatabaseQueryError

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Singleton database connection manager.
    Thread-safe: uses a lock to ensure only one instance is created.
    """

    _instance: Optional["DatabaseManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "DatabaseManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._dsn = cls._build_dsn()
        return cls._instance

    @staticmethod
    def _build_dsn() -> str:
        s = get_settings()
        return (
            f"host={s.pg_host} port={s.pg_port} dbname={s.pg_database} "
            f"user={s.pg_username} password={s.pg_password} sslmode={s.pg_sslmode}"
        )

    @classmethod
    def get_instance(cls) -> "DatabaseManager":
        return cls()

    @contextmanager
    def get_connection(self):
        try:
            conn = psycopg.connect(self._dsn)
        except psycopg.OperationalError as exc:
            logger.error("Postgres connection failed: %s", exc)
            raise DatabaseConnectionError(
                "Cannot connect to the database",
                detail=str(exc),
            ) from exc
        try:
            yield conn
        finally:
            conn.close()

    def execute_select(
        self, sql: str, params: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[str], List[Tuple[Any, ...]]]:
        """Execute a read-only SELECT query and return (column_names, rows)."""
        p = params if params else {}
        # When no parameters are passed, psycopg still interprets % in SQL as placeholders.
        # Escape literal % (e.g. in "50%" or "|| '%'") so we don't get "got '%,'" errors.
        if not p:
            sql = sql.replace("%", "%%")
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                try:
                    cur.execute(sql, p)
                    rows = cur.fetchall()
                except psycopg.errors.SyntaxError as exc:
                    logger.error("SQL syntax error: %s | SQL: %s", exc, sql[:300])
                    raise DatabaseQueryError(
                        "Invalid SQL syntax",
                        detail=str(exc),
                    ) from exc
                except psycopg.errors.InsufficientPrivilege as exc:
                    logger.error("Permission denied: %s | SQL: %s", exc, sql[:300])
                    raise DatabaseQueryError(
                        "Insufficient database permissions",
                        detail=str(exc),
                    ) from exc
                except psycopg.errors.UndefinedTable as exc:
                    logger.error("Table not found: %s | SQL: %s", exc, sql[:300])
                    raise DatabaseQueryError(
                        "Referenced table does not exist",
                        detail=str(exc),
                    ) from exc
                except psycopg.errors.UndefinedColumn as exc:
                    logger.error("Column not found: %s | SQL: %s", exc, sql[:300])
                    raise DatabaseQueryError(
                        "Referenced column does not exist",
                        detail=str(exc),
                    ) from exc
                except psycopg.errors.QueryCanceled as exc:
                    logger.error("Query timed out: %s | SQL: %s", exc, sql[:300])
                    raise DatabaseQueryError(
                        "Query timed out — try a narrower date range or simpler question",
                        detail=str(exc),
                    ) from exc
                except psycopg.Error as exc:
                    logger.error("Database query error: %s | SQL: %s", exc, sql[:300])
                    raise DatabaseQueryError(
                        f"Database error: {exc}",
                        detail=str(exc),
                    ) from exc

                colnames = (
                    [desc.name for desc in cur.description]
                    if cur.description
                    else []
                )
                return colnames, rows


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (used by router / other modules)
# ---------------------------------------------------------------------------
def execute_select(
    sql: str, params: Optional[Dict[str, Any]] = None
) -> Tuple[List[str], List[Tuple[Any, ...]]]:
    return DatabaseManager.get_instance().execute_select(sql, params)
