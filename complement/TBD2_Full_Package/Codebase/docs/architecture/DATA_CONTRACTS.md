# Data contracts

Where the pieces meet, what has to agree, and what happens when it does not.

`HOW_IT_WORKS.md` describes the flow. This describes the **joins**. It exists because of a
finding: in the August 2026 audit, every single defect lived in a contract between two
components rather than inside either one. The scripts worked. The registry was valid JSON. The
frontend was well formed. The mock was a working mock. The models and the migrations were each
correct.

Nothing was broken. The **agreements** were broken, and nothing was checking agreements.

Each contract below lists what must agree, what enforces it now, and the real failure that
motivated the guard. Every failure named here actually happened.

---

## 1. Reference data to the analytics scripts

**The agreement.** `input_metric_values_{token}.csv` holds **exactly** the metric leaves declared
in `{token}_performance_json_file.json`, as column headers. Nothing else. The module id,
sub-module ids and group ids are **not** in the raw input; step 1 computes them.

The tell that this is right: for every module, "JSON ids absent from the CSV" equals
sub-modules + groups exactly. ESGRC 55 = 14+41. Product 201 = 19+182.

| Requirement | Why |
|---|---|
| `module_id` matches `[A-Z]{4}_001` | `all_module_low_performance_analysis` matches `^[A-Z]{4}_001$`, and labeling's `CODE_RE` matches `[A-Z]{3,4}_\d{3}` |
| Filenames are lowercase | Windows is case-insensitive; the containers and CI are not |
| No UTF-8 BOM | The scripts call `open(path)` with no encoding, so `json.load` dies on character 0 |
| Every CSV column is declared in the JSON | An undeclared column is data with no definition, carried silently into the analysis |

**Enforced by** `pipeline/tests/test_registry_output_contract.py::test_module_reference_data_is_present_and_loadable`
and `pipeline/tests/test_failure_modes.py`.

**Real failures.** Brand shipped `"module_id": "EBM"`, which would have dropped it from the L0
roll-up and left its codes unlabelled forever. Market and Sales shipped
`Input_metric_values_mkts.csv` with a capital I, which loads on Windows and fails on Linux.
A PowerShell `Set-Content -Encoding utf8` added a BOM that removed 491 of 3,721 label codes.
Integration still has 48 CSV columns with no JSON definition.

---

## 2. The scripts registry to the analytics scripts

**The agreement.** For each registry key, the declared `output_files` must be produced by the
named script. Where the script writes a dated filename, `output_file_patterns` maps the stable
name to a glob, **and the key of that mapping must be the stable name itself.**

`script_runner._resolve` does `glob_patterns.get(stable_name)`. If the key does not match, the
lookup misses **silently** and the code falls back to looking for the undated filename, which
the script never writes.

**Enforced by** `test_registry_output_contract.py` (runs the real `_collect_outputs` for every
module and step, deriving expected filenames from the **scripts**, so the two remain independent
sources) and `test_modules_registry.py`.

**Real failure.** All seven modules added on 6-7 August had pattern keys still naming `shared`,
because the registry entries were cloned from Shared by a script that rewrote dict values but not
dict keys. Every one of them would have died at step 4 with `ScriptOutputMissingError` on its
first real run. The scripts ran perfectly standalone, which is how they had been verified.

---

## 3. Module registry to everything derived from it

**The agreement.** `pipeline/modules.py` is the single source of truth. Four things cannot be
derived and must be hand-written per module:

1. the `PipelineTypeEnum` member (enum members are class attributes; SQLAlchemy resolves them statically)
2. an alembic migration (`ALTER TYPE ... ADD VALUE` is DDL; passes on SQLite, fails on Postgres)
3. the frontend `PipelineType` union and `STEP_NAMES_BY_TYPE` (compile-time TypeScript)
4. a `pipeline/Dockerfile` `COPY` line (the build context cannot iterate a Python list)

Each is a silent failure if forgotten: the module never runs, or runs and cannot be stored, or
renders with the wrong labels.

**Enforced by** `test_modules_registry.py`, which turns every one into a failing test.

**Near miss.** The frontend-union check used a single-line regex. Once the union grew long enough
to wrap, it silently under-read and passed while five module types were missing.

---

## 4. Frontend to API

**The agreement.** Every `api.*` call resolves to a route the API serves, with the same method.

**Enforced by** `ESGRC/tests/test_frontend_api_contract.py`, which compares against the live
OpenAPI schema.

**Real failure.** `RiskPage` called `PUT /risks/{id}`; the API serves `PATCH`. Editing a risk
returned 405 in production.

