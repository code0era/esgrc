# How TBD2 Works - End-to-End Report

*Verified 2026-09-10: 828 backend tests pass (258 ESGRC + 570 pipeline, 1 skipped) plus 38
frontend; Playwright E2E runs in CI against a real compose stack; all 12 business modules
built plus the Apex roll-up.*

TBD2 (a.k.a. Vigilant Lens) is a multi-tenant SaaS platform that turns a client organisation's
raw ESG / risk / compliance data into **AI-generated risk reports**. This document explains how
the whole system works, from a raw CSV to a Claude-written recommendation on screen.

---

## 1. The one-paragraph version

A client uploads their raw metric data. Heavy **data-science scripts** (Praveen's Repo-01) crunch
it - low-performer analysis, correlation/CHAID, SPC/RPN control charts, regression - each writing
`.txt`/`.csv` reports. Those reports are **combined** into one master report, which is sent to
**Anthropic Claude**, which writes a structured risk assessment. All of this runs as background
**Celery** jobs (so the web app never blocks), with files stored in **Cloudflare R2** and live
progress streamed to the **React** UI. A **FastAPI** backend handles login, data, scoring, and an
overnight AI agent. Everything is scoped per organisation (`org_id`) so tenants never see each
other's data.

---

## 2. Three layers

```
┌───────────────────────────────────────────────────────────────────────┐
│ FRONTEND (frontend/)   React 19 + Vite + Zustand + TanStack Query      │
│   Dashboard · Risk · Compliance · Pipeline monitor · Reports · Copilot │
└───────────────┬───────────────────────────────────────────────────────┘
                │  REST + JWT   +   SSE (live token/step streams)
┌───────────────▼───────────────────────────────────────────────────────┐
│ BACKEND API (ESGRC/)   FastAPI + SQLAlchemy 2 + Postgres/SQLite        │
│   Auth · ESG · Risk · Compliance · Scoring · Org snapshot · AI agent   │
└───────────────┬───────────────────────────────────────────────────────┘
                │  shares one database; triggers pipeline jobs
┌───────────────▼───────────────────────────────────────────────────────┐
│ DATA PIPELINE (pipeline/)   Celery + Redis + Cloudflare R2 + Claude    │
│   Runs Repo-01 analytics scripts in subprocesses → combines → Claude   │
└───────────────────────────────────────────────────────────────────────┘
```

They run as one FastAPI process (the backend mounts the pipeline + copilot routers), with a
separate Celery worker for the heavy jobs, behind nginx.

---

## 3. The data journey (the core of how it works)

### Stage A - Raw input (per module)
A client provides two files per business module:
- `input_metric_values_esgrc.csv` - the raw metric readings
- `esgrc_performance_json_file.json` - the metric/benchmark config

### Stage B - The 5-step analytics chain (one module, e.g. `esgrc`)
Each module runs the same 5-step contract. Steps 4 & 5 run in parallel after step 1:

```
input_metric_values_esgrc.csv + esgrc_performance_json_file.json
      │
[1] Low-performing analysis  → module_values_esgrc.csv, low_performing_entities_report.txt
      │
[2] Split by hierarchy       → filtered_metrics/groups/sub_modules.csv,
      │                         data_for_risk_assessment_esgrc.csv   ← module→enterprise handoff
      ├──[3] Correlation/CHAID/Fourier → 4 report .txt   (needs step 2)
      ├──[4] SPC X-bar-R + RPN/FMEA    → metrics_summary.txt + 2 PDFs (needs step 1)
      └──[5] Multiple regression + NN  → ESGRC_Module_model_summary.txt (needs step 1)
      │
[6] Combine the .txt from steps 1,3,4,5 → MASTER_CONSOLIDATED_REPORT.txt
      │
[7] Claude (Haiku 4.5) reads the master report → MODULE_UNIFIED risk assessment
```

### Stage C - Enterprise roll-up (all 12 modules)
Run stage B for each of the 12 modules → each emits `data_for_risk_assessment_<module>.csv` →
feed all 12 into the enterprise ("L0" / Apex) chain:

```
12× data_for_risk_assessment_*.csv (+ module_mapping.csv, module_matrix.csv)
      │
[1] all-module low-performance → all_module_values.csv
      ├──[2] Correlation/CHAID L0   → 4 report .txt   ┐
      ├──[3] SPC/RPN L0             → SPC_summary.txt  │ parallel
      └──[4] Regression L0          → L0_Risk_Report.txt ┘
      │
[5] Combine → MASTER report → Claude (Sonnet 4.6) → GENERAL_RISK + SPC_RPN assessments
```

> **Status (2026-09-10):** **All 12 modules are built** and have real data. Integration was the
> last to land (2026-08-22) - its JSON originally declared 7 sub-modules but filled in only 2,
> while the CSV held 48 columns for the other 5; Praveen supplied a corrected JSON and all 7
> now carry real groups.
>
> Two things about the roll-up are worth knowing before you read its output. Its report size
> scales with the **square** of the column count, so it silently overflowed Claude's limit at
> 909,000 tokens once there were 11 modules to combine; that is fixed, but it is the failure to
> watch for. And the scenario simulation in the regression step does not read client metric
> values at all, so its Overall Risk is currently the same number for every client. See
> `docs/architecture/DATA_CONTRACTS.md` §7.

### How the scripts are actually executed
The Celery pipeline does **not** import these scripts - it runs each as an **isolated subprocess**
(so a script's heavy Pandas/PyTorch memory is reclaimed by the OS when it exits). A generic
`ScriptRunner` reads `scripts_registry.json` to know each step's script, inputs, outputs, and
order.

**Adding a module** is one `ModuleSpec` in `pipeline/modules.py`, a 38-line chain file, five
registry entries, and five generated analytics scripts:

```bash
python pipeline/scripts/generate_module_scripts.py --module enterprise --camel Enterprise --dir Enterprise
```

Four things still have to be hand-written and cannot be derived: the `PipelineTypeEnum` member,
an alembic migration, the frontend `PipelineType` union and step labels, and a Dockerfile `COPY`
line. Each is a silent failure if forgotten, so each has a test that fails instead. See
`docs/architecture/DATA_CONTRACTS.md` §3.

---

## 4. Runtime architecture - what runs where

| Component | Tech | Role |
|---|---|---|
| Backend API | FastAPI 0.139, SQLAlchemy 2 | Login, CRUD, scoring, org snapshot, triggers pipelines |
| DB | PostgreSQL (prod) / SQLite (dev) | Users, orgs, ESG/risk/compliance, pipeline runs, LLM outputs |
| Task queue | Celery 5.6.3 + Redis | Runs the analytics chains as background chords/chains |
| Object storage | Cloudflare R2 (S3-compatible, boto3) | Stores input CSVs, intermediate reports, final PDFs - keyed `org/{org_id}/runs/{run_id}/…` |
| AI | Anthropic Claude - Haiku 4.5 (module), Sonnet 4.6 (enterprise) | Writes the risk assessments |
| Live updates | Redis pub/sub → FastAPI SSE | Streams step progress + Claude tokens to the UI |
| Frontend | React 19 + Vite + Tailwind | The dashboard/monitor/copilot |
| Edge | nginx | TLS, security headers, SSE buffering |

**A pipeline run, end to end:** user clicks *Trigger* → backend writes a `PipelineRun` row and
dispatches a Celery chord → each step downloads inputs from R2, runs the script in a subprocess,
uploads outputs to R2, and pushes progress to Redis → the UI's SSE stream shows each step turning
green live → the final Claude step writes the recommendation to R2 + Postgres + Redis → the UI
shows it. An **emergency-stop** endpoint can revoke the whole chord mid-run.

---

## 5. What the user sees (typical workflow)

1. **Login** - JWT issued (access token in memory, refresh token in httpOnly cookie).
2. **Dashboard** - overall ESG score + E/S/G pillar scores, trend charts, category table, and the
   nightly AI-agent status.
3. **Risk Register** - a 5×5 likelihood×impact heatmap + sortable risk table.
4. **Compliance** - framework donut charts, per-requirement status, bulk updates.
5. **Pipeline** - pick a pipeline, *Trigger*, watch each step run live, expand the Claude step to
   read the recommendation.
6. **Reports** - past runs with confidence scores; compare runs; download reports.
7. **Co-Pilot** - chat that streams Claude's answer token-by-token over your actual data.

There is also an **overnight AI agent** (APScheduler): every night it scores new ESG metrics and
escalates critical risks; every 15 days it flags overdue compliance - producing a structured
`L1_ESRC_Risk_Assessment` per org.

---

## 6. Security & multi-tenancy

- **JWT auth** - 30-min access tokens (`typ=access`), rotating single-use refresh tokens (SHA-256
  hashed). bcrypt-12 passwords.
- **Roles** - `SUPER_ADMIN > ADMIN > ANALYST > VIEWER`. Prompt editing is super-admin-only; a
  guard stops a normal admin from minting a super-admin.
- **Tenant isolation** - every row and R2 key is scoped to `org_id`; cross-org access returns
  **404** (existence not even revealed).
- **Hardened** - dependencies are CVE-clean (pip-audit), bandit 0 High/0 Medium, nginx sends
  CSP/HSTS, R2 is private (presigned URLs only), rate limiting via slowapi.

---

## 7. How to run it

**Local (no external services - SQLite + mock data):**
```
.\bootstrap.ps1     # setup (venv + deps + .env)         [./bootstrap.sh on Mac/Linux]
.\run-tests.ps1     # both backend suites
.\run-server.ps1    # backend → http://127.0.0.1:8000/docs
cd frontend; npm run dev   # UI → http://localhost:3000 (mock data)
```
**Full stack:** `docker-compose up` (postgres, redis, api, celery worker+beat, nginx).
**Deploy:** no target is live. `.github/workflows/deploy.yml` (Railway) exists but is
manual-only (`workflow_dispatch`) and not adopted - Railway needs a paid plan. The actual
demo path is a Cloudflare tunnel from a local container; see `docs/deployment/DEMO_DEPLOY.md`.

**To run the analytics scripts directly** (Praveen's modules): see `docs/team/SHUBHAM_HANDOFF.md`
(install `requirements-analytics.txt` + torch, then run the steps in order).

---

## 8. Current state

*Updated 2026-09-10. The previous version of this table said 207/144 tests and "only `esgrc`
real; other 11 modules pending", both of which had been false for some time. It also said
"11 of 12 built"; Integration (the 12th) was onboarded 2026-08-22.*

| Area | Status |
|---|---|
| Backend API (auth, ESG, risk, compliance, scoring, agent) | complete, 258 tests |
| Pipeline (Celery chains, R2, SSE, Claude, emergency stop) | complete, 570 tests (1 skipped) |
| Frontend (all pages, SSE, copilot) | builds clean, tsc clean, 38 tests |
| **Business modules** | **all 12 built** plus Apex |
| Analytics scripts | 5 per module, **generated** from the Shared copies, not hand-ported |
| E2E | Playwright runs in CI against a real compose stack |
| Security hardening | CVE-clean deps, bandit clean, RBAC aligned, subprocess credential allowlist |
| Live LLM / R2 / Postgres | exercised for real: 4 module runs plus Apex against real Claude |
| Deploy | decided and documented (`docs/deployment/DEMO_DEPLOY.md`); no target live yet |

**Bottom line:** a working, tested pilot with all 12 modules built. The gating item for an
external demo is not deployment or module coverage: it is the scenario methodology, which
currently returns the same Overall Risk for every client.

**Read `docs/architecture/DATA_CONTRACTS.md` next.** Every defect found in the August audit lived in a
contract between two components rather than inside either one, and that document is the map of
those contracts.

---

## 9. Where to read more
- **`docs/architecture/DATA_CONTRACTS.md` - where the pieces meet and what must agree. Read this before changing anything that spans two components.**
- `README.md` - run/setup + folder structure
- `docs/architecture/architecture_and_onboarding.md` - architecture deep-dive
- `docs/architecture/MODULE_IO_AND_FLOW.md` - per-script inputs/outputs + flow
- `docs/analytics/MODULE_HEALTH_CHECK.md` - analytics script fixes + test results
- `docs/team/SHUBHAM_HANDOFF.md` - running the analytics modules directly
- `RUNBOOK.md` - demo + deploy runbook
