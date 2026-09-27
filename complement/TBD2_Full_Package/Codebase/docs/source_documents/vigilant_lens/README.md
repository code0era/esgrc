# Vigilant Lens / TBD2 - Product & Planning Docs

The original product vision, business case, architecture rationale, and full task
plan for this platform. Extracted from the source `.docx`/`.pdf` received April
2026 and converted to Markdown so the spec travels with the code. **Originals**
are kept under `_originals/`.

Provenance: the source set is archived at
`OneDrive\Documents\TBD2-Archive\01_planning_and_strategy\client_originals\`
(81 files, SHA-256 verified 2026-08-06). An earlier version of this README cited
`D:\Danish Ahmed\Documents\files (TBD@)`, a path that no longer exists.

> **Naming:** repo codename **TBD2** = *AI-ERMT-TBD-02* = "AI Enterprise Risk
> Monitoring Tool". Brand = **Vigilant Lens**. Design system = **Aegis Quantum**.
> PRD working title = "Enterprise Risk Monitoring Platform". All the same product.

## The documents

| File | What it is |
|---|---|
| [01_Architecture_Recommendation.md](01_Architecture_Recommendation.md) | 18-section stack decision doc - every layer evaluated vs a $2k/mo budget, 4-person team, 8-week MVP. The stack we run today. |
| [02_MVP_Project_Plan.md](02_MVP_Project_Plan.md) | Atomic task registry (DB/BE/CE/LLM/FE/INF), sprint plan, decision log, the 3 P0 + P1 blocking decisions. |
| [03_Strategic_Analysis.md](03_Strategic_Analysis.md) | Market sizing + SWOT + segment analysis. Validates/challenges the PRD. |
| [04_Technical_Breakdown_PRD.md](04_Technical_Breakdown_PRD.md) | PRD v1.2 analysis - every screen, FR, user story, the 5-level hierarchy, and 10 unspecced UI gaps. **Arrived as Markdown, so it needed no conversion and has no separate entry under `_originals/`.** |
| `_originals/` | Source `.pdf` + `.docx` + `*.pdf.txt` text dumps. |

## What the product is (one page)

An **AI enterprise-risk-intelligence SaaS**: ingest **1,200+ metrics across 12
business domains**, compute a composite **Enterprise Risk Score (0–100)**, and run
a **two-tier LLM pipeline** (12 parallel module analyses → 1 enterprise synthesis)
to produce board-level risk insight. Five-level data model:
`Enterprise → Module → Sub-Module → Group → Metric`.

**The 12 modules:** brand, shared, **esgrc**, enterprise, customer, service,
product, markets (mkts), business-partner (bspt), integration, ictm, resource.

**Screens:** Enterprise Dashboard · 12 Module Dashboards (SPC + heatmap + AI) ·
Sub-Module/Metric drill-down · AI Decision Hub (ranked risks, 5-step plan, Ask-AI,
PDF/PPT export) · Pipeline Monitor · Settings · Admin. Persistent right-hand
**AI Co-Pilot** on every route.

**Market (Strategic Analysis):** ERM/GRC ~$6B (2025) → ~$12B (2030), 14.8% CAGR;
broader GRC $38B → $138B; only 21% of orgs use a dedicated GRC platform, 59% still
on spreadsheets.

## Locked stack decisions (Architecture Recommendation §18)

React+Vite · Zustand · shadcn/ui + Recharts · Tailwind (Aegis Quantum tokens) ·
FastAPI + Pydantic · **SSE** (not WebSockets) · **Celery + Redis chord** (the 12→1
barrier) · custom **ModelRouter** for pipelines + LangChain for Co-Pilot only ·
**Anthropic** Haiku (Tier-1 module) + Sonnet (Tier-2 enterprise) · PostgreSQL
(LTREE hierarchy, JSONB, RLS from day 1) · Redis (Upstash) · **Cloudflare R2** ·
Supabase Auth / JWT RBAC · **Railway** hosting · GitHub Actions · **Sentry +
Langfuse**. Budget ~$75–165/mo at MVP (ceiling $2k).

## Original vision → current build (status)

| Area | Spec | Current TBD2 build |
|---|---|---|
| Two-tier LLM (12→1 chord) | Celery chord, Haiku+Sonnet | ✅ `pipeline/tasks/apex_chord.py` + `esgrc_chain.py` |
| Modules | 12 domains | ⚠️ **1 of 12 live (esgrc)**; Apex scaffolds all 12 |
| RBAC (SUPER_ADMIN…VIEWER) | 4-role ENUM, append-only audit | ✅ built (super_admin added) |
| Real-time | SSE `/pipelines/.../stream`, `/copilot/stream` | ✅ both endpoints |
| LLM layer | ModelRouter, prompt table (DB, versioned), Langfuse, confidence | ✅ LLMClient + guard + confidence + Langfuse; prompts seeded |
| Storage | Cloudflare R2, per-org paths | ✅ `pipeline/tasks/r2.py` |
| DB | Postgres + pipeline tables | ✅ 4 pipeline tables + 9 ESGRC tables |
| Docker / CI / deploy | compose, GitHub Actions, Railway | ✅ compose + ci.yml + deploy.yml |
| Frontend dashboards | Enterprise Dashboard, 12 Module Dashboards, AI Decision Hub, SPC heatmaps, PDF/PPT export | ❌ **not built** - current FE is ESG/Risk/Compliance/Pipeline/Reports/Settings pages |
| Hardening | slowapi rate-limit, structlog, Sentry init | ❌ missing (see repo `docs/project/SESSION_HANDOFF.md`) |
| Frontend tests | Vitest + Playwright | ❌ none yet |
| Unspecced gaps | Emergency Override, Force Recalc, Rollback, Deploy Watcher, KB RAG | ❌ mostly unbuilt (per PRD, meant to be stubs) |

**Net:** the hard core (two-tier LLM pipeline, RBAC, SSE, R2, one full module) is
built and matches the architecture. The flagship **multi-module dashboard UI** and
**11 remaining modules** are the largest unbuilt scope. See
[SESSION_HANDOFF.md](../../project/SESSION_HANDOFF.md) for the live status and remaining work.

## The blocking decisions the plan called out (P0/P1)

- **P0-1** exact 12-module list · **P0-2** cloud (Railway) vs on-prem · **P0-3** LLM
  provider (Anthropic). All effectively resolved in the current build.
- **P1** heatmap tab-vs-route · alert-severity ENUM (INFO/LOW/MEDIUM/HIGH/CRITICAL)
  · rollback = `is_current` flag (built) · add SSE endpoints (built).
- **Q6 confidence methodology** - MVP uses a heuristic (built); a real statistical
  model is still open.

---
*Not part of this product: the `yusanet` marketing-agent SaaS and a WordPress
crowdfunding site were mixed into the same `files (TBD@)` download dump - excluded here.*
