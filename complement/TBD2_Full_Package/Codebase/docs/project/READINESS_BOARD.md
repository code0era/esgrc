# TBD2 - Readiness & Blockers Board (2026-07-08)

Purpose: single source of "what's done / what I can run with zero input / what's waiting on a
decision from Danish / what's waiting on a client or the team." Every blocked item is **pre-staged**
so that the instant the input arrives, execution is one step. Nothing behavior-changing ships without
Danish's explicit sign-off (audit standard).

---

## A. DONE - verified this session (real terminal output)
- Apex pipeline runs **end-to-end on ESGRC-only data, fully automatic** (one trigger), on the
  **rebuilt images** - COMPLETED twice, all 8 steps.
- `max_tokens` bump to **8192 live** (GENERAL_RISK out=6636 - impossible under old 4096 cap).
- Tests green: **208 ESGRC + 151 pipeline + 25 Vitest** (Playwright 5 passed earlier this session).
- Module-scoped RBAC live (per-module logins) + RBAC nav E2E.
- Memory reconciled; **31 commits, all local, none pushed** (verified `git remote -v` empty).

---

## B. I CAN RUN NOW - zero external input (await your "go" per sign-off gate)
| # | Item | Behavior-changing? | Notes |
|---|------|--------------------|-------|
| B1 | Playwright E2E re-run (close the matrix) | no | just needs the flaky classifier to settle |
| B2 | **Option A** - each module's Step 2 double-writes `data_for_risk_assessment_{module}.csv` to `org/{org_id}/module_outputs/{module}/…` | yes | "safe now, no blockers." Staged as a ready patch. |
| B3 | **`apex_run_scores`** historical table + parse-and-write in Apex tasks (own-org analytics) | yes | confirmed product vision; Postgres OK to ~30 clients |
| B4 | Proper **singleton-seam test fix** for the `r2` patch flake (import module not name + `_reset_for_testing()`) | no (test-only) | closes the `test_apex_e2e`/truncation flake at the seam |
| B5 | **1M-context beta header** on the LLM client (removes truncation risk entirely) | yes | the "proper fix" noted in the guard bug |
| B6 | SPC_RPN cache-bust rerun to confirm bump on that call too | no (spends ~cents) | optional; GENERAL_RISK already proves the bump |
| B7 | Update `SESSION_HANDOFF.md` + commit | no | routine |

---

## C. BLOCKED ON YOUR DECISION - pre-staged; your answer → one step
| # | Decision | Recommended default | What it unblocks |
|---|----------|--------------------|------------------|
| C1 | **Prompt ownership** - platform-owned (you manage versions across all orgs) vs client-editable | platform-owned for MVP | finalizes the `super_admin` prompt-gate direction |
| C2 | **Reporting cadence** - monthly vs quarterly | quarterly → `max_age_days=180` (~2× cadence, dbt SLA) | Apex preflight staleness + per-org settings default |
| C3 | **Period alignment** for Apex - yes/no | yes (mixed-period aggregation is incoherent) | gates Option D preflight build |
| C4 | **ESGRC prompt** - single Haiku call vs split two-call (D4) | keep single for MVP (~$0.027/run) | post-demo optimization only |
| C5 | **GitHub push / deploy** - approve? | your call (on hold) | see Push Runbook below. ⚠️ `deploy.yml` auto-deploys to Railway on push to `main` |

---

## D. BLOCKED ON CLIENT / EXTERNAL / TEAM
| # | Item | Owner | Pre-staged asset |
|---|------|-------|------------------|
| D1 | **2nd module real data** - makes Apex genuinely multi-module (today it runs on ESGRC alone) | client + Praveen | New-Module Scaffold below |
| D2 | **Anthropic ZDR agreement** - email sales before client contract signs | you send | `docs/team/ZDR_EMAIL_DRAFT.md` (send-ready) |
| D3 | **Real Cloudflare R2 keys** - prod only (local uses MinIO) | you | env already templated; drop keys in `.env` |
| D4 | **Can analytics scripts emit a period label?** (manifest-file vs CSV-column) | Praveen | determines Option D's period-tracking shape |
| D5 | Client contract / privacy-counsel review / demo video / Canada registration | you + Praveen | - |

---

## Pre-staged runbooks

### Push Runbook (execute on C5 = approve)
1. Create a **new** repo under `AI-ERMT-TBD-02` (the existing `esgrc-backend` is the old backend-only repo; this is a monorepo).
2. `git remote add origin <url>` → `git push -u origin main` (31 commits).
3. CI/deploy secrets to set in GitHub: `ANTHROPIC_API_KEY`, `CLOUDFLARE_R2_*` (4), `RAILWAY_TOKEN`, `SECRET_KEY`.
4. ⚠️ **Push = deploy**: `deploy.yml` auto-deploys to Railway on push to `main`. Confirm you want the deploy, or I'll gate the workflow first.

### New-Module Scaffold (turnkey once Praveen delivers a module's scripts + data)
No Apex-level changes needed (the chord already references all 12 modules). Per module:
1. `{module}_chain.py` from the `esgrc_chain.py` template (7-step chain).
2. Script wrappers + a `scripts_registry.json` `scripts` block entry (exact `script_filename` + `output_file_patterns`).
3. `pipeline_definitions` seed row (`pipeline_type`, `config_json.required_input_files`, `steps`).
4. Optional `pipeline_prompts` row.
5. One-liners: `MODULE_PIPELINE_TYPES` in `ESGRC/app/dependencies/auth.py` + frontend `hasModule`/nav.
6. Tests mirroring `test_esgrc_e2e.py`.

### Prod R2 (execute on D3 = keys provided)
Swap MinIO vars for real `CLOUDFLARE_R2_*` in `.env`; `S3_ADDRESSING_STYLE` unset (path-style is MinIO-only). No code change.
