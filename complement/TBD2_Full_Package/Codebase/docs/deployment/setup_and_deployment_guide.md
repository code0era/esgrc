# Setup and Deployment Guide

> **SUPERSEDED - do not follow this document.**
> Audited 2026-08-05 and found materially wrong in ways that will break a
> live system: it names a model (`claude-3-5-sonnet-20240620`) the code does
> not use, environment variables (`R2_ACCESS_KEY_ID`, `R2_PUBLIC_URL`) that do
> not match the `CLOUDFLARE_R2_*` scheme in use, compose service names
> (`db`, `api`) that do not exist (`postgres`, `esgrc_api`), a frontend port
> that is not 5173, and Railway deployment steps for a target that was
> abandoned. Kept only as history.
> Current sources of truth: `docs/deployment/PROD_DEPLOY.md`, `RUNBOOK.md`,
> `deploy/hf/README_HF.md`, `.env.example`.

This guide contains everything you need to run the TBD2 platform from scratch, including necessary external accounts, required environment variables, and deployment instructions.

---

## 1. Required Accounts & Credentials

To run the application fully (especially the Celery pipeline and AI features), you will need the following 3rd-party accounts:

### A. Anthropic (Claude AI)
- **Purpose**: Powers the Copilot chat and the final AI reporting in the pipeline.
- **Requirement**: An active API key with access to `claude-3-5-sonnet-20240620`.

### B. Cloudflare R2 (or AWS S3)
- **Purpose**: Object storage for user-uploaded CSVs, generated data science CSVs, and final PDF/TXT reports. 
- **Requirement**: A Cloudflare account with an R2 bucket created. You need the `Access Key ID`, `Secret Access Key`, and the `Endpoint URL`.

### C. PostgreSQL Database
- **Purpose**: Core application data (Users, Orgs, Audit Logs, Pipeline states).
- **Requirement**: A Postgres 15+ database. For local development, Docker will spin one up for you.

### D. Redis
- **Purpose**: Celery task broker and Server-Sent Events (SSE) pub/sub backend.
- **Requirement**: A standard Redis instance. For local development, Docker will spin one up for you.

---

## 2. Environment Variables (`.env`)

Create a `.env` file in the root `TBD2/` directory (you can copy `.env.example`). At minimum, ensure these are filled out:

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/esgrc

# Redis (Celery Broker & SSE)
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Security (Generate a random string for JWT)
SECRET_KEY=your-super-secret-jwt-key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

# Anthropic AI
ANTHROPIC_API_KEY=sk-ant-api03-...

# Cloudflare R2 / S3
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_ACCOUNT_ID=your_cloudflare_account_id
R2_BUCKET_NAME=your-bucket-name
R2_PUBLIC_URL=https://pub-xxxx.r2.dev  # Used for direct user downloads
```

---

## 3. Running Locally (From Scratch)

We use `docker-compose` to make local development trivial. You must have Docker Desktop installed.

### Step 1: Start the Database and Redis
```bash
# From the TBD2 root directory
docker-compose up -d db redis
```

### Step 2: Run Database Migrations
Before starting the app, you must create the tables and seed the initial AI Prompts.
```bash
# Assuming you have a virtual environment with ESGRC/requirements.txt installed:
alembic upgrade head
```

### Step 3: Start the Backend (FastAPI)
You can run it via Docker or locally:
```bash
# Using Docker
docker-compose up api

# OR Using local Python (better for debugging)
uvicorn ESGRC.main:app --reload
```

### Step 4: Start the Celery Pipeline Worker
```bash
# Using Docker
docker-compose up celery_worker

# OR Using local Python
cd pipeline
celery -A celery_app worker --loglevel=info -P gevent -c 4
```

### Step 5: Start the Frontend
```bash
cd frontend
npm install
npm run dev
```
The frontend will be available at `http://localhost:5173`.

---

## 4. Production Deployment (Railway)

The `docker-compose.yml` and `Dockerfile`s in the repository are fully optimized for production environments like **Railway.app** or **Render**.

### Steps for Railway:
1. **Create a new Project** in Railway.
2. **Provision Databases**: Add the "PostgreSQL" and "Redis" plugins to your project.
3. **Connect your GitHub Repo**.
4. **Configure Services**: Railway will automatically detect the Dockerfiles. You should configure 3 separate services from the same repo:
   - **Service 1 (API)**: Set the Root Directory to `ESGRC/`. Wait Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`.
   - **Service 2 (Celery)**: Set the Root Directory to `pipeline/`. Start Command: `celery -A celery_app worker --loglevel=info`.
   - **Service 3 (Frontend)**: Set the Root Directory to `frontend/`. Let Railway build it using Node.js.
5. **Inject Variables**: Copy all variables from your `.env` into the Railway Shared Variables interface, substituting the local database URLs with Railway's internal connection strings (e.g., `DATABASE_URL=${{Postgres.DATABASE_URL}}`).

Once deployed, ensure you run `alembic upgrade head` via the Railway CLI or a deployment hook to instantiate the production database.
