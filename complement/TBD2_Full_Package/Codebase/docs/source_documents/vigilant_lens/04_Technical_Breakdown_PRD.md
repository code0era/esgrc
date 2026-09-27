# Enterprise Risk Monitoring Platform - Technical Breakdown
### Prepared for Engineering & Technical Lead | Based on PRD v1.2 + All UI Artefacts
**Source artefacts analysed:** `Enterprise_Risk_Platform_PRD_v1.2.pdf` (20 pages), `enterprise_dashboard/code.html`, `module_dashboard_financials/code.html`, `sub_module_detail_view/code.html`, `ai_decision_hub/code.html`, `pipeline_monitor/code.html`, `vigilant_lens_risk_management_system/code.html`, `heatmap_of_module_dashboard_financials/screen.png`, `enterprise_risk_monitoring_prd_summary.html`, `handoff_implementation_guide.html`, `aegis_quantum/DESIGN.md`

---

## 1. Product Identity & Naming

The PRD uses the working title **"Enterprise Risk Monitoring Platform"** throughout. However, the design artefacts have already adopted the product identity **"VIGILANT LENS"** as the brand name visible in all UI screens, with the design system internally named **"Aegis Quantum"** (per `handoff_implementation_guide.html`). The PRD notes: *"Confidential branding and product name to be applied at a later stage; PRD uses a working title."* As technical lead, be aware this divergence exists - the frontend codebase and assets already use Vigilant Lens as the live label. Align on the canonical name before the API contract freeze on Week 1 Day 3.

---

## 2. What This Product Is

An **AI-powered enterprise risk intelligence web application** that ingests 1,200+ operational metrics across 12 business domains, computes a composite **Enterprise Risk Score (0–100)**, and uses a **two-tier LLM processing pipeline** to generate human-readable insights at both the domain level and the overall enterprise level. The platform surfaces this intelligence through a five-level drill-down hierarchy:

```
Enterprise → Module (Domain) → Sub-Module → Group → Metric
```

The PoC (Proof of Concept) is confirmed complete, including Module-level and Enterprise-level LLM integration. V1.0 MVP is the productisation effort - not greenfield AI development.

**Who uses it:**

| Persona | Role | Primary Use |
|---|---|---|
| CRO / Risk Manager | Enterprise | Domain-level granular analytics |
| CFO / Strategy Head | Conglomerate | Consolidated view, investor exports |
| COO / Business Owner | SME | Affordable, clear risk overview |
| Operations / Network Risk Head | Telecom | SLA-linked domain monitoring |
| Super Admin | Internal | User management, RBAC, config |

---

## 3. Analytical Hierarchy - The Core Data Model

This is the backbone that every engineering decision must respect.

```
Enterprise Risk Score
└── Module 1 (e.g., Financial Liquidity)
    └── Sub-Module (e.g., Interest Rate Risk)
        └── Group (e.g., Treasury Core, Asset-Liability)
            └── Metric (e.g., DV01 Delta, Macaulay Duration)
```

**Confirmed from UI artefacts (sub_module_detail_view):** The Financial Module contains at minimum the following concrete metrics under "Interest Rate Risk":
- Short-Term Duration: `DV01 Delta` (value: 42.84, +12% trend), `Macaulay Duration` (3.41, flat), `Convexity Ratio` (1.88, -2%)
- Long-Term Duration: `Weighted Average Life` (12.5y, limit 15.0y), `Yield Curve Sensitivity` (0.94, limit 1.00)

**From the module_dashboard_financials screen**, the Financial Module sub-architecture shows:
- Sub-Module: **INTEREST RATE RISK** - 12 active metrics, status: Optimised
- A second unnamed Sub-Module - 8 active metrics, status: Volatility

Top-level metrics visible: `LIQUIDITY RATIO` (142.8%, IN CONTROL, UCL: 110%), `UNSECURED FUNDING` ($12.4B, OUT OF SPEC, UCL: $10.0B), `INTERBANK EXPOSURE` (8.2%, STABLE, MEAN: 8.5%)

