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
    InsightBuildError,
    SQLGenerationError,
    SQLValidationError,
    ViewRoutingError,
)
from app.redis_client import memory_store
from app.schemas.schema_metadata import get_view_schema
from app.services.aggregator import aggregate
from app.services.explanation_service import (
    generate_combined,
    generate_combined_stream,
    generate_combined_visualization_only,
    generate_explanation,
    generate_explanation_stream,
    generate_visualization_only,
)
from app.services.summarization_service import summarize_text
from app.services.insight_service import generate_insights, generate_insights_stream
from app.services.multi_query_runner import run_plan, run_plan_stream
from app.services.planner import Plan, plan_question
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
    # 1. Plan: single view, single insight, or multi
    # ---------------------------------------------------------------
    plan = plan_question(req.question)
    if len(plan.queries) == 1:
        q = plan.queries[0]
        if q.type == "insight" and q.report_key:
            return _handle_insight(req, q.report_key)
        if q.type == "view" and q.view:
            return _handle_qa(req)

    return _handle_multi(req, plan)


@router.post("/stream")
def chat_stream(req: ChatRequest):
    """
    SSE streaming endpoint for fixed insights, free-form Q&A, and multi-view.

    SSE events:
      event: phase   — progress (routing, planning, executing_query_N, aggregating, explaining)
      event: token   — text tokens from Claude
      event: visualization — chart payload
      event: done    — full_text (and view_key/sql for Q&A)
      event: error   — error details
    """
    is_insight, report_key = detect_insight_mode(req.question)

    if is_insight and report_key:
        return _stream_insight(req, report_key)

    plan = plan_question(req.question)
    if len(plan.queries) == 1:
        q = plan.queries[0]
        if q.type == "insight" and q.report_key:
            return _stream_insight(req, q.report_key)
        if q.type == "view" and q.view:
            return _stream_qa(req)

    return _stream_multi(req, plan)


