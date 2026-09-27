"""
modules/apex/tests/test_apex_analytics_scripts.py

Regression tests for three modules-area MEDIUM audit findings (2026-08-22)
fixed in Apex's own analytics scripts, plus a set of LOW-severity findings
from a follow-up fresh review (2026-09-10) - see the module-level docstrings
further down this file for the details of each:

1. Apex's consolidation script must list a data_for_risk_assessment_<token>.csv
   input for every business module directory under modules/, so a newly
   onboarded module (Integration nearly did this) never silently falls out of
   the enterprise roll-up. This mirrors the precedent set by
   pipeline/tests/test_registry_output_contract.py::
   test_module_is_present_in_apex_module_matrix for the equivalent gap in
   module_matrix.csv - same shape of bug (a module onboarded everywhere else
   but missed in one Apex-owned file), different file.

2. Both Apex scripts that train a PyTorch model must seed torch before doing
   so - unseeded weight init (and, for the correlation/CHAID script,
   DataLoader shuffling + Dropout draws) made report numbers non-reproducible
   run-to-run on identical input.

3. detect_inconsistencies() must be invoked exactly once in the consolidated
   L0 correlation/CHAID script. It was being called twice - the first result
   was discarded immediately when the second call overwrote it - which was
   wasted O(n^2) compute over the correlation matrix, not a correctness bug.

These are source-level checks (regex over the script text), not full runs of
the scripts: the scripts expect real pipeline-produced CSVs
(all_module_values.csv, module_mapping.csv, module_matrix.csv, etc.) as
working-directory inputs and are not import-safe modules, so exercising them
end-to-end belongs to the pipeline e2e suite, not a fast unit test here.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MODULES_DIR = REPO / "modules"
APEX_SCRIPTS = MODULES_DIR / "apex" / "analytics_scripts"

CONSOLIDATION_SCRIPT = APEX_SCRIPTS / "all_module_low_performance_analysis_1_0.py"
CORRELATION_CHAID_SCRIPT = APEX_SCRIPTS / "AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py"
REGRESSION_SCRIPT = APEX_SCRIPTS / "AI_ready_Multiple_Regression_Model_implementation_L0_19_0.py"

# Everything under modules/ except apex itself is a business module whose
# handoff CSV Apex is supposed to consolidate.
_NON_MODULE_DIRS = {"apex"}


def _business_module_tokens() -> set[str]:
    return {
        p.name for p in MODULES_DIR.iterdir()
        if p.is_dir() and p.name not in _NON_MODULE_DIRS
    }


def _my_files_tokens(src: str) -> set[str]:
    match = re.search(r"my_files\s*=\s*\[(.*?)\]", src, re.DOTALL)
    assert match, "Could not find `my_files = [...]` in the consolidation script"
    return set(re.findall(r"data_for_risk_assessment_(\w+)\.csv", match.group(1)))


def test_consolidation_script_lists_every_business_module():
    for script in (CONSOLIDATION_SCRIPT, CORRELATION_CHAID_SCRIPT, REGRESSION_SCRIPT):
        assert script.exists(), f"expected script not found: {script}"

    src = CONSOLIDATION_SCRIPT.read_text(encoding="utf-8")
    listed = _my_files_tokens(src)
    expected = _business_module_tokens()

    missing = expected - listed
    assert not missing, (
        f"modules/ directories with no matching data_for_risk_assessment_*.csv "
        f"entry in {CONSOLIDATION_SCRIPT.name}'s my_files list: {sorted(missing)}"
    )


@pytest.mark.parametrize(
    "script",
    [CORRELATION_CHAID_SCRIPT, REGRESSION_SCRIPT],
    ids=["correlation_chaid_L0", "regression_L0"],
)
def test_torch_training_is_seeded(script: Path):
    """Both scripts build/train a torch model (nn.Linear weight init, plus
    DataLoader shuffling and Dropout draws for the correlation/CHAID script).
    Without torch.manual_seed(...), those draws come from an unseeded global
    RNG and report numbers change on every re-run of identical input."""
    src = script.read_text(encoding="utf-8")
    assert "import torch" in src, f"{script.name} no longer imports torch - test is stale"
    assert re.search(r"torch\.manual_seed\(", src), (
        f"{script.name} trains a PyTorch model without seeding torch first, "
        "so report numbers are not reproducible run-to-run"
    )


def test_detect_inconsistencies_called_once():
    src = CORRELATION_CHAID_SCRIPT.read_text(encoding="utf-8")
    calls = re.findall(r"=\s*detect_inconsistencies\(", src)
    assert len(calls) == 1, (
        f"expected exactly 1 call to detect_inconsistencies() in "
        f"{CORRELATION_CHAID_SCRIPT.name}, found {len(calls)} - the first call's "
        "result used to be discarded immediately when a second call overwrote it"
    )


# ---------------------------------------------------------------------------
# Fresh LOW-severity review (2026-09-10)
#
# 1. The 2026-08-22 audit seeded torch in Apex's two L0 scripts above but never
#    propagated the same fix to the per-module template
#    (modules/shared/analytics_scripts/, the source `generate_module_scripts.py`
#    retokenises for every other module) or to any of the 10 modules already
#    generated from it. Every module's three PyTorch-training scripts - the
#    Low-Performing NN, the Correlation/CHAID NN, and the regression script's
#    Step 8 NN - trained with unseeded torch (nn.Linear weight init +
#    DataLoader shuffle=True), so their report numbers were not reproducible
#    run-to-run on identical input, same defect class as the already-fixed
#    Apex scripts. Fixed identically in all 10 non-ESGRC modules plus the
#    shared template itself. ESGRC is intentionally excluded/untested here:
#    it predates the shared template and is out of scope for this pass.
#
# 2. Apex's own regression script (AI_ready_Multiple_Regression_Model_
#    implementation_L0_19_0.py) has a second, separate unseeded-randomness gap
#    beyond the one already fixed in 2026-08-22: its STEP 3 KFold(shuffle=True)
#    had no random_state, so avg_mse (which drives the reported Risk
#    Confidence Score) drew from the unseeded global numpy RNG and changed
#    run-to-run even after the existing torch.manual_seed/np.random.seed calls
#    later in the file. Fixed by pinning random_state to the same
#    ANALYTICS_SEED convention.
#
# 3. Apex's SS_x_bar_r_chart_fmea_L0_6_0.py computes RPN = S * O * D with O
#    (Occurrence) uncapped, while every module-level x_bar_r_chart_fmea_*.py
#    (all 12, including ESGRC) caps O at 10 - the top of the standard FMEA
#    1-10 occurrence scale. This is a real inconsistency: the same metric with
#    many signals scores a different, higher RPN in the enterprise L0 report
#    than in its own module's report. Fixed by capping Apex's copy to match.
# ---------------------------------------------------------------------------

X_BAR_R_SCRIPT = APEX_SCRIPTS / "SS_x_bar_r_chart_fmea_L0_6_0.py"

SHARED_DIR = MODULES_DIR / "shared" / "analytics_scripts"

# Modules generated from (or, for "shared", constituting) the shared 5-script
# template. ESGRC predates the template and is excluded, as is apex itself
# (a consolidator, not a template consumer).
TEMPLATE_MODULES = [
    "shared", "brand", "bspt", "customer", "enterprise", "ictm",
    "integration", "mkts", "product", "resource", "service",
]


def _one_match(directory: Path, pattern: str) -> Path:
    matches = list(directory.glob(pattern))
    assert len(matches) == 1, f"expected exactly one match for {pattern} in {directory}, found {matches}"
    return matches[0]


@pytest.mark.parametrize("module", TEMPLATE_MODULES)
def test_module_pytorch_scripts_seed_torch(module: str):
    """Every module's Low-Performing NN, Correlation/CHAID NN, and regression
    Step 8 NN train a torch model with DataLoader shuffle=True. Without
    torch.manual_seed(...) first, weight init and batch order are drawn from
    an unseeded global RNG, so report numbers are not reproducible run-to-run
    on identical input - the same defect class already fixed in Apex's own
    L0 scripts (see test_torch_training_is_seeded above)."""
    scripts_dir = MODULES_DIR / module / "analytics_scripts"
    scripts = [
        _one_match(scripts_dir, "AI_ready_Low_Performing_M_G_SM_*.py"),
        _one_match(scripts_dir, "Correlation_CHAID_FT_Analysis_*.py"),
        _one_match(scripts_dir, "AI_ready_Mutiple_Regression_Model_implementation_*.py"),
    ]
    for script in scripts:
        src = script.read_text(encoding="utf-8")
        assert "import torch" in src, f"{script.name} no longer imports torch - test is stale"
        assert re.search(r"torch\.manual_seed\(", src), (
            f"{script.name} (module={module}) trains a PyTorch model without "
            "seeding torch first, so report numbers are not reproducible "
            "run-to-run"
        )


def test_apex_regression_kfold_is_seeded():
    """STEP 3's KFold(shuffle=True) must pin random_state - otherwise it draws
    from the unseeded global numpy RNG and avg_mse (which drives the reported
    Risk Confidence Score) is not reproducible run-to-run, independent of the
    torch/numpy seeding already covered by test_torch_training_is_seeded."""
    src = REGRESSION_SCRIPT.read_text(encoding="utf-8")
    kfold_calls = re.findall(r"KFold\([^)]*\)", src)
    assert kfold_calls, f"no KFold(...) call found in {REGRESSION_SCRIPT.name} - test is stale"
    for call in kfold_calls:
        if "shuffle=True" in call:
            assert "random_state" in call, (
                f"{REGRESSION_SCRIPT.name} calls {call} with shuffle=True but no "
                "random_state, so its split (and everything derived from it) is "
                "not reproducible run-to-run"
            )


def test_apex_rpn_occurrence_matches_module_template():
    """Apex's SS_x_bar_r_chart_fmea_L0_6_0.py must cap RPN's Occurrence factor
    at 10, exactly like every module-level x_bar_r_chart_fmea_*.py. An
    unbounded Occurrence would give the same metric a different (higher) RPN
    in the enterprise roll-up than in its own module's report."""
    assert X_BAR_R_SCRIPT.exists(), f"expected script not found: {X_BAR_R_SCRIPT}"
    l0_src = X_BAR_R_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"O\s*=\s*min\(10,\s*max\(1,\s*signals_count\)\)", l0_src), (
        f"{X_BAR_R_SCRIPT.name}'s rpn_score() does not cap Occurrence at 10 "
        "like every module-level x_bar_r_chart_fmea_*.py does"
    )

    module_script = _one_match(SHARED_DIR, "x_bar_r_chart_fmea_*.py")
    module_src = module_script.read_text(encoding="utf-8")
    assert re.search(r"O\s*=\s*min\(10,\s*max\(1,\s*signals_count\)\)", module_src), (
        f"{module_script.name} no longer caps Occurrence at 10 - test is stale"
    )


def test_consolidation_script_warns_on_row_count_mismatch():
    """consolidate_with_mapping() concatenates every module's
    data_for_risk_assessment_<module>.csv with pd.concat(axis=1), which aligns
    by row position and NaN-pads any shorter file instead of raising - a
    module produced by an out-of-sync pipeline run would silently misalign
    every row after it with no indication in the output. There must be a
    warning covering this."""
    src = CONSOLIDATION_SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"len\(df\)\s*!=\s*len\(dataframes\[0\]\)", src), (
        f"{CONSOLIDATION_SCRIPT.name} no longer checks row-count consistency "
        "across module files before concatenating them"
    )
