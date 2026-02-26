from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Generator, Optional

from app.db import DatabaseManager
from app.services.claude_client import ClaudeClient, ClaudeClientFactory
from app.services.insights.formatter import InsightFormatter
from app.services.insights.order_summary_repository import (
    OrderSummaryInsight,
    OrderSummaryRepository,
)
from app.services.insights.mid_health_repository import (
    MidHealthInsight,
    MidHealthRepository,
)
from app.services.insights.alert_repository import (
    AlertInsight,
    AlertRepository,
)
from app.services.insights.decline_recovery_repository import (
    DeclineRecoveryInsight,
    DeclineRecoveryRepository,
)
from app.services.insights.ltv_repository import (
    LtvInsight,
    LtvRepository,
)
from app.services.insights.hourly_revenue_repository import (
    HourlyRevenueInsight,
    HourlyRevenueRepository,
)
from app.services.insights.cohort_repository import (
    CohortInsight,
    CohortRepository,
)

logger = logging.getLogger(__name__)

# Map from report key -> (RepositoryClass, InsightClass, formatter_key)
_REPORT_REGISTRY = {
    "order_summary": (OrderSummaryRepository, OrderSummaryInsight, "order_summary"),
    "mid_health": (MidHealthRepository, MidHealthInsight, "mid_health"),
    "alerts": (AlertRepository, AlertInsight, "alerts"),
    "decline_recovery": (DeclineRecoveryRepository, DeclineRecoveryInsight, "decline_recovery"),
    "ltv": (LtvRepository, LtvInsight, "ltv"),
    "hourly_revenue": (HourlyRevenueRepository, HourlyRevenueInsight, "hourly_revenue"),
    "cohort": (CohortRepository, CohortInsight, "cohort"),
}


class InsightService:
    """
    Orchestrates the full Fixed Insight pipeline:
      1. Select correct repository & insight builder
      2. Phase A: Fetch data (repository)
      3. Phase B+C: Analytics + structured JSON (insight builder)
      4. Phase D: LLM formatting (formatter)
      5. Phase E: Safety (logging, error handling)
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        claude_client: ClaudeClient,
    ) -> None:
        self._db = db_manager
        self._formatter = InsightFormatter(claude_client)

    def generate(self, report_key: str) -> Dict[str, Any]:
        """
        Generate fixed insights for the given report.
        Returns dict with keys: report_key, structured_data, formatted_report.
        """
        if report_key not in _REPORT_REGISTRY:
            available = ", ".join(sorted(_REPORT_REGISTRY.keys()))
            raise ValueError(
                f"Unknown report: '{report_key}'. Available: {available}"
            )

        repo_cls, insight_cls, fmt_key = _REPORT_REGISTRY[report_key]

        start = time.time()
        logger.info("Generating insights for report: %s", report_key)

        # Phase A + B + C — deterministic
        try:
            repo = repo_cls(self._db)
            builder = insight_cls(repo)
            structured = builder.build()
        except Exception as e:
            logger.error("Insight build failed for '%s': %s", report_key, e)
            raise RuntimeError(f"Failed to build insights for '{report_key}': {e}")

        # Phase D — LLM formatting
        try:
            formatted = self._formatter.format(fmt_key, structured)
        except Exception as e:
            logger.error("Insight formatting failed for '%s': %s", report_key, e)
            formatted = f"Could not format report. Raw data available."

        elapsed = round(time.time() - start, 2)
        logger.info("Insight '%s' generated in %.2fs", report_key, elapsed)

        return {
            "report_key": report_key,
            "structured_data": structured,
            "formatted_report": formatted,
            "generation_time_seconds": elapsed,
        }

    def generate_stream(self, report_key: str) -> Generator[str, None, None]:
        """
        Stream fixed insights as SSE events.
        Phases A+B+C run first (deterministic), then Phase D streams tokens.

        SSE event format:
          event: phase\ndata: {"phase": "...", "message": "..."}\n\n
          event: token\ndata: {"token": "..."}\n\n
          event: done\ndata: {"report_key": "..."}\n\n
          event: error\ndata: {"error": "..."}\n\n
        """
        if report_key not in _REPORT_REGISTRY:
            available = ", ".join(sorted(_REPORT_REGISTRY.keys()))
            yield self._sse("error", {"error": f"Unknown report: '{report_key}'. Available: {available}"})
            return

        repo_cls, insight_cls, fmt_key = _REPORT_REGISTRY[report_key]

        # Phase A+B+C — deterministic (fetch, analytics, structuring)
        yield self._sse("phase", {"phase": "fetching_data", "message": "Fetching data from database..."})

        try:
            repo = repo_cls(self._db)
            builder = insight_cls(repo)
            structured = builder.build()
        except Exception as e:
            logger.error("Insight build failed for '%s': %s", report_key, e)
            yield self._sse("error", {"error": f"Failed to build insights: {e}"})
            return

        yield self._sse("phase", {"phase": "formatting", "message": "Generating report..."})

        # Phase D — stream LLM tokens
        full_text_parts: list[str] = []
        try:
            for token in self._formatter.format_stream(fmt_key, structured):
                full_text_parts.append(token)
                yield self._sse("token", {"token": token})
        except Exception as e:
            logger.error("Insight stream failed for '%s': %s", report_key, e)
            yield self._sse("error", {"error": f"Formatting failed: {e}"})
            return

        # Done
        yield self._sse("done", {
            "report_key": report_key,
            "full_text": "".join(full_text_parts),
        })

    @staticmethod
    def _sse(event: str, data: dict) -> str:
        """Format a single SSE event string."""
        payload = json.dumps(data, ensure_ascii=False, default=str)
        return f"event: {event}\ndata: {payload}\n\n"

    @staticmethod
    def available_reports() -> list[str]:
        """Return list of available report keys."""
        return sorted(_REPORT_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Backward-compatible module-level function
# ---------------------------------------------------------------------------
_default_service: Optional[InsightService] = None


def _get_default() -> InsightService:
    global _default_service
    if _default_service is None:
        _default_service = InsightService(
            db_manager=DatabaseManager.get_instance(),
            claude_client=ClaudeClientFactory.get_default(),
        )
    return _default_service


def generate_insights(report_key: str) -> Dict[str, Any]:
    return _get_default().generate(report_key)


def generate_insights_stream(report_key: str) -> Generator[str, None, None]:
    yield from _get_default().generate_stream(report_key)
