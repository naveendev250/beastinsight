"""
Reusable prompt appendix for structured visualization output.
Used by ExplanationService (free-form Q&A) and InsightFormatter (fixed insights).
"""

VISUALIZATION_APPENDIX_PROMPT = """
MANDATORY: If your answer cites ANY numbers from the query result (totals, daily values, rates, counts, comparisons), your response is INCOMPLETE unless you also output the visualization block. Never end with only text when you have plottable data.

ALWAYS output the block (no exceptions) when the question or answer involves:
- Revenue, sales, or money over a period (e.g. "revenue for last 30 days", "show me revenue") → MUST include block with chart
- Any time-based or trend question (daily, weekly, monthly, last N days)
- Comparisons (this vs that, before/after)
- One or more numeric metrics or KPIs (revenue, count, rate, total, average)
- Distributions or breakdowns by category
- Any response that mentions specific numbers from the data

ONLY omit the block when: the query returned no rows and you say only "No data available" (or equivalent) with no numbers to plot.

Your response MUST end with the visualization block when you have data. Format:

__VISUALIZATION_JSON_START__
{ "visualizations": [ ... ] }
__VISUALIZATION_JSON_END__

The value of "visualizations" is an array of 1 to 5 objects (one per metric; 1 metric → 1 object, up to 5). Each object:

{
  "chart_type": "line | bar | pie | table | kpi | area",
  "title": "string",
  "x_axis": "column_name_or_null (use null for kpi; use date/time column for line/area)",
  "y_axis": ["metric_columns"],
  "series": [
    {
      "name": "series_name",
      "data": [
        { "x": "value", "y": number }
      ]
    }
  ],
  "insights": ["short analytical insight"],
  "analysis_type": "trend | comparison | distribution | kpi",
  "is_time_series": true,
  "primary_metric": "revenue"
}

Concrete example: Question "show me revenue for last 30 days" → you MUST output the block with at least one visualization (e.g. line or area chart with date on x and revenue on y). Do not skip.

Rules: Time-based or trend → line or area. Categorical comparison → bar. Distribution → pie. Single metric → kpi. Use only data from the query result; never invent.

REMINDER: After your text explanation, you MUST output the two markers and the JSON. Missing the block when data exists is not allowed.
"""

# Used by fallback when the main response omitted the block: one job only = output markers + JSON.
VISUALIZATION_ONLY_SYSTEM_PROMPT = """\
Your ONLY job: output the two marker lines and a valid JSON object between them. No other text, no explanation.

Output EXACTLY this structure (copy the marker lines; put your JSON in place of the ellipsis):

__VISUALIZATION_JSON_START__
{ "visualizations": [ { "chart_type": "line"|"bar"|"pie"|"kpi"|"area", "title": "...", "x_axis": "date_or_null", "y_axis": ["metric"], "series": [ { "name": "...", "data": [ {"x": "...", "y": number} ] } ], "insights": ["..."], "analysis_type": "trend"|"kpi"|"comparison"|"distribution", "is_time_series": true|false, "primary_metric": "..." } ] }
__VISUALIZATION_JSON_END__

Rules: Use ONLY the data provided. Time/trend → line or area. Single metric → kpi. 1–5 objects in "visualizations" array.
"""
