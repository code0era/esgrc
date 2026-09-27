# Meeting Decisions - questions, options, recommendations & defense

**For the next team meeting.** Each item: the question, the options, the ⭐ recommendation, **why** (the defense, incl. why *not* the alternatives), and a **🎤 cue** - the one line to say to drive it. Source: the verified whole-repo audit in `docs/project/PROJECT_STATE.md`.

**If the meeting is short, the three that matter most:** **A1 (freeze date)**, **C2 (fix the random scenarios)**, **B2 (gate signup)**. Everything else has a safe default.

---

## A. MVP & scope

### A1. MVP closure criteria + feature-freeze date  *(the key one)*
**Question:** What exactly means "MVP done," and when do we freeze features?
**Options:** (a) ESGRC-only MVP + a fixed freeze date · (b) require a 2nd module first · (c) ship the demo as "MVP."
**⭐ Recommendation:** (a) - ESGRC-only MVP, and **pick a freeze date now** (~2–3 weeks out, covering: the security/decision items, Shubham's 3 jobs, one real run, deploy). After the date: only bug-fixes + deploy land in MVP; everything else → an explicit v1.1 list.
**Why:** ESGRC is functionally complete and tested (419 tests); the other 11 modules are blocked on Praveen's per-module defs - the long pole, months out. Option (b) **couples MVP to a dependency we don't control** → exactly the never-ending trap. Option (c) isn't sellable: the demo regenerates its secret key per boot, reseeds each restart, and `DEMO_MODE` *fakes* the analytics - proves nothing to a buyer. The **date** is the real lever - without it, "one more thing" leaks in forever.
**🎤 Cue:** *"MVP = ESGRC end-to-end, nothing else. Pick the freeze date today; after it, only bugs + deploy. Everything else is a v1.1 ticket."*

### A2. Module #2 sequencing
**Question:** Which module is #2, and when do we start it?
**⭐ Recommendation:** Defer to post-MVP; Praveen names #2 for after the freeze.
**Why:** blocked on Praveen's defs (the long pole); starting now splits focus and re-couples MVP to it. `docs/analytics/MODULE_REPLICATION_TEMPLATE.md` makes it mechanical when the defs land.
**🎤 Cue:** *"Praveen - which module is #2, and when can you start its defs? Agreed it's post-freeze."*

---

## B. Security  *(the audit found real multi-tenant holes)*

### B1. Cross-tenant agent trigger - ✅ ALREADY FIXED
**What was found:** `POST /agent/run` & `/agent/llm-run` required only per-org ADMIN but run a batch across **all** tenants + spend the platform LLM budget.
**Action taken:** gated both to SUPER_ADMIN (+ regression test that ADMIN now gets 403). **Just confirm the call** - per-org admins should not trigger platform-wide runs.
**🎤 Cue:** *"Fixed already - a tenant admin can no longer trigger a run across all tenants. Confirming, no action needed."*

### B2. Signup / org-creation model  *(product decision - deliberately not auto-fixed)*
**Question:** How does a new customer org get created? `POST /auth/organisations` is currently **unauthenticated and mints a full-module admin**.
**Options:** ⭐ provisioned (SUPER_ADMIN-only) · self-serve + verification · invite-only.
**⭐ Recommendation:** Provisioned for MVP; add self-serve later if ever needed.
**Why:** the motion is **relationship-driven B2B enterprise** - we onboard clients ourselves; nobody self-signs-up for an enterprise GRC tool. Self-serve needs email-verify + captcha + abuse handling = real work for **zero MVP value**. Invite-only needs a flow that doesn't exist. Provisioned is the **most secure + smallest change** (gate the existing endpoint) and reversible. `/auth/register` (add a user to an existing org) already works, so teammates can still be added. Leaving it open is indefensible - an unauthenticated endpoint minting a privileged admin.
**🎤 Cue:** *"We onboard clients ourselves - so gate org-creation to super-admin. Self-serve is a v1.1 feature, not this raw endpoint. Agreed?"*

### B3. Role-change propagation
**Question:** A demoted admin keeps admin rights until their token expires (≤30 min); deactivation is immediate. Accept, or enforce instantly?
**⭐ Recommendation:** Accept the ≤30-min lag for MVP.
**Why:** deactivation is *already* immediate (checked every request); only a role *downgrade* lags. Token versioning adds a DB check on **every request** to close a rare mid-session-downgrade window - not worth the perf/complexity at MVP scale; 30-min TTL is already short.
**🎤 Cue:** *"Deactivation is instant; only a role downgrade lags 30 min. Fine for MVP - revisit only if a client demands instant revocation."*

---

## C. Technical

### C1. Labeled-report fields - delivery path  *(unblocks Shubham's Job 1)*
**Question:** The labeled fields (`response_text_labeled` / `labels` / `labeling_status`) are on `GET /recommendations` & `/llm-outputs/{id}`, but the frontend reads `llm_outputs` **embedded** in the runs-list. Which do we standardize on?
**Options:** ⭐ frontend switches to the report-detail endpoints · backend also embeds labeled fields in the runs-list.
**⭐ Recommendation:** Frontend switches to `/recommendations` / `/llm-outputs/{id}`.
**Why:** labeling is computed at serve time on those endpoints. Embedding in the runs-list means running labeling on every list fetch (heavier) and **two code paths that drift**. Report bodies belong on detail endpoints; the list stays lightweight - cleaner design. The frontend audit flagged this exact mismatch as *"the single most likely thing to silently break Job 1."* Small cost to Shubham.
**🎤 Cue:** *"Shubham - pull report bodies from `/recommendations`, not the embedded list. That's where the labeled fields live. 2-minute change, prevents a silent bug."*

### C2. Regression "risk scenarios" methodology  *(highest-stakes non-security item)*
**Question:** Both regression scripts derive their headline drivers/scenarios/actions from **unseeded `np.random` noise** - different every run - and it feeds the client-facing Claude report.
**Options:** ⭐ fix with real data before first client · label "illustrative/synthetic" (internal demo only) · leave as-is (not acceptable).
**⭐ Recommendation:** Fix before any client sees a report; "illustrative" label acceptable only for internal demo.
**Why:** a risk product whose "top risks" change every run and aren't derived from the client's data is a **credibility and liability landmine**, and it undermines the core differentiator (real, data-grounded intelligence vs spreadsheets). Leaving it risks the whole value prop. **Owner: Praveen** (his scripts + methodology).
**🎤 Cue:** *"Right now the 'top risk drivers' in the report come from random noise, not the client's data - different every run. Praveen, we fix this with real data before any client. For internal demo we label it 'illustrative.'"*

### C3. Period alignment for Apex
**Question:** Should Apex refuse to aggregate modules whose data is from different reporting periods?
**⭐ Recommendation:** Yes.
**Why:** aggregating modules across different periods yields a statistically incoherent enterprise score; for a risk product, coherence beats convenience. Gates the staleness/preflight work.
**🎤 Cue:** *"Apex should refuse to mix reporting periods - an incoherent score is worse than none. Agreed?"*

### C4. ESGRC prompt - single call vs split
**Question:** Keep the single Haiku MODULE_UNIFIED call, or split into two?
**⭐ Recommendation:** Keep single for MVP.
**Why:** ~$0.03/run, works, tested. Splitting adds cost + complexity for unproven quality gain.
**🎤 Cue:** *"Keep the single ESGRC prompt call for MVP - cheap and it works."*

### C5. Prompt-change propagation  *(action, not a debate)*
**Note:** the "no-mechanism-speculation" update is in `pipeline/llm/prompts.py` (fallback + seed only). Existing `pipeline_prompts` DB rows need a **version bump** to pick it up, and the effect should be confirmed with **one live LLM run**. **Owner: Danish - when?**
**🎤 Cue:** *"The prompt tweak only reaches the live demo after a DB version bump - I'll do it + one live run by [date]."*

---

## D. People

### D1. Who is the "+1", and who owns the flagship dashboards?
**Question:** The team is described as 4; only 3 are named. Who is the 4th and what do they own? Separately, the **flagship multi-module dashboard UI** (Enterprise/Module dashboards, AI Decision Hub, SPC heatmaps, PDF/PPT export) is unbuilt and **unowned**.
**⭐ Recommendation:** Name the +1's scope; assign the flagship dashboards to Shubham or the +1, scoped to **v1.1**.
**Why:** the dashboard suite is huge, unbuilt, and it's the product *vision*, not MVP - forcing it into MVP blows the freeze. It needs an owner but not an MVP slot.
**🎤 Cue:** *"Two people-gaps: what does [+1] own, and who owns the flagship dashboards? I'm scoping the dashboards to v1.1 - agreed?"*

---

## E. Process logs / audit  *(agenda item - mostly already exists)*

### E1. Audit-log scope
**Question:** What do we add vs. what already exists?
**Options:** ⭐ small `audit_log` table (user actions) + one read endpoint/view · full SIEM-style logging (over-scoped).
**⭐ Recommendation:** Minimal `audit_log` (user actions) + one surface.
**Why:** step/pipeline logging **already exists** (`PipelineStepResult` = step/pass-fail/timestamp; `PipelineRun.triggered_by` = user; `AgentRunLog`). The genuine gap is **user-action** auditing (login, role change, prompt edit) + a view. A minimal table + endpoint meets the enterprise-trust bar without rebuilding what's there. **Owner: Danish (table + endpoint) + Shubham (view).**
**🎤 Cue:** *"Process logs are ~90% there already - pipeline steps have user/timestamp/pass-fail. New work is just user-action logging + a screen. Let's not rebuild the rest."*

---

## F. Business / legal  *(gate the first client - owner: Danish)*
- **Send the Anthropic ZDR email** (draft ready: `docs/team/ZDR_EMAIL_DRAFT.md`) - before any client data (SEC-13).
- **Canadian privacy-counsel review** of the data-processing flow.
- **Canadian entity + business card** - unblocks the DigitalOcean deploy (the single biggest blocker) + Bedrock/ZDR residency.
- **Record the 10-step demo video.**
**Why now:** these gate the first client and the deploy, and they have external lead times (counsel, entity registration) independent of the code - start them in parallel with the build.
**🎤 Cue:** *"These have external lead times, so we start them now in parallel: ZDR email this week, counsel engaged, entity/card is the deploy unblock, demo video before we pitch."*

---

## ✅ Decision log - DECIDED 18 Jul 2026

| # | Decision | Chosen | Owner | Date |
|---|---|---|---|---|
| A1 | MVP criteria + **freeze date** | **MVP = ESGRC + Apex both.** Freeze **Sat 25 Jul 2026** | Danish | 18 Jul |
| A2 | Module #2 | **Open** - Praveen to name it; he supplies full pipelines for all 12 from `Repo-01` | Praveen | - |
| B2 | Signup model | **Provisioned** - we create client orgs. Future self-signup is **payment-gated** | Danish | 18 Jul |
| B3 | Role-change propagation | **Accept the ≤30-min lag** for MVP | Danish | 18 Jul |
| C1 | Labeled-fields path | **(a) Frontend uses `/recommendations`** - no backend change | Danish/Shubham | 18 Jul |
| C2 | Regression scenarios | **Raised with Praveen** - fix with real data vs label illustrative; awaiting his call | Praveen | - |
| C3 | Period alignment | **Open** - recommend refusing mixed-period aggregation | Praveen/Danish | - |
| C5 | Prompt DB bump | **Pending** - needs a version bump + one live run | Danish | - |
| D1 | +1 scope + dashboard owner | **"+1" = the other modules** (not a person). **Dashboard → Shubham, post-freeze** | Shubham | 18 Jul |
| E1 | Audit-log scope | **Process-log endpoint built** (`GET /pipelines/process-log`); user-action audit still to scope | Danish/Shubham | 18 Jul |
| F | Business gates | Entity + card = deploy blocker; ZDR email + counsel outstanding | Danish | - |

### Additional decisions taken
| Decision | Chosen |
|---|---|
| **API cost model** | **BYOK - the client pays their own LLM cost**; we carry hosting only |
| **First-client hosting** | **Separate deployment per client** at first; shared multi-tenant is the target and pairs with BYOK |
| ~~**Demo deployment**~~ | ~~**Shubham deploys on free Render**~~ **SUPERSEDED 2026-08-07 - see [DEMO_DEPLOY.md](../deployment/DEMO_DEPLOY.md)** |
| **After MVP** | Chase **clients + funding in parallel** with completing the 12 modules |
| **Pricing / tiering** | **Deferred** - usage-based tiers with a price cap, designed later |

> **Demo deployment, superseded.** Render was chosen here, a `deploy.yml` comment named
> Hugging Face Spaces, and the 2026-08-06 daily report recorded it as unsolved. All three
> are now replaced by **[DEMO_DEPLOY.md](../deployment/DEMO_DEPLOY.md)**, which is the single source of
> truth: a Cloudflare tunnel for scheduled demos now, and a company-account deploy under
> METEOERAIT SOFTWARE P LTD as the permanent home. Render, Vercel, Koyeb and Hugging Face
> all trigger card KYC from Pakistan even on free tiers, which is what defeated every
> earlier attempt.

> ~~⚠️ **Flagged, not urgent:** `POST /auth/organisations` is currently unauthenticated.~~
> **RESOLVED 18 Jul 2026.** The endpoint is gated to SUPER_ADMIN
> (`ESGRC/app/routers/auth.py`, `_: SuperAdminOnly`). Client orgs are provisioned by the
> platform; any future self-serve signup will be a separate payment-gated flow, never this
> endpoint. Verified 2026-08-07 before publishing a demo URL.
