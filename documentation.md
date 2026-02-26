# BeastInsights AI — Product Documentation

This document describes the BeastInsights AI application: its features, product flow, SQL generation and validation, and what can and cannot be done. The application consists of a **backend** (FastAPI, Python) and a **frontend** (React, TypeScript) that together provide a natural-language analytics chat over PostgreSQL data and Claude AI.

---

## Overview

BeastInsights AI is an analytics assistant for e-commerce and subscription businesses. A user asks questions in plain English in a chat interface; the system routes the question to the appropriate data source, runs or generates queries against read-only PostgreSQL materialized views, and returns a business-focused answer. The backend exposes both synchronous and streaming chat endpoints; the frontend uses Server-Sent Events (SSE) to stream responses token-by-token and shows progress phases (e.g. routing, generating SQL, executing, explaining). Session conversation history is maintained per session (Redis or in-memory fallback) and is used as context for follow-up questions in the free-form Q&A path.

---

## Features

### Free-Form Q&A

Free-form Q&A allows arbitrary natural-language questions about the business data. The flow is:

1. The user submits a question (e.g. “What was the total revenue yesterday?” or “Which campaign had the highest approval rate last week?”).
2. The backend routes the question to a single materialized view using keyword-based view routing (no LLM call for routing).
3. Conversation history for the session (last 10 turns) is retrieved and passed to the SQL generator.
4. Claude generates exactly one PostgreSQL `SELECT` statement for the chosen view, constrained by table and column metadata and date-context hints.
5. The generated SQL is validated for safety (single SELECT, allowed table only, no DML/DDL, no semicolons, no CTEs, etc.).
6. The query is executed against PostgreSQL; results are capped (e.g. 500 rows) and serialized.
7. Claude produces a short business explanation from the question, the SQL, and the result set; this explanation is streamed to the client.
8. The exchange is stored in session memory for future context.

The frontend sends the question to `POST /chat/stream` with a `session_id` and displays streamed tokens, phase updates (routing, generating_sql, executing, explaining), and optional metadata (view key, SQL, row count). Errors (e.g. SQL generation failure, validation failure, database error, explanation failure) are returned as SSE `error` events and shown in the chat.

### Insight Reports

Insight reports are predefined, structured reports on a fixed set of topics. They are triggered when the question contains both an insight trigger phrase (e.g. “insight”, “insights”, “report”, “summary report”, “generate report”) and a topic keyword that maps to a report key (e.g. “order”, “mid health”, “alert”, “decline”, “ltv”, “hourly”, “cohort”).

Available report keys include: **order_summary**, **mid_health**, **alerts**, **decline_recovery**, **ltv**, **hourly_revenue**, **cohort**. Each report:

1. Fetches data via repository classes using fixed SQL (no user-supplied or LLM-generated SQL for the insight data).
2. Builds a structured JSON payload (counts, rates, top lists, trends, etc.) in Python.
3. Sends that payload to Claude with report-specific formatting instructions; Claude only formats the provided numbers into readable markdown and does not compute new metrics.
4. The formatted report is streamed to the client (or returned in full for the synchronous endpoint).

The frontend shows the same streaming UI and phase indicators (e.g. “Fetching data from database…”, “Generating report…”). Session memory is updated with the question and the report text for context.

### Error Handling

The backend uses a typed exception hierarchy rooted at `BeastInsightError`. Specific subtypes are mapped to HTTP status codes and user-facing messages:

- **ClaudeAuthError** (503): Invalid or missing Anthropic API key.
- **ClaudeRateLimitError** (429): Claude API rate limit; the client is instructed to retry later.
- **ClaudeOverloadedError** (503): Claude temporarily overloaded (e.g. 529).
- **ClaudeAPIError** (502): Other Claude API failures (e.g. network, non-2xx).
- **SQLGenerationError** (502): Claude did not return a valid SQL statement (e.g. non-SELECT or empty after cleaning).
- **SQLValidationError** (400): Generated SQL failed safety checks (forbidden keywords, wrong table, semicolons, CTEs, multiple statements, etc.).
- **DatabaseConnectionError** (503): Cannot connect to PostgreSQL.
- **DatabaseQueryError** (400): Query execution failed (syntax error, permission denied, undefined table/column, timeout, etc.).
- **ViewRoutingError** / **KeyError** (400): The question could not be mapped to a known view.

Global exception handlers in the FastAPI app catch unhandled `BeastInsightError` and map them to the appropriate status; any other exception returns 500 with a generic message and no internal details. In the streaming path, errors are sent as SSE `error` events so the UI can show them inline in the conversation.

---

## Product Flow

**Frontend**

- The React app presents a chat layout: a sidebar with quick actions (insight reports and sample Q&A questions), a main message list, a phase indicator during loading, and a chat input. Session ID is generated on the client and sent with each request; “New Chat” clears messages and creates a new session ID.
- On submit, the frontend calls `POST /chat/stream` with `{ session_id, question }`. It reads the response as an SSE stream and handles events: `phase` (progress), `meta` (view_key, sql, row_count), `token` (streamed text), `done` (final payload with full_text, view_key, sql), and `error` (error message). Streamed text is appended to the current assistant message; on `done` or `error`, the message is finalized. Non-streaming JSON responses (e.g. from `POST /chat/`) are also supported for compatibility.
- Messages support optional metadata (viewKey, sql, rowCount, isInsight, reportKey) and are rendered with markdown. The user can stop the stream via a stop button that aborts the fetch.

**Backend**

