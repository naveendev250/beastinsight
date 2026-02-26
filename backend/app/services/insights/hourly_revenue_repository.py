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

class HourlyRevenueRepository(BaseRepository):
    """Predefined SQL queries for Hourly Revenue insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("hourly_revenue")

    def fetch_all_hours(self) -> List[Dict[str, Any]]:
        """Small table — fetch all 24 rows."""
        sql = f"""
            SELECT
                hour,
                today_revenue,
                today_initial,
                today_rebill,
                today_straight_sales,
                avg_7d_revenue,
                avg_7d_initial,
                avg_7d_rebill,
                avg_7d_straight_sales
            FROM {self._tbl}
            ORDER BY hour
        """
        return self._fetch(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class HourlyRevenueInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: HourlyRevenueRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building Hourly Revenue insight")

        # Phase A — fetch
        hours = self._repo.fetch_all_hours()

        if not hours:
            return {
                "today_vs_avg": {},
                "breakdown": {},
                "peak_hour": None,
                "anomaly_hours": [],
            }

        # Phase B — analytics

        # 1. Today total vs 7-day average total
        today_total = sum(safe_float(h.get("today_revenue")) for h in hours)
        avg_total = sum(safe_float(h.get("avg_7d_revenue")) for h in hours)

        today_initial = sum(safe_float(h.get("today_initial")) for h in hours)
        today_rebill = sum(safe_float(h.get("today_rebill")) for h in hours)
        today_straight = sum(safe_float(h.get("today_straight_sales")) for h in hours)

        avg_initial = sum(safe_float(h.get("avg_7d_initial")) for h in hours)
        avg_rebill = sum(safe_float(h.get("avg_7d_rebill")) for h in hours)
        avg_straight = sum(safe_float(h.get("avg_7d_straight_sales")) for h in hours)

        ahead_behind = "ahead" if today_total >= avg_total else "behind"
        overall_change = pct_change(today_total, avg_total)

        # 2. Peak revenue hour
        peak_hour = max(hours, key=lambda h: safe_float(h.get("today_revenue")))

        # 3. Anomaly hours (deviation > 30% from 7d avg)
        anomaly_hours = []
        for h in hours:
            t_rev = safe_float(h.get("today_revenue"))
            a_rev = safe_float(h.get("avg_7d_revenue"))
            if detect_anomaly(t_rev, a_rev, threshold=0.30):
                anomaly_hours.append({
                    "hour": h.get("hour"),
                    "today_revenue": safe_round(t_rev),
                    "avg_7d_revenue": safe_round(a_rev),
                    "deviation_pct": pct_change(t_rev, a_rev),
                })

        # Phase C — structured JSON
        return {
            "today_vs_avg": {
                "today_total": safe_round(today_total),
                "avg_7d_total": safe_round(avg_total),
                "status": ahead_behind,
                "change_pct": overall_change,
            },
            "breakdown": {
                "initials": {
                    "today": safe_round(today_initial),
                    "avg_7d": safe_round(avg_initial),
                    "change_pct": pct_change(today_initial, avg_initial),
                },
                "rebills": {
                    "today": safe_round(today_rebill),
                    "avg_7d": safe_round(avg_rebill),
                    "change_pct": pct_change(today_rebill, avg_rebill),
                },
                "straight_sales": {
                    "today": safe_round(today_straight),
                    "avg_7d": safe_round(avg_straight),
                    "change_pct": pct_change(today_straight, avg_straight),
                },
            },
            "peak_hour": {
                "hour": peak_hour.get("hour"),
                "revenue": safe_round(safe_float(peak_hour.get("today_revenue"))),
            },
            "anomaly_hours": anomaly_hours[:5],  # top 5
        }
