from __future__ import annotations


class BeastInsightError(Exception):
    """Base exception for all BeastInsight errors."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        self.detail = detail or message
        super().__init__(message)


class ClaudeAPIError(BeastInsightError):
    """Raised when the Anthropic/Claude API call fails."""


class ClaudeRateLimitError(ClaudeAPIError):
    """Raised when Claude returns a 429 rate-limit response."""


class ClaudeAuthError(ClaudeAPIError):
    """Raised when the Anthropic API key is invalid or missing."""


class ClaudeOverloadedError(ClaudeAPIError):
    """Raised when Claude is temporarily overloaded (529)."""


class SQLGenerationError(BeastInsightError):
    """Raised when Claude fails to produce a valid SQL query."""


class SQLValidationError(BeastInsightError):
    """Raised when generated SQL fails safety checks."""


class DatabaseConnectionError(BeastInsightError):
    """Raised when we cannot connect to Postgres."""


class DatabaseQueryError(BeastInsightError):
    """Raised when a SQL query execution fails (syntax, permissions, timeout)."""


class ViewRoutingError(BeastInsightError):
    """Raised when the view key cannot be resolved."""


class InsightBuildError(BeastInsightError):
    """Raised when the insight data pipeline fails."""
