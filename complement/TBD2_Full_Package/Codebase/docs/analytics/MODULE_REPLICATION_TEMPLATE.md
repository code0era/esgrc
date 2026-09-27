# Module Replication Template - how to add a new module

### Vigilant Lens · ESGRC is the template all other modules were built from

ESGRC is fully built and is the reference implementation. **All 12 business modules
now exist** (Integration, the last, landed 2026-08-22 - see `pipeline/modules.py`);
this doc is kept as the reference for wiring up any future module, and is still
**mechanical** once its analytics definitions + data exist. This doc lists every
ESGRC-specific touchpoint so a new module drops in without hunting through the codebase.

> **Prerequisite (owner: Praveen):** the module's analytics scripts + its
> `data_for_risk_assessment_{module}.csv` output shape must exist first. The
> per-module definitions are the only genuinely new work - everything below is
> wiring that mirrors ESGRC.

> **Worked example: Customer** (done 31 Jul 2026). It is the first module built
> from this template, so every row below has a real Customer counterpart to copy:
> scripts in `modules/Customer/analytics_scripts/` (+ that dir's README for the deltas
> applied to Praveen's Repo-01 upload), chain in `pipeline/tasks/customer_chain.py`,
> registry keys `customer_*`, and `pipeline/tests/test_customer_e2e.py`.
> Since the factory refactor these chain files carry no step logic at all - compare
> `customer_chain.py` against `shared_chain.py` and the only difference is the token.

> **Modules 3 and 4: Shared + Business Partner** (done 4 Aug 2026, one PR).
> Same shape as Customer: `Shared/` and `BSPT/` script+reference dirs,
> `pipeline/tasks/{shared,bspt}_chain.py`, registry keys `shared_*` / `bspt_*`,
> `pipeline/tests/test_{shared,bspt}_e2e.py`. Note `bspt` is the routing/file token
> (it is what Praveen's scripts and data use) while "Business Partner" is the
> display label, and `pipeline/tasks/shared_chain.py` (the Shared **module**) is
> unrelated to `pipeline/tasks/shared.py` (the bookkeeping helpers).

---

## Vendoring Praveen's scripts - the recurring gotchas

Every Repo-01 upload so far has re-introduced the same defects. Check all of these
**before** wiring a new module; each one has bitten us at least twice.

| # | Check | What goes wrong |
|---|---|---|
| 1 | `grep -n 'app\.run' <scripts>` | The Flask dev server never exits, so the subprocess hangs forever. Typically 3 of the 5 scripts. Comment the call out; every output is written before it. |
| 2 | `grep -c save_rpn_summary_txt x_bar_*.py` | His SPC scripts have never carried it. Without it, spec report #7 (the RPN table that feeds Claude) does not exist for that module, only the stakeholder PDF. Port it and normalise the output names to `metrics_summary_` / `rpn_summary_` / `*_report_`. |
| 3 | Metric count vs ESGRC's 84 | Correlation and inconsistency output scale with the **square** of the metric count. Anything materially above 84 needs the top-N-at-write-time trim (see any `Correlation_CHAID_FT_Analysis_*` copy). Customer 348, Shared 288, Business Partner 336 all needed it. |
| 4 | Output filenames carry the module suffix | Shared's correlation wrote `trends_and_repetitions_report.txt` etc. with no suffix, which collides across modules in a shared work dir and breaks the registry's `output_files`. |
| 5 | Version numbers are **not** comparable across modules | Business Partner's LowPerf shipped as `2_0`, branched from an older base than Customer/Shared `3_0`. Always normalise the module token and diff his file against our newest equivalent, not against the version number. |
| 6 | **Group names with a leading ordinal** (`"1. Partner Recruitment"`) | A digit inside a business name breaks `validate_labeling`'s numeric-integrity gate: substituting the code injects a number the code text never had, gate B fails, and the whole labelled report is discarded in favour of raw codes. `load_label_map` strips the prefix (`_ORDINAL_PREFIX_RE`); Shared and Business Partner prefix **every** group name this way, ESGRC and Customer prefix none. |

The fastest path is usually to **retokenise our newest fixed copy** rather than
re-fix his, then diff the result back against his upload to confirm the only
differences are the intended fixes. That is how `Shared/` and `BSPT/` were built.

---

## ▶ Start here - the module registry

**`pipeline/modules.py`** is the single source of truth. Add one `ModuleSpec` and most of
the wiring follows automatically:

```python
MODULES = (
    ModuleSpec("esgrc",    "ESGRC",            "ESGRC_MODULE", factory_built=False),
    ModuleSpec("customer", "Customer",         "CUSTOMER_MODULE"),
    ModuleSpec("shared",   "Shared",           "SHARED_MODULE"),
    ModuleSpec("bspt",     "Business Partner", "BSPT_MODULE"),
    ModuleSpec("product",  "Product",          "PRODUCT_MODULE"),   # <- your new line
)
```

`token` is the identity. Everything else derives from it: the registry key prefix, the perf
JSON name, the metrics CSV, the handoff CSV, the chain module path and every output filename.

**The chain file no longer contains logic.** `pipeline/tasks/_module_chain_factory.py` builds
all 7 tasks from the spec, so `{token}_chain.py` is ~20 lines of re-exports. Copy an existing
one (`shared_chain.py`), change the token in the two places it appears, done. Task names stay
`pipeline.{token}.step1..7`, unchanged from the hand-written era.

> This replaced a ~365-line copied chain file per module, of which only ~24 lines actually
> differed. It also fixed a real bug: the old files did `from pipeline.tasks.r2 import
> download_file`, binding at import time, which made the module e2e tests pass or fail
> depending on pytest collection order. The factory resolves through the module object
> instead, so patching `pipeline.tasks.r2` always works.

### The 4 things you must still do by hand

These cannot be generated. **`pipeline/tests/test_modules_registry.py` fails loudly for each
one if you forget** - it is the checklist, enforced.

| # | Where | Why it can't be derived |
|---|---|---|
| 1 | `PipelineTypeEnum` in `pipeline/models.py` | Python enum members are class attributes; SQLAlchemy resolves them statically. |
| 2 | An alembic migration adding the value | `ALTER TYPE ... ADD VALUE` is DDL. Works without it on SQLite, fails on PostgreSQL. |
| 3 | `PipelineType` union + `STEP_NAMES_BY_TYPE` in the frontend | Compile-time TypeScript. |
| 4 | A `COPY` line in `pipeline/Dockerfile` | Docker's build context cannot iterate a Python list. |

### What the registry now drives for you

`sse.PIPELINE_STEP_COUNTS` · `auth.MODULE_PIPELINE_TYPES` · `celery_app` imports ·
`labeling._PERF_JSONS` · the router's chain-builder lookup and single-step dispatch ·
`seed_demo`'s pipeline definitions.

## The remaining moving parts (data, not wiring)

| # | Where | What to do for module `X` |
|---|---|---|
| 1 | `pipeline/tasks/r2.py` → `APEX_MODULE_NAMES` | Ensure `"X"` is in the list (all 12 already are). |
| 2 | `pipeline/tasks/apex_chord.py` → `MODULE_CSV_NAMES` | Ensure `data_for_risk_assessment_X.csv` is present (all 12 already are). Keep in sync with `APEX_MODULE_NAMES`. |
| 3 | **Handoff write** | Automatic. The factory's step 2 calls `write_module_handoff(..., spec.token, ...)`, which copies the CSV to the stable path **+ writes the provenance manifest**. Apex Step 1 auto-picks it up; no Apex change ever. |
| 4 | Analytics scripts | Vendor them into `X/analytics_scripts/` and add the five `X_*` keys to `pipeline/scripts/scripts_registry.json`. **Read the gotcha table above first** - every upload so far has needed the same fixes. |
| 5 | Reference data in R2 | Upload `input_metric_values_X.csv` + `X_performance_json_file.json` to `org/{org}/reference/`. |
| 6 | **Labeling names** | Drop `X_performance_json_file.json` into `pipeline/llm/data/`. `_PERF_JSONS` is derived from the registry, so there is nothing to edit. Until the file exists, X's module/sub-module codes still resolve from `module_mapping.csv` and its metric codes pass through as `unmapped_codes`. |
| 7 | Seed/demo data | Automatic - `seed_demo.py` loops the registry. |

---

## The happy path, end to end

```
Module X pipeline runs
  └─ data-prep step → write_module_handoff(csv, org, "X", run_id)
        ├─ copies  → org/{org}/module_outputs/data_for_risk_assessment_X.csv   (stable path)
        └─ writes  → org/{org}/module_outputs/data_for_risk_assessment_X.manifest.json
                     { module, source_run_id, produced_at, schema_version }

Apex pipeline runs (Step 1)
  └─ reads every data_for_risk_assessment_*.csv present in module_outputs/
        + logs each one's provenance (source run + produced_at) from the manifest
  └─ runs enterprise roll-up on whatever modules are present
        (missing modules are skipped; at least ESGRC must exist)

Frontend
  └─ GET /pipelines/handoff-provenance → per-module {present, produced_at, source_run_id}
        → "Data as of … · Run #…" freshness badge
```

Apex already tolerates a partial module set (it runs on whatever handoffs exist),
so modules can come online one at a time with **no Apex code change** - only the
per-module chain + its `write_module_handoff("X", …)` call.

---

## Definition of done for a new module

1. `data_for_risk_assessment_X.csv` is produced by module X's chain and copied via
   `write_module_handoff` (CSV **+** manifest at the stable path).
2. An Apex run picks it up (check the Step 1 log line: `Apex input 'X' from run=… produced_at=…`).
3. `GET /pipelines/handoff-provenance` shows `X` with `present: true` and a timestamp.
4. (Optional, for metric-level names) X's perf JSON added to `pipeline/llm/data/` and
   loaded in `load_label_map()`; report codes for X resolve to business names.
5. Tests: clone `pipeline/tests/test_handoff.py` coverage for the new module and add a
   chain e2e mirroring `test_esgrc_e2e.py`.

---

*Related: `docs/architecture/MODULE_IO_AND_FLOW.md` (per-script I/O), `docs/team/SHUBHAM_HANDOFF.md`
(analytics scripts), `pipeline/tasks/r2.py` (handoff helpers), `pipeline/llm/labeling.py`
(name resolver).*
