from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.exceptions import (
    ClaudeAPIError,
    ClaudeAuthError,
    ClaudeOverloadedError,
    ClaudeRateLimitError,
    DatabaseConnectionError,
    DatabaseQueryError,
    SQLGenerationError,
    SQLValidationError,
    ViewRoutingError,
)
from app.redis_client import memory_store
from app.schemas.schema_metadata import get_view_schema
from app.services.explanation_service import generate_explanation, generate_explanation_stream
from app.services.insight_service import generate_insights, generate_insights_stream
from app.services.query_executor import run_query
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.view_router import detect_insight_mode, detect_view

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    session_id: str = Field(default="local-dev")
    question: str


class ChatResponse(BaseModel):
    view_key: str
    sql: str = ""
    answer: str
    is_insight: bool = False
    error: Optional[str] = None


@router.post("/", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    # ---------------------------------------------------------------
    # 0. Check for Fixed Insight mode
    # ---------------------------------------------------------------
    is_insight, report_key = detect_insight_mode(req.question)

    if is_insight and report_key:
        return _handle_insight(req, report_key)

    # ---------------------------------------------------------------
    # Free-form Q&A flow
    # ---------------------------------------------------------------
    return _handle_qa(req)


@router.post("/stream")
def chat_stream(req: ChatRequest):
    """
    SSE streaming endpoint for both fixed insights and free-form Q&A.

    SSE events:
      event: phase   — progress updates (routing, generating_sql, executing, explaining)
      event: token   — individual text tokens from Claude
      event: done    — final event with full_text (and sql/view_key for Q&A)
      event: error   — error details
    """
    is_insight, report_key = detect_insight_mode(req.question)

    if is_insight and report_key:
        return _stream_insight(req, report_key)

    return _stream_qa(req)


def _sse(event: str, data: dict) -> str:
    """Format a single SSE event string."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _stream_insight(req: ChatRequest, report_key: str):
    """Stream fixed insight report via SSE."""
    logger.info("Streaming insight: report_key=%s", report_key)

    def event_generator():
        for chunk in generate_insights_stream(report_key):
            yield chunk

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _stream_qa(req: ChatRequest):
    """Stream free-form Q&A response via SSE. Steps 1-5 deterministic, step 6 streamed."""
    logger.info("Streaming Q&A for: %s", req.question[:80])

    def event_generator():
        # 1. Route to the correct view
        yield _sse("phase", {"phase": "routing", "message": "Identifying data source..."})
        try:
            view_key = detect_view(req.question)
            schema = get_view_schema(view_key)
        except (KeyError, ViewRoutingError) as e:
            logger.warning("View routing failed: %s", e)
            yield _sse("error", {"error": f"Could not determine data source: {e}"})
            return

        table_name = schema["table_name"]

        # 2. Get conversation history
        history = memory_store.get_history(req.session_id, limit=10)

        # 3. Generate SQL
        yield _sse("phase", {"phase": "generating_sql", "message": "Generating SQL query..."})
        try:
            sql = generate_sql(
                question=req.question,
                view_schema=schema,
                history=history,
            )
        except ClaudeRateLimitError:
            yield _sse("error", {"error": "AI service is busy — please retry in a moment"})
            return
        except ClaudeOverloadedError:
            yield _sse("error", {"error": "AI service is temporarily overloaded — please retry shortly"})
            return
        except ClaudeAuthError:
            yield _sse("error", {"error": "AI service authentication failed — contact support"})
            return
        except (ClaudeAPIError, SQLGenerationError) as e:
            logger.error("SQL generation failed: %s", e)
            yield _sse("error", {"error": f"AI SQL generation failed: {e}"})
            return

        # 4. Validate SQL safety
        try:
            validate_sql(sql=sql, allowed_table=table_name)
        except SQLValidationError as e:
            logger.warning("SQL validation failed: %s | SQL: %s", e, sql)
            yield _sse("error", {"error": f"Generated SQL failed safety check: {e}"})
            return

        # 5. Execute against Postgres
        yield _sse("phase", {"phase": "executing", "message": "Running query..."})
        try:
            columns, rows = run_query(sql)
        except DatabaseConnectionError:
            yield _sse("error", {"error": "Database is temporarily unavailable"})
            return
        except DatabaseQueryError as e:
            logger.error("Query execution failed: %s | SQL: %s", e, sql)
            yield _sse("error", {"error": f"Database query failed: {e}"})
            return

        # 6. Stream explanation from Claude
        yield _sse("phase", {"phase": "explaining", "message": "Generating explanation..."})
        yield _sse("meta", {"view_key": view_key, "sql": sql, "row_count": len(rows)})

        full_text_parts: list[str] = []
        try:
            for token in generate_explanation_stream(
                question=req.question,
                columns=columns,
                rows=rows,
                view_table=table_name,
                sql=sql,
            ):
                full_text_parts.append(token)
                yield _sse("token", {"token": token})
        except ClaudeRateLimitError:
            yield _sse("error", {"error": "AI service is busy — please retry in a moment"})
            return
        except ClaudeAPIError as e:
            logger.error("Explanation stream failed: %s", e)
            yield _sse("error", {"error": f"AI explanation failed: {e}"})
            return

        full_text = "".join(full_text_parts)

        # Store in conversation memory
        memory_store.append(
            req.session_id,
            {"role": "user", "content": req.question},
            limit=10,
        )
        memory_store.append(
            req.session_id,
            {"role": "assistant", "content": full_text},
            limit=10,
        )

        yield _sse("done", {
            "view_key": view_key,
            "sql": sql,
            "full_text": full_text,
        })

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _handle_insight(req: ChatRequest, report_key: str) -> ChatResponse:
    """Handle fixed insight report generation."""
    logger.info("Insight mode: report_key=%s", report_key)
    try:
        result = generate_insights(report_key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseConnectionError:
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable")
    except ClaudeRateLimitError:
        raise HTTPException(status_code=429, detail="AI service is busy — please retry in a moment")
    except ClaudeAPIError as e:
        logger.error("Insight Claude error: %s", e)
        raise HTTPException(status_code=502, detail=f"AI service error: {e}")
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error("Insight generation failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Insight generation failed: {e}")

    answer = result["formatted_report"]

    # Store in memory for context
    memory_store.append(
        req.session_id,
        {"role": "user", "content": req.question},
        limit=10,
    )
    memory_store.append(
        req.session_id,
        {"role": "assistant", "content": answer},
        limit=10,
    )

    return ChatResponse(
        view_key=report_key,
        sql="",
        answer=answer,
        is_insight=True,
    )


def _handle_qa(req: ChatRequest) -> ChatResponse:
    """Handle free-form Q&A via SQL generation."""
    # 1. Route to the correct view
    try:
        view_key = detect_view(req.question)
        schema = get_view_schema(view_key)
    except (KeyError, ViewRoutingError) as e:
        logger.warning("View routing failed: %s", e)
        raise HTTPException(status_code=400, detail=f"Could not determine data source: {e}")

    table_name = schema["table_name"]

    # 2. Get conversation history for context
    history = memory_store.get_history(req.session_id, limit=10)

    # 3. Generate SQL via Claude
    try:
        sql = generate_sql(
            question=req.question,
            view_schema=schema,
            history=history,
        )
    except ClaudeAuthError as e:
        logger.error("Claude auth error: %s", e)
        raise HTTPException(status_code=503, detail="AI service authentication failed — contact support")
    except ClaudeRateLimitError as e:
        logger.warning("Claude rate limited: %s", e)
        raise HTTPException(status_code=429, detail="AI service is busy — please retry in a moment")
    except ClaudeOverloadedError as e:
        logger.warning("Claude overloaded: %s", e)
        raise HTTPException(status_code=503, detail="AI service is temporarily overloaded — please retry shortly")
    except (ClaudeAPIError, SQLGenerationError) as e:
        logger.error("SQL generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI SQL generation failed: {e}")

    # 4. Validate SQL safety
    try:
        validate_sql(sql=sql, allowed_table=table_name)
    except SQLValidationError as e:
        logger.warning("SQL validation failed: %s | SQL: %s", e, sql)
        raise HTTPException(status_code=400, detail=f"Generated SQL failed safety check: {e}")

    # 5. Execute against Postgres
    try:
        columns, rows = run_query(sql)
    except DatabaseConnectionError as e:
        logger.error("DB connection failed: %s", e)
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable")
    except DatabaseQueryError as e:
        logger.error("Query execution failed: %s | SQL: %s", e, sql)
        raise HTTPException(status_code=400, detail=f"Database query failed: {e}")

    # 6. Generate business explanation via Claude
    try:
        answer = generate_explanation(
            question=req.question,
            columns=columns,
            rows=rows,
            view_table=table_name,
            sql=sql,
        )
    except ClaudeRateLimitError:
        raise HTTPException(status_code=429, detail="AI service is busy — please retry in a moment")
    except ClaudeAPIError as e:
        logger.error("Explanation generation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI explanation generation failed: {e}")

    # 7. Store in conversation memory
    memory_store.append(
        req.session_id,
        {"role": "user", "content": req.question},
        limit=10,
    )
    memory_store.append(
        req.session_id,
        {"role": "assistant", "content": answer},
        limit=10,
    )

    return ChatResponse(view_key=view_key, sql=sql, answer=answer)
