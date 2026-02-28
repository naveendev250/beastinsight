"""
Aggregation layer for multi-query results.

Consumes MultiQueryResult and produces a single combined_data structure
(views + insights, full data only) for the combined explanation service.
No single-row or first-row computation is done here; rates, deltas, and
comparisons are left to the explainer LLM.
"""

from __future__ import annotations

from typing import Any, Dict

from app.services.multi_query_runner import MultiQueryResult


def aggregate(multi_result: MultiQueryResult) -> Dict[str, Any]:
    """
    Build combined_data from multi-query results.

    Input: MultiQueryResult (from run_plan).
    Output: A single dict suitable for the combined explanation prompt:
      - views: per-view blocks (table_name, sql, columns, rows) — full data.
      - insights: per-report blocks (structured, formatted).

    No computation is done on single rows or first rows here. Full acquired
    data is passed through so the explainer LLM can produce accurate
    explanations; any rates, deltas, or comparisons are left to the LLM
    (or a separate LLM aggregation step).
    """
    view_results = multi_result.view_results
    insight_results = multi_result.insight_results

    views_combined: Dict[str, Any] = {}
    for view_key, data in view_results.items():
        views_combined[view_key] = {
            "table_name": data.get("table_name"),
            "sql": data.get("sql"),
            "columns": data.get("columns"),
            "rows": data.get("rows") or [],
        }

    insights_combined: Dict[str, Any] = {}
    for report_key, data in insight_results.items():
        insights_combined[report_key] = {
            "structured": data.get("structured"),
            "formatted": data.get("formatted"),
        }

    return {
        "views": views_combined,
        "insights": insights_combined,
    }
