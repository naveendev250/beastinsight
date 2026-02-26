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

class AlertRepository(BaseRepository):
    """Predefined SQL queries for Alert insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("alert_summary")

    def fetch_alert_totals(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(CASE WHEN date = CURRENT_DATE THEN alert_count ELSE 0 END)
                    AS today_alerts,
                SUM(CASE WHEN date >= DATE_TRUNC('week', CURRENT_DATE) THEN alert_count ELSE 0 END)
                    AS week_alerts,
                SUM(CASE WHEN date >= DATE_TRUNC('month', CURRENT_DATE) THEN alert_count ELSE 0 END)
                    AS month_alerts,
                SUM(CASE WHEN date = CURRENT_DATE THEN alert_dollar ELSE 0 END)
                    AS today_dollar,
                SUM(CASE WHEN date >= DATE_TRUNC('week', CURRENT_DATE) THEN alert_dollar ELSE 0 END)
                    AS week_dollar,
                SUM(CASE WHEN date >= DATE_TRUNC('month', CURRENT_DATE) THEN alert_dollar ELSE 0 END)
                    AS month_dollar
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
        """
        return self._fetch_single(sql)

    def fetch_alert_mix(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(rdr) AS rdr_count, SUM(rdr_dollar) AS rdr_dollar,
                SUM(ethoca) AS ethoca_count, SUM(ethoca_dollar) AS ethoca_dollar,
                SUM(cdrn) AS cdrn_count, SUM(cdrn_dollar) AS cdrn_dollar,
                SUM(other_alert) AS other_count
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
        """
        return self._fetch_single(sql)

    def fetch_duplicate_stats(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(alert_count) AS total_alerts,
                SUM(distinct_alert_count) AS distinct_alerts
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
        """
        return self._fetch_single(sql)

    def fetch_top_gateways(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT gateway_id, SUM(alert_count) AS total_alerts
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY gateway_id
            ORDER BY total_alerts DESC
            LIMIT 10
        """
        return self._fetch(sql)

    def fetch_daily_trend(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT date, SUM(alert_count) AS daily_alerts
            FROM {self._tbl}
            WHERE date >= CURRENT_DATE - 30
            GROUP BY date
            ORDER BY date
        """
        return self._fetch(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class AlertInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: AlertRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building Alert insight")

        # Phase A — fetch
        totals = self._repo.fetch_alert_totals()
        mix = self._repo.fetch_alert_mix()
        dup_stats = self._repo.fetch_duplicate_stats()
        top_gw = self._repo.fetch_top_gateways()
        daily_trend = self._repo.fetch_daily_trend()

        # Phase B — analytics

        # 1. Alert volume
        volume = {
            "today": totals.get("today_alerts", 0),
            "today_dollar": safe_round(totals.get("today_dollar")),
            "this_week": totals.get("week_alerts", 0),
            "this_week_dollar": safe_round(totals.get("week_dollar")),
            "this_month": totals.get("month_alerts", 0),
            "this_month_dollar": safe_round(totals.get("month_dollar")),
        }

        # 2. Alert mix
        total_month_alerts = safe_float(totals.get("month_alerts"))
        alert_mix = {
            "rdr": {
                "count": mix.get("rdr_count", 0),
                "dollar": safe_round(mix.get("rdr_dollar")),
                "pct": safe_round(safe_divide(mix.get("rdr_count"), total_month_alerts) * 100),
            },
            "ethoca": {
                "count": mix.get("ethoca_count", 0),
                "dollar": safe_round(mix.get("ethoca_dollar")),
                "pct": safe_round(safe_divide(mix.get("ethoca_count"), total_month_alerts) * 100),
            },
            "cdrn": {
                "count": mix.get("cdrn_count", 0),
                "dollar": safe_round(mix.get("cdrn_dollar")),
                "pct": safe_round(safe_divide(mix.get("cdrn_count"), total_month_alerts) * 100),
            },
            "other": {
                "count": mix.get("other_count", 0),
                "pct": safe_round(safe_divide(mix.get("other_count"), total_month_alerts) * 100),
            },
        }

        # 3. Duplicate rate
        total_alerts = safe_float(dup_stats.get("total_alerts"))
        distinct_alerts = safe_float(dup_stats.get("distinct_alerts"))
        duplicates = total_alerts - distinct_alerts
        duplicate_rate = safe_round(safe_divide(duplicates, total_alerts) * 100)

        # 4. Top gateways (top 5 for report)
        top_gateways = []
        for r in top_gw[:5]:
            top_gateways.append({
                "gateway_id": r.get("gateway_id"),
                "alert_count": r.get("total_alerts", 0),
            })

        # 5. 30-day trend direction
        trend_direction = "stable"
        if len(daily_trend) >= 14:
            first_half = daily_trend[: len(daily_trend) // 2]
            second_half = daily_trend[len(daily_trend) // 2:]
            avg_first = safe_divide(
                sum(safe_float(r.get("daily_alerts")) for r in first_half),
                len(first_half),
            )
            avg_second = safe_divide(
                sum(safe_float(r.get("daily_alerts")) for r in second_half),
                len(second_half),
            )
            change = pct_change(avg_second, avg_first)
            if change is not None:
                if change > 10:
                    trend_direction = "increasing"
                elif change < -10:
                    trend_direction = "decreasing"

        # Phase C — structured JSON
        return {
            "volume": volume,
            "alert_mix": alert_mix,
            "duplicate_rate_pct": duplicate_rate,
            "duplicates_count": int(duplicates),
            "top_gateways": top_gateways,
            "trend_direction": trend_direction,
            "daily_trend_sample": [
                {"date": r.get("date"), "alerts": r.get("daily_alerts")}
                for r in daily_trend[-7:]
            ],
        }
