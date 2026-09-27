> ✅ **STATUS (2026-07-04): ALL FIXES APPLIED & VERIFIED.** The scripts in
> `modules/esgrc/analytics_scripts/` are now fixed. Full ESGRC chain (5 steps + combiner) and full
> L0/Apex chain (4 steps) both run **end-to-end with clean exits (EXIT=0) and produce every
> output file**. Fixes applied: (1) `app.run(debug=True)` disabled in the 4 Flask scripts,
> (2) UTF-8 stdout guard added to the 2 emoji-printing scripts, (3) `requirements-analytics.txt`
> added. These fixes are in the TBD2 project copy - to update Praveen's `Repo-01` on GitHub,
> the same edits must be pushed there.

# Repo-01 Module Health Check - root cause of "modules not responding"

Ran all 5 ESGRC scripts on the **real Repo-01 input data** (`input_metric_values_esgrc.csv`,
`esgrc_performance_json_file.json`) on Windows, Python 3.10. Results and fixes below.
**Verdict: the modules are NOT logically broken - they finish and write their outputs - but
three environment/exit issues make them look "stuck" or crash.**

## Test results (verified 2026-07-04)

| Step | Script | Result | Outputs written? | Cause |
|---|---|---|---|---|
| 1 | `AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py` | ⚠️ **hangs** (never exits) | ✅ yes (csv + txt + .pth) | trailing `app.run(debug=True)` |
| 2 | `M_G_Sub_M_split_ESGRC_1_0.py` | ✅ **clean exit** | ✅ 4 CSVs | - |
| 3 | `Correlation_CHAID_FT_Analysis_ESGRC_8_0.py` | ⚠️ **hangs** (never exits) | ✅ all 4 reports | trailing `app.run(debug=True)` |
| 4 | `x_bar_r_chart_fmea_esg_5_0.py` | ✅ **clean exit** | ✅ txt + 2 PDFs | - |
| 5 | `AI_ready_..Regression..ESGRC_5_0.py` | ❌ **crashes instantly** | ❌ none (until fixed) | emoji `print` on Windows |

## The 3 root causes

### 1. Missing dependencies (instant `ModuleNotFoundError`)
The scripts import packages **not in `pipeline/requirements.txt`**: `torch`, `flask`, `CHAID`,
`graphviz` (plus the usual `pandas/numpy/scipy/scikit-learn/matplotlib/statsmodels`).
If any are missing the script dies on import.
**Fix:**
```bash
pip install pandas numpy scipy scikit-learn matplotlib statsmodels flask CHAID graphviz
pip install torch --index-url https://download.pytorch.org/whl/cpu
```
(`graphviz` also needs the system Graphviz binary if CHAID tree images are rendered.)

### 2. The "not responding" hang → trailing `app.run(debug=True)`  ← main cause
4 scripts do **all their analysis, write every output file, and then start a Flask web
server** that blocks forever:
```
* Running on http://127.0.0.1:5000
Press CTRL+C to quit          ← this is the "hang". The work is already DONE.
```
Scripts affected: `AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py`,
`Correlation_CHAID_FT_Analysis_ESGRC_8_0.py`,
`AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py`,
`AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py` (Apex).

**Fix (pick one):**
- **Best:** delete/comment the last 1–2 lines - `app.run(debug=True)` (and the `if __name__`
  block's Flask start). The batch pipeline doesn't use the Flask API; outputs are written before it.
- Or run each with a timeout: `timeout 120 python <script>.py` (Linux) - it runs, writes files, gets killed.
- Or press **Ctrl+C** once you see the output files appear - the files are already saved.

### 3. Windows emoji crash → `UnicodeEncodeError` on `print("✅ …")`
Step 5 (and any script printing emoji) crashes **immediately** on Windows because the console
uses cp1252, which can't encode `✅`:
```
UnicodeEncodeError: 'charmap' codec can't encode character '✅' … line 28
```
It dies **before writing any output**. On Linux (UTF-8) it would be fine - this is Windows-only.

**Fix (pick one):**
- **Best (no code edit):** set `PYTHONUTF8=1` before running. Verified: Step 5 then runs fully and
  writes `ESGRC_Module_model_summary.txt`.
  - PowerShell: `$env:PYTHONUTF8=1`   ·   cmd: `set PYTHONUTF8=1`   ·   permanent: `setx PYTHONUTF8 1`
- Or replace the emoji in `print()` lines with plain text (`"[OK] No duplicate columns…"`).

## Bottom line for the report
- **Working as-is:** Steps 2 and 4 (clean exit, correct outputs).
- **Working but hang on exit:** Steps 1 and 3 (and L0 correlation) - remove `app.run`.
- **Windows crash, fixed by `PYTHONUTF8=1`:** Step 5 (and any emoji-printing script).
- **Env setup:** install the 4 undocumented deps (`torch`, `flask`, `CHAID`, `graphviz`).

Once those three are applied, all 5 ESGRC steps run start-to-finish and produce every output
file in the correct order (1 → 2 → 3, with 4 and 5 after 1). See `MODULE_IO_AND_FLOW.md` for the
input/output map and combine order.

## Quickest way to run the whole chain cleanly (Windows PowerShell)
```powershell
$env:PYTHONUTF8=1
# in a folder containing the input csv + json + the scripts:
python AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py     # Ctrl+C after files appear (Flask hang)
python M_G_Sub_M_split_ESGRC_1_0.py                    # exits on its own
python Correlation_CHAID_FT_Analysis_ESGRC_8_0.py      # Ctrl+C after files appear
python x_bar_r_chart_fmea_esg_5_0.py                   # exits on its own
python AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py   # Ctrl+C after files appear
python text-report-combiner.py                         # combines all *.txt into MASTER report
```
(Removing the `app.run` lines makes the Ctrl+C unnecessary - everything exits on its own.)
