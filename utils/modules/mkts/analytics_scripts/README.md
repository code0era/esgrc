# Market and Sales module analytics scripts

Data source: Repo-01 commit [`7abf094`](https://github.com/AI-ERMT-TBD-02/Repo-01/commit/7abf094)
(Praveen, 6 Aug 2026), which supplied `input_metric_values_mkts.csv` and
`mkts_performance_json_file.json`. Those two files are the only real inputs; they
live in `modules/mkts/reference_data/`.

## These scripts are GENERATED, not hand-edited

Repo-01 contains **no analytics scripts for this module**, only data. These five were
produced by retokenising our fixed `modules/shared/analytics_scripts/` copies:

```
python pipeline/scripts/generate_module_scripts.py --module mkts --camel MKTS --dir MKTS
```

Do not hand-edit them. The analytics scripts are still under validation upstream, so any
fix has to reach every generated module; re-running that command is the mechanism. Editing
a file here means the next regeneration silently discards the edit.

The source is deliberately **our** copy rather than Praveen's, because ours carry the
corrections his do not: the `.iloc[0]` low-performer fix, the CHAID `bin_features`
wiring, `ANALYTICS_SEED` seeding, the top-N report trim, and the removed Flask
`app.run()` that never exits and blocks batch runs.

## Module facts

| | |
|---|---|
| Token | `mkts` |
| Module code | `MKTS_001` |
| Metrics | 192 |
| Sub-modules | 12 |
| Groups | 12 |
| Rows | 3000 |

**Correction applied to the upstream data.** The file was uploaded as `Input_metric_values_mkts.csv` with a capital I. Windows is case-insensitive so it loads locally, but the containers and CI run on Linux where it does not. Vendored here under the lowercase name every other module uses. Contents are byte-identical.

## Report consolidation

There is no per-module report combiner and there should not be one. Step 6 uses the single
shared `text_report_combiner.py`, and the combine step is generic: it collects the `.txt`
outputs of steps 1, 3, 4 and 5 and merges them. Confirmed by Praveen on 7 Aug as the
intended design.
