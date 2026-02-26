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

class MidHealthRepository(BaseRepository):
    """Predefined SQL queries for MID Health insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("mid_summary")

    def fetch_latest_month(self) -> str:
        sql = f"""
            SELECT month_year
            FROM {self._tbl}
            ORDER BY TO_DATE(month_year, 'Mon YYYY') DESC
            LIMIT 1
        """
        row = self._fetch_single(sql)
        return row["month_year"]

    def fetch_health_distribution(self, month_year: str):
        sql = f"""
            SELECT health_tag, COUNT(DISTINCT gateway_id) AS mid_count
            FROM {self._tbl}
            WHERE month_year = %s
            GROUP BY health_tag
        """
        return self._fetch(sql, (month_year,))

    def fetch_critical_mids(self, month_year: str):
        sql = f"""
            SELECT gateway_id, cb_rate, decline_rate, volume
            FROM {self._tbl}
            WHERE month_year = %s
              AND health_tag = 'critical'
            ORDER BY cb_rate DESC
            LIMIT 50
        """
        return self._fetch(sql, (month_year,))

    def fetch_capacity_mids(self, month_year: str):
        sql = f"""
            SELECT gateway_id, monthly_cap, capacity_left
            FROM {self._tbl}
            WHERE month_year = %s
              AND near_capacity = true
            ORDER BY capacity_left ASC
            LIMIT 50
        """
        return self._fetch(sql, (month_year,))

    def fetch_spike_mids(self, month_year: str):
        sql = f"""
            SELECT gateway_id, decline_rate
            FROM {self._tbl}
            WHERE month_year = %s
              AND decline_spike = true
            ORDER BY decline_rate DESC
            LIMIT 50
        """
        return self._fetch(sql, (month_year,))

    def fetch_no_alert_coverage(self, month_year: str):
        sql = f"""
            SELECT gateway_id, cb_rate
            FROM {self._tbl}
            WHERE month_year = %s
              AND no_alerts_enabled = true
            ORDER BY cb_rate DESC
            LIMIT 50
        """
        return self._fetch(sql, (month_year,))

    def fetch_visa_vs_mastercard(self, month_year: str):
        sql = f"""
            SELECT
                SUM(cb_visa) AS total_cb_visa,
                SUM(cb_master) AS total_cb_master,
                AVG(cb_visa_rate) AS avg_visa_cb_rate,
                AVG(cb_master_rate) AS avg_master_cb_rate
            FROM {self._tbl}
            WHERE month_year = %s
        """
        return self._fetch_single(sql, (month_year,))

    def fetch_monthly_trend(self):
        sql = f"""
            SELECT
                month_year,
                health_tag,
                COUNT(DISTINCT gateway_id) AS mid_count
            FROM {self._tbl}
            GROUP BY month_year, health_tag
            ORDER BY TO_DATE(month_year, 'Mon YYYY') DESC
        """
        return self._fetch(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class MidHealthInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: MidHealthRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building MID Health insight")

        month_year = self._repo.fetch_latest_month()
        # Phase A — fetch
        distribution = self._repo.fetch_health_distribution(month_year)
        critical_mids = self._repo.fetch_critical_mids(month_year)
        capacity_mids = self._repo.fetch_capacity_mids(month_year)
        spike_mids = self._repo.fetch_spike_mids(month_year)
        no_alert = self._repo.fetch_no_alert_coverage(month_year)
        visa_mc = self._repo.fetch_visa_vs_mastercard(month_year)
        monthly_trend = self._repo.fetch_monthly_trend()

        # Phase B — analytics

        # 1. Health distribution
        dist_map = {row["health_tag"]: int(row["mid_count"]) for row in distribution}
        total_mids = sum(dist_map.values())

        for tag in ["healthy", "critical", "at-risk", "inactive"]:
            dist_map.setdefault(tag, 0)


        # 2. Critical MIDs (top 10 for report)
        critical_list = []
        for r in critical_mids[:10]:
            critical_list.append({
                "gateway_id": r.get("gateway_id"),
                "cb_rate": safe_round(r.get("cb_rate"), 4),
                "decline_rate": safe_round(r.get("decline_rate"), 4),
                "volume": r.get("volume"),
            })

        # 3. Capacity warnings
        capacity_list = []
        for r in capacity_mids[:10]:
            capacity_list.append({
                "gateway_id": r.get("gateway_id"),
                "monthly_cap": r.get("monthly_cap"),
                "capacity_left": r.get("capacity_left"),
            })

        # 4. Decline spikes
        spike_list = []
        for r in spike_mids[:10]:
            spike_list.append({
                "gateway_id": r.get("gateway_id"),
                "decline_rate": safe_round(r.get("decline_rate"), 4),
            })

        # 5. No alert coverage
        no_alert_list = []
        for r in no_alert[:10]:
            no_alert_list.append({
                "gateway_id": r.get("gateway_id"),
                "cb_rate": safe_round(r.get("cb_rate"), 4),
            })

        # 6. Visa vs Mastercard
        visa_vs_mc = {
            "avg_visa_cb_rate": safe_round(visa_mc.get("avg_visa_cb_rate"), 4),
            "avg_master_cb_rate": safe_round(visa_mc.get("avg_master_cb_rate"), 4),
            "total_cb_visa": visa_mc.get("total_cb_visa"),
            "total_cb_master": visa_mc.get("total_cb_master"),
        }

        from datetime import datetime

        def parse_month(m: str):
            return datetime.strptime(m, "%b %Y")

        # 7. Month-over-month trend (group by month_year)
        months_data: Dict[str, Dict[str, int]] = {}
        for row in monthly_trend:
            my = str(row["month_year"])
            tag = row["health_tag"]
            months_data.setdefault(my, {})
            months_data[my][tag] = int(row["mid_count"])

        # Normalize missing tags per month
        for month in months_data:
            for tag in ["healthy", "critical", "at-risk", "inactive"]:
                months_data[month].setdefault(tag, 0)

        # Chronological sort
        sorted_months = sorted(
            months_data.keys(),
            key=lambda m: parse_month(m),
            reverse=True
        )[:6]

        trend = [
            {"month_year": m, "distribution": months_data[m]}
            for m in sorted_months
        ]

        # MoM change for critical count
        mom_change = None
        if len(sorted_months) >= 2:
            curr_critical = months_data[sorted_months[0]]["critical"]
            prev_critical = months_data[sorted_months[1]]["critical"]
            mom_change = pct_change(curr_critical, prev_critical)

        # Phase C — structured JSON
        return {
            "current_month": month_year,
            "distribution": dist_map,
            "total_mids": total_mids,
            "critical_mids": critical_list,
            "capacity_warnings": capacity_list,
            "decline_spikes": spike_list,
            "no_alert_coverage": no_alert_list,
            "visa_vs_mastercard": visa_vs_mc,
            "monthly_trend": trend,
            "critical_mom_change_pct": mom_change,
        }
