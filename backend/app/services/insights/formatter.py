from __future__ import annotations

import json
import logging
from typing import Any, Dict, Generator, Union

from app.services.claude_client import ClaudeClient
from app.services.visualization_prompt import VISUALIZATION_APPENDIX_PROMPT

logger = logging.getLogger(__name__)

_MARKER_START = "__VISUALIZATION_JSON_START__"
_MARKER_END = "__VISUALIZATION_JSON_END__"


class InsightFormatter:
    """
    Phase D — LLM Formatting Layer.
    Single Responsibility: takes structured insight JSON and asks Claude
    to format it into a human-readable markdown report.
    Claude NEVER computes — only formats pre-computed facts.
    """

    _SYSTEM_PROMPT = """\
You are a BI analytics report formatter for BeastInsights, an e-commerce/subscription analytics platform.

INSIGHT (required in every report):
An insight is: a derived, contextualized conclusion from structured data that reduces uncertainty and informs action.
Every report MUST include at least one clear insight — not just a summary of the numbers. End with or weave in a conclusion that helps the user decide what to do (e.g. what to watch, what to change, what is working or at risk).

STRICT RULES:
1. ONLY use the numbers and facts provided in the structured data below.
2. NEVER invent, estimate, or hallucinate any numbers.
3. NEVER perform any calculations — all metrics are pre-computed.
4. Format currency with $ and commas (e.g., $12,345.67).
5. Format percentages to 2 decimal places (e.g., 12.34%).
6. Use bullet points and clear section headers.
7. Highlight risks, anomalies, and notable patterns with bold text.
8. If a section has no data or null values, say "Data not available" — do NOT guess.
9. Keep the report concise but comprehensive.
10. Use markdown formatting (headers, bold, bullets).
"""

    @property
    def _system_prompt(self) -> str:
        return self._SYSTEM_PROMPT + "\n\n" + VISUALIZATION_APPENDIX_PROMPT

    # Per-report formatting instructions
    _REPORT_INSTRUCTIONS: Dict[str, str] = {
        "order_summary": (
            "Generate an Order Summary Insights report with sections:\n"
            "1. Revenue Overview (today/yesterday)\n"
            "2. Sales Type Breakdown (Initials vs Rebills vs Straight Sales with %)\n"
            "3. Week-over-Week Comparison\n"
            "4. Top Performers (campaign, affiliate)\n"
            "5. Risk Metrics (chargeback rate, refund rate)\n"
            "6. Average Order Value Trend\n"
            "7. Anomaly Alerts (if any)"
        ),
        "mid_health": (
            "Generate a MID Health Insights report with sections:\n"
            "1. Health Distribution (healthy/at-risk/critical/inactive counts)\n"
            "2. Critical MIDs (list with CB rate, decline rate)\n"
            "3. Capacity Alerts (MIDs near capacity)\n"
            "4. Decline Spikes\n"
            "5. Alert Coverage Gaps (high CB but no alerts)\n"
            "6. Visa vs Mastercard CB Rates\n"
            "7. Month-over-Month Trend"
        ),
        "alerts": (
            "Generate an Alert Insights report with sections:\n"
            "1. Alert Volume (today/week/month)\n"
            "2. Alert Mix (RDR vs Ethoca vs CDRN vs Other with counts + dollars)\n"
            "3. Effectiveness Rate (% that prevented chargebacks)\n"
            "4. Duplicate Alert Rate\n"
            "5. Top Gateways by Alert Volume\n"
            "6. 30-Day Trend (increasing/decreasing)"
        ),
        "decline_recovery": (
            "Generate a Decline Recovery Insights report with sections:\n"
            "1. Overall Recovery Rate & Dollar Amount\n"
            "2. Top Decline Reasons by Volume\n"
            "3. Recovery Rate by Category\n"
            "4. Reattempt Rate\n"
            "5. Organic vs Total Declines\n"
            "6. Revenue Impact"
        ),
        "ltv": (
            "Generate an LTV Insights report with sections:\n"
            "1. LTV at Key Milestones (30/60/90/180/360 days)\n"
            "2. Net vs Gross LTV Comparison\n"
            "3. Best Performing Cohort\n"
            "4. First Order Value Trend\n"
            "5. Customer Count Trend\n"
            "6. LTV Trajectory (improving/declining)"
        ),
        "hourly_revenue": (
            "Generate an Hourly Revenue Insights report with sections:\n"
            "1. Today vs 7-Day Average (ahead/behind by X%)\n"
            "2. Revenue Breakdown (Initials vs Rebills vs Straight Sales)\n"
            "3. Peak Revenue Hour\n"
            "4. Anomaly Hours (significant deviation from average)"
        ),
        "cohort": (
            "Generate a Cohort Performance Insights report with sections:\n"
            "1. Retention Rate by Billing Cycle\n"
            "2. Revenue per Customer by Cohort Month\n"
            "3. Cancellation Trend Across Cycles\n"
            "4. Best & Worst Acquisition Months"
        ),
    }

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._claude = claude_client

    def format(
        self, report_key: str, structured_data: Dict[str, Any]
    ) -> str:
        """
        Send structured insight JSON to Claude for human-readable formatting.
        Falls back to raw JSON dump if Claude fails (Phase E safety).
        """
        instructions = self._REPORT_INSTRUCTIONS.get(report_key, "")
        data_json = json.dumps(structured_data, indent=2, default=str)

        user_message = (
            f"{instructions}\n\n"
            f"Structured Data:\n```json\n{data_json}\n```"
        )

        try:
            return self._claude.chat(
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=2048,
            )
        except Exception as e:
            logger.error("Insight formatting failed: %s", e)
            return f"**Insight Report ({report_key})**\n\n```json\n{data_json}\n```"

    def format_stream(
        self, report_key: str, structured_data: Dict[str, Any]
    ) -> Generator[Union[str, Dict[str, Any]], None, None]:
        """
        Stream formatted insight tokens from Claude.
        Yields text chunks or {"type": "visualization", "payload": ...}.
        Falls back to raw JSON dump if Claude fails (Phase E safety).
        """
        instructions = self._REPORT_INSTRUCTIONS.get(report_key, "")
        data_json = json.dumps(structured_data, indent=2, default=str)

        user_message = (
            f"{instructions}\n\n"
            f"Structured Data:\n```json\n{data_json}\n```"
        )

        try:
            buffer = ""
            json_buffer = ""
            inside_json = False

            for chunk in self._claude.chat_stream(
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=2048,
            ):
                buffer += chunk

                if _MARKER_START in buffer:
                    before, _, after = buffer.partition(_MARKER_START)
                    if before:
                        yield before
                    json_buffer = after
                    buffer = ""
                    inside_json = True
                elif inside_json and _MARKER_END in buffer:
                    json_part, _, rest = buffer.partition(_MARKER_END)
                    json_buffer += json_part
                    try:
                        parsed = json.loads(json_buffer)
                        yield {"type": "visualization", "payload": parsed}
                    except json.JSONDecodeError:
                        pass
                    json_buffer = ""
                    buffer = rest
                    inside_json = False
                elif inside_json:
                    json_buffer += buffer
                    buffer = ""
                else:
                    if len(buffer) > len(_MARKER_START):
                        yield buffer[: -len(_MARKER_START)]
                        buffer = buffer[-len(_MARKER_START) :]
            if buffer and not inside_json:
                yield buffer
        except Exception as e:
            logger.error("Insight stream formatting failed: %s", e)
            yield f"**Insight Report ({report_key})**\n\n```json\n{data_json}\n```"
