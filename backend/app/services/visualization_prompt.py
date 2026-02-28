"""
Reusable prompt appendix for structured visualization output.
Used by ExplanationService (free-form Q&A) and InsightFormatter (fixed insights).
"""

VISUALIZATION_APPENDIX_PROMPT = """
CRITICAL: After the explanation, you MUST output structured visualization data.

The structured data must:
- Be valid JSON
- Be wrapped EXACTLY between:

__VISUALIZATION_JSON_START__
{ ... }
__VISUALIZATION_JSON_END__

Visualization JSON schema:

{
  "chart_type": "line | bar | pie | table | kpi | area",
  "title": "string",
  "x_axis": "column_name_or_null (use null for kpi/single-metric charts; use column name for line/bar/area)",
  "y_axis": ["metric_columns"],
  "series": [
    {
      "name": "series_name",
      "data": [
        { "x": "value", "y": number }
      ]
    }
  ],
  "insights": [
    "short analytical insight"
  ],
  "analysis_type": "trend | comparison | distribution | kpi",
  "is_time_series": true,
  "primary_metric": "revenue"
}

Rules for visualization:
- If time-based → use line or area chart
- If categorical comparison → use bar chart
- If distribution → use pie chart
- If single metric → use kpi
- NEVER invent data.
- Use only data present in the query result.
"""