---

## 5. MSW mocks to the API

**The agreement.** A mock exists for every real call, and every mock corresponds to a real route.

This is the subtlest contract in the system. **MSW answers whatever the frontend asks**, so a
handler encodes the *frontend's* assumption, not the API's. When the two disagree, everything
works in development and fails in production, and no frontend test can see it.

**Enforced by** the same file, in both directions.

**Real failures.** `handlers.ts` mocked `http.put('/api/risks/:id')`, which is what hid contract
4 for weeks. It also mocked `GET /pipelines/prompts/:id`, an endpoint that does not exist. And
StepCard's file download had no mock at all, so that call escaped to the network and silently
failed in dev.

---

## 6. ORM to the migration chain

**The agreement.** Tables **and columns** agree between the models and the schema the migrations
produce.

This matters because `conftest` builds its schema with `create_all` **from the models**, so no
ordinary test ever sees what the migration chain actually produces.

**Enforced by** `ESGRC/tests/test_migrated_schema.py`, which runs the real chain into a throwaway
database and compares both directions.

**Real failures.** `prompt_id` existed in the ORM and was accepted by the API but silently
dropped from the INSERT. `REFRESH_TOKEN_EXPIRE_DAYS` was configured while the column that would
enforce it did not exist, so refresh tokens never expired. A global `UNIQUE(name)` survived the
tenancy migrations, so two organisations could not share a category name.

---

## 7. Analytics output to the LLM

**The agreement.** The combined step-6 payload stays under the guard's hard limit (190,000
tokens). Reports that scale with the **square** of the column count must write top-N, not the
full dump.

The full matrices are still computed and still passed to `bin_features`; only what gets
**written** is bounded. CHAID output is byte-identical either way.

**Enforced by** `test_failure_modes.py::test_every_correlation_script_bounds_its_report` and
`test_regression_fixes.py::TestL0ReportTrim`.

**Real failures.** ESGRC's step-7 payload reached 289,973 tokens against the 190,000 limit, so a
third of the report was cut before Claude saw it, at $0.93 a run. Customer hit 9.1 MB. The L0
roll-up was missed entirely when the trim was applied per module, and reached **909,000 tokens**
once there were 11 modules to combine: 4.8x over, with about four fifths of the enterprise report
truncated. All three produced complete-looking reports.

---

## 8. Worker environment to the analytics subprocesses

**The agreement.** Subprocesses receive an explicit allowlist, never the worker's environment.

The scripts read exactly one variable, `ANALYTICS_SEED`. They are also the least reviewed code in
the system and are re-uploaded by an outside contributor.

**Enforced by** `test_script_runner.py::TestSubprocessEnvironmentIsolation` and
`test_failure_modes.py`.

**Real failure.** `subprocess.run` was called with no `env=`, so every script inherited
`ANTHROPIC_API_KEY`, `CLOUDFLARE_R2_SECRET_KEY`, `SECRET_KEY` and `DATABASE_URL`.

---

## 9. Erasure to every copy of the data

**The agreement.** Deleting data deletes **all** of it, and a failure to delete is never
reported as success.

| Copy | Reached by |
|---|---|
| R2 objects | per-run erasure |
| `response_text`, `output_file_r2_path` | per-run erasure |
| `pipeline:{run}:status`, `copilot:*:{run}:stream`/`:done` | per-run erasure |
| `copilot:{user}:session:{id}` | user- and org-scoped erasure |

**Real failures.** The Co-Pilot stream list held every token of the model's response and nothing
deleted it. Conversation history sat on a 7-day TTL that per-run erasure could not reach at all,
because it is keyed by session. `clear_session` swallowed every exception and returned 204
regardless, so a Redis outage looked exactly like a successful deletion.

---

## 10. Deployment configuration to itself

**The agreement.** compose files parse, nginx configs are valid **and correct**, every service
points at a Dockerfile that exists, and every `COPY` source resolves.

Validity is not correctness. The shipped nginx config parsed perfectly and still could not serve
the app: no `/api` route and no static root.

**Enforced by** the `validate-deploy-config` CI job: `docker compose config` on dev, prod and
local; `nginx -t` on both configs; and four assertions that `/api` is routed and stripped, the
SPA has an index fallback, and `/health` stays on the API rather than falling through to
`index.html`.

---

## How to add a contract

When you connect two things that must agree, ask: **if these silently disagreed, what would the
symptom be?** If the answer is "a plausible result" rather than "an error", write the check
before writing the feature. That single question would have caught all ten of the above.