**Key engineering implication:** The database schema must support the full five-level hierarchy as a tree structure. The PRD states 12 modules × 100+ metrics each = 1,200+ metrics total. However, the exact 12-module list is an **open question (Q3)** - not yet locked. The schema must be designed to be data-driven (not hardcoded), with Sub-Module and Group definitions manageable without code changes (NFR: Maintainability).

---

## 4. Functional Requirements - Feature by Feature

### 4.1 Enterprise Dashboard (FR-01 to FR-07)

**Screen artefact:** `enterprise_dashboard/code.html` + `vigilant_lens_risk_management_system/code.html` (these appear to be the same screen in two versions)

| FR | Feature | Priority | Acceptance Criteria |
|---|---|---|---|
| FR-01 | Composite Enterprise Risk Score (0–100) + trend vs prior period | Must Have | Renders within 3s; trend direction accurate |
| FR-02 | 12 Domain Cards - colour-coded (Green/Yellow/Red) + mini-sparkline | Must Have | All 12 displayed; thresholds configurable |
| FR-03 | AI Confidence % alongside Enterprise Score | Must Have | Sourced from validated projection model |
| FR-04 | Top 5 Risk Highlights - AI-generated priority list | Must Have | Refreshes with each pipeline run |
| FR-05 | One-paragraph AI Executive Summary card | Must Have | LLM-generated; max 200 words; refreshes on demand |
| FR-06 | Real-time Refresh button + last-run timestamp | Must Have | Manual refresh triggers pipeline status check |
| FR-07 | Trend chart (Enterprise Score over last 4–8 periods) | Should Have | Selectable period range; hover tooltip |

**Evidence from UI screen:**
- Score displayed as `84.2` with `+1.4 vs prior period` (arrow_upward icon)
- AI Confidence shown as `98.4%`
- "Data Freshness: REAL-TIME" badge visible
- Risk Trajectory panel shows: Historical Avg (6mo): 76.4, Projected (Q4): 89.1, Volatility Index: 12.4%
- Co-Pilot sidebar on the right shows three priority anomalies ranked `01`, `02`, `03` with descriptions
- Timestamp format: `2023.10.27 | 14:32:01 UTC` - note: this is sample/mock data, year will update
- A "SYNCHRONIZE" button maps to FR-06's refresh requirement
- Version indicator `v4.8.2` visible in header - implies the platform itself should surface a version number

**Gap for engineering:** The Co-Pilot sidebar shows 3 anomalies in the prototype but FR-04 specifies Top 5 risks. The sidebar UI must accommodate at minimum 5 items without overflow issues.

---

### 4.2 Module Dashboard × 12 (FR-08 to FR-12)

**Screen artefact:** `module_dashboard_financials/code.html`

| FR | Feature | Priority | Acceptance Criteria |
|---|---|---|---|
| FR-08 | Module Score + benchmark vs previous period | Must Have | Score and delta clearly displayed |
| FR-09 | Key Metrics Grid - SPC charts per Metric, organised by Sub-Module and Group | Must Have | SPC charts for 100+ metrics; Sub-Module grouping visible |
| FR-10 | Heatmap view of Module metric performance across Sub-Modules and Groups | Should Have | Colour intensity scales with deviation; Sub-Module/Group labels shown |
| FR-11 | AI Insight Panel - Module-level LLM insights (intra-module correlation) | Must Have | Sourced from Module report submitted to LLM API; includes correlation findings and recommendations |
| FR-12 | Drill-down to Sub-Module / Group / Metric | Must Have | Click on Sub-Module/Group/Metric navigates to detail level |

**Evidence from UI screen:**
- Module Health Index: `88.4 / 100`, `+4.2% VS PREV`, labelled "Top 5% Tier"
- Benchmark Distribution shows: LOWER BOUND / MEDIAN / TARGET thresholds
- Performance Matrix shows a grid with axes: Treasury, Lending, Retail, Wealth, Custody (columns) × Liquidity, Leverage, Exposure (rows), with CRITICAL/NOMINAL colour coding - this is the heatmap implementation for FR-10
- Core Metrics Engine section shows individual metric cards with SPC status (IN CONTROL / OUT OF SPEC / STABLE)
- "SPC ACTIVATED" indicator; "Export Dataset" and "Configure Thresholds" action buttons
- Module Sub-Architecture panel lists Sub-Modules with chevron drill-down (FR-12)
- Co-Pilot sidebar shows active LLM analysis: correlation between `Liquidity Coverage` and `Net Interest Margin` with 12% volatility increase prediction
- Breadcrumb: `Core Banking > Financial Liquidity Module`

