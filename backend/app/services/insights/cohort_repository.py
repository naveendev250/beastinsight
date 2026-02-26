from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.db import DatabaseManager
from app.services.insights.base import (
    BaseRepository,
    safe_divide,
    safe_float,
    safe_round,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase A — Data Fetch
# ---------------------------------------------------------------------------

class CohortRepository(BaseRepository):
    """Predefined SQL queries for Cohort Performance insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("cohort_summary")

    def fetch_retention_by_cycle(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                billing_cycle,
                SUM(attempts) AS attempts,
                SUM(approvals) AS approvals,
                SUM(cancel) AS cancels
            FROM {self._tbl}
            WHERE sales_type = 'Rebills'
            GROUP BY billing_cycle
            ORDER BY billing_cycle
        """
        return self._fetch(sql)

    def fetch_revenue_by_cohort_month(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                DATE_TRUNC('month', date) AS cohort_month,
                SUM(revenue) AS total_revenue,
                SUM(approvals) AS total_approvals
            FROM {self._tbl}
            WHERE sales_type = 'Initials'
            GROUP BY cohort_month
            ORDER BY cohort_month DESC
            LIMIT 12
        """
        return self._fetch(sql)

    def fetch_cancellation_by_cycle(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                billing_cycle,
                SUM(cancel) AS cancels,
                SUM(approvals) AS approvals
            FROM {self._tbl}
            GROUP BY billing_cycle
            ORDER BY billing_cycle
        """
        return self._fetch(sql)

    def fetch_acquisition_months(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                DATE_TRUNC('month', date) AS cohort_month,
                SUM(revenue) AS total_revenue,
                SUM(approvals) AS total_approvals,
                SUM(cancel) AS total_cancels
            FROM {self._tbl}
            WHERE sales_type = 'Initials'
            GROUP BY cohort_month
            ORDER BY cohort_month DESC
            LIMIT 12
        """
        return self._fetch(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class CohortInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: CohortRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building Cohort Performance insight")

        # Phase A — fetch
        retention = self._repo.fetch_retention_by_cycle()
        rev_by_month = self._repo.fetch_revenue_by_cohort_month()
        cancel_by_cycle = self._repo.fetch_cancellation_by_cycle()
        acq_months = self._repo.fetch_acquisition_months()

        # Phase B — analytics

        # 1. Retention by billing cycle
        retention_list = []
        for r in retention:
            attempts = safe_float(r.get("attempts"))
            approvals = safe_float(r.get("approvals"))
            cancels = safe_float(r.get("cancels"))
            retention_list.append({
                "billing_cycle": r.get("billing_cycle"),
                "attempts": int(attempts),
                "approvals": int(approvals),
                "approval_rate_pct": safe_round(safe_divide(approvals, attempts) * 100),
                "cancels": int(cancels),
                "cancel_rate_pct": safe_round(safe_divide(cancels, approvals) * 100),
            })

        # 2. Revenue per customer by cohort month
        rev_per_cust = []
        for r in rev_by_month[:6]:
            rev = safe_float(r.get("total_revenue"))
            appr = safe_float(r.get("total_approvals"))
            rev_per_cust.append({
                "cohort_month": r.get("cohort_month"),
                "total_revenue": safe_round(rev),
                "customers": int(appr),
                "revenue_per_customer": safe_round(safe_divide(rev, appr)),
            })

        # 3. Cancellation trend across cycles
        cancel_trend = []
        for r in cancel_by_cycle:
            cancels = safe_float(r.get("cancels"))
            approvals = safe_float(r.get("approvals"))
            cancel_trend.append({
                "billing_cycle": r.get("billing_cycle"),
                "cancel_rate_pct": safe_round(safe_divide(cancels, approvals) * 100),
                "cancels": int(cancels),
            })

        # 4. Best / worst acquisition months
        best_month = None
        worst_month = None
        if acq_months:
            valid = [
                r for r in acq_months if safe_float(r.get("total_approvals")) > 0
            ]
            if valid:
                best = max(
                    valid,
                    key=lambda r: safe_divide(
                        safe_float(r.get("total_revenue")),
                        safe_float(r.get("total_approvals")),
                    ),
                )
                worst = min(
                    valid,
                    key=lambda r: safe_divide(
                        safe_float(r.get("total_revenue")),
                        safe_float(r.get("total_approvals")),
                    ),
                )
                best_month = {
                    "month": best.get("cohort_month"),
                    "revenue_per_customer": safe_round(
                        safe_divide(
                            safe_float(best.get("total_revenue")),
                            safe_float(best.get("total_approvals")),
                        )
                    ),
                    "customers": best.get("total_approvals"),
                }
                worst_month = {
                    "month": worst.get("cohort_month"),
                    "revenue_per_customer": safe_round(
                        safe_divide(
                            safe_float(worst.get("total_revenue")),
                            safe_float(worst.get("total_approvals")),
                        )
                    ),
                    "customers": worst.get("total_approvals"),
                }

        # Phase C — structured JSON
        return {
            "retention_by_cycle": retention_list,
            "revenue_per_customer_by_month": rev_per_cust,
            "cancellation_by_cycle": cancel_trend,
            "best_acquisition_month": best_month,
            "worst_acquisition_month": worst_month,
        }
