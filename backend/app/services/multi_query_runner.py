from __future__ import annotations

from typing import Any, Dict, List, Literal, Tuple, Generator

from app.exceptions import (
    DatabaseConnectionError,
    DatabaseQueryError,
    InsightBuildError,
    SQLGenerationError,
    SQLValidationError,
)
from app.schemas.schema_metadata import get_view_schema
from app.services.insight_service import generate_insights
from app.services.planner import Plan, PlanQuery
from app.services.query_executor import run_query
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql

ResultKind = Literal["view", "insight"]


class MultiQueryResult:
    """
    Container for results of executing a multi-intent Plan.

    For view queries:
      {
        "kind": "view",
        "view_key": str,
        "table_name": str,
        "sql": str,
        "columns": List[str],
        "rows": List[Dict[str, Any]],
      }

    For insight queries:
      {
        "kind": "insight",
        "report_key": str,
        "structured": Dict[str, Any],
        "formatted": str,
      }
    """

    def __init__(self) -> None:
        self.view_results: Dict[str, Dict[str, Any]] = {}
        self.insight_results: Dict[str, Dict[str, Any]] = {}

    def add_view_result(
        self,
        view_key: str,
        table_name: str,
        sql: str,
        columns: List[str],
        rows: List[Dict[str, Any]],
    ) -> None:
        self.view_results[view_key] = {
            "kind": "view",
            "view_key": view_key,
            "table_name": table_name,
            "sql": sql,
            "columns": columns,
            "rows": rows,
        }

    def add_insight_result(
        self,
        report_key: str,
        structured: Dict[str, Any],
        formatted: str,
    ) -> None:
        self.insight_results[report_key] = {
            "kind": "insight",
            "report_key": report_key,
            "structured": structured,
            "formatted": formatted,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "views": self.view_results,
            "insights": self.insight_results,
        }


def _execute_view_query(
    question: str,
    query: PlanQuery,
    history: List[Dict[str, Any]],
) -> Tuple[str, str, List[str], List[Dict[str, Any]]]:
    """
    Execute a single view-type PlanQuery using the existing SQL pipeline.

    Returns: (view_key, sql, columns, rows)
    """
    view_key = query.view  # type: ignore[assignment]
    schema = get_view_schema(view_key)
    table_name = schema["table_name"]

    try:
        sql = generate_sql(
            question=question,
            view_schema=schema,
            history=history,
        )
    except Exception as e:
        # Surface SQLGenerationError and Claude errors directly; wrap others.
        raise SQLGenerationError(
            f"Failed to generate SQL for view '{view_key}'"
        ) from e

    try:
        validate_sql(sql=sql, allowed_table=table_name)
    except SQLValidationError:
        # Let caller handle specific validation error.
        raise

    try:
        columns, rows = run_query(sql)
    except DatabaseConnectionError:
        raise
    except DatabaseQueryError:
        raise

    return view_key, table_name, sql, columns, rows


def _execute_insight_query(report_key: str) -> Tuple[str, Dict[str, Any], str]:
    """
    Execute a single insight-type PlanQuery using the existing insight pipeline.

    Returns: (report_key, structured_data, formatted_report)
    """
    try:
        result = generate_insights(report_key)
    except Exception as e:
        raise InsightBuildError(
            f"Failed to build insights for report '{report_key}'"
        ) from e

    structured = result.get("structured_data", {})
    formatted = result.get("formatted_report", "")
    return report_key, structured, formatted


def run_plan(
    plan: Plan,
    question: str,
    history: List[Dict[str, Any]],
) -> MultiQueryResult:
    """
    Execute all queries in a Plan.

    Behavior:
    - Processes queries in order.
    - On first failure (SQL generation, validation, DB, insight build), raises the error.
      The caller can decide how to surface it (HTTPException, SSE 'error', etc.).
    - Returns a MultiQueryResult with separate maps for views and insights.

    History compatibility: history must be the same format as memory_store.get_history()
    (list of dicts with "role" and "content" keys). It is passed unchanged to generate_sql
    for each view query, so sql_generator's _build_prompt(history=...) contract is satisfied.
    """
    result = MultiQueryResult()

    for q in plan.queries:
        if q.type == "view":
            view_key, table_name, sql, columns, rows = _execute_view_query(
                question=question,
                query=q,
                history=history,
            )
            result.add_view_result(
                view_key=view_key,
                table_name=table_name,
                sql=sql,
                columns=columns,
                rows=rows,
            )
        elif q.type == "insight":
            if not q.report_key:
                raise InsightBuildError("Missing report_key for insight query")
            report_key, structured, formatted = _execute_insight_query(q.report_key)
            result.add_insight_result(
                report_key=report_key,
                structured=structured,
                formatted=formatted,
            )

    return result


def run_plan_stream(
    plan: Plan,
    question: str,
    history: List[Dict[str, Any]],
) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
    """
    Execute all queries in a Plan, yielding phase events for SSE before each query.
    Yields ("phase", {"phase": "executing_query_1", "message": "..."}), etc.
    Final yield is ("result", multi_result) — consumer must handle that to get the result.

    History compatibility: same as run_plan — history is passed to generate_sql unchanged
    for each view query (sql_generator expects list of {"role", "content"} dicts).
    """
    result = MultiQueryResult()
    n = len(plan.queries)

    for i, q in enumerate(plan.queries):
        yield ("phase", {
            "phase": f"executing_query_{i + 1}",
            "message": f"Running query {i + 1} of {n}...",
        })
        if q.type == "view":
            view_key, table_name, sql, columns, rows = _execute_view_query(
                question=question,
                query=q,
                history=history,
            )
            result.add_view_result(
                view_key=view_key,
                table_name=table_name,
                sql=sql,
                columns=columns,
                rows=rows,
            )
        elif q.type == "insight":
            if not q.report_key:
                raise InsightBuildError("Missing report_key for insight query")
            report_key, structured, formatted = _execute_insight_query(q.report_key)
            result.add_insight_result(
                report_key=report_key,
                structured=structured,
                formatted=formatted,
            )

    yield ("result", result)