**Separate heatmap screen:** `heatmap_of_module_dashboard_financials/screen.png` is a standalone heatmap view of the Financial Module - confirming the heatmap is either a modal/toggle within the Module Dashboard or a separate sub-screen. The PRD FR-10 marks it "Should Have." **Engineering decision needed:** is this a tab/toggle on the Module Dashboard or a separate routed screen?

---

### 4.3 Sub-Module / Group / Metric Detail Screen (FR-12 dependent)

**Screen artefact:** `sub_module_detail_view/code.html`

**Evidence from UI:**
- Breadcrumb: `Core Banking > Financial Liquidity > Interest Rate Risk`
- LIVE_DATA_STREAM badge - implies this screen reflects real-time or near-real-time data
- EXPORT REPORT and FORCE RECALC buttons
- Metric Distribution Matrix split into "NORMAL" and "CRITICAL" zones
- Short-Term and Long-Term Duration metric groups with individual metric cards showing value, trend arrow, and percentage change
- Each long-term metric shows its hard limit (e.g., "Limit: 15.0y", "Limit: 1.00") and a compliance status badge (OKAY, STABLE)
- SPC chart renders for DV01 Delta History with x-axis timestamps: 09:00 / 10:30 / 12:00 / 13:30 / CURRENT
- Yield Curve Sensitivity shown as a separate chart
- Pipeline Execute Log (timestamped to the second): data ingestion, anomaly check, threshold breach detection, recalculation steps
- AI Correlation Analysis panel: correlation coefficient surfaced (`r=0.92` between Yield Curve Sensitivity and Long-Term Duration), liquidity offset noted, "GENERATE FULL REPORT" CTA
- Critical Alerts: DV01 Delta Breach (Level 4), Yield Volatility (Level 2) - implies a severity level system (at minimum 1–4)
- AI Co-Pilot sidebar shows Suggested Actions: "Run sensitivity stress test", "Compare with 30-day historical baseline", "Audit execution log for ingest errors"
- Module Knowledge Base: links to `Interest Rate Risk Policies.pdf` and `DV01 Calculation Methodology`

**Engineering implication - Alert severity levels:** The screen shows "Level 4" and "Level 2" alerts. The PRD defines Green/Yellow/Red thresholds (80–100, 60–79, <60) but does not specify a numeric severity level schema (1–4+). This needs to be defined as part of the data model.

---

### 4.4 AI Decision Hub (FR-13 to FR-19)

**Screen artefact:** `ai_decision_hub/code.html`

| FR | Feature | Priority | Acceptance Criteria |
|---|---|---|---|
| FR-13 | Consolidated enterprise-level LLM analysis from all 12 Module outputs | Must Have | Full report rendered; sourced from two-tier LLM processing |
| FR-14 | Executive Summary section | Must Have | Clearly labelled; max 400 words |
| FR-15 | Top Risks - ranked list with severity | Must Have | Minimum 5 risks with domain attribution |
| FR-16 | 5-Step Action Plan | Must Have | Numbered steps; each actionable and domain-attributed |
| FR-17 | Ask AI - natural language chat | Must Have | Returns LLM response within 10s |
| FR-18 | Export Report - PDF and PowerPoint | Must Have | Formatted file; downloadable |
| FR-19 | Confidence Score % per risk projection | Must Have | Calculated from validated statistical model |

