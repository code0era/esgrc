# Customer module analytics scripts

Source: Repo-01 commit [`506dd84`](https://github.com/AI-ERMT-TBD-02/Repo-01/commit/506dd84)
("Add files via upload", Praveen, 30 Jul 2026). 11 files uploaded; the 5 `.py` are
vendored here, the 2 true inputs are in `modules/customer/reference_data/`.

The other 4 CSVs in that commit (`module_values_`, `filtered_metrics_`,
`filtered_groups_`, `filtered_sub_modules_`) are **derived outputs**, not inputs -
the pipeline regenerates them, so they are deliberately not vendored.

## Pipeline order

| Step | Script | Reads | Writes |
|---|---|---|---|
| 1 | `AI_ready_Low_Performing_M_G_SM_Customer_3_0.py` | `input_metric_values_customer.csv`, perf JSON | `module_values_customer.csv`, `low_performing_entities_report_customer.txt` |
| 2 | `M_G_Sub_M_split_Customer_1_0.py` | `module_values_customer.csv`, perf JSON | `filtered_{metrics,groups,sub_modules}_data_customer.csv`, **`data_for_risk_assessment_customer.csv`** (the Apex handoff) |
| 3 | `Correlation_CHAID_FT_Analysis_Customer_8_0.py` | the 3 `filtered_*` CSVs, perf JSON | `M_G_SM_correlation_report_customer.txt`, `trends_and_repetitions_report_customer.txt`, `inconsistencies_report_customer.txt`, `chaid_risk_segmentation_report_customer.txt` |
| 4 | `x_bar_r_chart_fmea_customer_5_0.py` | `input_metric_values_customer.csv` | `metrics_summary_customer_<date>.txt`, `rpn_summary_customer_<date>.txt`, + 2 PDFs |
| 5 | `AI_ready_Mutiple_Regression_Model_implementation_Customer_5_0.py` | `module_values_customer.csv`, perf JSON | `Customer_Module_model_summary.txt` |

## Deltas applied to Praveen's upload

These mirror fixes already carried by the ESGRC equivalents in
`modules/esgrc/analytics_scripts/`. Keep both sets in sync.

1. **`app.run(debug=True)` disabled** in the LowPerf, Correlation and Regression
   scripts. The Flask dev server never exits, so a batch/subprocess run hangs
   forever. All outputs are written before that line, so commenting it out is safe.
2. **SPC script: RPN summary TXT restored.** Praveen's `x_bar_r_chart_fmea_customer_5_0.py`
   was branched from an older base than our `x_bar_r_chart_fmea_esg_5_0.py` and had
   no `save_rpn_summary_txt` at all - spec report #7 (the RPN table that feeds
   Claude in step 6/7) did not exist for Customer, only the stakeholder PDF.
   Ported `RPN_SUMMARY_COLS` + `save_rpn_summary_txt`, and renamed the outputs to
   the `metrics_summary_` / `rpn_summary_` / `*_report_` convention the registry uses.
3. **Regression script: Windows UTF-8 stdout guard** (`sys.stdout.reconfigure`)
   added, matching ESGRC. Without it the emoji prints crash on cp1252 consoles.
4. **LowPerf: `'value' in sub_module` guard** on the no-groups fallback path.
   Not required by the current Customer perf JSON (all 19 sub-modules carry
   `value`), added for parity so a future JSON revision cannot KeyError.

## Verified

All 5 run to exit 0 against `modules/customer/reference_data/` (31 Jul 2026, local,
Python 3.10 + torch CPU + CHAID 5.4.3). Inputs are 348 metrics x 3002 rows.

## Known issue - step 6/7 report volume

Customer has **348 metrics vs ESGRC's 84**. The combined `.txt` payload that step 6
feeds to Claude measures **9.1 MB** (ESGRC's `MASTER_CONSOLIDATED_REPORT.txt` is
658 KB). Dominated by `inconsistencies_report_customer.txt` (6.4 MB) and
`M_G_SM_correlation_report_customer.txt` (2.6 MB), both of which scale with the
square of the metric count.

`pipeline/llm/guard.py` will not fail the run - it routes Haiku to Sonnet and
truncates the middle - but at Sonnet's 800K warn threshold roughly **70% of the
report is dropped** before Claude ever sees it. Fixing this properly means
trimming at the script level (top-N pairs by |r|, drop the full pairwise dump),
which is an analytics decision for Praveen, not a pipeline change. Tracked as a
follow-up; the module runs end to end today.
