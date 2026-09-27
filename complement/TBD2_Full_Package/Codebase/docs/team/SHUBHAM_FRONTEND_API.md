# Shubham - your frontend API is ready

### The backend for all 3 of your jobs is merged-ready (PR #1). Here are the exact fields.

You don't need the backend running to code against these - the shapes below are
final. Login for testing: **admin@demo.com** / **Demo1234!**

---

## Job 1 - Show names instead of codes

**Endpoints (unchanged URLs, new fields):**
- `GET /pipelines/runs/{run_id}/recommendations` → list of report outputs
- `GET /pipelines/llm-outputs/{output_id}` → one report output

Each output object now has **three new fields** on top of the existing `response_text`:

```jsonc
{
  "response_text":         "ESU10102 scored 72/100 …",              // codes (source of truth) - don't display raw
  "response_text_labeled": "Emissions Compliance Rate scored 72/100 …", // DISPLAY THIS
  "labels": [
    { "code": "ESU10102", "name": "Emissions Compliance Rate", "level": "metric" },
    { "code": "CSU10102", "name": "Average Patching Time",      "level": "metric" }
  ],
  "labeling_status": "ok"   // "ok" | "failed" | "skipped"
}
```

**How to use it:**
1. Render **`response_text_labeled`** as the report body (it's markdown, names already substituted).
2. Use **`labels`** to build tooltips / small grey code chips - e.g. show the `name`, and on hover show the `code`. `level` tells you if it's a module / sub_module / group / metric (style them differently if you like).
3. **`labeling_status`:**
   - `"ok"` → names are in, all good.
   - `"failed"` or `"skipped"` → `response_text_labeled` safely falls back to the code text. Just render it as-is; optionally show a subtle "codes only" note. **Never** show an error - the report is always present.

> Backend rule you can rely on: `response_text` is never mutated, and numbers
> (correlations, scores) are guaranteed identical between the two fields.

---

## Job 2 - "Data as of …" freshness badge

**New endpoint:** `GET /pipelines/handoff-provenance` (org-scoped, auth required)

```jsonc
[
  { "module": "esgrc",    "present": true,  "produced_at": "2026-07-15T12:00:00+00:00", "source_run_id": "run-abc" },
  { "module": "customer", "present": false, "produced_at": null, "source_run_id": null },
  … one entry per module …
]
```

**How to use it:**
- Badge text: **"Data as of {format(produced_at)} · Run #{short(source_run_id)}"**.
- `present: false` → that module hasn't produced data yet; show "No data yet" or hide it.
- Format `produced_at` (ISO-8601 UTC) however the design wants (e.g. "15 Jul 2026").

---

## Job 3 - Module-agnostic pages

Everything above is **keyed by module** already:
- `labels[].level` distinguishes module / sub_module / group / metric - don't hard-code ESGRC's hierarchy.
- `handoff-provenance` returns **all** modules; drive the sidebar / module switcher off the `module` values, not a hard-coded "ESGRC".
- The report endpoints work for any module's run - read the module from the run, don't assume ESGRC.

---

## Job 4 (new) - Process-log screen

Praveen asked for a log of executed steps: **who · when · which step · pass/fail**. The backend is built; this is the screen for it.

**Endpoint:** `GET /pipelines/process-log` (org-scoped, auth required)

**Query params:** `limit` (default 100, max 500) · `offset` (paging) · `run_id` (optional - filter to one run)

```jsonc
[
  {
    "run_id": "…", "pipeline_id": "…",
    "step_number": 3,
    "step_name": "Correlation CHAID FT Analysis",
    "status": "COMPLETED",              // COMPLETED | FAILED | RUNNING | SKIPPED | PENDING  ← the pass/fail
    "started_at": "2026-07-18T21:04:11Z",
    "completed_at": "2026-07-18T21:06:02Z",
    "duration_ms": 111000,
    "error_detail": null,               // populated when status = FAILED
    "triggered_by": 1,
    "triggered_by_email": "admin@demo.com",   // user already resolved for you
    "triggered_by_name": "Admin User"
  }
]
```

**How to use it:**
- Render as a table, **newest first** (already sorted that way): *When · Who · Step · Status · Duration*.
- Colour `status`: COMPLETED green · FAILED red · RUNNING blue · SKIPPED grey.
- Show `error_detail` on expand/hover **only when FAILED**.
- Use `limit`/`offset` for paging; pass `run_id` to show one run's log (e.g. a "view log" link from the Pipeline page).
- `triggered_by_email` / `_name` are pre-resolved - no extra user lookup needed.

## Quick contract summary

| Job | Endpoint | Field(s) to use |
|---|---|---|
| 1 Names | `…/recommendations`, `…/llm-outputs/{id}` | `response_text_labeled`, `labels[]`, `labeling_status` |
| 2 Freshness | `GET /pipelines/handoff-provenance` | `produced_at`, `source_run_id`, `present` |
| 3 Module-agnostic | all of the above | `labels[].level`, `module` |
| 4 Process log | `GET /pipelines/process-log` | `triggered_by_name`, `started_at`, `step_name`, `status` |

Any field you need that isn't here → ping Danish. Branch to work on: `frontend/labeling`.