**Evidence from UI screen:**
- Report ID displayed: `VL-AI-992-DELTA` - implies a structured report identifier format
- Executive Summary text (sample) references: cross-module synthesis, 88% operational stability, 14% regulatory friction increase within 72 hours, 94% predictive confidence
- 5-Step Action Plan with domain hashtags: `#FINANCE`, `#SUPPLY-CHAIN`, `#CYBERSECURITY`, `#COMPLIANCE`, `#HR-OPERATIONS`
- Ranked Risk Vectors table showing three risks in the prototype:
  1. Cybersecurity - SEVERITY: CRITICAL - 98% model confidence - $12.4M potential impact
  2. Global Logistics - SEVERITY: HIGH - 82% confidence - 4-Day Lag impact
  3. Fiscal Policy - SEVERITY: MED - 64% confidence - Marginal impact
- Module Integrity row at bottom showing M1–M12 status indicators
- Export buttons: EXPORT PDF (picture_as_pdf icon) and EXPORT POWERPOINT (present_to_all icon)
- Ask AI chat shows a sample exchange - question about Module 7 / APAC shipping correlation, answer includes "84% logical coupling" with explicit action recommendation
- "Synthesizing..." label visible - suggests a loading/streaming state needs to be implemented for the AI response

**Gap:** The prototype only shows 3 ranked risks. FR-15 requires minimum 5. The UI layout must handle 5+ risk rows gracefully, including scroll or pagination if the LLM returns more.

---

### 4.5 Pipeline Monitor (FR-20 to FR-23)

**Screen artefact:** `pipeline_monitor/code.html`

| FR | Feature | Priority | Acceptance Criteria |
|---|---|---|---|
| FR-20 | Live execution status for all 12 pipelines (Running / Success / Failed / Pending) | Must Have | All 4 statuses supported |
| FR-21 | Last successful run timestamp per domain | Must Have | Accurate to minute |
| FR-22 | Error log viewer per pipeline per run | Must Have | Error details expandable; last 5 runs retained |
| FR-23 | Manual pipeline trigger (Admin only) | Should Have | Triggers pipeline; status updates in <5s |

**Evidence from UI screen:**
- System status header: `SYSTEM STATUS: OPERATIONAL · 12 ACTIVE DOMAINS`
- System metrics: Overall Health `98.4%`, Active Alerts `02`, Processing Rate `12.4GB/s`
- Pipeline status cards shown (partial): Market Volatility (RUNNING, 64% complete), Transaction Fraud (SUCCESS), Core Infrastructure (FAILED, ERROR 502), Entity Screening (PENDING, next run 04:00 AM), Geopolitical Risk (SUCCESS), Legal Compliance (SUCCESS), Supply Chain Log (FAILED, TIMEOUT, 4 retries)
- Error Log Viewer table with columns: TIMESTAMP, MODULE, EVENT, STATUS - with expandable rows (`expand_more` icon)
- Sample error entries: `FATAL: DATABASE_CONNECTION_REFUSED` with detail (connection endpoint, SSL error), `ERROR: API_RATE_LIMIT_EXCEEDED`, `INFO: SHARD_REBALANCING_COMPLETE`, `INFO: PIPELINE_INITIALIZED`
- Admin Control panel with: Trigger Global Resync, Purge Data Cache, Rollback Last Domain
- Latency Monitor chart visible (14:00 to 14:30 range)

**Engineering implications:**
- The "RUNNING: 64% COMPLETE" state implies the pipeline exposes progress percentage - the backend must emit this. Consider whether Celery task state or a custom progress field handles this.
- "Rollback Last Domain" is a significant destructive operation - requires admin auth enforcement.
- The error log retention requirement (last 5 runs per pipeline) is specified in the PRD. The DB schema must model this explicitly.
- `12.4GB/s` processing rate shown - this appears to be sample data but implies a metrics dashboard that should source from real pipeline instrumentation.

---

### 4.6 Settings Module

Defined in PRD, no dedicated screen artefact. Requirements:
- LLM Configuration: API key, model selection, temperature, max tokens
- Risk Threshold Configuration: Green/Yellow/Red thresholds per domain and per metric
- Module & Sub-Module Management: enable/disable Modules; manage Sub-Module and Group metadata
- Reporting Period Settings: define quarter, half-year, annual period boundaries
- Export Templates: configure PDF/PowerPoint branding

