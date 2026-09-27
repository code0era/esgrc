# Analytics Modules - Handoff for Shubham

Everything you asked for. All 10 Repo-01 scripts were read, run on real data, fixed, and verified
(2026-07-04). Start here, then use the two detailed docs.

## TL;DR
- **The modules were never logically broken.** They finished their work and wrote all outputs -
  they just (a) hung on a leftover Flask server, (b) crashed on an emoji print (Windows), or
  (c) were missing dependencies. **All three are now fixed** in `modules/esgrc/analytics_scripts/`.
- **Verified:** full ESGRC chain (5 steps + combiner) and full L0/Apex chain (4 steps) all run
  **EXIT 0** and produce every output file.

## 1. Setup (one time)
```bash
pip install -r modules/requirements-analytics.txt
pip install torch --index-url https://download.pytorch.org/whl/cpu
```
Use **Python 3.10–3.12** (numpy/pandas have no 3.13 wheels).

## 2. Run one ESGRC module (order + inputs)
Put `input_metric_values_esgrc.csv` + `esgrc_performance_json_file.json` in a folder with the
scripts, then run in this order (each now exits on its own):
```
1  AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py   ->  module_values_esgrc.csv, low_performing…txt
2  M_G_Sub_M_split_ESGRC_1_0.py                  ->  filtered_*.csv, data_for_risk_assessment_esgrc.csv
3  Correlation_CHAID_FT_Analysis_ESGRC_8_0.py    ->  4 report .txt      (needs step 2)
4  x_bar_r_chart_fmea_esg_5_0.py                 ->  metrics_summary.txt + 2 PDFs  (needs step 1)
5  AI_ready_..Regression..ESGRC_5_0.py           ->  ESGRC_Module_model_summary.txt (needs step 1)
6  text-report-combiner.py                       ->  MASTER_CONSOLIDATED_REPORT.txt
```
Order: **1 → 2 → 3**, with **4 and 5 in parallel after 1**, then combine.
The combine (step 6 / AI input) uses the **`.txt` from steps 1, 3, 4, 5** (step 2 emits CSVs).

## 3. Enterprise roll-up (all 12 modules)
Run the 5-step flow **once per module** → each emits `data_for_risk_assessment_<module>.csv` →
collect all 12 → feed into the L0 chain:
```
1  all_module_low_performance_analysis_1_0.py    (in: 12x data_for_risk_assessment_*.csv)  -> all_module_values.csv
2  AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py   (in: all_module_values.csv)   ┐
3  SS_x_bar_r_chart_fmea_L0_6_0.py                     (in: all_module_values.csv)   │ parallel
4  AI_ready_..Regression..L0_19_0.py   (in: all_module_values.csv, module_mapping.csv, module_matrix.csv) ┘
   -> combine .txt -> MASTER report -> AI
```
All 12 modules now have real data (Integration, the last one, landed 2026-08-22).

## 4. For your report - the "too much text" fix
The scripts print a lot to the terminal (matrices, CHAID trees, training logs). **That stdout is
debug noise, not the deliverable.** Each script writes its real result to `.txt`/`.csv` files.
**Build your report from the output `.txt` files, ignore the terminal.**
To silence stdout: `python script.py > run.log 2>&1`.

## Detailed references
- **[`../architecture/MODULE_IO_AND_FLOW.md`](../architecture/MODULE_IO_AND_FLOW.md)** - every module's exact inputs → outputs → how verbose its terminal is, + full flow diagrams.
- **[`../analytics/MODULE_HEALTH_CHECK.md`](../analytics/MODULE_HEALTH_CHECK.md)** - the 3 bugs, root causes, and exact fixes (with before/after test results).

## What was fixed (already applied)
1. Disabled `app.run(debug=True)` in the 4 Flask scripts (the "not responding" hang).
2. Added a UTF-8 stdout guard to the 2 emoji-printing scripts (Windows crash).
3. Documented all deps in `requirements-analytics.txt`.

> These fixes are in the TBD2 project. **Praveen's `Repo-01` on GitHub still has the originals** -
> the same 3 fixes should be pushed there (or ask Danish for the patch).
