# Integration module analytics scripts

Data source: Repo-01 commit [`580dc6a`](https://github.com/AI-ERMT-TBD-02/Repo-01/commit/580dc6a)
(Praveen, 18 Aug 2026, "Updated json file"), which supplied
`input_metric_values_integration.csv` and `integration_performance_json_file.json`.
Those two files are the only real inputs; they live in
`modules/integration/reference_data/`.

## These scripts are GENERATED, not hand-edited

Repo-01's commit [`0c1c28e`](https://github.com/AI-ERMT-TBD-02/Repo-01/commit/0c1c28e)
(18 Aug 2026, "Updated code file for integration module, low performance
calculations") also uploaded `AI_ready_Low_Performing_M_G_SM_Integration_4_0`,
but it was **not vendored**. Diffed against our fixed
`modules/shared/analytics_scripts/AI_ready_Low_Performing_M_G_SM_Shared_3_0.py`
template, his file still has the `.iloc[0]` low-performer bug (an arbitrary
single row out of 3000, not the mean-across-series fix) and an uncommented
`app.run(debug=True)` that hangs batch runs, plus a duplicated-block typo in
the sub-module fallback branch. His one real fix (wrapping columns in
`pd.Series` before building the output DataFrame) is moot against our
template, which already pads every average list to full length before that
point. Same pattern as every other Repo-01 upload so far.

These five scripts were produced by retokenising our fixed
`modules/shared/analytics_scripts/` copies:

```
python pipeline/scripts/generate_module_scripts.py --module integration --camel Integration --dir integration --code INTG_001
```

Do not hand-edit them. The analytics scripts are still under validation upstream, so any
fix has to reach every generated module; re-running that command is the mechanism. Editing
a file here means the next regeneration silently discards the edit.

## Module facts

| | |
|---|---|
| Token | `integration` |
| Module code | `INTG_001` |
| Metrics | 90 |
| Sub-modules | 7 |
| Groups | 31 |
| Rows | 3000 |

7 of the 31 groups (under the AI Integration Management sub-module) carry a
leading ordinal in their name (`"1. AI Deployment"` etc.) - handled generically
by `load_label_map`'s `_ORDINAL_PREFIX_RE`, same as Shared and Business Partner.

## Report consolidation

There is no per-module report combiner and there should not be one. Step 6 uses the single
shared `text_report_combiner.py`, and the combine step is generic: it collects the `.txt`
outputs of steps 1, 3, 4 and 5 and merges them.
