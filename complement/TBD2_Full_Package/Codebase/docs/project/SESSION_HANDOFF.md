# TBD2 - Session Handoff (updated 2026-07-09)

Portable state summary. Everything marked ✅ was actually run/verified.

## 🎯 Milestone (2026-07-09): Apex "drill-down" report - real 12-module data, verified on rebuilt images
Praveen delivered all 12 `data_for_risk_assessment_<module>.csv` (Repo-01 → `Downloads/Repo-01-main.zip`).
Staged to MinIO `org/2/module_outputs/`; **real 12-module Apex COMPLETED**. Then shipped the report
format Praveen wanted (proven via a Gemini experiment): **Parent Module → Sub-Module → Group → Metric**
drill-down with correlation/impact/scenario traceability + a "Specific Items Needing Attention" table,
grounded (marks `not resolved in data`; no fabrication). Verified END-TO-END on **rebuilt images**.

**Root fix:** the regression report (Apex Step 4, `L0_Risk_Analysis_Report`) reached **neither** Claude
call - orphaned. Changed the General combine `[1,2]`→`[1,2,4]` (`apex_chord.py`) so drivers sit next to
the correlation matrix in the Step-6 call. (ESGRC already combines its regression via `[1,3,4,5]`.)
Rewrote the `GENERAL_RISK` prompt (`prompts.py`) + migration `20260709_apex_prompt_v2` to publish it to
the DB. Decision (Danish): keep two Apex Claude calls (General + SPC/RPN), add regression to General,
full drill-down.

**Verified on the baked image:** `alembic current = 20260709_apex_prompt_v2 (head)`, live prompt has the
drill-down, combine uses `[1,2,4]`, ESGRC run (285K tok→Sonnet) + Apex run (**868,476-token** General
call, full master) both COMPLETED. Outputs saved to `C:\Users\Danish Ahmed\OneDrive\Documents\TBD2_pipeline_outputs\`
(README + `APEX_b74eeb02/` 14 files + `ESGRC_1187cd94/` 15 files).

**⚠️ Two lessons (see [[tbd2-engineering-gotchas]]):** (1) migration revision ids MUST be ≤32 chars -
Postgres enforces `alembic_version` VARCHAR(32), SQLite doesn't, so an over-long id passes tests but
rolls back the real migration (this bit us: id was 35 chars → prompt update silently reverted). Added
guard test `ESGRC/test/test_alembic_revision_ids.py`. (2) **Verify on the REBUILT image, not `docker cp`'d
code** - early demos ran on a stale image whose old guard silently truncated the input to ~225K; only
after rebuild did the full 868K reach Claude.

**Token profile (real full data):** Apex General master ≈ **868K tokens**, near the 950K guard cap;
`inconsistency_report_L0.txt` is 1.33MB / 68% of it. **Decision: keep it in** (Claude actively cites it);
revisit trimming post-demo if client data grows. Sonnet 4.6 1M window **live-proven at 615K and 868K**.

Commits (local): `8d3b80a` migration-id fix + guard · `bc1c1c3` regression→General + drill-down prompt.
Tests: **209 ESGRC + 173 pipeline** green. Stack torn down (volumes kept); images rebuilt with changes baked in.

---

## 🚀 Milestone (2026-07-08): pipeline runs END-TO-END for the first time
Ran the ESGRC pipeline for real (real broker + real object storage, not the eager-mode
e2e tests) and it now COMPLETES all 7 steps: real Repo-01 analytics scripts on real inputs
→ real `claude-sonnet-4-6` risk report (grounded in the actual model/CHAID/SPC/regression
outputs). Storage is a **local MinIO** (S3-compatible, no Cloudflare/card) - proving R2 is
not required for local runs.

**Six integration bugs (the pipeline had never truly run; eager-mode tests masked them) - all fixed & committed:**
1. `/tmp/tbd2` root-owned bind-mount → non-root worker `PermissionError` (compose override).
2. `scripts_registry.json` had no `"scripts"` key the loader reads (`_load_registry` → `data["scripts"]`).
3. registry entries lacked `script_filename`/`output_file_patterns` for the real subprocess runner.
4. **Celery canvas**: `chord.set(link_error=…)` forwards to the header `group.apply_async()` →
   `TypeError: Cannot add link to group` → run stalls after step1. Fixed in `esgrc_chain.py`
   (verified live) and `apex_chord.py` (both now runtime-verified live - see the Apex milestone above).
5. `r2.py`: env-gated `S3_ADDRESSING_STYLE=path` so boto3 works with MinIO (no-op for real R2).
6. `guard.py`: `anthropic==0.40.0` genuinely lacks `messages.count_tokens` (live-verified
   `hasattr → False`) → char-estimate `len//4` under-counted dense reports → Haiku→Sonnet
   upgrade never fired → **Haiku 200K** overflow 400. Fixed to `len//3`. NOTE: the guard's
   Sonnet thresholds were later corrected too - see the "Sonnet 1M window" milestone below;
   Sonnet 4.6 has a native 1M window (NO beta header - that earlier note was wrong).

