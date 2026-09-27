# System Architecture & Onboarding Guide

Welcome to the TBD2 project! This document is designed to get you up to speed as quickly as possible. The sections are kept deliberately small so you can digest the architecture module by module.

---

## 1. High-Level Architecture

TBD2 is an enterprise risk assessment platform that uses AI to analyze corporate compliance, risk, and ESG (Environmental, Social, and Governance) data.

The platform is a **Monorepo** divided into three main layers:
1. **Frontend (`frontend/`)**: React + Vite + TypeScript.
2. **Backend API (`ESGRC/`)**: FastAPI + SQLAlchemy (PostgreSQL).
3. **Data Pipeline (`pipeline/`)**: Celery + RabbitMQ/Redis for heavy background processing and AI integration.

---

## 2. The Frontend (`frontend/`)

We use **React** with **TypeScript** and **Tailwind CSS**.

### Key Technologies
- **Vite**: Super-fast build tool and dev server.
- **Zustand**: Lightweight global state management (replaces Redux).
- **React Query**: For fetching, caching, and updating server data.
- **Server-Sent Events (SSE)**: Used heavily to stream live updates from the backend (e.g., streaming Claude's text generation).

### Important Files to Know
- `src/store/`: Contains our Zustand stores (`auth.ts`, `copilot.ts`, `pipeline.ts`).
- `src/hooks/usePipelineSSE.ts`: The hook that listens to live Celery task updates from the backend.
- `src/components/copilot/CopilotPanel.tsx`: The AI chat interface that streams responses token-by-token.

---

## 3. The Backend API (`ESGRC/`)

The core API is built with **FastAPI**. It handles authentication, database CRUD operations, and triggering pipeline runs.

### Key Technologies
- **FastAPI**: Asynchronous web framework.
- **SQLAlchemy (v2)**: ORM for interacting with PostgreSQL.
- **Alembic**: Database migrations.

### Important Files to Know
- `main.py`: The entry point. Connects the routers and handles CORS.
- `app/models/models.py`: All database tables are defined here.
- `app/routers/`: Grouped API endpoints (e.g., `auth.py`, `esg.py`, `agent.py`).
- `app/agent/`: The LLM Agent code for the AI Copilot.

---

## 4. The Data Pipeline (`pipeline/`)

Because running heavy data science scripts and calling the Anthropic Claude API takes a long time, we do **not** do this in the FastAPI web requests. Instead, we use **Celery** to run these tasks in the background.

### Key Technologies
- **Celery**: Distributed task queue.
- **Redis**: Acts as the message broker (queue) and result backend.
- **Cloudflare R2**: S3-compatible object storage used to store large CSVs and output reports.

### How the Pipeline Works
The pipeline orchestrates complex workflows called "Chains" (sequential tasks) and "Chords" (parallel tasks).
1. `pipeline/tasks/apex_chord.py` & `esgrc_chain.py`: Define the order in which steps execute.
2. `pipeline/tasks/script_runner.py`: A generic wrapper that executes our legacy data science Python scripts in isolated subprocesses.
3. `pipeline/scripts/scripts_registry.json`: The "brain" of the script runner. It tells the pipeline exactly which Python script to run for which step, what inputs it needs, and what outputs it produces.

### Important Concepts
- **`run_id`**: Every time a user clicks "Trigger Pipeline", a unique UUID is generated. All files in R2 and all logs in Postgres are tracked by this `run_id`.
- **`org_id`**: For security, all data is strictly scoped to the user's organization.

---

## 5. Typical Developer Workflows

### How to add a new API Endpoint
1. Define the Pydantic schema in `ESGRC/app/schemas/schemas.py`.
2. Write the database query in `ESGRC/app/crud/`.
3. Create the route in `ESGRC/app/routers/`.

### How to modify an AI Prompt
1. All prompts are seeded into the database via Alembic migrations (e.g., `alembic/versions/20260621_seed_pipeline_prompts.py`).
2. They are managed in the UI under Settings -> Prompts (Super Admin only).

### How to add a new Data Science Script
1. Add the raw python script to `pipeline/scripts/` (or `modules/esgrc/analytics_scripts/`).
2. Register the script's inputs and outputs in `pipeline/scripts/scripts_registry.json`. No changes to the core Celery code are required!
