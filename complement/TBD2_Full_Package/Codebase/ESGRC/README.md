# ESGRC - Integrated ESG, Risk & Compliance Platform

> **A production-grade REST API for managing Environmental, Social & Governance (ESG) metrics, Risk registers, and Compliance frameworks - with JWT multi-tenancy, an autonomous AI agent, and a two-LLM analysis pipeline.**

---

## Table of Contents

1. [What Is This?](#1-what-is-this)
2. [For Non-Technical Stakeholders](#2-for-non-technical-stakeholders)
3. [Architecture Overview](#3-architecture-overview)
4. [What Is Built - All 7 Phases](#4-what-is-built)
5. [The Data Model](#5-the-data-model)
6. [Every File Explained](#6-every-file-explained)
7. [All 48 API Endpoints](#7-all-48-api-endpoints)
8. [How to Run It](#8-how-to-run-it)
9. [Running Tests](#9-running-tests)
10. [Environment Variables](#10-environment-variables)
11. [Database Migrations](#11-database-migrations)
12. [Security Model](#12-security-model)
13. [The AI Agent](#13-the-ai-agent)
14. [Pipeline Integration](#14-pipeline-integration)
15. [How to Push to GitHub](#15-how-to-push-to-github)
16. [Technology Stack](#16-technology-stack)

---

## 1. What Is This?

ESGRC is a production-ready REST API that gives organisations a single platform to:

- **Track ESG metrics** - submit Environmental, Social, and Governance data points by period, auto-score them against configurable benchmarks (0-100), and retrieve them with full timestamps.
- **Manage a Risk Register** - log risks with likelihood and impact scores, track mitigation progress, get a live 5x5 risk heatmap.
- **Track Compliance** - map obligations to frameworks (GRI, ISO 14001, TCFD, SOC 2, etc.), mark requirements as compliant/non-compliant/partial, get instant compliance-rate summaries.
- **Authenticate securely** - multi-tenant JWT authentication with role-based access control (Admin, Analyst, Viewer). Each organisation only ever sees its own data.
- **Run an AI agent** - an autonomous two-LLM agent scores metrics, classifies compliance requirements, and escalates risks every night. Produces a structured L1_ESRC_Risk_Assessment JSON report aligned to the Golden Response specification.
- **Connect to the ML pipeline** - bulk import from CSV, bulk export to CSV, per-sub-module averages for all 14 ESGRC sub-modules, and a single-call org snapshot for the LLM context window.

---

## 2. For Non-Technical Stakeholders

### The problem this solves

Your organisation reports on ESG performance, manages risks, and tracks compliance obligations. These probably live in separate spreadsheets or systems that do not talk to each other. This platform puts all three in one place with:

- **One login** that works across everything
- **Automatic calculations** - compliance rates, risk scores, and ESG scores computed instantly, not by hand
- **An AI that works overnight** - every morning the system has already scored your latest ESG data, flagged overdue compliance requirements, and escalated critical risks
- **Role-based access** - Viewers read everything; Analysts submit and update data; Admins manage the team
- **A complete audit trail** - every record carries a creation date and last-modified timestamp

### What the AI agent does for you

Every day at 2 AM (configurable), the system wakes up and for every client organisation:

1. Reads all ESG data, risks, and compliance requirements
2. Scores any ESG metrics that have not been scored yet - calculates a 0-100 performance number automatically
3. Reviews compliance requirements that are overdue - reads the evidence and classifies each as Compliant, Partial, or Non-Compliant
4. Escalates critical risks - any open risk that is both high-severity and overdue gets escalated so it appears prominently
5. Produces a structured L1_ESRC_Risk_Assessment report with module-level risk score, confidence, trend direction, low-performing sub-modules, and specific recommendations

Compliance checks run on a 15-day cycle - daily compliance alerts cause noise; 15 days matches real-world review cycles.

### Who can do what

| Role | Permissions |
|---|---|
| **Viewer** | Read all ESG data, risks, compliance status, scores, heatmaps, summaries |
| **Analyst** | Everything a Viewer can do, plus submit ESG data, log risks, update compliance status |
| **Admin** | Everything an Analyst can do, plus manage users, set benchmarks, create frameworks |

---

## 3. Architecture Overview

```
CLIENTS
  Frontend App      ML Pipeline Scripts     AI/ML Engineer
      |                    |                      |
      | REST + JWT          | GET /esg/export       | POST /esg/import
      |                    |                      |
ESGRC FASTAPI BACKEND  (this repo)
  Auth Layer:       JWT + bcrypt + refresh rotation
  Business Layer:   ESG, Risk, Compliance CRUD
  Analytics Layer:  Scoring, Heatmap, Summary, Dashboard, Snapshot
  Agent Layer:      APScheduler + Rule tasks + LLM agent
      |
  SQLAlchemy 2.x
      |
  DATABASE
    SQLite (dev)   PostgreSQL (production)
    9 tables, 6 Alembic migrations

AI AGENT LAYER
  APScheduler ── Daily (02:00 UTC):       score metrics + escalate risks
              └─ Every 15 days:           flag overdue compliance

  LLM Agent ─── Orchestrator (Claude Sonnet) reads org snapshot
              │  delegates to Specialist (Claude Haiku) for:
              │    ESG scoring, compliance classification, risk assessment
              └─ writes L1_ESRC_Risk_Assessment JSON to AgentRunLog
```

---

## 4. What Is Built

### All 7 phases - 207 tests, zero failures

| Phase | What was built | Tests |
|---|---|---|
| **1 - Foundation** | Full CRUD, 9 database tables, Pydantic v2 schemas, SQLAlchemy 2.x ORM, pagination, error handling | 16 |
| **2 - Analytics** | ESG scoring engine (0-100), compliance rate summary, 5x5 risk heatmap, Alembic migrations | 55 |
| **3 - Auth and Multi-Tenancy** | JWT access + refresh tokens, bcrypt passwords, organisations, roles | 29 |
| **4 - Org Data Isolation** | Every ESG/Risk/Compliance record scoped to org_id. Cross-org access returns 404 | 16 |
| **5 - Batch Agent** | APScheduler with SQLAlchemyJobStore. Daily ESG/Risk job + 15-day Compliance job. Audit trail | 19 |
| **6 - LLM Agent** | Two-LLM orchestrator-specialist (Sonnet + Haiku). Tool use loop. L1_ESRC_Risk_Assessment output | included in phase 5 tests |
| **7 - Pipeline Integration** | metric_code, bulk import, CSV export, org snapshot, ESG dashboard, bulk requirement update, coverage tests | 72 |
| **Total** | | **207 tests, 0 failures** |

---

## 5. The Data Model

Nine database tables. Every table has created_at and updated_at timestamps (UTC). Foreign keys cascade on delete.

### Organisations
The tenant boundary. Every piece of data belongs to one organisation.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| name | string(200) | Unique |
| slug | string(100) | URL-safe, unique, e.g. acme-corp |
| active | bool | Inactive = all users blocked |

### Users
One user belongs to one organisation with one role.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| organisation_id | FK to organisations | |
| email | string(320) | Unique, normalised lowercase |
| full_name | string(200) | |
| hashed_password | string(200) | bcrypt 12 rounds - never plaintext |
| role | enum | admin / analyst / viewer |
| is_active | bool | |
| hashed_refresh_token | string(200) | SHA-256 hash. NULL when logged out |

### ESG Categories
Reusable measurement categories e.g. "Carbon Emissions".

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| org_id | FK to organisations | Org-scoped |
| name | string(200) | Unique within org |
| metric_code | string(20) | Pipeline code e.g. ESU10102. Globally unique. Used for bulk import/export |
| pillar | enum | environmental / social / governance |
| description | text | Optional |
| unit | string(50) | e.g. tonnes CO2, % |

### ESG Metrics
Individual data points submitted for a category and period.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| category_id | FK to esg_categories | Cascades on delete |
| organisation | string(200) | Reporting entity name |
| value | float | Raw measured value |
| period | string(20) | YYYY or YYYY-QN, regex validated |
| notes | text | Optional |
| score | float nullable | 0-100, computed by scoring engine |

### ESG Score Benchmarks
One benchmark per category. Defines the scale for 0-100 scoring.

| Column | Type | Notes |
|---|---|---|
| category_id | FK unique | One benchmark per category |
| target_value | float | Best case = score 100 |
| baseline_value | float | Worst case = score 0 |
| direction | enum | lower_is_better or higher_is_better |

Scoring formula:
- lower_is_better: score = clamp((baseline - value) / (baseline - target) x 100, 0, 100)
- higher_is_better: score = clamp((value - baseline) / (target - baseline) x 100, 0, 100)

### Risks
Risk register entries.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| org_id | FK to organisations | Org-scoped |
| title | string(300) | |
| level | enum | low / medium / high / critical |
| status | enum | open / in_progress / mitigated / closed |
| likelihood | int 1-5 | |
| impact | int 1-5 | |
| risk_score | computed | likelihood x impact (1-25), calculated in Python |
| due_date | timestamp | Optional |

Critical zone: risks where likelihood >= 4 AND impact >= 4 (score >= 16).

### Compliance Frameworks
A named standard e.g. GRI Standards 2021, ISO 14001:2015.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| org_id | FK to organisations | Org-scoped |
| name | string(200) | Unique within org |
| version | string(50) | e.g. 2021 |
| active | bool | Inactive excluded from global summary |

### Compliance Requirements
Individual obligations within a framework.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| framework_id | FK to compliance_frameworks | Cascades on delete |
| code | string(50) | e.g. GRI 302-1 |
| title | string(300) | |
| status | enum | compliant / non_compliant / partial / not_assessed |
| evidence | text | Supporting evidence reference |
| review_date | timestamp | Used by compliance batch to flag overdue items |

### Agent Run Logs
Audit trail for every agent run.

| Column | Type | Notes |
|---|---|---|
| id | int PK | |
| status | enum | running / success / partial / failed |
| started_at / finished_at | timestamp | |
| orgs_processed | int | |
| metrics_scored | int | |
| requirements_flagged | int | |
| risks_escalated | int | |
| details | text JSON | Per-org breakdown. LLM runs store full L1_ESRC_Risk_Assessment here |
| error_message | text | Populated on FAILED status |

---

## 6. Every File Explained

```
ESGRC/
|
+-- main.py                       Application entry point
+-- requirements.txt              All Python dependencies, pinned
+-- .env.example                  Copy to .env and fill in before starting
+-- .gitignore
|
+-- alembic.ini                   Alembic configuration
+-- alembic/
|   +-- env.py                    Migration environment
|   +-- versions/
|       +-- 20260430_initial_schema.py
|       +-- 20260501_add_organisations_and_users.py
|       +-- 20260502_add_org_scoping_to_business_tables.py
|       +-- 20260503_add_per_org_unique_constraints.py
|       +-- 20260504_add_agent_run_logs.py
|       +-- 20260507_add_metric_code_to_esg_categories.py
|
+-- app/
|   +-- config.py                 All settings loaded from .env via pydantic-settings
|   +-- database.py               SQLAlchemy engine, session factory, base class
|   |
|   +-- models/
|   |   +-- models.py             All 9 ORM models + 7 enums
|   |
|   +-- schemas/
|   |   +-- schemas.py            All Pydantic v2 request/response schemas
|   |
|   +-- crud/
|   |   +-- crud.py               Business data layer: ESG, Risk, Compliance, Agent
|   |   +-- auth_crud.py          Auth data layer: Org, User, tokens
|   |
|   +-- services/
|   |   +-- auth.py               Pure functions: bcrypt, JWT, token generation
|   |   +-- scoring.py            Pure function: compute_score(value, benchmark)
|   |
|   +-- dependencies/
|   |   +-- auth.py               FastAPI Depends: get_current_user, require_role, get_current_org
|   |
|   +-- agent/
|   |   +-- __init__.py
|   |   +-- tasks.py              Rule-based tasks: score_unscored_metrics, flag_overdue_requirements, escalate_critical_risks
|   |   +-- runner.py             run_batch, run_llm_batch, run_batch_esg_risk, run_batch_compliance
|   |   +-- scheduler.py          APScheduler: two jobs (daily ESG/Risk + 15-day Compliance)
|   |   +-- tools.py              Read/write tool functions the LLM agent calls
|   |   +-- llm_agent.py          Two-LLM orchestrator-specialist loop
|   |   +-- prompts.py            System prompts aligned to Golden Response spec
|   |
|   +-- routers/
|       +-- auth.py               /auth/...
|       +-- esg.py                /esg/... categories, metrics, dashboard, bulk import, CSV export
|       +-- risk.py               /risks/... register, heatmap
|       +-- compliance.py         /compliance/... frameworks, requirements, bulk update, summaries
|       +-- scoring.py            /esg/benchmarks/... and /esg/metrics/{id}/score
|       +-- agent.py              /agent/... run, llm-run, status, logs
|       +-- org.py                /org/snapshot
|
+-- test/
    +-- conftest.py               pytest fixtures, in-memory SQLite, SAVEPOINT isolation
    +-- test_esg.py
    +-- test_risk.py
    +-- test_compliance.py
    +-- test_scoring.py
    +-- test_compliance_summary.py
    +-- test_risk_heatmap.py
    +-- test_auth.py
    +-- test_org_isolation.py
    +-- test_agent.py
    +-- test_phase7.py
    +-- test_missing_coverage.py
```

### Key design decisions

**main.py** - boots FastAPI, configures CORS, structured JSON error handler (never exposes raw tracebacks), lifespan manager starts/stops the APScheduler and creates the DB schema on first boot.

**app/config.py** - single source of truth for all config. Reads from .env. Cached with @lru_cache - read exactly once per process.

**app/crud/crud.py** - uses select() + scalars() throughout (never legacy db.query()). All list queries have ORDER BY + LIMIT/OFFSET. IntegrityError on unique violations is re-raised as ValueError so routers return 409. The heatmap and compliance summary use aggregated SQL - single queries, never Python-side counting.

**app/services/scoring.py** - pure function compute_score(value, benchmark). No FastAPI, no DB. Returns 0.0 for degenerate benchmarks (target == baseline) instead of raising - the agent must not crash on bad data.

**app/dependencies/auth.py** - get_current_user decodes the JWT and asserts typ=access (prevents refresh tokens being used as access tokens). Role is read from the JWT claim, not re-fetched from the DB on every request - a role change takes effect on next login.

**app/agent/scheduler.py** - two separate APScheduler jobs with SQLAlchemyJobStore. Jobs persist across restarts. coalesce=True + max_instances=1 - never two copies running simultaneously.

**app/agent/llm_agent.py** - Sonnet reads the org snapshot and decides what to act on. Haiku classifies/scores each item. response.content serialised via .model_dump() before adding to message history. Hard stop at MAX_ITERATIONS=20.

**app/agent/prompts.py** - orchestrator system prompt specifies the exact L1_ESRC_Risk_Assessment JSON output format aligned to Golden_Response_ESGRC_Module_1_0.pdf.

**alembic/env.py** - DATABASE_URL comes from settings, never from alembic.ini. render_as_batch=True enables SQLite ALTER TABLE so the same migration files run on both SQLite (dev) and PostgreSQL (production).

---

## 7. All 48 API Endpoints

All endpoints return JSON. Errors use {"detail": "message"}. All timestamps are UTC ISO 8601.

### Authentication (/auth)

| Method | Path | Role | Description |
|---|---|---|---|
| POST | /auth/organisations | Public | Create a new tenant organisation |
| POST | /auth/register | Public | Register a user in an org |
| POST | /auth/login | Public | Get access + refresh tokens |
| POST | /auth/refresh | Public | Rotate token pair |
| POST | /auth/logout | Any | Invalidate refresh token |
| GET | /auth/me | Any | Current user profile |
| GET | /auth/users | Admin | List users in caller's org |
| PATCH | /auth/users/{id}/role | Admin | Change a user's role |
| PATCH | /auth/users/{id}/deactivate | Admin | Deactivate a user |

### ESG (/esg)

| Method | Path | Description |
|---|---|---|
| GET | /esg/dashboard | Latest score per category + org-level aggregates in one call |
| POST | /esg/import | Bulk import metric rows from CSV/JSON (mapped by metric_code) |
| GET | /esg/export | Export metrics as pipeline-compatible CSV (columns = metric codes) |
| POST | /esg/categories | Create a category |
| GET | /esg/categories | List categories (filter by pillar) |
| GET | /esg/categories/{id} | Get one category |
| PATCH | /esg/categories/{id} | Update (including metric_code) |
| DELETE | /esg/categories/{id} | Delete (cascades to metrics + benchmark) |
| GET | /esg/categories/{id}/benchmark | Get scoring benchmark |
| POST | /esg/benchmarks | Create or replace a benchmark |
| GET | /esg/benchmarks/{id} | Get a benchmark |
| PATCH | /esg/benchmarks/{id} | Update a benchmark |
| POST | /esg/metrics | Submit one metric data point |
| GET | /esg/metrics | List metrics (filter by org, category, period) |
| GET | /esg/metrics/{id} | Get one metric |
| PATCH | /esg/metrics/{id} | Update a metric |
| POST | /esg/metrics/{id}/score | Compute and persist score |

### Risk (/risks)

| Method | Path | Description |
|---|---|---|
| POST | /risks | Create a risk |
| GET | /risks | List risks (filter by status, level) |
| GET | /risks/heatmap | 5x5 heatmap (filter by status, category) |
| GET | /risks/{id} | Get one risk |
| PATCH | /risks/{id} | Update a risk |
| DELETE | /risks/{id} | Delete a risk |

### Compliance (/compliance)

| Method | Path | Description |
|---|---|---|
| POST | /compliance/frameworks | Create a framework |
| GET | /compliance/frameworks | List frameworks |
| GET | /compliance/frameworks/{id} | Get one framework |
| PATCH | /compliance/frameworks/{id} | Update |
| DELETE | /compliance/frameworks/{id} | Delete (cascades to requirements) |
| GET | /compliance/frameworks/{id}/summary | Counts + compliance rate for one framework |
| GET | /compliance/summary | Global summary across all active frameworks |
| POST | /compliance/requirements | Create a requirement |
| GET | /compliance/requirements | List (filter by framework, status) |
| PATCH | /compliance/requirements/bulk | Bulk update statuses - one call for N requirements |
| GET | /compliance/requirements/{id} | Get one requirement |
| PATCH | /compliance/requirements/{id} | Update one requirement |

### Organisation (/org)

| Method | Path | Description |
|---|---|---|
| GET | /org/snapshot | Full snapshot: ESG summary, risk summary, compliance rate, all 14 sub-module averages |

### Agent (/agent)

| Method | Path | Role | Description |
|---|---|---|---|
| POST | /agent/run | Admin | Trigger rule-based batch now |
| POST | /agent/llm-run | Admin | Trigger LLM agent now |
| GET | /agent/runs | Admin | Paginated run history |
| GET | /agent/runs/{id} | Admin | Single run with full L1_ESRC_Risk_Assessment JSON |
| GET | /agent/status | Admin | Scheduler status + next run times |

### System

| Method | Path | Description |
|---|---|---|
| GET | / | Liveness check |
| GET | /health | Health probe |
| GET | /docs | Swagger UI |
| GET | /redoc | ReDoc documentation |

---

## 8. How to Run It

### Prerequisites
- Python 3.12+

### Step 1 - Clone

```bash
git clone https://github.com/AI-ERMT-TBD-02/ESGRC.git
cd ESGRC
```

### Step 2 - Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\activate           # Windows
```

### Step 3 - Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 - Configure environment

```bash
cp .env.example .env
```

Set SECRET_KEY - required before any startup:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
# Paste the output into .env as SECRET_KEY=...
```

### Step 5 - Start the server

```bash
uvicorn main:app --reload
```

The app automatically creates the database schema on first boot.

### Step 6 - Open the interactive docs

- Swagger UI (try every endpoint): http://127.0.0.1:8000/docs
- ReDoc (readable reference): http://127.0.0.1:8000/redoc

### Step 7 - First API calls

```bash
# Create an organisation
curl -X POST http://localhost:8000/auth/organisations \
  -H "Content-Type: application/json" \
  -d '{"name": "My Organisation", "slug": "my-org"}'

# Register a user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "full_name": "Your Name", "password": "SecurePass123!", "organisation_slug": "my-org"}'

# Log in
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com", "password": "SecurePass123!"}'

# Use the access_token in all subsequent calls
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <your_access_token>"
```

### Production - PostgreSQL

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/esgrc
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

```bash
alembic upgrade head
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 9. Running Tests

```bash
# Run all 207 tests
pytest test/ -v

# Quick pass/fail
pytest test/ -q

# Run one module
pytest test/test_auth.py -v
pytest test/test_org_isolation.py -v
pytest test/test_phase7.py -v
```

Tests use an in-memory SQLite database. Each test runs inside a SAVEPOINT that rolls back after the test - fully isolated, no cleanup needed, any order.

### Test coverage by file

| File | Tests | What it covers |
|---|---|---|
| test_esg.py | 6 | Category and metric CRUD, cascade delete, period validation |
| test_risk.py | 5 | Risk CRUD, validation |
| test_compliance.py | 5 | Frameworks, requirements, cascade |
| test_scoring.py | 29 | Scoring algorithm, benchmarks, degenerate cases |
| test_compliance_summary.py | 12 | Per-framework and global summary, edge cases |
| test_risk_heatmap.py | 20 | Heatmap structure, all filters, critical zone |
| test_auth.py | 22 | Full auth flow, tokens, roles |
| test_org_isolation.py | 16 | Cross-org access returns 404 for every domain |
| test_agent.py | 19 | Scheduler, batch runner, endpoints |
| test_phase7.py | 58 | Bulk import, CSV export, snapshot, dashboard, bulk update, prompt alignment |
| test_missing_coverage.py | 17 | Framework summary, role update, deactivate, llm-run auth |
| **Total** | **207** | **0 failures** |

---

## 10. Environment Variables

| Variable | Default | Required | Description |
|---|---|---|---|
| APP_NAME | ESGRC API | No | Shown in docs |
| APP_VERSION | 1.0.0 | No | |
| DEBUG | false | No | true enables DEBUG logging |
| DATABASE_URL | sqlite:///./esgrc.db | Yes | Connection string |
| DB_POOL_SIZE | 5 | No | Postgres only |
| DB_MAX_OVERFLOW | 10 | No | Postgres only |
| SECRET_KEY | - | YES | Generate with: python -c "import secrets; print(secrets.token_hex(32))" |
| JWT_ALGORITHM | HS256 | No | |
| ACCESS_TOKEN_EXPIRE_MINUTES | 30 | No | |
| REFRESH_TOKEN_EXPIRE_DAYS | 7 | No | |
| ALLOWED_ORIGINS | "" | No | Comma-separated CORS origins. Empty = all (dev only) |
| AGENT_ENABLED | true | No | Set false in test/staging |
| AGENT_HOUR | 2 | No | Hour UTC the daily job runs |
| AGENT_MINUTE | 0 | No | Minute the daily job runs |
| AGENT_TIMEZONE | UTC | No | Any pytz timezone e.g. Europe/London |
| COMPLIANCE_CHECK_DAYS | 15 | No | Days between compliance re-checks |
| ANTHROPIC_API_KEY | - | LLM only | Get from console.anthropic.com |
| LLM_AGENT_ENABLED | false | No | Set true once API key is configured |
| ORCHESTRATOR_MODEL | claude-sonnet-4-20250514 | No | Reasoning model |
| SPECIALIST_MODEL | claude-haiku-4-5-20251001 | No | Fast classification model |

---

## 11. Database Migrations

```bash
# Apply all migrations (always safe to run)
alembic upgrade head

# Check current state
alembic current

# View history
alembic history

# Roll back one step
alembic downgrade -1

# Generate a migration after changing models
alembic revision --autogenerate -m "describe_what_changed"
```

### Migration history

| Migration | What it adds |
|---|---|
| 1b087c059d7e initial_schema | All 6 business tables |
| 0c004981e01c add_organisations_and_users | Auth tables + org_id FKs |
| e2a54ef84063 add_org_scoping | org_id FK on categories, risks, frameworks |
| 07256f6eed55 add_per_org_unique_constraints | Composite unique (org_id, name) |
| 737db0c70862 add_agent_run_logs | agent_run_logs table |
| af5072b9c5f4 add_metric_code | metric_code column + unique index on esg_categories |

---

## 12. Security Model

### Tokens

- **Access tokens**: HS256 JWTs, 30-minute lifetime. Carry user_id, org_id, role, and typ=access (prevents refresh tokens being used as access tokens).
- **Refresh tokens**: Opaque random bytes, stored as SHA-256 hashes. Rotation on every use - each token can only be used once. A second use returns 401 (replay attack detection).
- **Passwords**: bcrypt at cost factor 12. Never stored or logged in plaintext.

### Authorisation

- Role hierarchy: viewer < analyst < admin
- Roles are read from the JWT claim, not the database on every request - a role change takes effect on next login
- All business data is scoped to org_id - cross-org IDs return 404, not 403 (existence not revealed to other tenants)

### Frontend integration notes

```javascript
// Store access_token in memory (NOT localStorage)
// Store refresh_token in httpOnly cookie
// Every protected call:
headers: { "Authorization": `Bearer ${accessToken}` }
// When token expires (30 min), call POST /auth/refresh
// On logout, call POST /auth/logout
```

---

## 13. The AI Agent

### Two scheduled jobs

| Job | Schedule | What it does |
|---|---|---|
| esgrc_daily_batch | Daily at AGENT_HOUR:AGENT_MINUTE UTC | Score unscored metrics, escalate critical risks |
| esgrc_compliance_batch | Every COMPLIANCE_CHECK_DAYS days | Flag overdue requirements for re-review |

### Two run modes

```bash
# Rule-based (no API key needed)
POST /agent/run

# LLM agent (requires ANTHROPIC_API_KEY)
POST /agent/llm-run
```

### LLM agent flow

```
Orchestrator (Claude Sonnet)
  1. read_org_snapshot()          full picture in one call
  2. read_unscored_metrics()      find metrics to score
  3. delegate_scoring(...)        Specialist (Haiku) computes score, writes to DB
  4. read_overdue_requirements()  find requirements to classify
  5. delegate_classification(...) Specialist classifies, writes to DB
  6. read_open_risks()            find risks to assess
  7. delegate_risk_assessment(...) Specialist assesses, writes to DB
  8. write_findings({...})        L1_ESRC_Risk_Assessment JSON saved to AgentRunLog
```

### Retrieving agent results

```bash
GET /agent/runs          # list all runs
GET /agent/runs/{id}     # full L1_ESRC_Risk_Assessment per org in details field
```

### Service account setup for ML/AI engineer

```bash
POST /auth/register
{
  "email": "ai-service@yourorg.com",
  "full_name": "AI Service Account",
  "password": "<strong random password>",
  "organisation_slug": "your-org"
}
# Analyst role: read + write, cannot manage users.
# Implement token refresh before 30-minute expiry.
```

---

## 14. Pipeline Integration

This API connects directly to the existing ESGRC data pipeline (Repo-01, Repo-04, AI_ERMT).

### Data flow

```
PIPELINE CSV
    |
    v
POST /esg/import       bulk import by metric_code
    |
DATABASE
    |
    +-- GET /esg/export         pipeline-compatible CSV for ML scripts
    +-- GET /org/snapshot       LLM agent context window feed
    +-- GET /esg/dashboard      frontend main screen
```

### Setting up metric codes

For bulk import to work, each category needs a metric_code matching the pipeline JSON (esgrc_performance_json_file.json):

```bash
PATCH /esg/categories/{id}
{"metric_code": "ESU10102"}
```

### Bulk import

```bash
POST /esg/import
[
  {"metric_code": "ESU10102", "value": 342.0, "period": "2024-Q1", "organisation": "Acme Corp"},
  {"metric_code": "SSU10101", "value": 0.02,  "period": "2024-Q1", "organisation": "Acme Corp"}
]
# Returns: {"imported": 2, "skipped": 0, "errors": []}
```

### Export for pipeline scripts

```bash
GET /esg/export
GET /esg/export?period=2024-Q1
# Returns CSV with columns: period, organisation, ESU10102, SSU10101, ...
# Matches input_metric_values_esgrc.csv format used by ML pipeline scripts
```

### The 14 sub-modules

The metric_code prefix maps to sub-modules automatically in /org/snapshot:

| Prefix | Sub-module |
|---|---|
| ESU | Environmental and Sustainability Unit |
| SSU | Social and Safety Unit |
| CSU | Cybersecurity Unit |
| GNT | General Notes and Training |
| CGS | Corporate Governance Systems |
| GRC | Governance, Risk and Compliance |
| ERM | Enterprise Risk Management |
| AUD | Audit |
| POL | Policy Management |
| REG | Regulatory Compliance |
| ETI | Ethics and Integrity |
| CGV | Corporate Governance |
| IGV | Information Governance |
| CPI | Corporate Social Programs |

---

## 15. How to Push to GitHub

### First time setup

```bash
cd ESGRC

# Initialise git if not done
git init

# Add the remote
git remote add origin https://github.com/AI-ERMT-TBD-02/ESGRC.git

# Verify
git remote -v
```

### Every time you push changes

```bash
# See what changed
git status

# Stage all changes
git add .

# Commit with a message
git commit -m "Phase 7: bulk import, CSV export, dashboard, snapshot, LLM output, 207 tests"

# Push
git push origin main

# First push ever:
git push -u origin main
```

### IMPORTANT - what must NOT be committed

Make sure these are in .gitignore:

```
.env                # contains SECRET_KEY and ANTHROPIC_API_KEY
esgrc.db            # development database
.venv/              # virtual environment
__pycache__/
*.pyc
```

If .env was accidentally committed, rotate SECRET_KEY and ANTHROPIC_API_KEY immediately.

### Set your Git identity if needed

```bash
git config --global user.email "danish@yourcompany.com"
git config --global user.name "Danish"
```

### If remote already has commits

```bash
git pull origin main --rebase
git push origin main
```

---

## 16. Technology Stack

| Layer | Technology | Version |
|---|---|---|
| API framework | FastAPI | 0.115.0 |
| Web server | Uvicorn | 0.30.6 |
| ORM | SQLAlchemy | 2.0.36 |
| Migrations | Alembic | 1.13.3 |
| Data validation | Pydantic v2 | 2.9.2 |
| Password hashing | bcrypt | 4.2.1 |
| JWT | PyJWT | 2.13.0 |
| Settings | pydantic-settings | 2.5.2 |
| Scheduler | APScheduler | 3.11.0 |
| Timezone support | pytz | 2024.1+ |
| LLM | Anthropic Claude | 0.40.0+ |
| Testing | pytest | 8.3.3 |
| HTTP test client | httpx | 0.27.0+ |
| Python | CPython | 3.12 |
| Database dev | SQLite | built-in |
| Database prod | PostgreSQL | any modern version |

---

*ESGRC API v1.0.0 - 207 tests, 0 failures - Built with FastAPI + SQLAlchemy 2.x + Anthropic Claude*
