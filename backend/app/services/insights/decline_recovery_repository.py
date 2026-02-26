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

class DeclineRecoveryRepository(BaseRepository):
    """Predefined SQL queries for Decline Recovery insights."""

    def __init__(self, db_manager: DatabaseManager) -> None:
        super().__init__(db_manager)
        self._tbl = self._table("decline_recovery")

    def fetch_overall_recovery(self) -> Dict[str, Any]:
        sql = f"""
            SELECT
                SUM(recovered) AS total_recovered,
                SUM(declines) AS total_declines,
                SUM(recovered_dollar) AS recovered_dollar,
                SUM(reattempts) AS total_reattempts,
                SUM(organic_declines) AS organic_declines
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
        """
        return self._fetch_single(sql)

    def fetch_top_decline_reasons(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                decline_group,
                SUM(declines) AS total_declines,
                SUM(recovered) AS total_recovered,
                SUM(recovered_dollar) AS recovered_dollar
            FROM {self._tbl}
            WHERE date >= DATE_TRUNC('month', CURRENT_DATE)
            GROUP BY decline_group
            ORDER BY total_declines DESC
            LIMIT 10
        """
        return self._fetch(sql)

    def fetch_daily_trend(self) -> List[Dict[str, Any]]:
        sql = f"""
            SELECT
                date,
                SUM(declines) AS declines,
                SUM(recovered) AS recovered,
                SUM(recovered_dollar) AS recovered_dollar
            FROM {self._tbl}
            WHERE date >= CURRENT_DATE - 30
            GROUP BY date
            ORDER BY date
        """
        return self._fetch(sql)


# ---------------------------------------------------------------------------
# Phase B — Analytics + Phase C — Insight Structuring
# ---------------------------------------------------------------------------

class DeclineRecoveryInsight:
    """Pure Python analytics and structured JSON builder."""

    def __init__(self, repository: DeclineRecoveryRepository) -> None:
        self._repo = repository

    def build(self) -> Dict[str, Any]:
        logger.info("Building Decline Recovery insight")

        # Phase A — fetch
        overall = self._repo.fetch_overall_recovery()
        top_reasons = self._repo.fetch_top_decline_reasons()
        daily_trend = self._repo.fetch_daily_trend()

        # Phase B — analytics

        # 1. Overall recovery
        total_declines = safe_float(overall.get("total_declines"))
        total_recovered = safe_float(overall.get("total_recovered"))
        recovered_dollar = safe_float(overall.get("recovered_dollar"))
        total_reattempts = safe_float(overall.get("total_reattempts"))
        organic_declines = safe_float(overall.get("organic_declines"))

        recovery_rate = safe_round(safe_divide(total_recovered, total_declines) * 100)
        reattempt_rate = safe_round(safe_divide(total_reattempts, total_declines) * 100)
        organic_pct = safe_round(safe_divide(organic_declines, total_declines) * 100)

        # 2. Recovery by category
        by_category = []
        for r in top_reasons:
            dec = safe_float(r.get("total_declines"))
            rec = safe_float(r.get("total_recovered"))
            by_category.append({
                "decline_group": r.get("decline_group"),
                "declines": int(dec),
                "recovered": int(rec),
                "recovered_dollar": safe_round(r.get("recovered_dollar")),
                "recovery_rate_pct": safe_round(safe_divide(rec, dec) * 100),
            })

        # 3. Trend direction (30 days)
        trend_direction = "stable"
        if len(daily_trend) >= 14:
            first_half = daily_trend[: len(daily_trend) // 2]
            second_half = daily_trend[len(daily_trend) // 2:]
            avg_first_rec = safe_divide(
                sum(safe_float(r.get("recovered")) for r in first_half),
                len(first_half),
            )
            avg_second_rec = safe_divide(
                sum(safe_float(r.get("recovered")) for r in second_half),
                len(second_half),
            )
            change = pct_change(avg_second_rec, avg_first_rec)
            if change is not None:
                if change > 10:
                    trend_direction = "improving"
                elif change < -10:
                    trend_direction = "declining"

        # Phase C — structured JSON
        return {
            "overall": {
                "total_declines": int(total_declines),
                "total_recovered": int(total_recovered),
                "recovered_dollar": safe_round(recovered_dollar),
                "recovery_rate_pct": recovery_rate,
                "reattempt_rate_pct": reattempt_rate,
                "period": "current_month",
            },
            "organic_vs_total": {
                "organic_declines": int(organic_declines),
                "total_declines": int(total_declines),
                "organic_pct": organic_pct,
            },
            "by_category": by_category,
            "trend_direction": trend_direction,
            "revenue_impact": {
                "recovered_dollar": safe_round(recovered_dollar),
                "period": "current_month",
            },
        }
