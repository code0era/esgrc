# TBD2 / Vigilant Lens - Project State

> **CORRECTIONS as of 2026-08-05.** This document is three weeks stale and now
> understates the project. Re-verified against the code today:
>
> - **"11 of 12 modules are not built as full chains"** is wrong. Four module
>   chains exist (ESGRC, Customer, Shared, Business Partner) plus Apex, driven
>   by the module registry (`pipeline/modules.py`) and chain factory.
> - **Both multi-tenant security holes are fixed** in code: the agent trigger is
>   SUPER_ADMIN-gated (`ESGRC/app/routers/agent.py`), as is org creation
>   (`ESGRC/app/routers/auth.py`).
> - **The `np.random` methodology risk is now seeded** and the scenarios are
>   labelled in-code as synthetic. The deeper point stands and is Praveen's
>   call: the scenarios are still noise unrelated to the input data, so the
>   "drivers" ranking derived from them is not evidence about the business.
> - **Test baseline** is 237 ESGRC + 276 pipeline = 513 backend (plus 32
>   frontend), not 418.
> - **§7's "which docs to trust" table is itself stale.** `docs/deployment/setup_and_deployment_guide.md`
>   and `docs/project/production_readiness_audit.md` are now banner-stamped as superseded.
> - **Newly found and fixed 2026-08-05:** a global `UNIQUE(name)` left on
>   `esg_categories` / `compliance_frameworks` by the initial schema meant two
>   organisations could not share a category or framework name. See
>   `docs/daily_reports/2026-08-05.md`.
>
> **FURTHER CORRECTIONS as of 2026-08-07:**
>
> - **"ESGRC is the one fully-built module" and the four-module note above are
>   both out of date.** **11 of 12 module chains now exist** plus Apex, after
>   the analytics owner supplied `input_metric_values_*.csv` and
>   `*_performance_json_file.json` for the remaining modules on 6 Aug.
>   **Integration is the only one left**, blocked on an incomplete JSON: it
>   declares 7 sub-modules but only `API10000` and `AII10000` carry groups.
> - **"The one true blocker: deployment ... DigitalOcean once the Canadian
>   business card lands"** is superseded twice over. The company was registered
>   as **METEOERAIT SOFTWARE P LTD (India)** on 7 Aug, not in Canada, and the
>   deploy approach is now decided and written up in
>   [DEMO_DEPLOY.md](../deployment/DEMO_DEPLOY.md). It is not blocked on a card.
> - **"Open org + first-admin creation"** (item 2 in the HIGH list) was resolved
>   18 Jul. `POST /auth/organisations` is SUPER_ADMIN-gated. Re-verified 7 Aug.
> - **The scenario finding (item 3) is now proven, not suspected.** Two opposite
>   datasets return the identical `Overall Risk = 0.3802845671230959`, because
>   the block reads no client metric values. Still Praveen's call, and still the
>   gate on any external demo.
> - **Test baseline** is now 243 ESGRC + 346 pipeline (plus 32 frontend).
>
> Everything below is preserved as the 16 July snapshot.

**As of 2026-07-16.** Produced by a full-repo deep read (6 parallel readers over ESGRC backend, pipeline, frontend, analytics scripts, infra/CI, docs) cross-checked against the actual files. Severity/ownership below reflect **verified** facts; three agent-reported "HIGH" items were disproved on inspection and are marked ❌ FALSE ALARM so they don't waste anyone's time.

**Verified test baseline this session:** 215 ESGRC + 203 pipeline = **418 passing** (run locally via `ESGRC/.venv2`). Doc figures that say 351 / 354 / 391 are older snapshots - ignore them.

---

## 1. Bottom line

