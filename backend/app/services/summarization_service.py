from __future__ import annotations

from typing import Optional

from app.services.claude_client import ClaudeClient, ClaudeClientFactory


class SummarizationService:
    """
    Summarizes text using Claude for use as chat history context.
    Single Responsibility: prompt construction + Claude call for summarization.
    Dependency injected: receives a ClaudeClient instance.
    """

    _SYSTEM_PROMPT = """\
You summarize assistant answers for chat history context.

Rules:
- Output only the summary. No preamble or labels.
- Be concise: keep key facts, numbers, and conclusions. No over-explanations.
- Preserve important figures (currency, percentages, counts) when present.
- Keep the summary under 400 characters so it fits in context without exceeding token limits.
"""

    def __init__(self, claude_client: ClaudeClient) -> None:
        self._claude = claude_client

    def summarize(self, text: str) -> str:
        """Return a concise summarized version of the given text for history context."""
        if not (text or "").strip():
            return ""
        user_message = f"Summarize the following for chat history context:\n\n{text.strip()}"
        return self._claude.chat(
            system=self._SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
            max_tokens=256,
        ).strip()


# ---------------------------------------------------------------------------
# Backward-compatible module-level function (used by router)
# ---------------------------------------------------------------------------
_default_service: Optional[SummarizationService] = None


def _get_default() -> SummarizationService:
    global _default_service
    if _default_service is None:
        _default_service = SummarizationService(ClaudeClientFactory.get_default())
    return _default_service


def summarize_text(text: str) -> str:
    """Return summarized text for chat history context."""
    return _get_default().summarize(text)
