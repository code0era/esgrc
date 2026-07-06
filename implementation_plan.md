# ESGRC 9-Module Automation Pipeline — Implementation Plan

## Background

The app currently has a single-module analysis flow (Step 1 → Upload → Generate Report → AI Chat). The user wants to add a **full automation pipeline** of 9 scripts that run sequentially *after* the low-performance analysis, displaying a live progress bar for each script, and generating a consolidated report at the end — matching the style of the existing report.

---

## Pipeline Overview: 9 Scripts in Order

| # | Script File | Role | Inputs | Outputs |
|---|------------|------|--------|---------|
| 1 | `AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py` | Compute weighted averages + low performers per ESGRC module | `input_metric_values_esgrc.csv`, `esgrc_performance_json_file.json` | `module_values_esgrc.csv`, `low_performing_entities_report_esgrc.txt` |
| 2 | `M_G_Sub_M_split_ESGRC_1_0.py` | Split module values CSV into metrics / groups / sub-modules / risk assessment CSVs | `module_values_esgrc.csv`, `esgrc_performance_json_file.json` | `filtered_metrics_data_esgrc.csv`, `filtered_groups_data_esgrc.csv`, `filtered_sub_modules_data_esgrc.csv`, `data_for_risk_assessment_esgrc.csv` |
| 3 | `x_bar_r_chart_fmea_esg_5_0.py` | SPC (Individuals X-MR chart) + FMEA RPN scoring for ESGRC metrics | `input_metric_values_esgrc.csv` | `metrics_summary_<date>.txt`, `RPN_summary_report_<date>.pdf`, `SPC_charts_report_<date>.pdf` |
| 4 | `Correlation_CHAID_FT_Analysis_ESGRC_8_0.py` | Correlation matrix + Fourier trend analysis + CHAID risk segmentation for ESGRC | `filtered_metrics_data_esgrc.csv`, `filtered_groups_data_esgrc.csv`, `filtered_sub_modules_data_esgrc.csv` | `M_G_SM_correlation_report_esgrc.txt`, `trends_and_repetitions_report_esgrc.txt`, `inconsistencies_report_esgrc.txt`, `chaid_risk_segmentation_report_esgrc.txt` |
| 5 | `AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py` | Multiple regression + PyTorch model + risk scenarios for ESGRC | `module_values_esgrc.csv`, `esgrc_performance_json_file.json` | `ESGRC_Module_model_summary.txt`, `risk_assessment_model.pth` |
| 6 | `all_module_low_performance_analysis_1_0.py` | Consolidate all module risk CSVs → `all_module_values.csv` + identify L0-level low performers | Multiple `data_for_risk_assessment_*.csv` files | `all_module_values.csv`, `performance_report_2025.txt` |
| 7 | `SS_x_bar_r_chart_fmea_L0_6_0.py` | SPC + FMEA RPN + Cpk/Sigma Level for ALL modules (L0 view) | `all_module_values.csv` | `SPC_summary_L0_<date>.txt`, `RPN_summary_L0_<date>.pdf`, `SPC_charts_L0_<date>.pdf` |
| 8 | `AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py` | Correlation + Fourier + CHAID risk segmentation at enterprise L0 | `all_module_values.csv` | `correlation_analysis_L0.txt`, `trends_and_repetitions_report_L0.txt`, `inconsistency_report_L0.txt`, `chaid_risk_segmentation_L0.txt` |
| 9 | `AI_ready_Mutiple_Regression_Model_implementation_L0_19_0.py` | Multiple regression + PyTorch + scenario analysis at L0 enterprise level | `all_module_values.csv`, `module_mapping.csv`, `module_matrix.csv` | `L0_Risk_Analysis_Report_2025.txt` |
| Final | `text-report-combiner.py` | Combine all `.txt` reports into one master report | All `.txt` files in working dir | `MASTER_CONSOLIDATED_REPORT.txt` |

---

## Open Questions

> [!IMPORTANT]
> **Q1: Where are the 9 scripts' input files coming from?**
> 
> Several scripts depend on files from *other* modules (e.g., `all_module_low_performance_analysis_1_0.py` needs 12 `data_for_risk_assessment_*.csv` files from all 12 modules). For the UI automation, do you want to:
> - **Option A**: Have the user upload ALL required input files at once at the start of the pipeline, OR
> - **Option B**: Auto-generate whatever files possible and skip/warn on missing ones
>
> **Recommended: Option B** — generate what we can from ESGRC files, and warn on any missing cross-module files.

> [!IMPORTANT]
> **Q2: Scripts with Flask & PyTorch**
>
> Scripts 4, 5, 8, 9 import `flask` and `torch` (PyTorch). These will fail if those packages are not installed. The UI should catch errors gracefully and report which script failed and why — should we also show an install-requirements step or just show the error?

> [!IMPORTANT]
> **Q3: Scripts with CHAID**
>
> Scripts 4 and 8 require the `CHAID` package (`pip install CHAID`). If not installed, CHAID analysis is skipped with a message inside the output file. Should the UI warn the user if this module is unavailable?

---

## Proposed UI Changes

### New Tab: "🤖 Full Pipeline Automation"

