# ESGRC module analytics scripts

Source: Repo-01 (Praveen). ESGRC is the **origin template** - the first module
built, and the one every other module's fixes trace back to ("mirrors fixes
already carried by the ESGRC equivalents"). The 5 `.py` scripts are vendored
here; the 2 true inputs are in `modules/esgrc/reference_data/`.

## Pipeline order

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py` | `input_metric_values_esgrc.csv`, perf JSON | `module_values_esgrc.csv`, `low_performing_entities_report_esgrc.txt` |
| 2 | `M_G_Sub_M_split_ESGRC_1_0.py` | `module_values_esgrc.csv`, perf JSON | `filtered_{metrics,groups,sub_modules}_data_esgrc.csv`, **`data_for_risk_assessment_esgrc.csv`** (the Apex handoff) |
| 3 | `Correlation_CHAID_FT_Analysis_ESGRC_8_0.py` | the 3 `filtered_*` CSVs, perf JSON | `M_G_SM_correlation_report_esgrc.txt`, `trends_and_repetitions_report_esgrc.txt`, `inconsistencies_report_esgrc.txt`, `chaid_risk_segmentation_report_esgrc.txt` |
| 4 | `x_bar_r_chart_fmea_esg_5_0.py` | `input_metric_values_esgrc.csv` | `metrics_summary.txt`, `rpn_summary.txt`, + 2 PDFs |
| 5 | `AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py` | `module_values_esgrc.csv`, perf JSON | `ESGRC_Module_model_summary.txt` |

## Fixes applied (originated here, then mirrored to every later module)

Praveen's Repo-01 upload ran into the same three defects every subsequent
module's upload has re-introduced since (see
`docs/analytics/MODULE_REPLICATION_TEMPLATE.md`'s "recurring gotchas" table):

1. **`app.run(debug=True)` disabled** in the LowPerf, Correlation and Regression
   scripts. The Flask dev server never exits, so a batch/subprocess run hangs
   forever. All outputs are written before that line, so commenting it out is safe.
2. **Windows UTF-8 stdout guard** (`sys.stdout.reconfigure`) added to the
   Regression script. Without it the emoji prints crash on cp1252 consoles.
3. **Missing dependencies** installed and pinned in
   `modules/requirements-analytics.txt` (verified against all 10 Repo-01
   scripts end to end, 2026-07-04).

## Verified

All 5 run to exit 0 against `modules/esgrc/reference_data/`, and the full
7-step ESGRC pipeline (these 5 scripts + the text-report combiner + the LLM
step) has run end to end multiple times against real Claude, not just mocks
- see `docs/project/SESSION_HANDOFF.md` and `docs/project/PROJECT_STATE.md`
for the verification history.
