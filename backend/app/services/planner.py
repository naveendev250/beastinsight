from __future__ import annotations

from typing import Dict, List, Literal, Optional
import json

from pydantic import BaseModel, Field, validator

from app.schemas.schema_metadata import list_view_keys
from app.services.insight_service import _REPORT_REGISTRY
from app.services.claude_client import claude_chat
from app.services.view_router import detect_view


#
# Planning module: plan schema, guardrails, metric→view registry,
# and LLM-backed planner with deterministic fallback.
#


PlanQueryType = Literal["view", "insight"]


class PlanQuery(BaseModel):
    """
    Single atomic data requirement in a multi-intent question.

    - type="view": use free-form SQL pipeline against a materialized view.
    - type="insight": use fixed insight pipeline against a report_key.
    """

    type: PlanQueryType = Field(..., description='"view" or "insight"')
    view: Optional[str] = Field(
        default=None,
        description="View key from SchemaRegistry (when type='view').",
    )
    report_key: Optional[str] = Field(
        default=None,
        description="Fixed insight report key (when type='insight').",
    )
    metrics: List[str] = Field(
        default_factory=list,
        description="High-level metric names requested (e.g. ['revenue', 'cb_rate']).",
    )
    filters: List[str] = Field(
        default_factory=list,
        description="High-level filters / time ranges (e.g. ['this_month']).",
    )

    @validator("view")
    def _validate_view_for_type(cls, v: Optional[str], values: Dict) -> Optional[str]:
        if values.get("type") == "view" and not v:
            raise ValueError("view is required when type='view'")
        return v

    @validator("report_key")
    def _validate_report_key_for_type(
        cls, v: Optional[str], values: Dict
    ) -> Optional[str]:
        if values.get("type") == "insight" and not v:
            raise ValueError("report_key is required when type='insight'")
        return v


class Plan(BaseModel):
    """
    High-level plan produced by the intent parser / planner.

    - queries: list of atomic data requirements.
    - requires_comparison: whether the question asks for cross-query comparison.
    """

    queries: List[PlanQuery] = Field(
        default_factory=list,
        description="List of atomic data requirements (views and/or insights).",
    )
    requires_comparison: bool = Field(
        default=False,
        description=(
            "True if user explicitly/implicitly asks to compare across queries "
            "(e.g. 'vs', 'compare', 'trend between')."
        ),
    )


#
# Guardrails
#

MAX_QUERIES_PER_PLAN: int = 3
MAX_METRICS_PER_QUERY: int = 5

# Use existing registries to derive allowed keys.
ALLOWED_VIEWS: List[str] = list_view_keys()
ALLOWED_REPORT_KEYS: List[str] = sorted(_REPORT_REGISTRY.keys())


def is_allowed_view(view_key: str) -> bool:
    return view_key in ALLOWED_VIEWS


def is_allowed_report_key(report_key: str) -> bool:
    return report_key in ALLOWED_REPORT_KEYS


#
# Metric → view registry
#

# This maps view keys to the metric keywords they are primarily responsible for.
# It is intentionally high-level; the planner can use it to:
# - choose views when LLM output is ambiguous
# - validate that a requested metric is compatible with a view
METRIC_VIEW_REGISTRY: Dict[str, List[str]] = {
    # Core revenue & order performance.
    "order_summary": [
        "revenue",
        "orders",
        "volume",
        "approvals",
        "approval_rate",
        "cancels",
        "cancel_rate",
        "chargeback",
        "cb_rate",
        "refunds",
        "refund_rate",
        "aov",
        "average_order_value",
    ],
    # MID / gateway health and capacity.
    "mid_summary": [
        "mid_health",
        "critical_mids",
        "at_risk_mids",
        "capacity",
        "near_capacity",
        "decline_spike",
        "overall_cb_rate",
        "decline_rate",
    ],
    # Alert performance.
    "alert_summary": [
        "alerts",
        "alert_volume",
        "alert_mix",
        "rdr",
        "ethoca",
        "cdrn",
        "alert_effectiveness",
    ],
    # Chargeback/refund with alert correlation.
    "cb_refund_alert": [
        "cb_timing",
        "refund_timing",
        "disputes",
        "cb_vs_alerts",
    ],
    # Decline recovery.
    "decline_recovery": [
        "declines",
        "recovered",
        "recovery_rate",
        "reattempts",
        "organic_declines",
    ],
    # LTV cohorts and milestones.
    "ltv_summary": [
        "ltv",
        "lifetime_value",
        "cohort_ltv",
        "ltv_milestones",
    ],
    # Cohort retention / churn.
    "cohort_summary": [
        "cohort_retention",
        "retention",
        "churn",
        "billing_cycle_retention",
    ],
    # Hourly performance.
    "hourly_revenue": [
        "hourly_revenue",
        "today_vs_7d",
        "revenue_by_hour",
        "peak_hour",
        "tracking_today",
    ],
}


