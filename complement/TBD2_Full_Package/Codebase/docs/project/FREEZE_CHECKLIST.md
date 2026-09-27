# 🏁 MVP Freeze Checklist - target: Sat 25 Jul 2026

## The bar: "MVP is done when…"
A client can **log in → run ESGRC + Apex → see a report in business names with a freshness badge → trust it (RBAC + a process log)** - feature-complete, verified on a real run, and demo-live. *(Production deploy is a separate milestone, gated on the entity + card - see §4.)*

---

## 1. Must be TRUE to freeze - by owner

### 🟢 Danish (backend) - mostly done
- [x] Labeling (names), handoff + freshness API, process-log endpoint, security fixes - built, **423 tests green (218 ESGRC + 205 pipeline)**
- [ ] **Lock `POST /auth/organisations`** - before the demo link goes public
- [ ] **Prompt DB version-bump + one live run** - so the no-mechanism prompt reaches the live demo
- [ ] Confirm one **real non-DEMO end-to-end run** (ESGRC + Apex on real keys)

### 🟡 Praveen (analytics)
- [ ] **Decision on the `np.random` risk scenarios** - fix with real data, or label "illustrative" *(credibility-critical if a client sees a report)*
- [ ] Post-merge review of the shipped work
- [ ] *(NOT for MVP: module #2 + the 12 pipelines → v1.1)*

### 🟢 Shubham (frontend) - the biggest open block
- [ ] **Job 1** - render `response_text_labeled` + `labels` chips (names, not codes)
- [ ] **Job 2** - "Data as of · Run #" freshness badge (`/handoff-provenance`)
- [ ] **Job 3** - pages read the module from data (not hard-coded ESGRC)
- [ ] **Job 4** - process-log screen (`/process-log`)
- [x] ~~Fix **refresh-logout** (a demo hits it immediately)~~ **DONE 2026-08-05** (`a33b4b2`)
- [ ] Deploy the demo - see [DEMO_DEPLOY.md](../deployment/DEMO_DEPLOY.md). **Not Render**: it and every
      other free tier trigger card KYC from Pakistan. Cloudflare tunnel for scheduled demos,
      company account under METEOERAIT SOFTWARE P LTD for the permanent URL.

---

## 2. Verification gate (run before declaring freeze)
- [ ] `main` build passes CI (ESGRC + pipeline + frontend + docker) - currently green
- [ ] One **real ESGRC + Apex run** → labeled report + freshness + process-log, end to end
- [ ] Login + RBAC work; no console errors on core screens
- [ ] Demo URL is live and reachable from outside the dev machine, per
      [DEMO_DEPLOY.md](../deployment/DEMO_DEPLOY.md), and its pre-share checklist has been run
- [ ] **Scenario methodology resolved with the analytics owner.** Until it is, every client
      shows `Overall Risk = 0.38`, so a link must not be sent to anyone outside the team

---

## 3. Explicitly OUT of MVP → v1.1 (say it out loud so it stops leaking in)
- [ ] The other **11 modules** (only ESGRC is a full chain)
- [ ] **Flagship multi-module dashboards** (Enterprise/Module dashboards, AI Decision Hub, PDF/PPT export) - Shubham, post-freeze
- [ ] **Agentic model migration** + **BrowseComp deep-search Co-Pilot** (v1.1/v2 - see roadmap)
- [ ] **Self-serve/paid signup**, billing, tiered pricing, **BYOK**
- [ ] **User-action audit table** (process-log covers pipeline steps; user-action logging is v1.1)
- [ ] RAG, SSO/SAML, k8s, multi-cloud, TimescaleDB, self-hosted LLMs, full Force-Recalc/Emergency-Stop

---

## 4. Separate milestone (NOT blocking the freeze) - gated externally
- [ ] **US C-Corp formed** (Praveen's CA)
- [ ] **Corporate card** (Mercury/Brex/Airwallex) → unblocks the DigitalOcean **production deploy**
- [ ] **ZDR email** to Anthropic + privacy counsel - before first client data

---

## 5. The post-freeze rule (25 Jul onward)
> After the freeze, **only bug fixes + the deploy land in MVP.** Every new idea becomes a **v1.1 ticket** - no exceptions.

---

**Single riskiest item for hitting 25 Jul:** Shubham's 4 frontend jobs - all unstarted, and they're what a client actually sees. That's the critical path.

*Related: `MEETING_DECISIONS.md` · `PROJECT_STATE.md` · `ROADMAP_TO_FUNDING.md` · `SHUBHAM_FRONTEND_API.md`.*
