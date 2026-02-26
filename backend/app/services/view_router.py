from __future__ import annotations

import re
from typing import Optional, Tuple


class ViewRouter:
    """
    Deterministic single-view router.
    Single Responsibility: maps a natural-language question to a VIEW_SCHEMAS key.
    Also detects Fixed Insight mode when user asks for a report summary.
    Priority order matters — more specific matches first.
    """

    # Map of keywords to insight report keys
    _INSIGHT_REPORT_MAP = {
        "order": "order_summary",
        "revenue summary": "order_summary",
        "mid": "mid_health",
        "gateway health": "mid_health",
        "mid health": "mid_health",
        "alert": "alerts",
        "decline": "decline_recovery",
        "recovery": "decline_recovery",
        "ltv": "ltv",
        "lifetime value": "ltv",
        "hourly": "hourly_revenue",
        "hourly revenue": "hourly_revenue",
        "cohort": "cohort",
        "retention": "cohort",
    }

    def detect_insight_mode(self, question: str) -> Tuple[bool, Optional[str]]:
        """
        Detect if the question is asking for a fixed insight report.
        Returns (is_insight, report_key) or (False, None).

        Triggers on patterns like:
          - "give me order summary insights"
          - "show me MID health insights"
          - "insights for alerts"
          - "generate decline recovery report"
        """
        q = question.lower()

        # Must contain an insight trigger word
        insight_triggers = ["insight", "insights", "report", "summary report", "generate report"]
        has_trigger = any(t in q for t in insight_triggers)

        if not has_trigger:
            return False, None

        # Find which report they want
        for keyword, report_key in self._INSIGHT_REPORT_MAP.items():
            if keyword in q:
                return True, report_key

        # Generic "give me insights" without specifying a report
        return False, None

    def detect(self, question: str) -> str:
        """
        Return the VIEW_SCHEMAS key (not the physical table name).

        Priority is designed so that specific domain keywords (LTV, decline,
        chargeback, alert) win over ambiguous structural keywords (gateway,
        billing cycle) that appear across multiple domains.
        """
        q = question.lower()

        # --- 1. LTV (check before cohort — "LTV for X cohort" → ltv_summary) ---
        if (
            "ltv" in q
            or "lifetime value" in q
            or "life time value" in q
            or "first order value" in q
            or "first order" in q
        ):
            if "email" in q or "individual" in q or "per customer" in q or "per-customer" in q:
                return "ltv_analysis"
            return "ltv_summary"

        # --- 2. MID (strong intent — user explicitly asks about MIDs) ---
        if "mid" in q:
            return "mid_summary"

        # --- 3. Decline / Recovery (before hourly — "recovery" + "7-day average" is decline) ---
        if "decline" in q or "recovery" in q or "reattempt" in q or "recovered" in q:
            return "decline_recovery"

        # --- 4. Alert vs Chargeback/Refund ---
        has_alert = "alert" in q or "rdr" in q or "ethoca" in q or "cdrn" in q
        has_cb_refund = any(
            t in q
            for t in [
                "chargeback", "refund", "cb rate", "cb dollar",
                "refund rate", "refund type", "dispute",
                "days before chargeback", "days before refund",
            ]
        ) or bool(re.search(r"\bcb\b", q))

        if has_alert and has_cb_refund:
            if "alert" in q and q.index("alert") < q.index(next(
                t for t in ["chargeback", "refund", "cb "]
                if t in q
            )):
                if "detail" in q or "individual" in q:
                    return "alert_details"
                return "alert_summary"
            return "cb_refund_alert"

        if has_cb_refund:
            return "cb_refund_alert"

        if has_alert:
            if "detail" in q or "individual" in q:
                return "alert_details"
            return "alert_summary"

        # --- 6. Hourly ---
        hourly_triggers = [
            "hour", "hourly", "peak hour",
            "7-day average", "7 day average", "daily average",
            "ahead or behind", "tracking today",
            "today's revenue tracking", "today revenue tracking",
            "compare to average",
        ]
        if any(t in q for t in hourly_triggers):
            return "hourly_revenue"

        # --- 7. Cohort ---
        if "cohort" in q or "retention" in q:
            return "cohort_summary"
        if re.search(r"\bcycle\s+\d", q):
            return "cohort_summary"
        if "billing cycle" in q and not any(t in q for t in ["revenue", "approval"]):
            return "cohort_summary"

        # --- 8. Gateway / Health / Capacity (lower priority — only when no stronger domain matched) ---
        if "gateway" in q or "health" in q or "capacity" in q:
            return "mid_summary"

        # --- Default: order_summary covers revenue, approvals, cancels, etc. ---
        return "order_summary"


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (used by router)
# ---------------------------------------------------------------------------
_default_router = ViewRouter()


def detect_view(question: str) -> str:
    return _default_router.detect(question)


def detect_insight_mode(question: str) -> Tuple[bool, Optional[str]]:
    return _default_router.detect_insight_mode(question)
