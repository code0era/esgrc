# Self-Serve Module Data Upload — Product Proposal
### Vigilant Lens · For Praveen's review · 16 Aug 2026

**Status: proposal only, nothing built.** This needs your input on one design question (Section 4)
before it goes anywhere near a build plan. Filed as v1.1/v2 backlog — post-MVP, does not touch the
25 Jul freeze or the current module work.

---

## 1. Where this came from

Danish's idea, from a working session: instead of a client's data always arriving as a CSV Praveen
hand-vendors per module, give the client a dashboard where they can:

1. Pick the number of columns and name them.
2. Download a generated template (CSV / Excel / TXT) matching that spec.
3. Fill it in with their own data and upload it back.
4. The platform checks the format and shows them a preview before anything is finalized.
5. Once confirmed, the file is stored encrypted, accessible only to users in their org.

---

## 2. The problem this is aimed at

Today, every module's input data follows a **fixed shape Praveen defines** (the per-module CSV
columns baked into each `analytics_scripts/` folder). Onboarding a new client's data means Praveen
(or whoever adapts the scripts) matching their data to that shape by hand. This proposal asks: could
part of that matching be self-serve, so a client can supply data without a person in the loop for
every file?

---

## 3. What already exists (so we're not starting from zero)

- A generic streaming upload endpoint (`/pipelines/{id}/upload-input`) — role-gated, 100MB cap,
  writes to Cloudflare R2 under `org/{org_id}/reference/{filename}`.
- A drag-and-drop upload modal in the frontend with per-file progress — reusable UI base.
- `openpyxl` is already a backend dependency (unused so far) — ready for generating Excel templates.
- R2 already encrypts everything at rest by default (Cloudflare-managed AES-256) — the "encrypted
  storage" half of this is likely close to free, not new engineering, pending confirmation that's
  sufficient for our compliance claims.
- A pre-flight check already blocks a pipeline run with a clear error if a required file is missing.

**What's genuinely new to build:** validating a CSV's actual columns/content at upload time (today
we only check a file *exists*, never its contents), and a preview-before-commit step in the UI
(today files commit to storage the moment they're dropped).

---

## 4. The open question — this is what we need from you

There are two very different versions of "user defines their own columns," and they lead to
different amounts of work:

**Option A — Fixed schema, friendlier delivery.** The columns are still whatever your analytics
scripts expect for that module (unchanged). The new part is just: instead of Praveen manually
building/sending a template file, the platform generates the correctly-formatted template on demand
and validates the upload against it before accepting it. Client-facing convenience; **your scripts
and column definitions don't change at all.**

**Option B — Genuinely free-form schema.** The client picks arbitrary column names/counts with no
tie to what a module's scripts expect. This is closer to a general data-intake tool than a module
pipeline input — the uploaded data can't feed an analytics script until someone (still you, most
likely) maps it to what that script needs. This doesn't remove your manual adaptation work per
client; it just changes where the raw data comes from.

**The question for you:** which of these is actually useful, given how your scripts consume data
today? Is there a middle ground — e.g., a client can add *optional* extra columns on top of a
required fixed core — that would be worth more than either extreme?

---

## 5. Not in scope here

- Per-org customer-managed encryption keys (stronger isolation than R2's default) — only worth
  building if a specific client's security review demands it.
- Any change to how the 11 built modules currently ingest data — this is additive, not a replacement.

---

*Related: `docs/project/ROADMAP_TO_FUNDING.md` (v1.1/v2 backlog), `docs/analytics/MODULE_REPLICATION_TEMPLATE.md`
(how modules currently declare input data).*
