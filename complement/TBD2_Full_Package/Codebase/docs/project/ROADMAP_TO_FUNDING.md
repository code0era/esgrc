# Roadmap - MVP → 12 modules → funding

**As of 19 Jul 2026.** The single plan the team works from. Complements `PROJECT_STATE.md` (what exists) and `MEETING_DECISIONS.md` (what was decided).

---

## 0. Decisions already locked

| Decision | Choice |
|---|---|
| **MVP scope** | **ESGRC + Apex** (module pipeline + enterprise roll-up). The other 11 modules and the flagship dashboards are **not** MVP. |
| **Architecture** | **Shared multi-tenant - keep the current structure and build around it.** No re-architecture. |
| **API cost** | **Client pays.** We cover hosting only. |
| **How (for now)** | Platform Anthropic key + a **per-client cost report** (we already record tokens per call) → settle with the client. **BYOK deferred** to a post-MVP upgrade. |
| **Pricing / tiering** | **Deferred** - decide later. |
| **Labeled report fields** | Frontend reads `/recommendations` (option a). **No backend work.** |
| **"+1" headcount** | Aimed at **the other modules**. |

**Our cost model (much improved):** hosting only - **~$60/mo now · ~$110–150/mo at 10 clients · ~$400–700/mo at 50.** Well inside the $2,000/mo budget. *Hosting is not our constraint.*

---

## 1. The strategic call

> **Do not wait for all 12 modules before fundraising.**

Investors fund **the pattern and the trajectory**, not completeness. The thesis is proven by:
- ESGRC working end-to-end ✅ *(done)*
- **A second module built quickly** - proving replication is mechanical *(the proof point)*
- The enterprise roll-up combining them ✅ *(done)*
- The 12-module architecture visibly in place ✅ *(template done)*

Gating the raise on all 12 modules ties it to the analytics/data timeline (~1–2 months per module set, ×11) - potentially **4–6 months of runway spent proving what a second module already proves.**

**Sequence: MVP → module #2 → demo + dashboard → RAISE → modules 3–12 with funding.**

---

## 2. The critical path

```
CARD / CANADIAN ENTITY ──► DEPLOY ──► STABLE DEMO ──► INVESTOR DEMO
                                            ▲
        PRAVEEN'S MODULE #2 ────────────────┤
                                            │
        FLAGSHIP DASHBOARD ─────────────────┘   ⚠️ currently UNOWNED
```

Three things gate the investor demo. **Two are not started; one has no owner.**

---

## 3. Phases

### Phase 1 - Close MVP  *(now → freeze date)*
Four parallel tracks; nothing here waits on Praveen except the last row.

| Track | Owner | Work | Done when |
|---|---|---|---|
| Frontend | **Shubham** | 3 jobs (names · freshness badge · module-agnostic) + hard-refresh logout fix | Reports show business names + "Data as of…" badge |
| Backend | **Danish** | Gate org-creation · audit log (user actions) · prompt DB version bump + 1 live run · merge PR #1 & #2 | `main` is current; security items closed |
| Deploy | **Danish** | DigitalOcean + TLS + real env - **the day the card lands** | Stable URL, smoke test passes |
| Analytics | **Praveen** | ⚠️ **Replace the `np.random` risk scenarios with real-data-derived ones** | Reports reproducible run-to-run |

### Phase 2 - Prove replication  *(module #2)*
| Owner | Work |
|---|---|
| **Praveen** | 5 adapted analytics scripts + that module's data - **the long pole** |
| **Danish** | ~30 min of plumbing: one `ModuleSpec` in `pipeline/modules.py`, a ~20-line chain file, register scripts |

**Success = a second module live, and Apex rolling up two *real* modules.** That is the investor proof point.

### Phase 3 - Make it demo-worthy
- **Flagship multi-module dashboard** - ⚠️ **needs an owner.** This is what makes "12 modules → one enterprise risk score" *land*. Without it the demo is a text report.
- Demo script + recorded walkthrough
- Stable URL, seeded believable data

### Phase 4 - Raise
- Deck + live demo + the refreshed strategy (GCC/UAE beachhead, agentic-AI positioning) + the improved unit economics
- Business gates cleared: ZDR confirmation, privacy counsel, entity

### Phase 5 - Modules 3–12  *(post-funding)*
With funding, parallelise the analytics work instead of serialising it on one person. Per module: Praveen's scripts + data, then same-day plumbing via the template.

---

## 4. Risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **The card / entity** blocks deploy | No deploy → no stable demo → **no investor demo**. The #1 blocker, and it's commercial not technical. | Push entity registration hard; it also unlocks Bedrock residency later |
| 2 | **`np.random` risk scenarios** | Report "top risks" change every run and aren't derived from client data. If an investor or client notices, **credibility damage**. | **Fix before any external demo.** Highest-stakes open item. |
| 3 | **Praveen is a single point of failure** | Owns the 11 modules + confidence math + team lead. The whole 12-module path serialises on him. | Prioritise module #2 only; parallelise after funding |
| 4 | **Flagship dashboard unowned** | The UI that showcases multi-module value has nobody assigned. | Assign to Shubham (after his 3 jobs) or the +1 |
| 5 | Shared key until BYOK | We front API cost until settled with the client | Per-client cost report + usage guard rails |

