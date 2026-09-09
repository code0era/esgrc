# Brand Management module analytics scripts

Data source: Repo-01 commit [`7abf094`](https://github.com/AI-ERMT-TBD-02/Repo-01/commit/7abf094)
(Praveen, 6 Aug 2026), which supplied `input_metric_values_brand.csv` and
`brand_performance_json_file.json`. Those two files are the only real inputs; they
live in `modules/brand/reference_data/`.

## These scripts are GENERATED, not hand-edited

Repo-01 contains **no analytics scripts for this module**, only data. These five were
produced by retokenising our fixed `modules/shared/analytics_scripts/` copies:

```
python pipeline/scripts/generate_module_scripts.py --module brand --camel Brand --dir Brand
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
| Token | `brand` |
| Module code | `BRDM_001` |
| Metrics | 15 |
| Sub-modules | 6 |
| Groups | 8 |
| Rows | 3000 |

**Correction applied to the upstream data.** The uploaded JSON had `"module_id": "EBM"`, which matches neither `all_module_low_performance_analysis`'s `^[A-Z]{4}_001$` nor labeling's `CODE_RE`, so this module would have dropped out of the L0 roll-up and never been labelled. Praveen supplied `BRDM_001` on 7 Aug 2026 to match the 4-alpha + underscore + 3-numeric convention. That single field is the only edit to his file.

## Report consolidation

There is no per-module report combiner and there should not be one. Step 6 uses the single
shared `text_report_combiner.py`, and the combine step is generic: it collects the `.txt`
outputs of steps 1, 3, 4 and 5 and merges them. Confirmed by Praveen on 7 Aug as the
intended design.
