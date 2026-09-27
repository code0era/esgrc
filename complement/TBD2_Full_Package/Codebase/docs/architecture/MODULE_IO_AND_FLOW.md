# ESGRC Analytics - Module I/O, Terminal Output & Automation Flow

Concise reference for report generation and pipeline automation.
Source: the 10 scripts in `Repo-01` / `modules/esgrc/analytics_scripts/`, cross-checked against
`pipeline/scripts/scripts_registry.json` (the validated I/O contract).

---

## ⚡ First - the "too much text" fix

The scripts print a lot to the terminal (correlation matrices, CHAID trees, training epochs,
tensor shapes). **That stdout is debug noise - it is NOT the deliverable.** Every script also
**writes its real result to `.txt`/`.csv` files.** For a concise report, **read the output
`.txt` files, ignore stdout.**

To silence the noise when running:
```bash
python <script>.py > /dev/null 2>&1      # discard all terminal text; keep the output files
# or keep only errors:
python <script>.py > run.log 2>&1        # everything goes to run.log, terminal stays clean
```

---

## PART A - Module reference (inputs → outputs → what it prints)

### ESGRC module (per single module, 5 analytics steps)

| # | Script | Inputs | Output files (the report) | Terminal (stdout) |
|---|--------|--------|---------------------------|-------------------|
| 1 | `AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py` | `input_metric_values_esgrc.csv`, `esgrc_performance_json_file.json` | `module_values_esgrc.csv`, `low_performing_entities_report_esgrc.txt` | ~40 lines: 3 low-performer tables + module average |
| 2 | `M_G_Sub_M_split_ESGRC_1_0.py` | `module_values_esgrc.csv`, `esgrc_performance_json_file.json` | `filtered_metrics_data_esgrc.csv`, `filtered_groups_data_esgrc.csv`, `filtered_sub_modules_data_esgrc.csv`, `data_for_risk_assessment_esgrc.csv` | 4 lines ("… saved to …") |
| 3 | `Correlation_CHAID_FT_Analysis_ESGRC_8_0.py` | `filtered_metrics_data_esgrc.csv`, `filtered_groups_data_esgrc.csv`, `filtered_sub_modules_data_esgrc.csv`, `esgrc_performance_json_file.json` | `M_G_SM_correlation_report_esgrc.txt`, `trends_and_repetitions_report_esgrc.txt`, `inconsistencies_report_esgrc.txt`, `chaid_risk_segmentation_report_esgrc.txt` | **100+ lines** (verbose: full correlation matrices + CHAID tree) |
| 4 | `x_bar_r_chart_fmea_esg_5_0.py` | `input_metric_values_esgrc.csv` *(the original user file)* | `metrics_summary_<date>.txt`, `RPN_summary_report_<date>.pdf`*, `SPC_charts_report_<date>.pdf`* | 1 summary table |
| 5 | `AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py` | `module_values_esgrc.csv`, `esgrc_performance_json_file.json` | `ESGRC_Module_model_summary.txt` | ~150 lines (training/feature logs) |

\* PDFs = user-download only, not fed into the AI report.
⚠️ Step 4 reads the **original** `input_metric_values_esgrc.csv`, **not** Step 2's output.
⚠️ Hardcoded date `2026-01-07` in Step 4 → output filename is dated (glob it).

### L0 / Enterprise (all 12 modules together, 4 analytics steps)

| # | Script | Inputs | Output files | Terminal (stdout) |
|---|--------|--------|--------------|-------------------|
| 1 | `all_module_low_performance_analysis_1_0.py` | 12× `data_for_risk_assessment_<module>.csv` | `all_module_values.csv`, `performance_report_2025.txt` | Moderate (headers + counts) |
| 2 | `AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py` | `all_module_values.csv` | `correlation_analysis_L0.txt`, `trends_and_repetitions_report_L0.txt`, `inconsistency_report_L0.txt`, `chaid_risk_segmentation_L0.txt` | Verbose (matrix + CHAID) |
| 3 | `SS_x_bar_r_chart_fmea_L0_6_0.py` | `all_module_values.csv` | `SPC_summary_L0_<date>.txt`, `RPN_summary_L0_<date>.pdf`*, `SPC_charts_L0_<date>.pdf`* | 1 summary table |
| 4 | `AI_ready_Multiple_Regression_Model_implementation_L0_19_0.py` | `all_module_values.csv`, `module_mapping.csv`, `module_matrix.csv` | `L0_Risk_Analysis_Report_2025.txt` | Moderate (epoch logs + metrics) |
| - | `text-report-combiner.py` | all `*.txt` in the folder | `MASTER_CONSOLIDATED_REPORT.txt` | Minimal (per-file "added") |