The existing app has one workflow (upload → generate → report). We will add a **second tab** called "🤖 Full Pipeline Automation" that gives users access to the 9-step sequential automation.

### UI Flow

```
[ Tab 1: Standard Report ]  [ Tab 2: 🤖 Full Pipeline Automation ]

Tab 2:
─────────────────────────────────────────────────
📁 Step 1 — Upload Files
  - Metric CSV (input_metric_values_esgrc.csv)
  - Config JSON (esgrc_performance_json_file.json)
  - [Optional] Module Mapping CSV (module_mapping.csv)
  - [Optional] Module Matrix CSV (module_matrix.csv)
  - [Optional] Additional risk assessment CSVs for L0 analysis

🤖 Step 2 — Run Full Pipeline
  [ ▶ Start Automation ]

─────────────────────────────────────────────────
Progress Panel (appears after clicking Start):

  ┌─────────────────────────────────────────────┐
  │ 📊 Pipeline Progress                         │
  │ ══════════════════════════════ 3/9 (33%)     │
  │                                              │
  │ ✅ Script 1: Low Performance Analysis        │
  │    └─ module_values_esgrc.csv generated      │
  │ ✅ Script 2: M/G/Sub-Module Split            │
  │    └─ 4 filtered CSV files generated         │
  │ ✅ Script 3: X-Bar R Chart (FMEA/SPC)        │
  │    └─ RPN summary + SPC chart PDFs saved     │
  │ 🔄 Script 4: Correlation + CHAID Analysis    │  ← animated pulse
  │    └─ Running...                             │
  │ ⬜ Script 5: Multiple Regression (ESGRC)     │
  │ ⬜ Script 6: All-Module L0 Consolidation     │
  │ ⬜ Script 7: SPC/FMEA — L0 Level            │
  │ ⬜ Script 8: Correlation + CHAID — L0       │
  │ ⬜ Script 9: Regression Model — L0          │
  │ ⬜ Final: Combine All Reports               │
  └─────────────────────────────────────────────┘

─────────────────────────────────────────────────
📋 Step 3 — Final Consolidated Report (shown after completion)
  - Displays MASTER_CONSOLIDATED_REPORT.txt content
  - [ ⬇️ Download Master Report (.txt) ]
  - [ ⬇️ Download Individual Reports (.zip) ]
  - List of all generated output files with download buttons
```

---

## Proposed Changes

### Component: Backend Engine

#### [NEW] `utils/pipeline_engine.py`
A new engine module that wraps each script's core logic as a callable Python function (instead of running them as separate subprocesses). This avoids subprocess complexity and Flask/port conflicts.

Each function will:
- Accept file paths / dataframes as parameters
- Return `(success: bool, outputs: dict, message: str)`
- Be called sequentially from the UI

**Key functions:**
- `run_low_performance_esgrc(csv_bytes, json_data, work_dir)` → wraps script 1
- `run_split_esgrc(work_dir)` → wraps script 2
- `run_spc_fmea_esgrc(work_dir)` → wraps script 3
- `run_correlation_chaid_esgrc(work_dir)` → wraps script 4
- `run_regression_esgrc(work_dir)` → wraps script 5
- `run_all_module_consolidation(work_dir)` → wraps script 6
- `run_spc_fmea_l0(work_dir)` → wraps script 7
- `run_correlation_chaid_l0(work_dir)` → wraps script 8
- `run_regression_l0(work_dir)` → wraps script 9
- `run_report_combiner(work_dir)` → wraps final combiner

---

### Component: Streamlit UI (app.py)

#### [MODIFY] `app.py`
- Add a **tab layout** at the top: Tab 1 = existing workflow, Tab 2 = new pipeline automation
- Add new session state keys: `pipeline_running`, `pipeline_step`, `pipeline_log`, `pipeline_outputs`, `pipeline_complete`
- Add new render functions:
  - `render_pipeline_upload()` — file upload for pipeline inputs
  - `render_pipeline_progress()` — animated step-by-step progress panel
  - `render_pipeline_report()` — show final consolidated report + download options

---

## Verification Plan

### Automated Tests
- Run `streamlit run app.py` and confirm both tabs render without errors
- Test the pipeline with the existing `input_metric_values_esgrc.csv` and `esgrc_performance_json_file.json`

### Manual Verification
- Verify each pipeline step shows ✅ on completion or ❌ with error message on failure
- Confirm the progress bar advances correctly for each step
- Confirm the master report is downloadable at the end
- Confirm individual output file downloads work

---

## Implementation Notes

> [!WARNING]
> Scripts 4, 5, 8, 9 call `app.run(debug=True)` in their `if __name__ == "__main__"` block — this will NOT be called when importing as a module, so it's safe.

> [!NOTE]
> All scripts use hardcoded filenames (e.g., `'module_values_esgrc.csv'`). The pipeline engine will use a **temporary working directory** (`tempfile.mkdtemp()`) and write all files there, then pass file paths accordingly.

> [!NOTE]
> Scripts that depend on `torch` (PyTorch) will be caught with `try/except ImportError` and will show a warning if torch is not installed, while still continuing with whatever analysis doesn't need it.
