from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.db import DatabaseManager
from app.services.insights.base import (
    BaseRepository,
    detect_anomaly,
    pct_change,
    safe_divide,
    safe_float,
    safe_round,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase A — Data Fetch
# ---------------------------------------------------------------------------

class OrderSummaryRepository(BaseRepository):
    """Predefined SQL queries for Order Summary insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("order_summary")

    def fetch_today_yesterday_metrics(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                date,
                SUM(revenue) AS revenue,
                SUM(approvals) AS approvals,
                SUM(attempts) AS attempts
            FROM {self._tbl}
            WHERE date IN (CURRENT_DATE, CURRENT_DATE - 1)
            GROUP BY date
            ORDER BY date DESC
        """
        return self._fetch(sql)

    def fetch_sales_type_split(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                date,
                sales_type,
                SUM(revenue) AS revenue
            FROM {self._tbl}
            WHERE date IN (CURRENT_DATE, CURRENT_DATE - 1)
            GROUP BY date, sales_type
            ORDER BY date DESC, revenue DESC
        """
        return self._fetch(sql)

    def fetch_week_over_week(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                CASE
                    WHEN date >= DATE_TRUNC('week', CURRENT_DATE)
                        THEN 'current_week'
                    ELSE 'previous_week'
                END AS week_label,
                SUM(revenue) AS revenue
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('week', CURRENT_DATE) - INTERVAL '7 days'
            GROUP BY week_label
        """
        return self._fetch(sql)

    def fetch_top_campaigns(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT campaign_id, SUM(revenue) AS revenue
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY campaign_id
            ORDER BY revenue DESC
            LIMIT 5
        """
        return self._fetch(sql)

    def fetch_top_affiliates(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT affid, SUM(revenue) AS revenue
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY affid
            ORDER BY revenue DESC
            LIMIT 5
        """
        return self._fetch(sql)

    def fetch_cb_refund_rates(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(cb) AS total_cb,
                SUM(refund) AS total_refund,
                SUM(approvals) AS total_approvals
            FROM {self._tbl}
            WHERE date >= CURRENT_DATE - 30
        """
        return self._fetch_single(sql)

    def fetch_aov_trend(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                date,
                SUM(revenue) AS revenue,
                SUM(approvals) AS approvals
            FROM {self._tbl}
            WHERE date >= CURRENT_DATE - 30
            GROUP BY date
            ORDER BY date
        """
        return self._fetch(sql)

    def fetch_anomaly_data(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(CASE WHEN date = CURRENT_DATE THEN revenue ELSE 0 END)
                    AS today_revenue,
                SUM(CASE WHEN date BETWEEN CURRENT_DATE - 7
                    AND CURRENT_DATE - 1 THEN revenue ELSE 0 END) / 7.0
                    AS avg_7d_revenue
            FROM {self._tbl}
            WHERE date >= CURRENT_DATE - 7
        """
        return self._fetch_single(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class OrderSummaryInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: OrderSummaryRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building Order Summary insight")

        # Phase A — fetch all raw data
        today_yest = self._repo.fetch_today_yesterday_metrics()
        sales_split = self._repo.fetch_sales_type_split()
        wow = self._repo.fetch_week_over_week()
        top_campaigns = self._repo.fetch_top_campaigns()
        top_affiliates = self._repo.fetch_top_affiliates()
        cb_refund = self._repo.fetch_cb_refund_rates()
        aov_rows = self._repo.fetch_aov_trend()
        anomaly = self._repo.fetch_anomaly_data()

        # Phase B — analytics
        # 1. Today / Yesterday metrics
        today_data = next((r for r in today_yest if r.get("date") and str(r["date"]) >= str(today_yest[0]["date"])), {}) if today_yest else {}
        yest_data = next((r for r in today_yest if r != today_data), {}) if len(today_yest) > 1 else {}

        today_metrics = {
            "date": today_data.get("date"),
            "revenue": safe_round(today_data.get("revenue")),
            "approvals": today_data.get("approvals", 0),
            "attempts": today_data.get("attempts", 0),
            "approval_rate": safe_round(
                safe_divide(today_data.get("approvals"), today_data.get("attempts")) * 100
            ),
        }
        yesterday_metrics = {
            "date": yest_data.get("date"),
            "revenue": safe_round(yest_data.get("revenue")),
            "approvals": yest_data.get("approvals", 0),
            "attempts": yest_data.get("attempts", 0),
            "approval_rate": safe_round(
                safe_divide(yest_data.get("approvals"), yest_data.get("attempts")) * 100
            ),
        }

        # 2. Sales type split (today)
        today_date = today_metrics["date"]
        today_split_rows = [r for r in sales_split if str(r.get("date")) == str(today_date)] if today_date else sales_split[:3]
        total_split_rev = sum(safe_float(r.get("revenue")) for r in today_split_rows)
        sales_breakdown = []
        for r in today_split_rows:
            rev = safe_float(r.get("revenue"))
            sales_breakdown.append({
                "sales_type": r.get("sales_type"),
                "revenue": safe_round(rev),
                "pct": safe_round(safe_divide(rev, total_split_rev) * 100),
            })

        # 3. Week-over-week
        current_rev = safe_float(next((r.get("revenue") for r in wow if r.get("week_label") == "current_week"), 0))
        prev_rev = safe_float(next((r.get("revenue") for r in wow if r.get("week_label") == "previous_week"), 0))
        wow_result = {
            "current_week_revenue": safe_round(current_rev),
            "previous_week_revenue": safe_round(prev_rev),
            "change_pct": pct_change(current_rev, prev_rev),
        }

        # 4. Top performers
        top_campaign = top_campaigns[0] if top_campaigns else {}
        top_affiliate = top_affiliates[0] if top_affiliates else {}

        # 5. CB & refund rates
        cb_rate = safe_round(
            safe_divide(cb_refund.get("total_cb"), cb_refund.get("total_approvals")) * 100
        )
        refund_rate = safe_round(
            safe_divide(cb_refund.get("total_refund"), cb_refund.get("total_approvals")) * 100
        )

        # 6. AOV trend
        aov_list = []
        for r in aov_rows[-7:]:  # last 7 days for brevity
            aov_list.append({
                "date": r.get("date"),
                "aov": safe_round(safe_divide(r.get("revenue"), r.get("approvals"))),
            })

        # 7. Anomaly detection
        today_rev = safe_float(anomaly.get("today_revenue"))
        avg_7d = safe_float(anomaly.get("avg_7d_revenue"))
        is_anomaly = detect_anomaly(today_rev, avg_7d)

        # Phase C — structured JSON
        return {
            "today": today_metrics,
            "yesterday": yesterday_metrics,
            "sales_breakdown": sales_breakdown,
            "week_over_week": wow_result,
            "top_campaign": {
                "campaign_id": top_campaign.get("campaign_id"),
                "revenue": safe_round(top_campaign.get("revenue")),
            },
            "top_affiliate": {
                "affid": top_affiliate.get("affid"),
                "revenue": safe_round(top_affiliate.get("revenue")),
            },
            "risk_metrics": {
                "chargeback_rate_pct": cb_rate,
                "refund_rate_pct": refund_rate,
                "period": "last_30_days",
            },
            "aov_trend": aov_list,
            "anomaly": {
                "is_anomaly": is_anomaly,
                "today_revenue": safe_round(today_rev),
                "avg_7d_revenue": safe_round(avg_7d),
                "deviation_pct": pct_change(today_rev, avg_7d),
            },
        }
