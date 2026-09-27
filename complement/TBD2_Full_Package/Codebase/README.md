# TBD2 - AI-Powered ESG Risk & Compliance Intelligence Platform

Multi-tenant SaaS for ESG, Risk & Compliance (ESGRC). Organizations track ESG metrics, run a
risk register, manage compliance frameworks, and execute data-science pipelines whose outputs
are summarized into risk reports by Anthropic Claude. Guiding principle: **extend, don't rewrite.**

> **Status (verified 2026-09-10):** All backend tests pass (**258 ESGRC + 570 pipeline**, 1 skipped),
> backend boots, frontend builds clean (38 frontend tests, tsc clean).
> **All 12 business modules are built, plus the Apex enterprise roll-up.** Integration was the
> last one onboarded (2026-08-22, once Praveen supplied corrected reference data) - see
> [Modules built](#modules-built) and [Live verification](#live-verification). This is a
> **working pilot-grade** codebase - see [Remaining gaps](#remaining-gaps) before calling it
> production-ready.
>
> Test counts move most days. They are deliberately no longer encoded in CI job names, which
> previously drifted twice in one week and had to be corrected each time.

---

## Architecture

Three subsystems, one FastAPI process, fronted by nginx, orchestrated by docker-compose.

```
Frontend (React 19 + Vite 8 + TS)  ──REST+JWT / SSE──►  Backend API (FastAPI + SQLAlchemy 2)
                                                              │  shares one Postgres DB
                                                              ▼
                                            Pipeline (Celery + Redis + Cloudflare R2 + Claude)
```

| Layer | Stack (verified) |
|---|---|
| Frontend | React 19.2, Vite 8.1, TypeScript 6, Tailwind 3.4, Zustand 5, TanStack Query 5, Radix UI, Recharts, MSW |
| Backend | FastAPI 0.139, SQLAlchemy 2.0.36, Alembic 1.13.3, Pydantic v2 (2.9.2), APScheduler 3.11.0, PyJWT 2.13.0, bcrypt 4.2.1 |
| Pipeline | Celery 5.6.3, Redis 5.0.8 client, boto3 1.35.76 (R2), anthropic 0.120.2, structlog 24.4.0, slowapi 0.1.9, Sentry (sentry-sdk 2.19.2) |
| Data | PostgreSQL 16 (prod) · SQLite (dev) |
| AI | Claude Haiku 4.5 (ESGRC Step 7) · Claude Sonnet 4.6 (Apex Steps 6 & 8) |
| Infra | docker-compose, nginx, GitHub Actions CI. **No deploy target is live** (see Deploy below) |

---

## Folder structure

```
TBD2/
├── ESGRC/                       # FastAPI backend (9 tables, 50 endpoints)
│   ├── main.py                  # entry point - mounts pipeline + copilot routers
│   ├── requirements.txt
│   ├── alembic/versions/        # 16 migrations
│   ├── app/
│   │   ├── config.py  database.py
│   │   ├── models/models.py     # ORM models + enums (UserRole = ADMIN/ANALYST/VIEWER)
│   │   ├── schemas/schemas.py   # Pydantic v2
│   │   ├── crud/                # crud.py, auth_crud.py
│   │   ├── services/            # auth.py (JWT/bcrypt), scoring.py
│   │   ├── dependencies/auth.py # get_current_user / require_role / get_current_org
│   │   ├── agent/               # nightly two-LLM agent (orchestrator+specialist)
│   │   └── routers/             # auth, esg, risk, compliance, scoring, agent, org
│   ├── tests/                   # 258 tests
│   └── ESGRC_Reports_for_LLM/   # golden-response spec + reports
├── modules/                     # module dirs: analytics_scripts + reference_data each
│   ├── esgrc/  customer/  shared/  bspt/  enterprise/  ictm/
│   └── product/  resource/  service/  brand/  mkts/  apex/
├── pipeline/                    # Celery data pipeline (4 tables, 25 endpoints)
│   ├── modules.py               # module registry - one ModuleSpec per business module
│   ├── celery_app.py  database.py  db.py  models.py  schemas.py  middleware.py
│   ├── llm/                     # client.py, guard.py, confidence.py, prompts.py
│   ├── tasks/                   # _module_chain_factory, esgrc_chain, apex_chord, script_runner, r2, claude_tasks
│   ├── routers/                 # pipeline_router, copilot_router, sse
│   ├── scripts/                 # scripts_registry.json, seed_demo, r2 lifecycle, audit
│   └── tests/                   # 571 tests
├── frontend/                    # React SPA
│   └── src/
│       ├── pages/               # Login, Register, Dashboard, Risk, Compliance, Pipeline, Reports, Settings
│       ├── components/          # copilot/, layout/, pipeline/, ui/
│       ├── store/               # Zustand: auth, pipeline, copilot
│       ├── hooks/               # usePipelineSSE, useCopilotSSE
│       ├── lib/                 # axios (token refresh), queryClient, utils
│       └── mocks/               # MSW handlers + fixtures (dev runs standalone)
├── docs/                        # DATA_CONTRACTS.md (read first), HOW_IT_WORKS, deploy, audits
├── nginx/nginx.conf             # security headers + SSE tuning
├── docker-compose.yml           # postgres, redis, esgrc_api, celery worker+beat, nginx
├── .github/workflows/           # ci.yml, deploy.yml (Railway - manual only, not wired up)
├── bootstrap.ps1                # one-command setup (.env + venv + npm install)
├── run-server.ps1               # start backend (SQLite dev, self-contained)
├── run-tests.ps1               # run both suites
├── RUNBOOK.md                   # demo + deploy runbook
└── .env.example
```

---

## Quick start (this machine - dev, no external services)

```powershell
.\bootstrap.ps1                    # creates .env (generated secrets), venv, installs deps  (once)
.\run-server.ps1                   # backend  → http://127.0.0.1:8000/docs
cd frontend; npm run dev           # frontend → http://localhost:3000  (MSW mock data, no backend needed)
.\run-tests.ps1                    # both backend suites
```

**Dev login (mock):** `admin@tbd2.io` · **Seeded demo:** `admin@demo.com / Demo1234!`

The frontend in dev uses **Mock Service Worker**, so the UI works with zero backend/keys.
The backend runs on **SQLite** with no external services - LLM/pipeline features are inert
until you add the keys below.

## What each feature needs to actually run

| Feature | Requires |
|---|---|
| UI browsing (mock data) | Node only |
| Backend API, auth, scoring | Python + `SECRET_KEY` (SQLite fine) |
| Copilot chat + nightly AI agent | `ANTHROPIC_API_KEY` |
| Pipeline runs + live SSE | Redis + `CLOUDFLARE_R2_*` + Celery worker (`docker-compose up`) |
| Production | Postgres + Redis + all above + nginx (all in `docker-compose.yml`) |

---

## Environment variables

Copy `.env.example` → `.env` and fill in. Always required: `SECRET_KEY`
(`python -c "import secrets; print(secrets.token_hex(32))"`).

| Var | Purpose |
|---|---|
| `SECRET_KEY` | JWT signing (required) |
| `DATABASE_URL` | `sqlite:///./esgrc.db` (dev) / `postgresql+psycopg://…` (prod) |
| `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Celery + SSE |
| `ANTHROPIC_API_KEY` | Claude (copilot + pipeline) |
| `CLOUDFLARE_R2_BUCKET/ENDPOINT/ACCESS_KEY/SECRET_KEY` | Object storage |
| `ORCHESTRATOR_MODEL` / `SPECIALIST_MODEL` | `claude-sonnet-5` / `claude-haiku-4-5` |
| `LANGFUSE_*`, `SENTRY_DSN` | optional observability |

---

## Moving to a new machine

Install Python 3.10+, Node 18+, (Docker Desktop for full stack), Git.

```bash
git clone <repo>           # .venv*, node_modules, *.db, .env are gitignored - not transferred
cd TBD2
.\bootstrap.ps1            # sets up everything; edit .env for ANTHROPIC + R2 to enable AI/pipeline
```

External accounts needed only for full function: **Anthropic**, **Cloudflare R2** (or S3),
**PostgreSQL 15+**, **Redis 7+**. Dev/mock UI needs none of them.

---

## Tests & CI

- Local: `.\run-tests.ps1` (both suites, LLM/R2 mocked).
- CI (`.github/workflows/ci.yml`), six jobs: ESGRC suite, pipeline suite, frontend (Vitest +
  tsc), **Playwright E2E against a real compose stack**, Docker build of all four images, and
  deploy-config validation (`docker compose config` + `nginx -t`). **LLM calls always mocked.**
- Deploy: see **[docs/deployment/DEMO_DEPLOY.md](docs/deployment/DEMO_DEPLOY.md)**, the single source of truth. A
  Cloudflare tunnel serves scheduled demos today; a company account under METEOERAIT SOFTWARE
  P LTD is the permanent home. Every free tier tried (Render, Vercel, Koyeb, Hugging Face)
  triggers card KYC from Pakistan, which is what defeated the earlier attempts.
- `deploy.yml` is **manual only (`workflow_dispatch`) and is not the deploy path.** It still
  describes Railway, which was abandoned because it requires a paid plan. The automatic
  `push: branches: [main]` trigger was removed so a merge cannot fire a surprise deploy.

---

## Security model

- JWT access (30 min, `typ=access`) + rotating refresh tokens (SHA-256 hashed, single-use).
- bcrypt cost 12. Multi-tenant: every query scoped to `org_id`; cross-org access returns **404**.
- R2 keys namespaced `org/{org_id}/…`; private bucket, presigned URLs only.
- nginx: CSP, HSTS, X-Frame-Options DENY, etc. slowapi rate limiting. Structlog + Sentry.

---

## Security posture (hardened July 2026)

Verified this session with real tool output:

- **Dependency CVEs: `pip-audit` = "No known vulnerabilities found"** on **both** requirement
  sets. On 2026-08-14, `python-jose` was replaced with PyJWT 2.13.0 to remove its vulnerable
  `ecdsa` dependency. `npm audit` also reports zero production and development vulnerabilities.
  (uploads), `python-dotenv`→1.2.2, `pytest`/`pytest-asyncio`→9.1.1/1.4.0, `celery`/`kombu`→5.6.3/5.6.2,
  `fastapi`→0.139.0, `starlette`→1.3.1.
- **Static scan (bandit): 0 High, 0 Medium, 13 Low.** The former 12 Medium `/tmp` findings are
  resolved via a configurable `PIPELINE_WORK_DIR` (`shared.pipeline_work_dir`).
- **RBAC:** `SUPER_ADMIN` added to the backend enum + role hierarchy; prompt-editing gated to it
  (platform-owned); privilege-escalation guard prevents a regular admin minting a super_admin.
  Frontend and backend role models now agree.

### One documented tech-debt suppression
`starlette` 1.x's TestClient prints a deprecation telling you to migrate `httpx`→`httpx2`. That
package **does not exist yet** (July 2026) and `anthropic` pins `httpx<1`, so the migration is not
yet actionable. The warning is suppressed in `pytest.ini` + CI (`StarletteDeprecationWarning`) and
should be revisited when `httpx2` ships.

## Modules built

**All twelve** business modules are built, plus the Apex enterprise roll-up. Each is
registered as a single `ModuleSpec` in `pipeline/modules.py`; adding one is that spec plus a
38-line chain file.

| Module | Token | Code | Chain |
|---|---|---|---|
| ESGRC | `esgrc` | `ESRC_001` | hand-written (predates the template, kept as the reference implementation) |
| Customer | `customer` | `CUST_001` | factory-built |
| Shared | `shared` | `SHRD_001` | factory-built |
| Business Partner | `bspt` | `BSPT_001` | factory-built |
| Enterprise | `enterprise` | `ETPR_001` | factory-built |
| IT Processes | `ictm` | `PRCY_001` | factory-built |
| Product | `product` | `PROD_001` | factory-built |
| Resource | `resource` | `RSRC_001` | factory-built |
| Service | `service` | `SRVC_001` | factory-built |
| Brand Management | `brand` | `BRDM_001` | factory-built |
| Market and Sales | `mkts` | `MKTS_001` | factory-built |
| Integration | `integration` | `INTG_001` | factory-built (onboarded 2026-08-22) |
| Apex Enterprise | `apex` | - | 8-step chord; rolls up whatever modules have produced a handoff |

All module pipelines are 7 steps. Token and code differ where the business name does
(`ictm`/`PRCY_001`, `esgrc`/`ESRC_001`); that is normal.

Their analytics scripts are **generated**, not hand-ported:

```bash
python pipeline/scripts/generate_module_scripts.py --module enterprise --camel Enterprise --dir enterprise
```

The source is always our own fixed copies, never the upstream repo, because ours carry the
corrections upstream does not. Do not hand-edit a generated script; the next regeneration
discards the edit.

**Integration was the last module onboarded** (2026-08-22): its JSON originally declared 7
sub-modules but only `API10000` and `AII10000` carried groups, with `LIN`, `BRP`, `FUL`, `ASI`
and `APM` shipping `"groups": []` while the CSV held 48 columns of real data for exactly those
prefixes. Praveen supplied a corrected JSON and all 7 sub-modules now carry real groups
(`modules/integration/reference_data/integration_performance_json_file.json`); the module is
wired into `pipeline/modules.py` with its own alembic migration
(`ESGRC/alembic/versions/20260822_add_integration_pipeline_type.py`).

## Live verification

These paths have been exercised end to end against real services, not only against mocks
(local MinIO for R2, `DEMO_MODE=false`, real analytics scripts, real Claude calls):

| Run | Module | Result |
|---|---|---|
| `251d9eeb` | ESGRC | 7 steps completed, 26,756 input tokens after the report trim |
| `e42c4a66` | Shared | 7 steps completed, haiku-4-5, $0.0597 |
| `92e895f2` | Business Partner | 7 steps completed, haiku-4-5, $0.0733 |
| `0ecac529` | Apex | 8 steps completed, "Modules Analysed: 3 (BSPT_001, SHRD_001, ESRC_001)" |

Postgres and Redis run under `docker-compose`. Cloudflare R2 itself is the one integration never
exercised against the real service; local MinIO stands in for it and speaks the same S3 API.

## Remaining gaps

1. **No deploy target is live yet**, though the approach is decided: see
   [docs/deployment/DEMO_DEPLOY.md](docs/deployment/DEMO_DEPLOY.md). Note its warning that an external URL is
   gated on the scenario methodology, not on hosting.
2. **Frontend does not consume the newer backend contracts.** `response_text_labeled`,
   `handoff-provenance` and `process-log` are built, tested and documented in
   `docs/team/SHUBHAM_FRONTEND_API.md`, with zero references in `frontend/src`.
3. **Two analytics methodology questions** are open with the analytics owner: the low-performer
   aggregation (was `.iloc[0]`, now the mean) and the scenario simulation, whose outputs do not
   currently vary with client data.

   *(The six audit follow-ups formerly tracked here as issue #9 — frontend service missing from
   the prod compose stack, `Dockerfile.hf` unbuilt by CI, rate limits applied on no endpoint,
   GDPR erasure leaving Co-Pilot text in Redis with no direct-erasure path, uploads with no size
   cap, and `script_runner` passing the worker's full environment to analytics subprocesses — are
   all resolved: issue #9 closed 2026-08-07, issue #12 (Co-Pilot erasure) closed 2026-08-08.)*

---

*Verified 2026-08-08: 758 backend tests pass (247 ESGRC + 511 pipeline, 1 skipped) via
`.\run-tests.ps1`. Dependency and static-analysis figures below were last verified 2026-08-05:
FastAPI 0.139, starlette 1.3.1, Celery 5.6.3, pytest 9.1.1 · all Python compiles · tsc clean ·
0 npm prod vulns · **pip-audit clean on both requirement sets** · bandit 0 High / 0 Medium.*