⚠️ Hardcoded date `2026-01-07` in L0 Step 3. ⚠️ L0 Step 4 uses `BASE_DIR = os.getcwd()` - run it from the data folder.

---

## PART B - Automation flow (order + input combinations)

### Flow 1 - one ESGRC module
```
USER PROVIDES:  input_metric_values_esgrc.csv  +  esgrc_performance_json_file.json
        │
   ┌────▼──────────────────────────────────────────────┐
   │ STEP 1  Low_Performing_ESGRC                       │
   │   in : input_metric_values_esgrc.csv, *.json       │
   │   out: module_values_esgrc.csv, low_performing…txt │
   └────┬──────────────────────────────────────────────┘
        │ (module_values_esgrc.csv)
   ┌────▼─────────────────────────────┐
   │ STEP 2  M_G_Sub_M_split           │
   │   in : module_values_esgrc.csv,   │
   │        *.json                     │
   │   out: filtered_metrics.csv,      │
   │        filtered_groups.csv,       │
   │        filtered_sub_modules.csv,  │
   │        data_for_risk_assessment_esgrc.csv  ← handoff to Enterprise (Flow 2)
   └────┬─────────────────────────────┘
        │ (3 filtered_*.csv)
        ├──────────────► STEP 3  Correlation_CHAID_FT   (needs Step 2)
        │                  in : filtered_metrics/groups/sub_modules.csv
        │                  out: 4 report .txt
        │
   run in parallel after Step 1 (they only need Step 1):
        ├──────────────► STEP 4  x_bar_r SPC/RPN         (needs Step 1)
        │                  in : input_metric_values_esgrc.csv
        │                  out: metrics_summary.txt (+PDFs)
        └──────────────► STEP 5  Regression              (needs Step 1)
                           in : module_values_esgrc.csv, *.json
                           out: ESGRC_Module_model_summary.txt
        │
   ┌────▼────────────────────────────────────────────────┐
   │ STEP 6  combine .txt from Steps 1, 3, 4, 5           │  (NOT step 2 - those are CSV)
   │   out: MASTER_CONSOLIDATED_REPORT.txt                │
   └────┬────────────────────────────────────────────────┘
        │
   STEP 7  → AI (Claude) → final ESGRC risk report
```
**Order:** 1 → 2 → 3, with **4 and 5 running in parallel** right after 1 → 6 → 7.
**Combine input = the `.txt` outputs of steps 1, 3, 4, 5** (step 2 emits CSVs, so it's not in the combine).

### Flow 2 - Enterprise roll-up (all 12 modules)
```
INPUT: data_for_risk_assessment_<module>.csv  × 12   (each is that module's Step-2 output)
       + module_mapping.csv + module_matrix.csv

STEP 1  all_module_low_performance     in: 12 csv          out: all_module_values.csv (+report)
   │ (all_module_values.csv)
   ├─► STEP 2  Correlation_CHAID_L0     in: all_module_values.csv     out: 4 report .txt   ┐
   ├─► STEP 3  SPC/RPN_L0               in: all_module_values.csv     out: SPC_summary.txt │ parallel
   └─► STEP 4  Regression_L0            in: all_module_values.csv,     out: L0_Risk_…txt   ┘
                                            module_mapping.csv, module_matrix.csv
STEP 5  combine .txt → MASTER_CONSOLIDATED_REPORT.txt → AI (Claude) → enterprise risk report
```

### The key link between the two flows
> Run **Flow 1 (5 steps) for each of the 12 modules** → each produces its own
> **`data_for_risk_assessment_<module>.csv`** → collect all 12 → feed them into
> **Flow 2 Step 1**. That single file is the module→enterprise handoff.

All 12 modules are built (Integration, the last, landed 2026-08-22), each following
the exact same 5-step contract.

---

## PART C - Naming gotchas (case matters on Linux)
- `ESGRC_Module_model_summary.txt`, `SPC_summary_L0`, `L0_Risk_Analysis_Report` → capitals as shown.
- All Step-3 correlation/CHAID outputs are **lowercase**.
- Dated filenames (`*_2026-01-07.txt`, `*_<date>.pdf`) must be matched with a glob, not an exact name.
