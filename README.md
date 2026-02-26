# BeastInsights AI

Natural-language analytics assistant for e-commerce/subscription businesses. Ask questions in plain English and get answers powered by Postgres data and Claude AI.

## Architecture

```
User Question
      │
      ▼
┌─────────────┐    SSE stream
│  React UI   │◄─────────────────────────────────────────────┐
│  (Chakra)   │─── POST /chat/stream ──┐                    │
└─────────────┘                        ▼                     │
                              ┌────────────────┐             │
                              │  FastAPI Router │             │
                              └───────┬────────┘             │
                                      │                      │
                         ┌────────────┼────────────┐         │
                         ▼            ▼            ▼         │
                   ┌──────────┐ ┌──────────┐ ┌──────────┐   │
                   │  View    │ │  Insight  │ │  Insight  │   │
                   │  Router  │ │ Detector  │ │ Service   │   │
                   └────┬─────┘ └──────────┘ └────┬──────┘   │
                        │                         │          │
              ┌─────────┼─────────┐         Fixed Insight    │
              ▼         ▼         ▼         Pipeline         │
        ┌──────┐  ┌──────────┐  ┌────────┐       │          │
        │Schema│  │   SQL    │  │  SQL   │       │          │
        │Regis.│  │Generator │  │Validat.│       │          │
        └──────┘  └────┬─────┘  └───┬────┘       │          │
                       │Claude      │             │          │
                       ▼            ▼             │          │
                 ┌──────────┐ ┌──────────┐        │          │
                 │  Query   │ │Explanat. │        │          │
                 │ Executor │ │ Service  │────────┼──── tokens
                 └────┬─────┘ └────┬─────┘        │          │
                      │  Postgres  │Claude        │          │
                      ▼            ▼              ▼          │
                 ┌──────────┐                ┌──────────┐    │
                 │   DB     │                │Formatter │────┘
                 │ Manager  │                │  (LLM)   │
                 └──────────┘                └──────────┘
```

### Two Query Modes

| Mode | Trigger | Flow |
|------|---------|------|
| **Free-form Q&A** | Any natural-language question | View Router → SQL Generator (Claude) → SQL Validator → Query Executor (Postgres) → Explanation (Claude) → streamed answer |
| **Fixed Insights** | Keywords like "insights", "report" + topic | Insight Detector → Repository (predefined SQL) → Analytics Builder → LLM Formatter (Claude) → streamed report |

### Key Design Decisions

- **SQL generation via LLM, not direct DB access** — Claude generates SELECT-only queries constrained to a single materialized view per question. A strict validator blocks DML, DDL, multi-statement, and cross-table access before execution.
- **Deterministic view routing** — keyword-based routing (no LLM call) maps questions to the correct materialized view, keeping latency low and costs down.
- **Fixed Insight pipeline** — pre-computed analytics (repository → insight builder → LLM formatter). Claude only *formats* pre-calculated numbers, never computes them, eliminating hallucinated metrics.
- **SSE streaming** — real-time token streaming from Claude to the UI via Server-Sent Events, with phase indicators (routing → SQL → executing → explaining).
- **Typed exception hierarchy** — `BeastInsightError` base with specific subtypes (`ClaudeRateLimitError`, `DatabaseConnectionError`, `SQLValidationError`, etc.) mapped to appropriate HTTP status codes.
- **Tenant isolation** — all table names include `client_id` suffix (`reporting.order_summary_10042`), enforced at the schema registry level.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Chakra UI v2, Vite, TypeScript |
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| AI | Anthropic Claude (claude-sonnet-4-20250514) |
| Database | PostgreSQL (read-only materialized views) |
| Session Memory | Redis (optional, in-memory fallback) |

## Project Structure

```
beastinsight_ai/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory + global error handlers
│   │   ├── config.py                # Pydantic settings (env-driven)
│   │   ├── db.py                    # Postgres connection manager (singleton)
│   │   ├── redis_client.py          # Session memory (Redis / in-memory)
│   │   ├── exceptions.py            # Typed exception hierarchy
│   │   ├── routers/
│   │   │   └── chat.py              # POST /chat/ and POST /chat/stream
│   │   ├── schemas/
│   │   │   └── schema_metadata.py   # View schema registry (10 views)
│   │   ├── services/
│   │   │   ├── claude_client.py      # Anthropic SDK wrapper
│   │   │   ├── sql_generator.py      # NL → SQL via Claude
│   │   │   ├── sql_validator.py      # SQL safety checks
│   │   │   ├── query_executor.py     # Postgres query runner
│   │   │   ├── explanation_service.py# Results → business explanation
│   │   │   ├── view_router.py        # Question → view key routing
│   │   │   ├── insight_service.py    # Fixed Insight orchestrator
│   │   │   └── insights/             # Per-report repositories + builders
│   │   │       ├── base.py
│   │   │       ├── formatter.py
│   │   │       ├── order_summary_repository.py
│   │   │       ├── mid_health_repository.py
│   │   │       ├── alert_repository.py
│   │   │       ├── decline_recovery_repository.py
│   │   │       ├── ltv_repository.py
│   │   │       ├── hourly_revenue_repository.py
│   │   │       └── cohort_repository.py
│   │   └── utils/
│   │       └── date_helpers.py
│   ├── requirements.txt
│   └── .env                          # Environment config (not committed)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── types.ts
│   │   ├── theme.ts
│   │   ├── hooks/
│   │   │   └── useChat.ts            # SSE streaming hook
│   │   └── components/
│   │       ├── ChatInput.tsx
│   │       ├── MessageBubble.tsx
│   │       ├── MarkdownRenderer.tsx
│   │       ├── PhaseIndicator.tsx
│   │       ├── WelcomeScreen.tsx
│   │       └── Sidebar.tsx
│   ├── package.json
│   └── .env
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL (read-only access to reporting views)
- Anthropic API key
- Redis (optional)

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt


```