- **What it is:** a multi-tenant AI **ESG-Risk-Compliance SaaS** (brand *Vigilant Lens*). FastAPI + Celery/Redis + Postgres + Cloudflare R2 + Claude, React 19 frontend. Vision = 12 business modules → an Enterprise Risk Score on a 5-level hierarchy; **ESGRC is the one fully-built module**, Apex is the enterprise roll-up.
- **How far along:** the **ESGRC single-module MVP is functionally complete and tested** end-to-end (API, pipeline, frontend, auth, labeling, handoff). The code is in good shape - consistent, few TODOs, real tests.
- **The one true blocker:** **deployment**. The multi-service prod stack is code-complete; it is blocked purely on a **payment card** (HF billing / Render PK-verification wall) → DigitalOcean once the Canadian business card lands. Nothing in the code blocks a deploy.
- **The real must-fix list before a client:** two multi-tenant **security holes** (cross-tenant agent trigger; open org-creation), one **methodology credibility risk** (regression "risk scenarios" are computed from `np.random` noise), and the deploy/secrets provisioning. Everything else is polish or v1.1.
- **Biggest scope reality:** **11 of 12 modules are not built as full chains.** The 12 handoff CSVs exist (Praveen delivered them) and Apex runs on them, but only ESGRC has the 5-step analytics chain + dashboards. Full 12-module product is months out and gated on Praveen's per-module definitions.

---

## 2. Architecture (verified)

Monorepo, three layers; the API process and the Celery worker are separate containers behind nginx.

```
Frontend (frontend/, React19+Vite+TS)         ── real ~90% app, 8 pages, SSE, react-query, RBAC
        │  /api  (Vite proxy)
        ▼
ESGRC backend (ESGRC/app, FastAPI+SQLAlchemy2) ── auth, ESG/Risk/Compliance CRUD, scoring,
        │   mounts pipeline + copilot routers      nightly APScheduler agent, /org/snapshot
        │   (main.py imports the pipeline pkg - the two are NOT independently deployable)
        ▼
Pipeline (pipeline/, Celery+Redis)             ── ESGRC 7-step chain, Apex 8-step nested chord,
        │                                          LLMClient (Claude), labeling, module handoff
        ▼
Analytics scripts (modules/esgrc/analytics_scripts/)   ── Praveen's CHAID/SPC/correlation/regression,
        run as subprocesses via ScriptRunner       driven by scripts_registry.json
        ▼
Storage: Postgres (state) · Redis (broker+live UI) · Cloudflare R2 (artifacts; MinIO locally)
LLM: Claude Haiku (module) → auto-upgrades to Sonnet on large context; Sonnet (enterprise)
```

**Data journey (per module):** raw CSV + perf JSON → 5 analytics steps (low-performer → hierarchy split → correlation/CHAID/Fourier → SPC/RPN → regression) → combine `.txt` → Claude writes a risk report. **Only derived reports reach Claude, never raw client data.** Each module's step 2 emits `data_for_risk_assessment_{module}.csv` + a provenance manifest to a stable path; Apex step 1 consumes whatever module handoffs exist (tolerates missing modules; needs at least ESGRC).