def _sse(event: str, data: dict) -> str:
    """Format a single SSE event string."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _summarize_for_history(text: str) -> str:
    """Summarize assistant answer for history so context stays under token limits."""
    try:
        summarized = summarize_text(text)
    except (ClaudeRateLimitError, ClaudeOverloadedError, ClaudeAuthError, ClaudeAPIError) as e:
        logger.error("Summarization failed: %s", e)
        return text[:400]
    return summarized


def _stream_insight(req: ChatRequest, report_key: str):
    """Stream fixed insight report via SSE."""
    logger.info("Streaming insight: report_key=%s", report_key)

    def event_generator():
        full_text_to_save = None
        for chunk in generate_insights_stream(report_key):
            if "event: done" in chunk and "data:" in chunk:
                for part in chunk.split("\n\n"):
                    if "event: done" not in part:
                        continue
                    for line in part.split("\n"):
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                full_text_to_save = data.get("full_text") or ""
                                break
                            except (json.JSONDecodeError, TypeError):
                                pass
                    if full_text_to_save is not None:
                        break
            yield chunk
        if full_text_to_save is not None:
            summarized = _summarize_for_history(full_text_to_save)
            memory_store.append(
                req.session_id,
                {"role": "user", "content": req.question},
                limit=10,
            )
            memory_store.append(
                req.session_id,
                {"role": "assistant", "content": summarized},
                limit=10,
            )

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
        viz_emitted = 0
        try:
            for item in generate_explanation_stream(
                question=req.question,
                columns=columns,
                rows=rows,
                view_table=table_name,
                sql=sql,
            ):
                if isinstance(item, dict) and item.get("type") == "visualization":
                    yield _sse("visualization", item["payload"])
                    viz_emitted += 1
                else:
                    full_text_parts.append(item)
                    yield _sse("token", {"token": item})
        except ClaudeRateLimitError:
            yield _sse("error", {"error": "AI service is busy — please retry in a moment"})
            return
        except ClaudeAPIError as e:
            logger.error("Explanation stream failed: %s", e)
            yield _sse("error", {"error": f"AI explanation failed: {e}"})
            return

        full_text = "".join(full_text_parts)

        if viz_emitted == 0 and rows:
            for payload in generate_visualization_only(
                req.question, columns, rows, table_name, sql
            ):
                yield _sse("visualization", payload)

        # Store in conversation memory (summarized to keep context under token limits)
        memory_store.append(
            req.session_id,
            {"role": "user", "content": req.question},
            limit=10,
        )
        memory_store.append(
            req.session_id,
            {"role": "assistant", "content": _summarize_for_history(full_text)},
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

    # Store in memory for context (summarized to keep context under token limits)
    memory_store.append(
        req.session_id,
        {"role": "user", "content": req.question},
        limit=10,
    )
    memory_store.append(
        req.session_id,
        {"role": "assistant", "content": _summarize_for_history(answer)},
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

    # 7. Store in conversation memory (summarized to keep context under token limits)
    memory_store.append(
        req.session_id,
        {"role": "user", "content": req.question},
        limit=10,
    )
    memory_store.append(
        req.session_id,
        {"role": "assistant", "content": _summarize_for_history(answer)},
        limit=10,
    )

    return ChatResponse(view_key=view_key, sql=sql, answer=answer)


def _handle_multi(req: ChatRequest, plan: Plan) -> ChatResponse:
    """Handle multi-view/multi-intent: run plan, aggregate, combined explanation."""
    logger.info("Multi-view flow: %d queries", len(plan.queries))
    history = memory_store.get_history(req.session_id, limit=10)

    try:
        multi_result = run_plan(plan, req.question, history)
    except SQLGenerationError as e:
        raise HTTPException(status_code=502, detail=f"AI SQL generation failed: {e}")
    except SQLValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseConnectionError:
        raise HTTPException(status_code=503, detail="Database is temporarily unavailable")
    except DatabaseQueryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except InsightBuildError as e:
        raise HTTPException(status_code=502, detail=str(e))

    combined_data = aggregate(multi_result)

    try:
        answer = generate_combined(req.question, combined_data, history)
    except ClaudeRateLimitError:
        raise HTTPException(status_code=429, detail="AI service is busy — please retry in a moment")
    except ClaudeOverloadedError:
        raise HTTPException(status_code=503, detail="AI service is temporarily overloaded — please retry shortly")
    except ClaudeAuthError:
        raise HTTPException(status_code=503, detail="AI service authentication failed — contact support")
    except ClaudeAPIError as e:
        logger.error("Combined explanation failed: %s", e)
        raise HTTPException(status_code=502, detail=f"AI explanation failed: {e}")

    memory_store.append(
        req.session_id,
        {"role": "user", "content": req.question},
        limit=10,
    )
    memory_store.append(
        req.session_id,
        {"role": "assistant", "content": _summarize_for_history(answer)},
        limit=10,
    )

    return ChatResponse(view_key="multi", sql="", answer=answer, is_insight=False)


def _stream_multi(req: ChatRequest, plan: Plan):
    """Stream multi-view: planning → executing_query_N → aggregating → explaining → tokens/viz → done."""
    logger.info("Streaming multi-view: %d queries", len(plan.queries))

    def event_generator():
        yield _sse("phase", {"phase": "planning", "message": "Planning your question..."})
        history = memory_store.get_history(req.session_id, limit=10)

        multi_result = None
        try:
            for event_name, event_data in run_plan_stream(plan, req.question, history):
                if event_name == "result":
                    multi_result = event_data
                    break
                yield _sse("phase", event_data)
        except (SQLGenerationError, SQLValidationError, DatabaseConnectionError, DatabaseQueryError, InsightBuildError) as e:
            logger.exception("Multi-query execution failed: %s", e)
            yield _sse("error", {"error": str(e)})
            return

        if multi_result is None:
            yield _sse("error", {"error": "No result from multi-query run"})
            return

        yield _sse("phase", {"phase": "aggregating", "message": "Combining results..."})
        combined_data = aggregate(multi_result)

        yield _sse("phase", {"phase": "explaining", "message": "Generating explanation..."})
        view_keys = list(multi_result.view_results.keys())
        report_keys = list(multi_result.insight_results.keys())
        yield _sse("meta", {"view_keys": view_keys, "report_keys": report_keys})

        full_text_parts: list[str] = []
        viz_emitted = 0
        try:
            for item in generate_combined_stream(req.question, combined_data, history):
                if isinstance(item, dict) and item.get("type") == "visualization":
                    yield _sse("visualization", item["payload"])
                    viz_emitted += 1
                else:
                    full_text_parts.append(item)
                    yield _sse("token", {"token": item})
        except ClaudeRateLimitError:
            yield _sse("error", {"error": "AI service is busy — please retry in a moment"})
            return
        except ClaudeAPIError as e:
            logger.error("Combined explanation stream failed: %s", e)
            yield _sse("error", {"error": f"AI explanation failed: {e}"})
            return

        full_text = "".join(full_text_parts)

        if viz_emitted == 0 and (combined_data.get("views") or combined_data.get("insights")):
            yield _sse("phase", {"phase": "visualizing", "message": "Generating chart..."})
            for payload in generate_combined_visualization_only(
                req.question, combined_data, history
            ):
                yield _sse("visualization", payload)

        memory_store.append(
            req.session_id,
            {"role": "user", "content": req.question},
            limit=10,
        )
        memory_store.append(
            req.session_id,
            {"role": "assistant", "content": _summarize_for_history(full_text)},
            limit=10,
        )
        yield _sse("done", {
            "view_key": "multi",
            "view_keys": view_keys,
            "report_keys": report_keys,
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