**Required environment variables** (in `backend/.env`):

```env
APP_ENV=local
APP_NAME=beastinsights-ai
CORS_ORIGINS=http://localhost:5173

PG_HOST=db-host
PG_PORT=5432
PG_DATABASE=postgres
PG_USERNAME=username
PG_PASSWORD=password
PG_SSLMODE=require

CLIENT_ID=10042

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

REDIS_URL=redis://localhost:6379/0                      # leave empty for in-memory fallback
```

**Start the backend:**

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend

npm install
```
# Configure API URL
**Required environment variables** (in `frontend/.env`):

```env
VITE_API_URL=http://localhost:8000
```

```bash
npm run dev
```

The UI will be available at `http://localhost:5173`.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat/` | Synchronous chat (JSON response) |
| `POST` | `/chat/stream` | SSE streaming chat (token-by-token) |
| `GET` | `/health` | Health check |

### Request Body

```json
{
  "session_id": "local-dev",
  "question": "What was today's revenue?"
}
```

### SSE Event Types

| Event | Payload | Description |
|-------|---------|-------------|
| `phase` | `{ phase, message }` | Pipeline progress update |
| `meta` | `{ view_key, sql, row_count }` | Query metadata |
| `token` | `{ token }` | Streamed text token from Claude |
| `done` | `{ view_key, sql, full_text }` | Final response |
| `error` | `{ error }` | Error description |

## Error Handling

The backend uses a typed exception hierarchy rooted at `BeastInsightError`:

| Exception | HTTP Status | When |
|-----------|-------------|------|
| `ClaudeAuthError` | 503 | Invalid/missing Anthropic API key |
| `ClaudeRateLimitError` | 429 | Claude API rate limit hit |
| `ClaudeOverloadedError` | 503 | Claude temporarily overloaded |
| `ClaudeAPIError` | 502 | Other Claude API failures |
| `SQLGenerationError` | 502 | Claude returned non-SQL response |
| `SQLValidationError` | 400 | Generated SQL fails safety checks |
| `DatabaseConnectionError` | 503 | Cannot connect to Postgres |
| `DatabaseQueryError` | 400 | SQL syntax/permission/timeout errors |
| `ViewRoutingError` | 400 | Cannot determine data source |

Unhandled exceptions return 500 with a generic message (no internal details leaked).

## Available Data Views

| View Key | Description | ~Rows |
|----------|-------------|-------|
| `order_summary` | Revenue, approvals, cancels, chargebacks by day | 2.3M |
| `mid_summary` | MID/gateway health metrics by month | 952 |
| `alert_summary` | Alert aggregates by type/day | 145k |
| `alert_details` | Individual alert records | 173k |
| `cohort_summary` | Cohort retention through rebill cycles | 479k |
| `decline_recovery` | Decline reasons and recovery tracking | 1.38M |
| `hourly_revenue` | Today vs 7-day average by hour | 24 |
| `ltv_analysis` | Per-customer LTV across time buckets | 291k |
| `ltv_summary` | Aggregated LTV by cohort/period | 283k |
| `cb_refund_alert` | Chargeback/refund with alert correlation | 207k |

## Fixed Insight Reports

Trigger with keywords like *"give me order summary insights"* or *"generate MID health report"*:

- `order_summary` — Revenue, sales mix, WoW comparison, top performers, risk metrics
- `mid_health` — Health distribution, critical MIDs, capacity alerts, decline spikes
- `alerts` — Volume trends, alert mix, effectiveness rate, top gateways
- `decline_recovery` — Recovery rates, top decline reasons, revenue impact
- `ltv` — LTV milestones, net vs gross, cohort comparison
- `hourly_revenue` — Today vs average, peak hours, anomaly detection
- `cohort` — Retention by cycle, revenue per customer, best/worst months