**Labeling (this week's work):** Claude reasons on codes; business names are substituted at serve time with a validation gate + fail-safe. `response_text` stays codes (source of truth); `response_text_labeled` / `labels[]` / `labeling_status` are the display view.

---

## 3. What's built vs. not

| Area | Built | Not built / partial |
|---|---|---|
| **Backend API** | Auth+RBAC+multi-tenant, ESG/Risk/Compliance CRUD, scoring, dashboard, org snapshot, nightly agent (rule + LLM) | Org self-signup (onboarding); a few RBAC gaps (§4) |
| **Pipeline** | ESGRC 7-step chain, Apex 8-step chord, R2 I/O, SSE, Claude client, confidence, labeling, handoff+provenance, freshness API | Chord error-handlers not wired (failed runs don't mark downstream SKIPPED); preflight vs step-1 module-count disagree |
| **Analytics** | All 10 scripts run clean (ESGRC + L0); filenames reconcile with registry | 11 modules' script sets; `np.random` scenario methodology; hardcoded date/weights |
| **Frontend** | 8 real pages, auth/token refresh, SSE monitor, module-RBAC, tests | **Shubham's 3 jobs not started**; flagship multi-module dashboards; hard-refresh logout |
| **Labeling/handoff** | Serve-time names, validation gate, provenance manifests, `/handoff-provenance` | Metric-level names exist for ESGRC only (others pass through) |
| **Infra** | Complete multi-service prod compose, nginx TLS conf, CI (418 tests + build), secrets hygiene | **No deploy live** (card); no DigitalOcean artifact; TLS certs; a few prod-compose config gaps |
| **Docs** | Extensive | Several stale (model IDs, deploy target); 4 strategy/labeling docs live only on an unmerged branch |

---

## 4. Gaps & risks (verified, severity-ranked)

### ❌ FALSE ALARMS (disproved on inspection - do not action)
- **"Real Anthropic key in `.env.example`"** - it's a placeholder (`sk-ant-REPLACE_WITH_YOUR_KEY`). Real key is only in the untracked, gitignored `.env`. Hygiene is correct.
- **"L0 regression `BASE_DIR` unpatched, MVP-blocking"** - the script already uses `os.getcwd()` (`AI_ready_..._L0_19_0.py:21`). Only the *comments* in `apex_chord.py` / `scripts_registry.json` are stale (LOW cleanup).
- **"Scripts not in `SCRIPTS_DIR` → every real run fails"** - the worker image copies them in (`pipeline/Dockerfile:34` + `ENV SCRIPTS_DIR`). Real gotcha is **local non-Docker runs only** (set `SCRIPTS_DIR=modules/esgrc/analytics_scripts`).

### 🔴 HIGH - fix before a client touches it
1. **Cross-tenant agent trigger.** `POST /agent/run` & `/agent/llm-run` require only per-org ADMIN (`agent.py:141,170`) but the runner processes **all organisations** (`runner.py:67-82`) and spends the platform LLM budget; reading results needs SUPER_ADMIN (`agent.py:69`). → gate both triggers to SUPER_ADMIN (or org-scope them). **Owner: Danish.**
2. **Open org + first-admin creation.** `POST /auth/organisations` is unauthenticated and mints a full-module ADMIN; its own docstring says restrict to super-admins (`auth.py:67-102`). → gate it. **Owner: Danish.**
3. **Regression "risk scenarios" are statistical noise.** Both regression scripts derive headline scenarios/drivers/actions from unseeded `np.random.normal` (`regression_ESGRC:66`, `regression_L0:168`) - different every run, feeds straight into the client-facing Claude report. → replace with real-data scenarios or clearly label illustrative. **Owner: Praveen** (product decision with Danish).
4. **Deployment blocked on payment card.** Multi-service stack is code-ready; HF/Render walls hit; no DigitalOcean artifact. **Owner: Danish** (blocked on the Canadian business card).

### 🟠 MEDIUM - correctness / reliability / prod-readiness
5. **Two schema sources of truth.** Prod builds schema via Alembic; tests via `create_all()` (`ESGRC/conftest.py:81`). This already leaked a bug (missing `metric_code`, fixed in `20260705`). Verify a full `alembic upgrade head` against **real Postgres** (enum/JSONB paths never run in CI). **Owner: Danish.**
6. **Nested chords in Apex** (`apex_chord.py:582-592`) - a chord as another chord's body is a fragile Celery construct; no automated guard. Needs a live-broker end-to-end run to trust. **Owner: Danish.**
7. **Co-Pilot task may be unregistered on the worker** - `stream_copilot_response` is defined in `copilot_router.py` but `celery_app.py` only imports `esgrc_chain`/`apex_chord`. If the worker never imports it, copilot enqueues a task it can't run. **Verify. Owner: Danish.**
8. **Chord error-handlers defined but not wired** (`esgrc_chain.py:49-54`, `apex_chord.py:488-499`) → failed runs don't mark downstream steps SKIPPED (degraded UX, not data loss). **Owner: Danish.**
9. ~~**Preflight vs step-1 disagree on module count**~~ **RESOLVED 2026-08-17.** `check_apex_preflight`/`check_esgrc_preflight` (`r2.py`) were never actually called anywhere - `trigger_pipeline`'s own inline, config-driven `file_exists()` loop is the real preflight and doesn't have this disagreement. Deleted the dead functions rather than relaxing them.
10. **Frontend endpoint mismatch for labeled fields** - Reports reads `run.llm_outputs` embedded in the runs-list response, but the new `response_text_labeled`/`labels` are only on `GET /recommendations` & `/llm-outputs/{id}`. Either add the labeled fields to the embedded objects or Shubham re-wires. **Decision: Danish → then Shubham.** *(Most likely thing to silently break Job 1.)*
11. **Hard-refresh logs the user out** - token is memory-only with no silent-refresh-on-load; a page reload kicks to `/login` (`ProtectedRoute.tsx:14`). A demo will hit this immediately. → bootstrap `/auth/me` on mount. **Owner: Shubham + Danish (confirm cookie-only `/auth/me`).**
12. **Prod compose config gaps:** ~~worker inherits the root-owned `/tmp/tbd2` bind that `local` fixes but `prod` doesn't~~ **RESOLVED (`docker-compose.prod.yml`: `celery_worker.volumes: !override []`, same fix `local` already used).** Still open: no `restart:` policies; `nginx/certs/` absent; no compose healthchecks. All config, not code. **Owner: Danish.**
13. **`count_tokens` unavailable on anthropic 0.40.0** → guard/preflight use a `len//3` estimate, so the Haiku→Sonnet upgrade + truncation run on an approximation. Safe with current headroom; revisit on SDK bump. **Owner: Danish.**
14. **Confidence scoring** is ESGRC-coupled, period-string-ordered, returns 0.5 on any error (silent degrade). Heuristic-only for MVP by decision. **Owner: Praveen/Danish.**

### 🟡 LOW - tech-debt / cleanup
- Role changes lag ≤30 min (token asserts role; deactivation is immediate) - documented, decide if acceptable.
- Manual `PATCH /esg/metrics/{id}` can set an arbitrary score bypassing the benchmark.
- N+1 in ESG dashboard query (`crud.py:1060`).
- Dead/duplicate code: unused `.pth` model training every run, duplicate L0-regression blocks, orphan `text-report-combiner.py`, dead `write_llm_to_redis` Redis key, `audit_scripts.py` looks up the wrong filename, hardcoded `ANALYSIS_DATE="2026-01-07"`, hardcoded L0 `custom_weights`.
- SSE passes JWT as a URL query param (EventSource can't set headers).
- GDPR erase misses the module-handoff CSV + manifest.
- Stray duplicate migration at repo-root `alembic/versions/`.
- Frontend branding hard-coded to ESG in several spots (Job 3 surface).

---

## 5. Remaining work - who does what

### Danish (backend / AI / integration / devops)
| Task | MVP-critical | Blocked by |
|---|---|---|
| Gate `/agent/run` + `/agent/llm-run` to SUPER_ADMIN | **Y** | - |
| Gate `POST /auth/organisations` (+ decide signup model) | **Y** | product decision |
| Verify full `alembic upgrade head` on real Postgres | **Y** | PG env |
| Non-DEMO end-to-end run (ESGRC + Apex) on live Redis/R2/Anthropic - validates nested chords, handoff, scripts | **Y** | keys + card |
| Confirm worker registers the copilot task | **Y** | - |
| Decide labeled-fields delivery (embed vs re-wire) for Shubham | **Y** | - |
| Deploy: DigitalOcean artifact + TLS certs + prod-compose fixes (`/tmp/tbd2`, `restart:`, healthchecks) + real `.env`/R2 | **Y** | **card** |
| ~~Relax `check_apex_preflight`~~ done (deleted, 2026-08-17); wire chord error handlers; fix `deploy.yml` build context | N | - |
| Security review lists #5, #7 already flagged | - | - |

### Praveen (analytics / 12-module defs / confidence)
| Task | MVP-critical | Blocked by |
|---|---|---|
| Replicate the 5 ESGRC scripts for the other 11 modules (column IDs, filenames, registry keys) | N for MVP · **Y for full product** | his per-module definitions |
| Replace `np.random` scenario methodology (or label illustrative) | credibility **Y** | product decision |
| De-hardcode `ANALYSIS_DATE`, L0 `custom_weights`; strip dead Flask/torch/graphviz + unused `.pth`; delete orphan combiner; add CSV-existence guards | N | - |
| Push the 3 script fixes to upstream Repo-01 (avoid drift) | N | - |
| Fix `module_mapping.csv` at source (already fixed in our copy) | N | - |

### Shubham (frontend) - all 3 jobs, contracts ready
| Task | MVP-critical | Blocked by |
|---|---|---|
| **Job 1:** render `response_text_labeled` + `labels[]` chips/tooltips + `labeling_status` (Reports, StepCard, Pipeline) | **Y** | Danish decision #10 |
| **Job 2:** "Data as of · Run #" badge from `GET /pipelines/handoff-provenance` | **Y** | - |
| **Job 3:** drive step names + module switcher from backend, de-hardcode ESG branding | Y (for module-agnostic) | mild backend support |
| Fix hard-refresh logout (bootstrap `/auth/me`) | Med | Danish confirm |
| Verify download/file endpoints; fill/deferred Integrations tab | Med/N | - |

### +1 (unassigned - see decisions)
- Flagship multi-module dashboard UI (Enterprise/Module dashboards, AI Decision Hub, SPC heatmaps, PDF/PPT export) is unbuilt and unowned. Big scope; needs an owner.

---

## 6. Decisions needed from you (Danish)
1. **Who is the "+1"** and what do they own? (affects the ownership table + the flagship-dashboard gap).
2. **Current MVP target date** - the roadmap dates (ESGRC 10 Jul, Apex 31 Jul) have passed; is there a live target, or does the closure meeting set it?
3. **Signup model** - self-serve org signup vs. manual/super-admin provisioning? (gates the org-creation fix + the "user module" agenda item).
4. **Labeled-fields delivery** - add to embedded `llm_outputs`, or have Shubham use `/recommendations`? (unblocks Job 1 cleanly).
5. **Regression scenario methodology** - fix the `np.random` scenarios before any client sees a report, or label them illustrative for now?
6. **Role-change propagation** - accept the ≤30-min lag, or add token versioning?
7. **MVP closure criteria + feature-freeze date** (your agenda item) - I have a concrete proposal ready.

---

## 7. Which docs to trust
- **Authoritative live state:** `docs/project/SESSION_HANDOFF.md` (this file supersedes it going forward).
- **Current-but-slightly-behind:** `README.md`, `HOW_IT_WORKS.md` (module data + test counts lag).
- **STALE - do not trust for model IDs or deploy target:** `docs/deployment/setup_and_deployment_guide.md`, `docs/project/production_readiness_audit.md` (say `claude-3-5-sonnet-20240620`, Railway).
- **Historical intent (April 2026), partly superseded:** `docs/source_documents/vigilant_lens/*`.
- **Note:** the strategy/labeling/drift/hallucination docs (`CONTEXTUAL_LABELING_PROPOSAL.md`, `DRIFT_TEST_RESULTS.md`, `LABELING_HALLUCINATION_ANALYSIS.md`, `VIGILANT_LENS_STRATEGY_2026-07.md`) are **not on this branch** - they live on the unmerged `docs/strategy-and-labeling-analysis` branch (pushed, PR not created). Not lost; just not merged.
- Deploy-target references to **Railway** are obsolete; the plan is DigitalOcean. `deploy.yml` (Railway) is disabled and has a wrong build context.

---

## 8. The one-paragraph answer
The ESGRC single-module MVP is built and tested; the code quality is genuinely good. To put it in front of a client you need, in order: (1) fix two multi-tenant security holes and decide the regression-scenario methodology; (2) do one real non-DEMO end-to-end run against live keys; (3) unblock deployment (card → DigitalOcean) and finish Shubham's 3 frontend jobs (contracts are ready). Everything else - the other 11 modules, the flagship dashboards, confidence modelling - is post-MVP and mostly waits on Praveen's per-module definitions and a decision on MVP closure.