**Engineering implication:** The "Module & Sub-Module Management" feature means the hierarchy is database-driven and editable at runtime - engineers must not hardcode module/sub-module/group names anywhere. The PRD explicitly states: "Sub-Module and Group definitions manageable without code changes."

---

### 4.7 Admin Module

- User Management: create, edit, deactivate users
- RBAC: roles: Super Admin, Admin, Analyst, Viewer
- Audit Log: all user actions + config changes + exports, with timestamp, user ID, action detail
- SSO/SAML: configuration placeholder only for V1.0

**From UI screen (sidebar):** Admin nav item is marked with `admin_panel_settings` icon and is confirmed to only appear for Admin/Super Admin roles - this must be enforced both in the frontend route guard and at the API layer.

---

## 5. Non-Functional Requirements

| Category | Requirement | Target |
|---|---|---|
| Performance | Dashboard cold load | < 3 seconds |
| Performance | LLM API response | < 10 seconds |
| Scalability | Metric volume | 1,200+ metrics; extensible to 20+ domains |
| Scalability | Concurrent users | 100+ |
| Reliability | Uptime | 99.5% |
| Security | In-transit encryption | TLS 1.2+ |
| Security | At-rest encryption | AES-256 |
| Security | RBAC | Enforced on all endpoints; no role escalation |
| Security | API keys | Encrypted secrets vault; never in code |
| Compliance | Audit trail | All user actions logged with timestamp + user ID + detail |
| Usability | Resolution support | 1280px+ desktop |
| Maintainability | Module pipelines | Each independently deployable |

---

## 6. System Architecture

### 6.1 Recommended Technology Stack (from PRD Section 7)

| Layer | Component | Technology |
|---|---|---|
| Presentation | React SPA | React.js / Next.js, TailwindCSS, Recharts / D3.js |
| Application | Backend API | Python (FastAPI / Django REST), Celery for async |
| AI Integration | Two-tier LLM Layer | Anthropic / OpenAI / Gemini API (configurable) |
| Data | Storage | PostgreSQL, Redis (cache), S3-compatible object storage |
| Infrastructure | Deployment | Docker / Kubernetes, Cron / Celery Beat |

**From design artefacts (already implemented in prototype):** Tailwind CSS is confirmed - the HTML files embed a full Tailwind config with custom tokens. Font stack: Space Grotesk (headlines) + Inter (body/labels), both via Google Fonts. Icon library: Google Material Symbols Outlined.

### 6.2 Two-Tier LLM Data Flow

```
Tier 1 (runs in parallel for all 12 modules):
  Module Pipeline Script
    → processes 100+ Metrics (by Sub-Module and Group)
    → generates structured Module Report (including intra-module correlations)
    → submits to LLM API → parses response → stores Module AI output

Tier 2 (runs after all 12 Tier 1 calls complete):
  Report Orchestrator
    → aggregates all 12 Module Reports + Module AI outputs
    → submits consolidated Enterprise Report to LLM API
    → parses Enterprise response → stores as authoritative Enterprise Risk Intelligence

Confidence Engine:
  → validates all risk projections at both tiers
  → confidence % stored with each output

Frontend:
  → fetches scores, Module AI outputs, Enterprise AI output via REST API
  → Users query via Ask AI co-pilot (relay to LLM API with context)
```

**Key sequencing constraint from PRD Section 7.3:** "All 12 Module-level calls must complete before the Enterprise-level call is triggered." This means the pipeline orchestrator must implement a barrier/join pattern. Celery workflows (chord or group + callback) are the natural fit here.

### 6.3 LLM Integration Specifics

- LLM provider is **configurable from Settings** (model-agnostic design) - which provider is confirmed as **Open Question Q1**
- Separate prompt templates for Module-level vs Enterprise-level calls - both version-controlled and editable by Super Admin (this means prompt templates must be stored in the DB, not in code)
- Rate limiting + retry logic required in the LLM API wrapper
- **Response caching:** identical Module inputs return cached LLM output within the same pipeline run; Enterprise call cache invalidated when any Module output changes
- LLM outputs stored with a structured schema to support future cross-period comparison
- API keys: encrypted secrets vault, never in frontend or logs

---

