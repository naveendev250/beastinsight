"""
Reusable prompt appendix for structured visualization output.
Used by ExplanationService (free-form Q&A) and InsightFormatter (fixed insights).
"""

VISUALIZATION_APPENDIX_PROMPT = """
You MUST output a visualization block whenever the answer contains data that can be visualized. THIS IS REQUIRED, NOT OPTIONAL.

WHEN TO ALWAYS EMIT THE BLOCK (do not skip):
- Trend information (over time, month-over-month, week-over-week)
- Comparisons (this vs that, before/after, A vs B)
- One or more numeric metrics or KPIs (revenue, count, rate, total, average)
- Distributions (breakdown by category, share of total)
- Time series (daily, weekly, monthly values)
- Any response that cites specific numbers from the query result

ONLY omit the visualization block when:
- The query returned no data and you are only explaining that (e.g. "No data available")
- The answer is purely qualitative with zero numbers to plot

After the explanation, output ONE JSON object with key "visualizations" (an array) between the markers. The number of items in the array MUST match the number of metrics in the result: 1 metric → 1 object, 2 metrics → 2 objects, up to 5 metrics → 5 objects. Wrap EXACTLY between (no other text):

__VISUALIZATION_JSON_START__
{ "visualizations": [ ... ] }
__VISUALIZATION_JSON_END__

Schema: the value of "visualizations" is an array of 1 to 5 objects. Each object:

{
  "chart_type": "line | bar | pie | table | kpi | area",
  "title": "string",
  "x_axis": "column_name_or_null (use null for kpi/single-metric; use column name for line/bar/area)",
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

Example: 2 metrics (e.g. revenue and count) → { "visualizations": [ { chart_type, title, series, ... }, { chart_type, title, series, ... } ] }.

Rules:
- If time-based or trend → use line or area chart
- If categorical comparison → use bar chart
- If distribution → use pie chart
- If single metric → use kpi
- NEVER invent data; use only data present in the query result.
"""