- The chat router first checks for insight mode (trigger phrase + report keyword). If matched, it runs the fixed insight pipeline (repository → builder → formatter) and returns or streams the report.
- Otherwise it runs the free-form Q&A pipeline: view routing → schema lookup → history retrieval → SQL generation (Claude) → SQL validation → query execution → explanation generation (Claude, streamed) → store in memory → send `done` (or send `error` at any failing step).
- Configuration (database, Claude API key, model, Redis URL, CORS, client_id) is read from environment via Pydantic settings. Tenant isolation is enforced by a schema registry that resolves view keys to table names of the form `reporting.<view_name>_<client_id>`.

---

## SQL Generation and Validation

**SQL Generation**

- The SQL generator receives the current question, the view schema (table name, description, column list with optional enum hints), and the last several conversation turns. It builds a system prompt that includes: strict rules (single SELECT only, no DML/DDL, no semicolons, only the given table and columns, date filters where relevant, LIMIT on non-aggregated queries, etc.), performance guidance (always date filter on large tables, avoid SELECT *), and date-context strings (e.g. today, yesterday, this week, last month). For `mid_summary`, special instructions require `month_year` to be handled via `TO_DATE(month_year, 'Mon YYYY')` rather than raw string comparison.
- The generator sends the prompt and messages to Claude and parses the response: it strips markdown code fences and trailing semicolons, and if multiple top-level SELECTs are present, it keeps the last one. If the result is empty or does not start with “select”, it raises `SQLGenerationError`.
- Claude is instructed to answer only the latest question and to output exactly one SELECT statement; conversation history is provided so follow-ups like “What about last month?” can be interpreted in context.

**SQL Validation**

- Before execution, the generated SQL is validated by a dedicated validator. It enforces: non-empty string; must start with `select`; no forbidden keywords (e.g. insert, update, delete, drop, alter, create, truncate, grant, revoke, execute, copy); no semicolons; no CTEs (WITH ...); no multiple top-level SELECTs; the query must reference the single allowed table (the one from the schema for the routed view); and no other tables in the `reporting` schema. On violation, it raises `SQLValidationError`, which is translated to 400 and a clear message to the client.

**Query Execution**

- The query executor runs the validated SQL against PostgreSQL via a singleton database manager. Each request uses a new connection (or pool); results are read and serialized (e.g. Decimal to float, date/datetime to ISO strings). The number of rows returned is capped (e.g. 500) as a safety limit. Database connection and query errors (syntax, permissions, undefined table/column, timeout) are caught and re-raised as `DatabaseConnectionError` or `DatabaseQueryError` with appropriate HTTP status.

---

## What Can Be Done

- **Ask natural-language questions** about revenue, approvals, chargebacks, refunds, alerts, MIDs/gateway health, declines and recovery, LTV, hourly revenue, and cohorts, within the scope of the registered materialized views (order_summary, mid_summary, alert_summary, alert_details, cohort_summary, decline_recovery, hourly_revenue, ltv_analysis, ltv_summary, cb_refund_alert).
- **Receive streamed answers** with progress phases (routing, generating SQL, executing, explaining) and optional metadata (view key, SQL, row count).
- **Use session context** so follow-up questions (e.g. “What about last week?”) can be answered using the same view and recent conversation history.
- **Request fixed insight reports** by asking for “insights” or “report” plus a topic (order summary, MID health, alerts, decline recovery, LTV, hourly revenue, cohort); the system runs predefined analytics and streams a formatted report.
- **See clear errors** when SQL generation fails, validation fails, the database is unreachable or returns an error, or the AI service is unavailable or rate-limited; errors are shown in the chat and mapped to appropriate HTTP status codes.
- **Start a new chat** to reset the conversation and session context.
- **Stop an in-progress stream** from the UI.
- **Use the synchronous endpoint** (`POST /chat/`) for non-streaming JSON responses when needed.
- **Run the backend without Redis**; session memory falls back to an in-memory store.

---

## What Cannot Be Done

- **Query arbitrary tables or ad-hoc SQL**: Only the views defined in the schema registry (and their columns) are allowed. The validator rejects queries that reference other tables or use forbidden SQL (DML, DDL, CTEs, multiple statements).
- **Use CTEs (WITH clauses)**: The validator explicitly disallows common table expressions.
- **Cross-table or multi-view queries**: Each question is routed to a single view; the generated SQL may only reference that view.
- **Bypass row caps**: Non-aggregated result sets are limited (e.g. 500 rows) and the generator is instructed to use LIMIT; the executor also caps returned rows.
- **Change data**: The database layer is read-only (SELECT only); the validator blocks INSERT, UPDATE, DELETE, and other mutating or administrative statements.
- **Request insight reports by arbitrary names**: Only the predefined report keys (order_summary, mid_health, alerts, decline_recovery, ltv, hourly_revenue, cohort) are supported; an unknown report key returns a 400 with the list of available keys.
- **Rely on view routing for questions that do not match keywords**: Routing is deterministic and keyword-based; if the question does not match any view (and is not an insight request), it defaults to order_summary. Ambiguous phrasing may route to a different view than intended.
- **Get explanations that use data not in the current result set**: Conversation history is implemented (Redis or in-memory) and is passed to the SQL generator for follow-up context. The **explanation** step, however, does not receive that history—it receives only the current question and the current query result. So the written answer is based solely on this turn’s data; the model is instructed not to invent numbers, though behavior may occasionally deviate.
- **Persist session across server restarts without Redis**: When Redis is not configured, session memory is in-memory only and is lost on restart.
- **Use the app without valid configuration**: PostgreSQL connection details, Anthropic API key, and (for correct tenant behavior) client_id must be set; missing or invalid configuration leads to connection or authentication errors.

---

## Summary

BeastInsights AI provides free-form Q&A and fixed insight reports over PostgreSQL materialized views, with strict SQL generation and validation, structured error handling, and a streaming chat UI. Supported capabilities are bounded by the registered views, the safety rules of the SQL validator, and the predefined insight report set; anything outside those bounds is either rejected or defaulted in a defined way.