## 7. Design System - "Aegis Quantum" / "Vigilant Lens"

This is documented in `aegis_quantum/DESIGN.md` and is the authoritative specification for your UI/UX partner. Key details the engineering team must understand:

### 7.1 Colour Tokens (all defined in Tailwind config - confirmed in HTML artefacts)

| Token | Hex | Use |
|---|---|---|
| `surface` / `surface-dim` | `#041329` | Deepest background layer |
| `surface-container-low` | `#0d1c32` | Sidebars / utility zones |
| `surface-container` | `#112036` | Standard container |
| `surface-container-high` | `#1c2a41` | Primary content cards |
| `surface-container-highest` | `#27354c` | Hovered / active elements |
| `surface-container-lowest` | `#010e24` | Input fields (stealth state) |
| `primary` | `#b0c6ff` | Highlights / CTAs |
| `primary-container` | `#003582` | CTA gradient end |
| `tertiary` | `#00daf3` | Low risk indicator / data accents |
| `error` | `#ffb4ab` | High risk indicator |
| `on-surface` | `#d6e3ff` | Primary text |
| `on-surface-variant` | `#c3c6cf` | Secondary text |

**The "No-Line" Rule:** Separation between sections must be achieved exclusively through background colour shifts, not 1px borders. The only exception is a 1px `primary` bottom-border on focused input fields.

### 7.2 Typography

- Headlines/Display: **Space Grotesk** (geometric sans-serif)
- Body/Labels/Data: **Inter**
- Label metadata: `label-sm` all-caps with 5–10% letter spacing

### 7.3 Border Radius

From Tailwind config: DEFAULT `0.125rem`, lg `0.25rem`, xl `0.5rem`, full `0.75rem` - notably small, creating a "machined/precise" look rather than rounded SaaS cards.

### 7.4 Key Signature Components

- **Pulse Beacons:** 8px `error` circle with repeating scale-out animation for Critical Risk items
- **Glassmorphism overlays:** semi-transparent `surface-bright` with 12–20px `backdrop-blur` for modals/tooltips
- **Ghost Borders:** `outline_variant` at 15% opacity as fallback contrast separator
- **Data-Density Shields:** `surface-bright` text on `surface-container-highest` badges for categorising dense data

### 7.5 Navigation Architecture

Fixed left sidebar with these items (confirmed across all screen artefacts):
1. Enterprise Overview (home) - `dashboard` icon
2. Modules - `view_module` icon
3. AI Decision Hub - `psychology` icon
4. Pipeline Monitor - `analytics` icon
5. Settings - `settings` icon
6. Admin - `admin_panel_settings` icon (role-gated)
7. EMERGENCY OVERRIDE - persistent CTA (appears in multiple screens - purpose/behaviour not defined in PRD)

**⚠️ Engineering Gap: EMERGENCY OVERRIDE** - This button appears prominently in the sidebar across multiple screens with a `warning` icon. It has no corresponding FR in the PRD. Its intended behaviour is undefined. This must be clarified with the product/business owner before implementation.

### 7.6 Persistent AI Co-Pilot Sidebar (Right Panel)

Confirmed across all screen artefacts. Contains:
- Status indicator: "Active Analysis" / "Risk Analysis active..."
- Executive Insight / Intra-Module Analysis summary text
- Priority Anomalies list (numbered, with icon)
- "Adjust Model" / "Ignore" action buttons (Module Dashboard variant)
- Free-text chat input with send button
- "Active Queries" section showing queued NL questions

This must be implemented as a **global component across all routes** - confirmed by the handoff guide: "The Co-Pilot sidebar is a persistent overlay. It should be implemented as a global component across all routes."

---

## 8. User Stories (All 8 Confirmed in PRD)