**How to run it locally (no Cloudflare):** `docker-compose.local.yml` (committed) + `.env` with a real
`ANTHROPIC_API_KEY` and MinIO storage vars. Bring up: `docker compose -p tbd2 -f docker-compose.yml
-f docker-compose.local.yml up -d esgrc_api celery_worker celery_beat minio createbuckets`, seed,
then trigger via `/pipelines/{id}/trigger`. `DEMO_MODE=false` = real scripts; `=true` = fake scripts
(real storage + real LLM). MinIO console: http://localhost:9001 (minioadmin/minioadmin123).
⚠️ `.env` holds a REAL Anthropic key now (gitignored, not committed) - each real run costs ~cents–$1.

---

## 🏛️ Milestone (2026-07-08): Apex Enterprise pipeline runs END-TO-END - first time
The 8-step Apex enterprise pipeline had never been runtime-verified because Step 1 required
all 12 `data_for_risk_assessment_<module>.csv` files. For the MVP ("Apex runs on ESGRC data
only"), `apex_step1` was relaxed to **tolerate missing modules** - it `file_exists`-checks each
module CSV, downloads only what's present, requires at least the ESGRC handoff, and logs which
modules were skipped (the underlying `all_module_low_performance_analysis_1_0.py` already
warns-and-skips absent files). Execution stays fully automatic; only input-gathering changed.
Commit `944a1c4` (+ 2 hermetic tests: runs-on-esgrc-only, requires-at-least-esgrc).

**Live run - all 8 steps COMPLETED (100%, no errors), on ESGRC data alone:**
`1 All-Module-Low-Perf 1.3s · 2 Correlation-CHAID-L0 15.9s · 3 SPC-RPN-L0 4.0s ·
4 Regression-L0 7.2s · 5 Combine-General 0.1s · 6 Claude General-Risk (Sonnet) 88s ·
7 Combine-Statistical 0.03s · 8 Claude SPC-RPN (Sonnet) 66s`. Two real `claude-sonnet-4-6`
reports produced (GENERAL_RISK 17.6K chars, SPC_RPN 11.4K chars). The single-module
**Regression L0 (Step 4)** - the main risk - handled it fine.

**Caveats (recorded for accuracy):** (a) current DB has only **org 2**; the genuine ESGRC
handoff lived under an orphaned **org 1** from before the last re-seed, so it (+ mapping/matrix)
was copied under org 2 for the run - real data, staged placement. (b) "12 modules" is nominal:
the enterprise stats ran over one module's sub-module cluster (ESGRC `ESRC_001`) - exactly the
MVP behavior. (c) run made 2 real Sonnet calls (~cents–$1). (d) images have since been
**rebuilt** (`celery_worker` + `esgrc_api` + `celery_beat`) so the fix is baked in, and Apex was
**re-run on the rebuilt images → COMPLETED again** (GENERAL_RISK out=6636 tokens, confirming the
8192 bump is live). Real order for a clean run: **run ESGRC first** (produces the handoff) **→ then Apex**.

**Also (2026-07-08):** LLM `max_tokens` 4096 → **`MAX_OUTPUT_TOKENS` 8192** (env
`LLM_MAX_OUTPUT_TOKENS`) in `pipeline/llm/client.py` - both Apex Sonnet reports hit the old 4096
ceiling and were clipped; 8192 lets them finish, well within the model's output limit.

**⬆️ SUPERSEDED (2026-07-09): Apex verified on REAL 12-module data.** Praveen uploaded all 12
`data_for_risk_assessment_<module>.csv` (+ `module_mapping.csv`/`module_matrix.csv`) to Repo-01
(`Repo-01-main.zip`). Staged all 12 to `org/2/module_outputs/` + refs to `org/2/reference/` and
triggered a real run - **all 8 steps COMPLETED (100%, no errors), genuinely across 12 modules**
(caveat (b) above no longer applies). Timings scaled as expected: `2 Correlation-CHAID-L0 45.6s ·
3 SPC-RPN-L0 34.4s · 4 Regression-L0 15.7s · 6 Claude General-Risk 144s · 8 Claude SPC-RPN 135s`.
Reports are enterprise-wide: "12 modules / 157 sub-modules / 175 metrics", posture **6.8/10**,
flags SRVC_001/ETPR_001/MKTS_001; 11/12 module codes appear verbatim.
- **Guard 1M fix vindicated in production:** GENERAL_RISK input was **226,153 tokens** - over
  Haiku's 200K *and* over the OLD wrong Sonnet cap (190K). Pre-fix, this real client-scale report
  would have been **truncated ~36K tokens (16%)**; the native-1M fix passed all 226K through intact.
- **Cost validated:** full 12-module run = **$0.9370** (GENERAL_RISK $0.79 + SPC $0.15) - matches
  the ~$1 estimate; LLM spend is immaterial, as the data-driven decision concluded.
- **No real Repo-01 drift:** deep-diffed all 9 scripts - only Flask-blocker removal + CRLF; nothing
  to port. Our `analytics_scripts/` copies are current.

---

## 🪟 Milestone (2026-07-08): Sonnet 4.6 1M context window - corrected & live-proven
`pipeline/llm/guard.py` capped `claude-sonnet-4-6` at **170K/190K** on a wrong comment claiming its
1M window needs a `context-1m` beta header. Per the July-2026 Claude catalog that belief is false -
**Sonnet 4.6's 1M window is GA/native, no header** (the beta only ever applied to Sonnet 4.5/4.0).
The old cap silently **truncated ~40K tokens out of the middle** of large ESGRC reports routed to Sonnet.
- **Fix (`836f288`):** raised `claude-sonnet-4-6` thresholds to **800K/950K** (50K buffer under 1M);
  kept deprecated `claude-sonnet-4-20250514` (Sonnet 4.0, no native 1M) conservative at 170K/190K;
  corrected the comment; +2 regression tests (210K report not truncated; Sonnet-4.0 stays conservative).
- **Live-proven on this account:** a **615,012-token** prompt to `claude-sonnet-4-6` returned HTTP 200
  (no "prompt too long" 400) and replied `OK` - 3× the old 200K cap, confirming the native 1M window.
- `count_tokens` proper fix deferred: needs an SDK upgrade off 0.40.0 (heavy 2025–26 API drift) - not
  worth it pre-deadline; `len//3` + the true 1M thresholds is safe (huge headroom).

**Decisions made by Danish (2026-07-08):** prompt ownership = **platform-owned** (super_admin manages
versions); reporting cadence = **quarterly → `max_age_days=180`**; push/deploy = **HOLD** (stay local).

---

## 🔐 Milestone (2026-07-08): module-scoped RBAC (per-module logins) - live-verified
Layered on the existing org isolation + role RBAC (2026 best-practice; ReBAC/ABAC judged overkill
for a static user→module map). An ESGRC user sees only ESGRC pipelines/data; an Apex admin only Apex.

- **Backend (`5860426`):** `User.module_access` JSON column + Alembic migration `20260708`;
  `require_module()` gates the ESGRC data routers (risk/esg/scoring/compliance); `/pipelines` is
  filtered by module (an out-of-module pipeline id → 404); `super_admin` bypasses everything. Adding
  the other 10 modules is one line each in `MODULE_PIPELINE_TYPES` (`ESGRC/app/dependencies/auth.py`).
- **Frontend (`fff4f41`):** `hasModule()` in `store/auth.ts`; the Sidebar gates Dashboard/Risk/
  Compliance to the `esgrc` module; login lands a user on their first allowed page.
- **Verified live:** `apex.admin@demo.com` → only the Apex pipeline, nav = [Pipeline, Reports,
  Settings], `GET /risks` → **403**. `esgrc.admin@demo.com` → full ESGRC nav + data.
  `admin@demo.com` → both modules.
- **E2E:** `frontend/e2e/rbac.spec.ts` (Playwright) - apex-admin nav gating + deep-link block +
  esgrc-admin full nav. Needs the seeded stack (`npm run test:e2e`).

**Demo logins (all `Demo1234!`):** `admin@demo.com` [esgrc+apex] · `esgrc.admin@demo.com` [esgrc] ·
`apex.admin@demo.com` [apex] · `analyst@demo.com` / `viewer@demo.com` [esgrc].

---

## What TBD2 is
Multi-tenant ESG-Risk-Compliance SaaS: FastAPI backend (`ESGRC/`) + Celery pipeline
(`pipeline/`) + React frontend (`frontend/`). Runs Repo-01 analytics scripts → Claude risk reports.
It is **one module (ESGRC) of a 12-module "Vigilant Lens" enterprise-risk platform** - the full
product vision, architecture rationale, and task plan now live in **`docs/source_documents/vigilant_lens/`**
(read `docs/source_documents/vigilant_lens/README.md` first).

## The big discovery (earlier session)
The app had only ever run on SQLite (`create_all`) + local Python - never on real PostgreSQL,
in Docker, or against the real frontend↔backend contract. Running it for real surfaced ~9 latent
bugs; all fixed. The frontend was also built against MSW mock shapes and crashed on real data -
now reconciled (below).

---

## ✅ Done & committed (LOCAL only - NOTHING PUSHED; ~33 commits, no remote)
Most recent first:
```
836f288 Fix guard: restore Sonnet 4.6 to its true native 1M context window
61e276e Add readiness/blockers board + send-ready ZDR email draft
11ef9ae Update handoff for module-scoped RBAC; add RBAC nav E2E
944a1c4 Bump LLM max output tokens to 8192; record Apex end-to-end milestone
fff4f41 Frontend: module-scoped nav gating + landing route
5860426 Add module-scoped RBAC (per-module logins) for ESGRC + Apex
1103e3e Apply the chord link_error fix to Apex; record the end-to-end milestone
d998473 Add docker-compose.local.yml for card-free local end-to-end runs
d10661d Fix LLM context guard so real-data runs reach Claude (ESGRC step 7)
d90c848 Fix pipeline so it runs end-to-end for the first time (ESGRC)
3259f2f CI: frontend Vitest job + fix Docker build-context bug
20e40b9 Expand frontend tests: component + Playwright E2E
17e659b Add production deploy config (templated, not deployed)
481735f Update handoff: security verified live, frontend tests, stack rebuilt
7708190 Add frontend test suite (Vitest) + extract API normalizers
3f3dbf8 Fix /pipelines/prompts route shadow; add regression tests
05c0ede Security hardening: RBAC on business writes, IDOR, path traversal, BOLA, rate limit
02838b5 Update session handoff to current state
ff6c139 Wire frontend to the real API; fix stale model default & docs
9c4d374 Add Vigilant Lens / TBD2 product & planning docs
9f522bf Add session handoff summary (state + remaining work)
193f85b Allow frontend to run against a real backend (auth wired)
e15d058 Add missing metric_code migration; fix stale seed_demo
6682fe9 Fix Postgres/Docker deploy: migrations + celery commands
4be1dea Fix esgrc_api image to include the pipeline package + deps
… (earlier: analytics packaging, Repo-01 fixes, docs, MVP initial commit)
```

### 🔒 Security hardening (`05c0ede`) - deep multi-agent audit + fixes, all covered by tests
- **HIGH RBAC:** viewers could create/update/DELETE risk/ESG/compliance → `require_role` added
  (ANALYST for writes, ADMIN for deletes) across the business routers.
- **HIGH benchmark IDOR:** `/esg/benchmarks/{id}` was cross-org readable/overwritable → org-scoped + role-gated.
- **HIGH path traversal:** `upload-input?filename=` → basename validation.
- **HIGH copilot BOLA:** SSE stream key namespaced by `user_id`.
- **HIGH login brute-force:** Redis-backed shared limiter, 5/min on `/auth/login` (env-gated off in tests).
- **MEDIUM agent-log tenant leak:** `/agent/runs` restricted to SUPER_ADMIN; `/agent/status` stays ADMIN.
- **MEDIUM R2 error info leak:** generic client message, detail logged server-side.
- **Frontend:** Settings Users tab (3 bugs) + Compliance per-framework NaN.
- Verified clean: SQLi, mass-assignment, Celery=json, subprocess, secrets, pip-audit + npm audit (0 vulns), JWT/refresh/bcrypt-12.

### 🩹 Working-tree changes NOT yet committed (2026-07-07)
- **`/pipelines/prompts` route-shadow FIXED** (was remaining item #4). The static `/prompts` routes
  are now declared **before** the `/{pipeline_id}` catch-all in `pipeline/routers/pipeline_router.py`
  (FastAPI matches in definition order; the catch-all was capturing `GET /prompts` as
  `pipeline_id="prompts"` → 404, silently breaking the Settings → Prompts tab). Added a comment so it
  can't regress + 2 regression tests (`TestPromptRouteNotShadowed` in `test_pipeline_endpoints.py`).
  Verified: `pytest pipeline/test/` → **146 pass**. Not yet committed (awaiting review/commit).

**By area:**
- **Tests: 391 green (all re-run 2026-07-08):** 208 ESGRC + 153 pipeline + 25 frontend Vitest (normalizers, auth/RBAC,
  StatusBadge component) + Playwright E2E: `smoke.spec.ts` (login→dashboard, viewer RBAC) +
  `rbac.spec.ts` (module-scoped nav gating, new 2026-07-08). E2E run live vs :3100/:8080.
  `pytest.ini` has `-W error`. CVE-clean (pip-audit); bandit 0 High / 0 Medium.
- **CI (`.github/workflows/ci.yml`):** now 4 jobs - ESGRC (208), pipeline (146), **frontend (Vitest+tsc,
  new)**, docker build. Fixed a latent bug: build-images used `context: ./ESGRC` but the Dockerfiles
  COPY repo-root paths → changed to `context: .` + explicit `file:`. (E2E not in CI - needs the stack.)
- **Deploy hardening (templated, NOT deployed):** `nginx/nginx.prod.conf` (TLS/HSTS/redirect),
  `docker-compose.prod.yml` (Redis auth, uvicorn not exposed, CORS, DEBUG=false - `docker compose config`
  validated), `docs/deployment/PROD_DEPLOY.md` checklist.
- **Live pipeline trigger verified (2026-07-08):** `POST /pipelines/{id}/trigger` fails-closed with
  **400** ("inputs missing in R2") - auth + lookup + preflight all work; only real R2/Anthropic keys are
  missing for an actual run. Full 7-step chain is covered by the 146 pipeline tests (mocked).
- **Consolidated archive:** `D:\Vigilant_Lens_TBD2\` gathers all scattered TBD2/Vigilant material
  (clean source snapshot + planning docs + input data + archives) - see its `INVENTORY.md`. Copies only;
  live git repo untouched.
- **RBAC:** `SUPER_ADMIN` end-to-end (enum + hierarchy + migration + prompt gate + escalation guard).
- **Docker/deploy:** both images build + run; enum/migration drift fixed; `metric_code` migration added; api runs `alembic upgrade head` before boot. Drift scan clean.
- **Backend hardening (B-16) - ALREADY WIRED:** `pipeline/middleware.py` provides request-ID
  middleware, structlog JSON logging, Sentry init (guarded by `SENTRY_DSN`), and slowapi rate
  limiting (60/min); `ESGRC/main.py:186` calls `add_pipeline_middleware(app)`. (An earlier audit
  wrongly flagged this as missing - it grepped only `ESGRC/` and missed the cross-package import.)
- **Model IDs (verified vs July-2026 Anthropic catalog):** pipeline uses `claude-haiku-4-5` +
  `claude-sonnet-4-6` - both **valid/active**, will NOT 404. Fixed the one stale default:
  `ESGRC/app/config.py` `ORCHESTRATOR_MODEL` `claude-sonnet-4-20250514` (deprecated) → `claude-sonnet-4-6`.
- **Frontend ↔ real backend:** auth works (LoginPage token-only flow → `/auth/me` + `/org/snapshot`).
  **Data pages reconciled to the real API and verified live on the running backend:**
  - Dashboard - normalizes `/esg/dashboard` (real `categories[].{category_name,latest_score,pillar}`
    + `overall_avg_score`); no longer crashes on `pillar_scores.governance`.
  - Risk - `/risks` is a bare array (not `{items}`); shows all 12 risks + heatmap.
  - Compliance - built from `/compliance/summary` + `/compliance/requirements` (+ version from
    `/compliance/frameworks`); real counts (45% global, 40 reqs) instead of NaN; single-update
    PUT→PATCH; bulk `POST /bulk-update` → `PATCH /bulk` with `[{id,status}]`.
  - Register - same token-only flow as Login.
  - All kept mock-compatible; `tsc --noEmit` clean.
- **Docs:** `docs/source_documents/vigilant_lens/` (Architecture Recommendation, MVP Project Plan, Strategic Analysis,
  PRD breakdown + index) recovered from the D: archive and committed. Plus HOW_IT_WORKS,
  MODULE_IO_AND_FLOW, MODULE_HEALTH_CHECK, SHUBHAM_HANDOFF, production_readiness_audit.

---

## 🔴 REMAINING (prioritized)

0. ✅ **Live-verified the security fixes (2026-07-07)** on a freshly rebuilt stack - all pass on the
   running containers: viewer write→**403**, rapid logins→**429**, filename `..`→**400** (traversal
   payloads confined to basename), `/pipelines/prompts`→**200**. Bonus: R2 error is generic (info-leak
   fix confirmed). Nothing left here.
1. **Push to GitHub.** ~28 commits are LOCAL; no remote set, `gh` not installed. Existing
   `AI-ERMT-TBD-02/esgrc-backend` is the OLD backend-only repo - the monorepo needs a new repo.
   ⚠️ `deploy.yml` auto-deploys to Railway on push to `main`. (User: **hold off** for now.)
2. ✅ **Frontend tests - DONE (2026-07-08).** 21 Vitest (unit + StatusBadge component) + 2 Playwright
   E2E, all green; wired into CI. Could add more component/E2E coverage over time, but the plan's
   "tests exist" gate is met. `cd frontend && npm test` / `npm run test:e2e` (needs the stack + `npx
   playwright install`).
3. **A real pipeline run.** Needs real Cloudflare R2 + Anthropic keys. `DEMO_MODE` skips only script
   execution, NOT R2. Inputs (ESGRC): `org/{org_id}/reference/input_metric_values_esgrc.csv` +
   `esgrc_performance_json_file.json`.
4. **Settings sub-tabs (minor).** Org tab works on real data. Prompts tab **fixed** (route-shadow, see
   above - was 404, now returns the list). Users tab reads `/auth/users` (a bare array) via
   `r.data.items` → may still show empty; apply the same bare-array fix as Risk if so. (Note: the
   security session fixed 3 Users-tab bugs; re-verify the bare-array shape once Docker is back.)
5. **11 remaining business modules** (MVP = `esgrc` only). Each needs `{module}_chain.py`, script
   wrappers, a `pipeline_definitions` row, `scripts_registry.json` entry.
6. **Repo-01 script fixes** live in the TBD2 copy; Praveen's `AI-ERMT-TBD-02/Repo-01` still has the
   originals - push the fixes there or send a patch.
7. **Open product decisions / business** (from `docs/source_documents/vigilant_lens/`): D4 (ESGRC single vs two-call
   prompt), D5 (R2 retention); demo video, Anthropic ZDR email, privacy-counsel review.
8. **Stale memory** (earlier audit): R2 keys DO have `org/{org_id}/` prefix; super_admin in backend;
   versions bumped; B-16 wired; frontend data pages fixed. Worth correcting so a fresh session
   starts from truth.

---

## Current running state (this machine)
- **History (2026-07-07):** Docker Desktop crashed during a 3-image parallel rebuild (WSL engine
  wedged → `distro installation timeout`). Recovered via an **elevated force-stop of `wslservice`**;
  getting Docker "green" again (factory reset / distro re-registration) **wiped Docker's entire data
  store** - all images, containers, AND volumes for BOTH projects. Rebuilt TBD2 from scratch (no real
  loss; demo data re-seeded). ⚠️ **yusanet's Docker volumes were also wiped** - that project must be
  restarted/re-seeded separately by you.
- **Stack REBUILT & UP (fresh, isolated), running the latest code incl. `05c0ede` + `3f3dbf8`:**
  postgres, redis, esgrc_api (**:8080**, seeded), celery_worker, celery_beat. Images built **one at a
  time** (parallel build is what crashed the engine). Login `admin@demo.com / Demo1234!`
  (also analyst@ / viewer@, same pw). Docs: http://localhost:8080/docs
  - Bring-up cmd used: `docker compose -p tbd2verify -f docker-compose.yml -f <scratchpad>/compose.override.yml
    up -d esgrc_api celery_worker celery_beat` (override maps esgrc_api→**:8080**; named services only so
    nginx isn't started). Seed: `docker exec tbd2verify-esgrc_api-1 python pipeline/scripts/seed_demo.py`.
  - **Note:** `docker` may be missing from PATH after a Docker restart - use the full path
    `C:\Program Files\Docker\Docker\resources\bin\docker.exe`, and prepend that bin dir to `$env:Path`
    so builds find `docker-credential-desktop`.
- **Frontend:** verified live on **:3100** (`frontend-preview` launch config) against the :8080 backend -
  Dashboard + Risk (12 rows) render, no console errors. `frontend/.env.local` → `VITE_USE_MOCKS=false`,
  `VITE_API_TARGET=http://localhost:8080`.
- ⚠️ **yusanet** normally runs on :8000/:6379/:5432 (that's why TBD2's api is on :8080). Currently DOWN
  (volumes wiped, see above). `files (TBD@)` on D: is a mixed dump - yusanet + a WordPress site,
  unrelated to TBD2.

## How to resume
```powershell
docker compose -p tbd2verify ps                 # stack still up? (Docker may be down - see running state)
docker compose -p tbd2verify down -v            # tear down when done
.\run-tests.ps1                                 # 354 tests (208 ESGRC + 146 pipeline)
# frontend on mocks for a clean demo: frontend/.env.local -> VITE_USE_MOCKS=true (or delete it)
```
