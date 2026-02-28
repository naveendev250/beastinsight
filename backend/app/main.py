from __future__ import annotations

import logging
import sys

# Use "app" logger so config applies even when uvicorn has already configured the root logger.
# All app code uses getLogger(__name__) (e.g. app.routers.chat) so logs propagate here.
_app_log = logging.getLogger("app")
_app_log.setLevel(logging.DEBUG)
_app_log.propagate = False
_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
for _h in (
    logging.FileHandler("beastinsights.log", mode="w"),
    logging.StreamHandler(sys.stderr),
):
    _h.setFormatter(_formatter)
    _app_log.addHandler(_h)

logger = _app_log

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.exceptions import (
    BeastInsightError,
    ClaudeAuthError,
    ClaudeOverloadedError,
    ClaudeRateLimitError,
    DatabaseConnectionError,
)
from app.routers.chat import router as chat_router

_ERROR_STATUS_MAP = {
    ClaudeAuthError: 503,
    ClaudeRateLimitError: 429,
    ClaudeOverloadedError: 503,
    DatabaseConnectionError: 503,
}


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title=s.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.parsed_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(BeastInsightError)
    async def beast_insight_error_handler(
        request: Request, exc: BeastInsightError
    ) -> JSONResponse:
        status = _ERROR_STATUS_MAP.get(type(exc), 500)
        logger.error("Unhandled BeastInsightError: %s (type=%s)", exc, type(exc).__name__)
        return JSONResponse(
            status_code=status,
            content={"detail": str(exc)},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred. Please try again."},
        )

    app.include_router(chat_router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
logger.info("BeastInsights AI app started — logging to stderr")
