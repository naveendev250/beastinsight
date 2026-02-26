from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.config import get_settings


class SchemaRegistry:
    """
    Registry of all materialized view schemas for a given client.
    Single Responsibility: holds view metadata and resolves view keys.
    """

    def __init__(self, client_id: Optional[int] = None) -> None:
        self._client_id = client_id or get_settings().client_id
        self._schemas: Dict[str, Dict[str, Any]] = self._build_schemas()

    def _table(self, name: str) -> str:
        return f"reporting.{name}_{self._client_id}"

    def _build_schemas(self) -> Dict[str, Dict[str, Any]]:
        return {
            "order_summary": {
                "table_name": self._table("order_summary"),
                "description": "Core order/transaction data aggregated daily. ~2.3M rows. Date range 2023-01-01 to present.",
                "columns": [
                    "client_id", "date", "campaign_id", "product_id",
                    "trial_gateway_id", "gateway_id", "bin", "affid",
                    "sub_affid", "c", "price_point", "sales_type",
                    "billing_cycle", "refund_type", "alert_type", "cpa",
                    "attempts_total", "attempts", "approvals", "net_approvals",
                    "approvals_organic", "cancel", "cancel_organic", "revenue",
                    "void", "void_dollar", "void_void_date",
                    "void_void_date_dollar", "cb", "cb_dollar", "cb_organic",
                    "cb_non_organic", "cb_organic_dollar", "cb_cb_date",
                    "cb_cb_date_dollar", "refund", "refund_dollar",
                    "refund_organic", "refund_organic_dollar",
                    "refund_refund_date", "refund_refund_date_dollar",
                ],
            },
            "mid_summary": {
                "table_name": self._table("mid_summary"),
                "description": "Monthly MID/gateway health and performance metrics. ~952 rows.",
                "columns": [
                    "client_id", "gateway_id", "month_year", "volume",
                    "initials", "rebills", "overall_cb", "cb_visa",
                    "cb_master", "overall_declines", "decline_percent",
                    "declines_exclude_zero", "declines_visa", "declines_master",
                    "attempts", "attempts_exclude_zero", "attempts_visa",
                    "attempts_master", "attempts_initials", "attempts_rebills",
                    "approvals", "approvals_exclude_zero", "approvals_visa",
                    "approvals_master", "approvals_master_pm", "overall_refund",
                    "refund_alert_visa", "refund_alert_master", "alert", "rdr",
                    "ethoca", "cdrn", "verifi", "ethoca_visa",
                    "rdr_effective_percent", "ethoca_effective_percent",
                    "cb_rate", "cb_visa_rate", "cb_master_rate", "decline_rate",
                    "alert_rate", "higher_cb", "count_critical",
                    "count_at_risk", "inactive", "health_tag", "monthly_cap",
                    "capacity_left", "near_capacity", "initials_performance",
                    "rebills_performance", "high_cb_alert_coverage",
                    "no_alerts_enabled", "decline_spike",
                ],
            },
            "alert_details": {
                "table_name": self._table("alert_details"),
                "description": "Individual alert-level detail data. ~173k rows.",
                "columns": [
                    "client_id", "alert_id", "alert_date", "alert_type",
                    "alert_status", "alert_duplication", "order_id",
                    "bill_email", "is_cb", "is_refund_void",
                    "transaction_amount", "transaction_date", "gateway_id",
                    "gateway_alias", "is_approved", "is_crm", "card_bin",
                    "card_group", "campaign_id", "product_id", "billing_cycle",
                    "attempt_sort", "price_point", "affid", "sub_affid", "c",
                    "subscription_type", "product_group", "count_of_alert",
                    "alert_dollar", "alert_count",
                ],
            },
            "alert_summary": {
                "table_name": self._table("alert_summary"),
                "description": "Aggregated alert data with breakdowns by type. ~145k rows.",
                "columns": [
                    "date", "client_id", "gateway_id", "alert_type",
                    "alert_status", "alert_duplication", "card_bin", "is_crm",
                    "is_refund_void", "is_cb_final", "campaign_id",
                    "product_id", "billing_cycle", "attempt_sort",
                    "price_point", "affid", "sub_affid", "c", "is_tc40",
                    "transaction_amount", "alert_count", "alert_dollar", "rdr",
                    "rdr_dollar", "ethoca", "ethoca_dollar", "cdrn",
                    "cdrn_dollar", "other_alert", "other_alert_dollar",
                    "distinct_alert_count",
                ],
            },
            "cohort_summary": {
                "table_name": self._table("cohort_summary"),
                "description": "Cohort-based analysis tracking customers from initial order through rebill cycles. ~479k rows.",
                "columns": [
                    "client_id", "date", "sales_type", "billing_cycle",
                    "attempt_col", "refund_type", "alert_type", "cpa",
                    "trial_price_point", "trial_bin", "trial_sub_affid",
                    "trial_c", "trial_affid", "trial_campaign_id",
                    "trial_product_id", "trial_gateway_id", "attempts",
                    "approvals", "net_approvals", "cancel", "revenue", "cb",
                    "cb_dollar", "refund", "refund_dollar",
                ],
            },
            "decline_recovery": {
                "table_name": self._table("decline_recovery"),
                "description": "Decline and recovery tracking. ~1.38M rows.",
                "columns": [
                    "client_id", "date", "decline_group", "gateway_id", "bin",
                    "campaign_id", "product_id", "affid", "sub_affid", "c",
                    "price_point", "sales_type", "billing_cycle",
                    "recovery_attempts", "organic_declines", "declines",
                    "reattempts", "recovered", "cancel", "cb", "refund",
                    "cb_cb_date", "refund_refund_date",
                    "organic_declines_dollar", "reattempts_dollar",
                    "not_reattempts_dollar", "recovered_dollar",
                ],
            },
            "hourly_revenue": {
                "table_name": self._table("hourly_revenue"),
                "description": "Hourly revenue tracking comparing today vs 7-day average. 24 rows (one per hour).",
                "columns": [
                    "client_id", "sort_order", "hour", "avg_7d_revenue",
                    "avg_7d_initial", "avg_7d_rebill",
                    "avg_7d_straight_sales", "today_revenue", "today_initial",
                    "today_rebill", "today_straight_sales",
                ],
            },
            "ltv_analysis": {
                "table_name": self._table("ltv_analysis"),
                "description": "Customer-level LTV data across time buckets. ~291k rows.",
                "columns": [
                    "email", "product_id", "campaign_id", "gateway_id",
                    "week_range", "month", "first_order_total",
                    "first_order_date",
                    "days_30_total", "days_30_count",
                    "net_days_30_total", "net_days_30_count",
                    "days_60_total", "days_60_count",
                    "net_days_60_total", "net_days_60_count",
                    "days_90_total", "days_90_count",
                    "net_days_90_total", "net_days_90_count",
                    "days_120_total", "days_120_count",
                    "net_days_120_total", "net_days_120_count",
                    "days_150_total", "days_150_count",
                    "net_days_150_total", "net_days_150_count",
                    "days_180_total", "days_180_count",
                    "net_days_180_total", "net_days_180_count",
                    "days_210_total", "days_210_count",
                    "net_days_210_total", "net_days_210_count",
                    "days_240_total", "days_240_count",
                    "net_days_240_total", "net_days_240_count",
                    "days_270_total", "days_270_count",
                    "net_days_270_total", "net_days_270_count",
                    "days_300_total", "days_300_count",
                    "net_days_300_total", "net_days_300_count",
                    "days_330_total", "days_330_count",
                    "net_days_330_total", "net_days_330_count",
                    "days_360_total", "days_360_count",
                    "net_days_360_total", "net_days_360_count",
                    "days_360_plus_total", "days_360_plus_count",
                    "net_days_360_plus_total", "net_days_360_plus_count",
                    "client_id", "bin",
                ],
            },
            "ltv_summary": {
                "table_name": self._table("ltv_summary"),
                "description": "Aggregated LTV summary by cohort/period. ~283k rows.",
                "columns": [
                    "first_order_date", "month_date", "month", "week_range",
                    "product_id", "campaign_id", "gateway_id", "bin",
                    "customer_count", "first_order_total_sum",
                    "days_30_total_sum", "days_60_total_sum",
                    "days_90_total_sum", "days_120_total_sum",
                    "days_150_total_sum", "days_180_total_sum",
                    "days_210_total_sum", "days_240_total_sum",
                    "days_270_total_sum", "days_300_total_sum",
                    "days_330_total_sum", "days_360_total_sum",
                    "days_360_plus_total_sum",
                    "net_days_30_total_sum", "net_days_60_total_sum",
                    "net_days_90_total_sum", "net_days_120_total_sum",
                    "net_days_150_total_sum", "net_days_180_total_sum",
                    "net_days_210_total_sum", "net_days_240_total_sum",
                    "net_days_270_total_sum", "net_days_300_total_sum",
                    "net_days_330_total_sum", "net_days_360_total_sum",
                    "net_days_360_plus_total_sum",
                    "days_30_customer_count", "days_60_customer_count",
                    "days_90_customer_count", "days_120_customer_count",
                    "days_150_customer_count", "days_180_customer_count",
                    "days_210_customer_count", "days_240_customer_count",
                    "days_270_customer_count", "days_300_customer_count",
                    "days_330_customer_count", "days_360_customer_count",
                    "days_360_plus_customer_count",
                ],
            },
            "cb_refund_alert": {
                "table_name": self._table("cb_refund_alert"),
                "description": "Chargeback and refund data with alert correlation and timing. ~207k rows.",
                "columns": [
                    "client_id", "date", "campaign_id", "product_id",
                    "gateway_id", "bin", "affid", "sub_affid", "c",
                    "price_point", "sales_type", "billing_cycle",
                    "refund_type", "alert_type", "cpa", "cb_no_of_days",
                    "refund_no_of_days", "dispute_no_of_days",
                    "attempts_total", "attempts", "approvals", "net_approvals",
                    "approvals_organic", "cancel", "revenue", "cb",
                    "cb_dollar", "cb_cb_date", "cb_cb_date_dollar", "refund",
                    "refund_dollar", "refund_refund_date",
                    "refund_refund_date_dollar",
                ],
            },
        }

    @property
    def client_id(self) -> int:
        return self._client_id

    def get_view_schema(self, view_key: str) -> Dict[str, Any]:
        if view_key not in self._schemas:
            raise KeyError(f"Unknown view_key: {view_key}")
        return self._schemas[view_key]

    def list_view_keys(self) -> List[str]:
        return sorted(self._schemas.keys())


# ---------------------------------------------------------------------------
# Default instance and backward-compatible module-level functions
# ---------------------------------------------------------------------------
_default_registry: Optional[SchemaRegistry] = None


def _get_default_registry() -> SchemaRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = SchemaRegistry()
    return _default_registry


def get_view_schema(view_key: str) -> Dict[str, Any]:
    return _get_default_registry().get_view_schema(view_key)


def list_view_keys() -> List[str]:
    return _get_default_registry().list_view_keys()
