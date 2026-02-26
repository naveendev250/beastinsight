from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.db import DatabaseManager
from app.services.insights.base import (
    BaseRepository,
    pct_change,
    safe_divide,
    safe_float,
    safe_round,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase A — Data Fetch
# ---------------------------------------------------------------------------

class LtvRepository(BaseRepository):
    """Predefined SQL queries for LTV insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("ltv_summary")

    def fetch_ltv_by_period(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(customer_count) AS total_customers,
                SUM(first_order_total_sum) AS first_order_total,
                SUM(days_30_total_sum) AS gross_30,
                SUM(days_60_total_sum) AS gross_60,
                SUM(days_90_total_sum) AS gross_90,
                SUM(days_180_total_sum) AS gross_180,
                SUM(days_360_total_sum) AS gross_360,
                SUM(days_30_customer_count) AS count_30,
                SUM(days_60_customer_count) AS count_60,
                SUM(days_90_customer_count) AS count_90,
                SUM(days_180_customer_count) AS count_180,
                SUM(days_360_customer_count) AS count_360,
                SUM(net_days_30_total_sum) AS net_30,
                SUM(net_days_60_total_sum) AS net_60,
                SUM(net_days_90_total_sum) AS net_90,
                SUM(net_days_180_total_sum) AS net_180,
                SUM(net_days_360_total_sum) AS net_360
            FROM {self._tbl}
        """
        return self._fetch_single(sql)

    def fetch_best_cohort(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                month,
                SUM(customer_count) AS customers,
                SUM(days_90_total_sum) AS gross_90,
                SUM(days_90_customer_count) AS count_90
            FROM {self._tbl}
            GROUP BY month
            HAVING SUM(days_90_customer_count) > 0
            ORDER BY SUM(days_90_total_sum) / NULLIF(SUM(days_90_customer_count), 0) DESC
            LIMIT 10
        """
        return self._fetch(sql)

    def fetch_first_order_trend(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                month,
                SUM(first_order_total_sum) AS first_order_total,
                SUM(customer_count) AS customer_count
            FROM {self._tbl}
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """
        return self._fetch(sql)

    def fetch_customer_count_trend(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                month,
                SUM(customer_count) AS customer_count
            FROM {self._tbl}
            GROUP BY month
            ORDER BY month DESC
            LIMIT 12
        """
        return self._fetch(sql)

    def fetch_ltv_trajectory(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                month,
                SUM(days_90_total_sum) AS gross_90,
                SUM(net_days_90_total_sum) AS net_90,
                SUM(days_90_customer_count) AS count_90
            FROM {self._tbl}
            GROUP BY month
            HAVING SUM(days_90_customer_count) > 0
            ORDER BY month DESC
            LIMIT 6
        """
        return self._fetch(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class LtvInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: LtvRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building LTV insight")

        # Phase A — fetch
        overall = self._repo.fetch_ltv_by_period()
        best_cohorts = self._repo.fetch_best_cohort()
        fo_trend = self._repo.fetch_first_order_trend()
        cust_trend = self._repo.fetch_customer_count_trend()
        trajectory = self._repo.fetch_ltv_trajectory()

        # Phase B — analytics

        # 1. LTV at key milestones
        milestones = {}
        for days in [30, 60, 90, 180, 360]:
            gross_key = f"gross_{days}"
            net_key = f"net_{days}"
            count_key = f"count_{days}"
            gross_val = safe_float(overall.get(gross_key))
            net_val = safe_float(overall.get(net_key))
            count_val = safe_float(overall.get(count_key))
            milestones[f"days_{days}"] = {
                "gross_ltv": safe_round(safe_divide(gross_val, count_val)),
                "net_ltv": safe_round(safe_divide(net_val, count_val)),
                "customers": int(count_val),
            }

        # 2. Net vs Gross comparison at 90 days
        gross_90 = safe_float(overall.get("gross_90"))
        net_90 = safe_float(overall.get("net_90"))
        count_90 = safe_float(overall.get("count_90"))
        net_vs_gross = {
            "gross_90_ltv": safe_round(safe_divide(gross_90, count_90)),
            "net_90_ltv": safe_round(safe_divide(net_90, count_90)),
            "net_to_gross_ratio": safe_round(safe_divide(net_90, gross_90)),
        }

        # 3. Best cohort
        best_cohort = None
        if best_cohorts:
            bc = best_cohorts[0]
            best_cohort = {
                "month": bc.get("month"),
                "customers": bc.get("customers"),
                "avg_90d_ltv": safe_round(
                    safe_divide(bc.get("gross_90"), bc.get("count_90"))
                ),
            }

        # 4. First order value trend (last 6 months)
        fo_list = []
        for r in fo_trend[:6]:
            fo_list.append({
                "month": r.get("month"),
                "avg_first_order": safe_round(
                    safe_divide(r.get("first_order_total"), r.get("customer_count"))
                ),
                "customers": r.get("customer_count"),
            })

        # 5. Customer count trend
        cc_list = []
        for r in cust_trend[:6]:
            cc_list.append({
                "month": r.get("month"),
                "customers": r.get("customer_count"),
            })

        # 6. LTV trajectory (improving / declining)
        trajectory_list = []
        ltv_values = []
        for r in trajectory:
            avg_ltv = safe_divide(safe_float(r.get("gross_90")), safe_float(r.get("count_90")))
            trajectory_list.append({
                "month": r.get("month"),
                "avg_90d_ltv": safe_round(avg_ltv),
                "customers": r.get("count_90"),
            })
            ltv_values.append(avg_ltv)

        trajectory_direction = "stable"
        if len(ltv_values) >= 3:
            # Compare most recent vs oldest in the 6-month window
            recent_avg = sum(ltv_values[:2]) / 2 if len(ltv_values) >= 2 else ltv_values[0]
            older_avg = sum(ltv_values[-2:]) / 2
            change = pct_change(recent_avg, older_avg)
            if change is not None:
                if change > 5:
                    trajectory_direction = "improving"
                elif change < -5:
                    trajectory_direction = "declining"

        # Phase C — structured JSON
        return {
            "milestones": milestones,
            "net_vs_gross_90d": net_vs_gross,
            "best_cohort": best_cohort,
            "first_order_trend": fo_list,
            "customer_count_trend": cc_list,
            "ltv_trajectory": trajectory_list,
            "trajectory_direction": trajectory_direction,
        }
