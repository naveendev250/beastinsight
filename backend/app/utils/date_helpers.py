from __future__ import annotations

from datetime import date, timedelta


class DateHelper:
    """Provides concrete date references for SQL prompt generation."""

    @staticmethod
    def get_date_context() -> str:
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_start = today - timedelta(days=today.weekday())
        last_week_start = week_start - timedelta(days=7)
        last_week_end = week_start - timedelta(days=1)
        month_start = today.replace(day=1)
        if today.month == 1:
            last_month_start = today.replace(
                year=today.year - 1, month=12, day=1
            )
        else:
            last_month_start = today.replace(month=today.month - 1, day=1)
        last_month_end = month_start - timedelta(days=1)

        lines = [
            "Date references (use these for date filters):",
            "- Today: '" + str(today) + "'",
            "- Yesterday: '" + str(yesterday) + "'",
            "- This week (Mon-Sun): '" + str(week_start) + "' to '" + str(today) + "'",
            "- Last week: '" + str(last_week_start) + "' to '" + str(last_week_end) + "'",
            "- Last 7 days: '" + str(today - timedelta(days=7)) + "' to '" + str(today) + "'",
            "- Last 30 days: '" + str(today - timedelta(days=30)) + "' to '" + str(today) + "'",
            "- This month: '" + str(month_start) + "' to '" + str(today) + "'",
            "- Last month: '" + str(last_month_start) + "' to '" + str(last_month_end) + "'",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Backward-compatible module-level function
# ---------------------------------------------------------------------------
def get_date_context() -> str:
    return DateHelper.get_date_context()
