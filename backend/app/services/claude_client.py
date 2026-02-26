from __future__ import annotations

import logging
import threading
from typing import Dict, Generator, List, Optional

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from app.config import get_settings
from app.exceptions import (
    ClaudeAPIError,
    ClaudeAuthError,
    ClaudeOverloadedError,
    ClaudeRateLimitError,
)

logger = logging.getLogger(__name__)


def _translate_anthropic_error(exc: Exception) -> ClaudeAPIError:
    """Map Anthropic SDK exceptions to our typed hierarchy."""
    if isinstance(exc, AuthenticationError):
        return ClaudeAuthError(
            "Invalid or missing Anthropic API key",
            detail="Check your ANTHROPIC_API_KEY environment variable.",
        )
    if isinstance(exc, RateLimitError):
        return ClaudeRateLimitError(
            "Claude API rate limit exceeded — please retry in a moment",
            detail=str(exc),
        )
    if isinstance(exc, APIStatusError) and exc.status_code == 529:
        return ClaudeOverloadedError(
            "Claude is temporarily overloaded — please retry shortly",
            detail=str(exc),
        )
    if isinstance(exc, APIConnectionError):
        return ClaudeAPIError(
            "Cannot reach the Claude API — network issue",
            detail=str(exc),
        )
    if isinstance(exc, APIStatusError):
        return ClaudeAPIError(
            f"Claude API error (HTTP {exc.status_code})",
            detail=str(exc),
        )
    return ClaudeAPIError(f"Unexpected Claude error: {exc}", detail=str(exc))


class ClaudeClient:
    """
    Wraps the Anthropic SDK for chat and single-turn calls.
    Instances are created via ClaudeClientFactory.
    """

    def __init__(self, api_key: str, model: str) -> None:
        self._client = Anthropic(api_key=api_key)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self,
        system: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
    ) -> str:
        try:
            resp = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            )
            return resp.content[0].text.strip()
        except (APIStatusError, APIConnectionError) as exc:
            logger.error("Claude chat call failed: %s", exc)
            raise _translate_anthropic_error(exc) from exc

    def chat_stream(
        self,
        system: str,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
    ) -> Generator[str, None, None]:
        """Yield text tokens as they arrive from the Anthropic streaming API."""
        try:
            with self._client.messages.stream(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except (APIStatusError, APIConnectionError) as exc:
            logger.error("Claude stream call failed: %s", exc)
            raise _translate_anthropic_error(exc) from exc

    def text(self, prompt: str, max_tokens: int = 1024) -> str:
        return self.chat(
            system="",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
        )


class ClaudeClientFactory:
    """
    Factory for ClaudeClient instances.
    Caches clients by (api_key, model) to avoid redundant SDK initializations.
    Thread-safe.
    """

    _cache: Dict[tuple, ClaudeClient] = {}
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def create(
        cls,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> ClaudeClient:
        """
        Create (or retrieve cached) ClaudeClient.
        Falls back to settings for any unspecified parameter.
        """
        s = get_settings()
        resolved_key = api_key or s.anthropic_api_key
        resolved_model = model or s.anthropic_model

        if not resolved_key:
            raise RuntimeError("Missing ANTHROPIC_API_KEY")

        cache_key = (resolved_key, resolved_model)
        with cls._lock:
            if cache_key not in cls._cache:
                cls._cache[cache_key] = ClaudeClient(
                    api_key=resolved_key, model=resolved_model
                )
            return cls._cache[cache_key]

    @classmethod
    def get_default(cls) -> ClaudeClient:
        """Convenience: create client from app settings."""
        return cls.create()

    @classmethod
    def clear_cache(cls) -> None:
        """Reset the factory cache (useful in tests)."""
        with cls._lock:
            cls._cache.clear()


# ---------------------------------------------------------------------------
# Backward-compatible module-level functions (used by router / other modules)
# ---------------------------------------------------------------------------
def claude_chat(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 1024,
) -> str:
    return ClaudeClientFactory.get_default().chat(system, messages, max_tokens)


def claude_text(prompt: str, max_tokens: int = 1024) -> str:
    return ClaudeClientFactory.get_default().text(prompt, max_tokens)