| ID | Persona | Story Summary | Acceptance Criteria |
|---|---|---|---|
| US-01 | CRO | See enterprise risk score at a glance within 30 seconds | Dashboard loads with score visible without scrolling |
| US-02 | Risk Analyst | Drill into Module → Sub-Module → Group → Metric | 1-click access; SPC charts render; full drill-down works |
| US-03 | CFO | Export investor-ready PDF/PPT performance profile | Export generates formatted file within 30 seconds |
| US-04 | Ops Lead | Monitor pipeline execution for all 12 Modules | All 12 statuses shown; errors highlighted in red |
| US-05 | Executive | AI action recommendations from Module + Enterprise analysis | ≥5 specific Module-attributed steps; enterprise synthesis labelled |
| US-06 | Executive | Ask AI natural language questions about any Module | Returns relevant answer in under 10s |
| US-07 | Risk Analyst | See confidence level for all risk projections | Confidence % on all projections with tooltip explanation |
| US-08 | Super Admin | Manage users and assign roles | Create/edit/deactivate works; RBAC enforced on login |

---

## 9. MVP Scope - In vs Out

### In Scope (V1.0)
- Enterprise Dashboard
- 12 Domain Dashboards (SPC charts, heatmaps, AI insights)
- AI Decision Hub (LLM reports, action plans, Ask AI chat)
- Pipeline Monitor
- Settings Module (LLM config, thresholds, domain/module management)
- Admin Module (user management, RBAC, audit logs)
- PDF / PowerPoint export
- Confidence scoring layer

### Out of Scope (V1.0)
- Multi-tenant / multi-entity consolidation (V2.0)
- Native mobile app (responsive web only)
- Custom domain builder (self-service)
- Real-time streaming ingestion (batch pipeline only)
- Third-party ERP / ITSM direct integrations (manual import only)

---

## 10. 8-Week MVP Delivery Plan

| Phase | Sprint | Your Role (Backend & AI) | Frontend | DevOps & Data |
|---|---|---|---|---|
| 1 | Wk 1–2 Foundation | FastAPI scaffold, DB connection, pipeline wrapper for 2 Modules, REST API spec | UI component library, Enterprise Dashboard shell, **API contract agreement** | PostgreSQL schema, Docker, CI/CD, dev env, RBAC schema |
| 2 | Wk 3–4 Core Dashboards | REST APIs for all 12 Module scores + metrics, pipeline orchestrator, all 12 Module wrappers | Enterprise Dashboard (complete), 12 Module Dashboards, Pipeline Monitor screen | Admin module backend, user management APIs, audit log, Redis cache |
| 3 | Wk 5–6 AI Hub | Two-tier LLM integration (Module + Enterprise), confidence scoring engine, LLM response storage | AI Decision Hub UI, Ask AI chat, Module drill-down, AI insight panels | Secrets management, Celery Beat scheduling, pipeline monitoring APIs, staging deployment |
| 4 | Wk 7–8 Polish & Launch | Settings APIs, export data endpoints, performance tuning, API documentation | PDF/PPT export, dark/light theme toggle, Settings UI, Admin UI, UAT fixes | Production env, Kubernetes, load testing, go-live |

**Critical milestones:**
- **Week 1 Day 3:** API contract freeze - Frontend builds against mocks from this point
- **End of Week 4:** Integration checkpoint - Frontend connects to live Backend APIs for the first time
- **Week 7 Days 3–5:** UAT window

---

## 11. Open Questions & Engineering Decisions Pending

| # | Question | Owner | Resolution Target | Engineering Impact |
|---|---|---|---|---|
| Q1 | Which LLM provider - Gemini, Anthropic, or OpenAI? | Product / Engineering | Phase 1 | API wrapper design; prompt engineering; cost model |
| Q2 | Cloud-hosted SaaS or on-premise deployment? | Product / Business | Phase 1 | Infra architecture; secrets management; networking |
| Q3 | Exact list of 12 Modules and Sub-Module/Group structure? | Product / Data | Phase 1 | **Blocks DB schema finalisation and pipeline wrapper work** |
| Q4 | Quarterly and half-yearly reporting periods both required? | Product / Business | Phase 1 | Affects time-series data model; reporting period logic |
| Q5 | SSO / identity provider requirements? | Engineering / Sales | Phase 2 | SAML configuration placeholder needed in V1.0 |
| Q6 | Confidence scoring methodology - which statistical model? | Data Science | Phase 2–3 | **Blocks confidence engine implementation** |