def get_metric_view_registry() -> Dict[str, List[str]]:
    """
    Accessor for the metric→view registry.
    Kept as a function so future implementations can compute/extend this dynamically.
    """
    return METRIC_VIEW_REGISTRY


# ---------------------------------------------------------------------------
# Planner implementation (Phase 2)
# ---------------------------------------------------------------------------

_PLANNER_SYSTEM_PROMPT = """\
You are an intent planner for the BeastInsights analytics assistant.

Your job:
- Read the user's natural-language question.
- Break it into one or more atomic data requirements.
- Each requirement either uses a free-form SQL view or a fixed insight report.

You MUST output ONLY valid JSON, with NO markdown, NO comments, and NO explanations.

Allowed view keys (for type=\"view\"):
- These are materialized views in the warehouse.

Allowed fixed insight report keys (for type=\"insight\").

Rules:
- Prefer using at most 3 total queries.
- Prefer at most 5 metrics per query.
- If the question clearly asks for a comparison (e.g. 'vs', 'compare', 'difference', 'trend between'),
  set requires_comparison=true.
- If the question is simple and clearly about a single view, return a single query.

Output JSON schema:
{
  "queries": [
    {
      "type": "view" | "insight",
      "view": "view_key_when_type_view_or_null",
      "report_key": "report_key_when_type_insight_or_null",
      "metrics": ["metric_keywords"],
      "filters": ["time_or_other_filters"]
    }
  ],
  "requires_comparison": true_or_false
}

Do NOT invent view or report keys outside the allowed lists.
If unsure, pick the single most relevant view and leave requires_comparison=false.
"""


def _build_planner_messages(question: str) -> Dict[str, str]:
    """Build the user content string for the planner, including allowed keys and metric hints."""
    allowed_views_str = ", ".join(sorted(ALLOWED_VIEWS))
    allowed_reports_str = ", ".join(sorted(ALLOWED_REPORT_KEYS))

    metric_registry = get_metric_view_registry()
    metric_lines: List[str] = []
    for view_key, metrics in metric_registry.items():
        metric_lines.append(f"- {view_key}: {', '.join(metrics)}")
    metric_block = "\n".join(metric_lines)

    user_content = (
        f"User question:\n{question}\n\n"
        f"Allowed view keys:\n{allowed_views_str}\n\n"
        f"Allowed fixed insight report keys:\n{allowed_reports_str}\n\n"
        f"""Metric→view hints (for your reference):
        {metric_block}
        """
        "Now produce the JSON plan as described in the system prompt."
    )
    return {"role": "user", "content": user_content}


def _clean_llm_json(raw: str) -> str:
    """Strip common wrappers (e.g. ```json fences) so we can parse JSON safely."""
    text = raw.strip()
    if text.startswith("```"):
        # Remove leading ```json or ```
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _apply_guardrails(plan: Plan) -> Plan:
    """Enforce global guardrails on the parsed plan."""
    if len(plan.queries) == 0:
        raise ValueError("Plan has no queries")
    if len(plan.queries) > MAX_QUERIES_PER_PLAN:
        raise ValueError("Plan exceeds maximum allowed queries")

    for q in plan.queries:
        if q.type == "view":
            if not q.view or not is_allowed_view(q.view):
                raise ValueError(f"Unknown or disallowed view_key: {q.view!r}")
        if q.type == "insight":
            if not q.report_key or not is_allowed_report_key(q.report_key):
                raise ValueError(f"Unknown or disallowed report_key: {q.report_key!r}")
        if len(q.metrics) > MAX_METRICS_PER_QUERY:
            raise ValueError("Query exceeds maximum allowed metrics")

    return plan


def _parse_plan(raw: str) -> Plan:
    """Parse raw LLM output into a validated Plan instance with guardrails applied."""
    cleaned = _clean_llm_json(raw)
    data = json.loads(cleaned)
    plan = Plan.parse_obj(data)
    return _apply_guardrails(plan)


def _fallback_single_view_plan(question: str) -> Plan:
    """Deterministic fallback using existing single-view router."""
    view_key = detect_view(question)
    query = PlanQuery(type="view", view=view_key, metrics=[], filters=[])
    return Plan(queries=[query], requires_comparison=False)


def plan_question(question: str) -> Plan:
    """
    Main entrypoint: plan a user question into one or more queries.

    Behavior:
    - Uses Claude (via claude_chat) to produce a JSON plan.
    - Parses and validates using Pydantic, enforcing guardrails.
    - On any error (API, JSON, validation), falls back to a single-view plan.
    """
    try:
        system = _PLANNER_SYSTEM_PROMPT
        user_msg = _build_planner_messages(question)
        raw = claude_chat(system=system, messages=[user_msg], max_tokens=512)
        plan = _parse_plan(raw)
        if not plan.queries:
            return _fallback_single_view_plan(question)
        return plan
    except Exception:
        # Safe deterministic fallback: route to a single view.
        return _fallback_single_view_plan(question)