---

## 5. Decisions - settled 18 Jul 2026

| # | Decision | Outcome | Owner |
|---|---|---|---|
| 1 | **MVP scope** | **ESGRC + Apex both** - that's the MVP | Danish |
| 2 | **Feature-freeze date** | **Saturday 25 July 2026** | Danish |
| 3 | **Flagship dashboard owner** | **Shubham** - after the freeze, not inside it | Shubham |
| 4 | **Deployment for the demo** | **SUPERSEDED 2026-08-07 - see [DEMO_DEPLOY.md](../deployment/DEMO_DEPLOY.md).** Render and every other free tier trigger card KYC from Pakistan. Cloudflare tunnel for scheduled demos; company account under METEOERAIT SOFTWARE P LTD for the permanent URL | Danish, then Praveen |
| 5 | **The 12 modules** | Praveen delivers **full pipelines** per module (scripts + data), not just handoff CSVs - from `AI-ERMT-TBD-02/Repo-01` | Praveen |
| 6 | **Sequencing after MVP** | Chase **clients + funding in parallel** with completing the 12 modules - not sequentially | Danish |
| 7 | **Signup / org creation** | **Provisioned** - we create client orgs. Future self-signup is **payment-gated** (org created only after payment clears) | Danish |
| 8 | **API cost model** | **BYOK - client pays their own LLM cost.** We carry hosting only | Danish |
| 9 | **First clients' hosting** | **Separate deployment per client** initially; shared multi-tenant is the target, and pairs with BYOK | Danish |
| 10 | **Pricing / tiering** | **Deferred** - tiered usage-based pricing with a price cap, to be designed later | Danish |

### Still open

| # | Question | Owner |
|---|---|---|
| 1 | **Which module is #2?** (the proof point for fundraising) | Praveen |
| 2 | Raise after module #2, or after all 12? | Danish |
| 3 | Tiered pricing design + metering | Danish (deferred) |

---

## 6. Definition of done - MVP

A client can:
1. Log in to their organisation (multi-user, role-based) ✅ *built*
2. Run **ESGRC** end-to-end and get an AI risk report ✅ *built*
3. See the **Apex** enterprise roll-up ✅ *built*
4. Read reports in **business language** with a **"data as of"** freshness badge - *backend ✅, frontend pending*
5. Trust it: RBAC ✅ + **audit log** *(pending)*
6. Reach it on a **stable deployed URL** *(blocked on card)*

---

## 7. v1.1 / v2 backlog  *(captured, deliberately deferred past the freeze)*

**Everything below is post-MVP.** Captured so nothing is lost; **none of it competes with the 25 Jul freeze.**

**Near-term v1.1**
- The other **11 modules** (need Praveen's per-module scripts + data; the chain template makes the plumbing instant)
- **Flagship multi-module dashboards** (Enterprise/Module dashboards, AI Decision Hub, SPC heatmaps, PDF/PPT export) - owner: Shubham
- **BYOK** (client's own LLM key) · **tiered/usage-based pricing + billing** · **self-serve (payment-gated) signup**
- **User-action audit log** (the pipeline process-log ships in MVP; user-action auditing is v1.1)
- SSO/SAML

**Bigger v2 bets (Praveen, 19 Jul) - right direction, deliberate re-architecture, not toggles**
- **Agentic model migration.** Move the pipeline from "analytics → single report → one LLM call" to iterative tool-using agent loops. Foundation already exists (ESGRC orchestrator/specialist agent + the Co-Pilot). Aligns with the 2026 market pivot to agentic GRC. ⚠️ **Materially higher LLM cost per run + new tooling/guardrails/evals.** Best time: after MVP is stable and a client/funder justifies the cost.
- **BrowseComp-style deep-search Co-Pilot.** Turn the chat box into a multi-hop, evidence-gathering, self-verifying agent over internal + external sources (RAG + knowledge graph + evidence scoring + governance). Strong fit for enterprise risk. 🔴 **Key caveat:** searching *raw* internal data + external sources **breaks the current "we never send raw client data to the LLM - only derived reports" security/residency promise**, which is a core selling point - so it needs a deliberate v2 security design, not a bolt-on.

---

*Related: `PROJECT_STATE.md` (full audit) · `MEETING_DECISIONS.md` (decision log) · `HOSTING_COST_ESTIMATE.md` (cost options) · `MODULE_REPLICATION_TEMPLATE.md` + `pipeline/modules.py` (how to add a module).*