**Additional engineering gaps identified from artefact analysis (not in PRD open questions):**

1. **EMERGENCY OVERRIDE button** - visible in all screens in the sidebar, no FR defined. What does it do? Who can trigger it? Is it a hard kill switch for pipelines?

2. **Heatmap navigation** - is the heatmap a tab/toggle on the Module Dashboard or a separate routed screen? The existence of a standalone `heatmap_of_module_dashboard_financials/screen.png` screen suggests the latter, but the PRD's FR-10 implies it's a view within the Module Dashboard.

3. **Alert severity level schema** - Sub-Module detail screen shows "Level 4" and "Level 2" alerts. The PRD only defines Green/Yellow/Red by score range but not a separate numeric alert severity model.

4. **"FORCE RECALC" button** on Sub-Module detail - no FR covers this. Is it Admin-only? Does it trigger a full pipeline run or only a local metric recalculation?

5. **"Deploy New Watcher" button** in Module Sub-Architecture panel - implies the ability to add new metric watchers dynamically. No FR or spec exists for this.

6. **Module Knowledge Base** (Sub-Module detail screen) - links to policy PDFs and methodology documents. Is this user-uploaded content? Where is it stored? Is it accessible to the LLM for Ask AI context?

7. **Report ID format** (`VL-AI-992-DELTA`) - implies a structured naming convention for LLM reports. This needs to be standardised and documented before the storage schema is finalised.

8. **"Rollback Last Domain"** in Pipeline Monitor Admin Control - a destructive action with no spec. What does rollback mean (restore previous pipeline output? roll back DB state?). Needs a spec before implementation.

9. **Processing rate metric** (`12.4GB/s`) shown in Pipeline Monitor - is this a real instrumented value or decorative? If real, what emits it?

10. **SSO placeholder (V1.0)** - the PRD says "configuration placeholder." Is this just a settings page field that does nothing, or should SAML integration be wired up even if not fully activated?

---

## 12. Handoff Notes for Your Partners

### For Your UI/UX Partner
- The `aegis_quantum/DESIGN.md` file is the authoritative design system specification. All five screens have working HTML/Tailwind prototypes - use these as the reference implementation.
- The Tailwind config is fully specified and should be copy-pasted into the project's `tailwind.config.js`.
- The persistent Co-Pilot sidebar must be a global layout component - not reimplemented per screen.
- The "No-Line" rule and surface hierarchy are strict - enforce in code review.
- The handoff guide recommends exporting screens to Figma via the toolbar - use `screen.png` files as the visual baseline.

### For Your ML Partner
- The PoC pipeline is the confirmed starting point - your job is wrapping, not rebuilding.
- Two-tier LLM call sequencing is the core ML architecture: 12 parallel Module calls → 1 Enterprise synthesis call.
- Prompt templates must be stored in the DB, versioned, and editable by Super Admin.
- Confidence scoring methodology is **Open Question Q6** - this is the biggest ML risk item in the roadmap. It must be resolved before Week 5.
- Response caching strategy: cache invalidation on Module output change, not TTL-based.
- The Ask AI feature is a relay - user query + current context (scores, active Module, report) → LLM → response. The context construction logic is ML's responsibility.

### For You (Backend / API)
- API contract must be frozen by **Week 1 Day 3**.
- The hierarchy is data-driven - no hardcoded Module/Sub-Module/Group names in the backend.
- Module pipeline wrappers must emit progress percentage (for the "64% COMPLETE" display in Pipeline Monitor).
- Error log retention: minimum last 5 runs per pipeline stored.
- All endpoints require RBAC enforcement - no role escalation vulnerabilities permitted (NFR: Security).
- LLM API keys: secrets vault only, never in code, never in logs.
- The pipeline orchestrator must implement a barrier/join on the 12 Module calls before triggering the Enterprise-level call.

---

*Document compiled from: Enterprise_Risk_Platform_PRD_v1.2.pdf (20 pages) + all 6 screen HTML artefacts + heatmap PNG + enterprise_risk_monitoring_prd_summary.html + handoff_implementation_guide.html + aegis_quantum/DESIGN.md*
