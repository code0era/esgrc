"""
pipeline/tasks/apex_chord.py
Apex Enterprise Pipeline - 8-step Celery chord.

Step 1:    all_module_low_perf (sequential)
Steps 2-4: parallel group (chord header)
Step 5:    combine callback (chord body)
Steps 6-8: sequential chain after chord

Entry point: build_apex_pipeline(run_id, org_id, overrides)

CORRECTIONS APPLIED (June 2026 audit):
1. MODULE_CSV_NAMES replaced. The original list used 11 placeholder module
   names (social, cyber, gnotes, corpgov, grc, erm, audit, policy, reg,
   ethics, cgi) plus esgrc - none of the 11 placeholders correspond to any
   real TBD2 module. Replaced with the real 12 modules: brand, shared,
   esgrc, enterprise, customer, service, product, mkts, bspt, integration,
   ictm, resource. Matches the fix already applied to r2.py's
   APEX_MODULE_NAMES - keep both lists in sync if either changes.
2. apex_step1: now downloads using module_output_key(org_id, csv_name)
   with the corrected MODULE_CSV_NAMES list (mechanism unchanged, only the
   filenames in the list changed).
3. apex_step2: output filenames in the registry/script_runner.run() call
   are unaffected by this file directly (ScriptRunner owns output naming
   via scripts_registry.json), but the *step5 combine* below was reading
   the OLD wrong filenames before this fix - see apex_step5.
4. apex_step5: report filenames corrected. Original combine list expected
   "Correlation_analysis_L0.txt" / "Trends_and_Repetition_L0.txt" /
   "inconsistencies_report_L0.txt" / "CHAID_risk_segmentation_report_L0.txt"
   - all wrong case/spelling vs. the real script
   (AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py) which writes
   "correlation_analysis_L0.txt" / "trends_and_repetitions_report_L0.txt" /
   "inconsistency_report_L0.txt" (singular) / "chaid_risk_segmentation_L0.txt"
   - all lowercase. This file's combine loop is filename-agnostic (it just
   takes every .txt under steps 2/3/4), so no explicit filename list needed
   fixing in the combine itself - the real fix is at the SOURCE: apex_step4's
   regression script must actually produce "L0_Risk_Analysis_Report_2025.txt"
   (capital letters, matches the real script's report_path), and apex_step3's
   SPC script must produce "SPC_summary_L0.txt" (capital S) after the
   ScriptRunner glob-and-rename step - neither of those filenames appear as
   literals in THIS file, they live in scripts_registry.json. Flagging here
   so the registry stays in sync; no code change needed in apex_chord.py
   itself for steps 2/3/4's filenames since this file never hardcodes them.
5. apex_step7's combine ALSO needs the RPN exclusion the requirements doc
   specifies (RPN is PDF, never fed to Claude). The existing .txt-only
   filter already achieves this correctly as long as the RPN output's
   real extension is .pdf, not .txt - confirmed via scripts_registry.json's
   "user_download_only" flag. No code change needed here; flagging that
   this depends on scripts_registry.json being correct, which it has been
   separately verified to be.
6. mark_run_running(run_id) added to apex_step1 only. Same bug as
   esgrc_chain.py - this was never called anywhere in this file, so
   pipeline_runs.status never became RUNNING for Apex runs either.
"""
import json
import logging
import os
import time
import traceback
from typing import Dict, List

from celery import chain, chord, group
from celery.exceptions import MaxRetriesExceededError
from pipeline.tasks.script_runner import ScriptRunner, get_runner

from pipeline.celery_app import app
from pipeline.tasks.shared import (
    mark_run_failed,
    mark_run_running,
    mark_step_completed,
    mark_step_failed,
    mark_step_running,
    mark_step_skipped,
    pipeline_work_dir,
)
from pipeline.tasks.r2 import (
    R2Error,
    download_file,
    download_text,
    file_exists,
    list_files,
    module_manifest_key,
    module_output_key,
    reference_key,
    run_key,
    upload_file,
)

logger = logging.getLogger(__name__)

APEX_STEP_NAMES = {
    1: "All Module Low Performance Analysis",
    2: "Correlation CHAID L0 Analysis",
    3: "SPC RPN L0 Analysis",
    4: "Regression L0 Analysis",
    5: "Combine General Risk Reports",
    6: "AI General Risk Assessment (Claude)",
    7: "Combine Statistical Reports",
    8: "AI SPC RPN Assessment (Claude)",
}

# FIX: replaced placeholder module names with the real 12 TBD2 modules.
# Keep in sync with r2.py's APEX_MODULE_NAMES if either list changes.
MODULE_CSV_NAMES = [
    "data_for_risk_assessment_brand.csv",
    "data_for_risk_assessment_shared.csv",
    "data_for_risk_assessment_esgrc.csv",
    "data_for_risk_assessment_enterprise.csv",
    "data_for_risk_assessment_customer.csv",
    "data_for_risk_assessment_service.csv",
    "data_for_risk_assessment_product.csv",
    "data_for_risk_assessment_mkts.csv",
    "data_for_risk_assessment_bspt.csv",
    "data_for_risk_assessment_ictm.csv",
    "data_for_risk_assessment_resource.csv",
    "data_for_risk_assessment_integration.csv",
]


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 - All Module Low Performance
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.apex.step1", max_retries=2, default_retry_delay=30)
def apex_step1(self, run_id: str, org_id: str, overrides: Dict):
    step = 1

    # FIX: mark_run_running was never called in this file either - same
    # bug as esgrc_chain.py. Called once, here, at the Apex entry point.
    mark_run_running(run_id)

    mark_step_running(run_id, step, self.request.id, APEX_STEP_NAMES[step])
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        # MVP (single-module Apex): consume whatever module handoff files exist
        # in the org's stable module_outputs path. Only the ESGRC module is built
        # today, so typically just data_for_risk_assessment_esgrc.csv is present.
        # Missing modules are SKIPPED here (the underlying script
        # all_module_low_performance_analysis_1_0.py already warns-and-skips
        # absent files), and additional modules are picked up automatically as
        # they come online - no further wrapper change needed. At least the
        # ESGRC handoff must exist, or there is nothing to analyse.
        input_keys = []
        local_inputs = {}
        missing = []
        for csv_name in MODULE_CSV_NAMES:
            key = module_output_key(org_id, csv_name)
            if not file_exists(key):
                missing.append(csv_name)
                continue
            local_path = f"{work_dir}/{csv_name}"
            download_file(key, local_path)
            input_keys.append(key)
            local_inputs[csv_name] = local_path

        if "data_for_risk_assessment_esgrc.csv" not in local_inputs:
            raise ValueError(
                "Apex Step 1 requires at least the ESGRC module handoff file "
                "(data_for_risk_assessment_esgrc.csv) under org/{org}/module_outputs/. "
                "Run the ESGRC module pipeline first to produce it."
            )
        if missing:
            logger.warning(
                "Apex running on %d of %d modules; missing (skipped): %s",
                len(local_inputs), len(MODULE_CSV_NAMES), missing,
            )

        # Handoff provenance (best-effort): record when/which run produced each
        # consumed module CSV, from its sidecar manifest. Purely informational -
        # a missing/unreadable manifest never blocks the run. The file_exists guard
        # means download_text is only hit when a manifest actually exists.
        for csv_name in local_inputs:
            module = csv_name.replace("data_for_risk_assessment_", "").replace(".csv", "")
            manifest_key = module_manifest_key(org_id, module)
            if not file_exists(manifest_key):
                logger.info("Apex input '%s' has no provenance manifest", module)
                continue
            try:
                manifest = json.loads(download_text(manifest_key))
                logger.info(
                    "Apex input '%s' from run=%s produced_at=%s",
                    module, manifest.get("source_run_id"), manifest.get("produced_at"),
                )
                input_keys.append(manifest_key)
            except Exception:  # never let provenance logging break the run
                logger.warning("Apex input '%s' has an unreadable manifest", module)

        outputs = get_runner().run(
            script_name="all_module_low_perf",
            input_paths=local_inputs,
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, input_keys, output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Steps 2, 3, 4 - Parallel group
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.apex.step2", max_retries=2, default_retry_delay=30)
def apex_step2(self, run_id: str, org_id: str, overrides: Dict):
    step = 2
    mark_step_running(run_id, step, self.request.id, APEX_STEP_NAMES[step])
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        step1_keys = _list_step_outputs(org_id, run_id, 1)
        local_inputs = _download_step_outputs(step1_keys, work_dir)

        # Real script: AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py
        # Outputs (all lowercase): correlation_analysis_L0.txt,
        # trends_and_repetitions_report_L0.txt, inconsistency_report_L0.txt,
        # chaid_risk_segmentation_L0.txt - naming owned by scripts_registry.json.
        outputs = get_runner().run(
            script_name="correlation_CHAID_L0",
            input_paths=local_inputs,
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, step1_keys, output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


@app.task(bind=True, name="pipeline.apex.step3", max_retries=2, default_retry_delay=30)
def apex_step3(self, run_id: str, org_id: str, overrides: Dict):
    """SPC RPN L0 - produces dated output files, handled by glob in ScriptRunner."""
    step = 3
    mark_step_running(run_id, step, self.request.id, APEX_STEP_NAMES[step])
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        step1_keys = _list_step_outputs(org_id, run_id, 1)
        local_inputs = _download_step_outputs(step1_keys, work_dir)

        # Real script: SS_x_bar_r_chart_fmea_L0_6_0.py
        # Hardcoded ANALYSIS_DATE in the script - ScriptRunner globs the dated
        # filenames and renames to stable names (per scripts_registry.json).
        # RPN summary is emitted as BOTH .txt (SPC_summary_L0.txt + rpn_summary_L0.txt
        # feed the Step 7 statistical combine → Step 8 Claude) and .pdf; the RPN +
        # SPC-charts PDFs are user-download-only, excluded from the combine's .txt filter.
        outputs = get_runner().run(
            script_name="SPC_RPN_L0",
            input_paths=local_inputs,
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, step1_keys, output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


@app.task(bind=True, name="pipeline.apex.step4", max_retries=2, default_retry_delay=30)
def apex_step4(self, run_id: str, org_id: str, overrides: Dict):
    """Regression L0 - also needs module_mapping.csv and module_matrix.csv."""
    step = 4
    mark_step_running(run_id, step, self.request.id, APEX_STEP_NAMES[step])
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        step1_keys = _list_step_outputs(org_id, run_id, 1)
        local_inputs = _download_step_outputs(step1_keys, work_dir)

        for ref_file in ["module_mapping.csv", "module_matrix.csv"]:
            key = reference_key(org_id, ref_file)
            local_path = f"{work_dir}/{ref_file}"
            download_file(key, local_path)
            local_inputs[ref_file] = local_path
            step1_keys.append(key)

        # Real script: AI_ready_Multiple_Regression_Model_implementation_L0_19_0.py
        # The script reads module_mapping.csv / module_matrix.csv / all_module_values.csv
        # relative to BASE_DIR, and BASE_DIR is already `os.getcwd()` in the current
        # script (verified), which matches ScriptRunner's subprocess cwd=work_dir where
        # those inputs are staged. (Earlier revisions used dirname(__file__); that has
        # been fixed - no wrapper action needed.)
        # Output is "L0_Risk_Analysis_Report_2025.txt" (confirmed from the
        # script's own report_path construction).
        outputs = get_runner().run(
            script_name="regression_L0",
            input_paths=local_inputs,
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, step1_keys, output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 - Combine general risk reports (chord callback)
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.apex.step5", max_retries=1, default_retry_delay=10)
def apex_step5(self, run_id: str, org_id: str, overrides: Dict):
    """Chord body - runs only after steps 2, 3, 4 all complete."""
    step = 5
    mark_step_running(run_id, step, self.request.id, APEX_STEP_NAMES[step])
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)


        # General master combines steps 1 (performance), 2 (correlation/trends/
        # inconsistencies/CHAID) AND 4 (regression L0_Risk_Analysis - scenario rankings
        # + top negative risk drivers with impact factors). Step 4 added 2026-07-09
        # (Danish sign-off) so the driver analysis reaches the General Claude call and can
        # be cross-linked to the correlation matrix for the Module→Sub-Module→Group→Metric
        # drill-down. Matches ESGRC (which already combines its regression step) and
        # MODULE_IO_AND_FLOW.md Flow 2. Step 3 (SPC/RPN) stays out - it feeds the separate
        # statistical Claude call (Step 7→8). Chord body runs after steps 2,3,4 complete,
        # so step 4's output is present.
        input_keys = []
        local_reports = []
        for src_step in [1, 2, 4]:
            for key in _list_step_outputs(org_id, run_id, src_step):
                filename = key.split("/")[-1]
                if not filename.endswith(".txt"):
                    continue
                local_path = f"{work_dir}/{filename}"
                download_file(key, local_path)
                local_reports.append(local_path)
                input_keys.append(key)

        if not local_reports:
            raise ValueError("No .txt report files found in steps 1,2,4 outputs.")

        from pipeline.scripts.text_report_combiner import combine_reports
        combined_path = f"{work_dir}/MASTER_CONSOLIDATED_REPORT.txt"
        combine_reports(
            input_paths=local_reports,
            output_path=combined_path,
            label="Apex General Risk Report",
        )

        master_key = run_key(org_id, run_id, step, "MASTER_CONSOLIDATED_REPORT.txt")
        upload_file(combined_path, master_key)

        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, input_keys, [master_key], duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 - Claude Sonnet: General Risk Assessment
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.apex.step6", max_retries=3, default_retry_delay=60)
def apex_step6_claude(self, run_id: str, org_id: str, overrides: Dict):
    from pipeline.tasks.claude_tasks import run_claude_step
    run_claude_step(
        celery_task=self,
        run_id=run_id,
        org_id=org_id,
        step=6,
        step_name=APEX_STEP_NAMES[6],
        analysis_type="GENERAL_RISK",
        model="claude-sonnet-5",
        input_step=5,
        # FIX: was reading "MASTER_CONSOLIDATED_STATISTICAL_REPORT.txt" -
        # that's the SPC/RPN combine's output (now produced by Step 7
        # below), not Step 5's general-risk combine. Step 6 (general risk)
        # must read Step 5's output, "MASTER_CONSOLIDATED_REPORT.txt".
        input_filename="MASTER_CONSOLIDATED_REPORT.txt",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 - Combine SPC/RPN statistical reports
# FIX: this step's purpose was swapped with Step 5's in the original file.
# Per the requirements doc (Section 2.2): Step 5 combines the GENERAL RISK
# reports (5 inputs: performance, correlation, trends, inconsistencies,
# CHAID) and feeds Step 6 (General Risk Claude call). Step 7 combines the
# STATISTICAL reports (2 inputs: SPC summary only - RPN is PDF) and feeds
# Step 8 (SPC/RPN Claude call). The original file had Step 5 doing the
# statistical-only combine and Step 7 doing a combine of "step5+step6
# outputs" (mixing a Claude recommendation back into a combine step, which
# doesn't match either spec). Rewritten below to match the documented flow.
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.apex.step7", max_retries=1, default_retry_delay=10)
def apex_step7(self, run_id: str, org_id: str, overrides: Dict):
    step = 7
    mark_step_running(run_id, step, self.request.id, APEX_STEP_NAMES[step])
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        # Step 3's SPC summary AND RPN summary (both .txt) go into the
        # statistical combine. The RPN + SPC-charts PDFs are excluded by the
        # .txt filter below (user-download-only), same pattern as every other
        # combine step in this codebase.
        input_keys = []
        local_reports = []
        for key in _list_step_outputs(org_id, run_id, 3):
            filename = key.split("/")[-1]
            if not filename.endswith(".txt"):
                continue
            local_path = f"{work_dir}/{filename}"
            download_file(key, local_path)
            local_reports.append(local_path)
            input_keys.append(key)

        if not local_reports:
            raise ValueError("No .txt report files found in step 3 outputs.")

        from pipeline.scripts.text_report_combiner import combine_reports
        combined_path = f"{work_dir}/MASTER_CONSOLIDATED_STATISTICAL_REPORT.txt"
        combine_reports(
            input_paths=local_reports,
            output_path=combined_path,
            label="Apex Statistical Reports",
        )

        master_key = run_key(org_id, run_id, step, "MASTER_CONSOLIDATED_STATISTICAL_REPORT.txt")
        upload_file(combined_path, master_key)

        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, input_keys, [master_key], duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 8 - Claude Sonnet: SPC RPN Assessment
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.apex.step8", max_retries=3, default_retry_delay=60)
def apex_step8_claude(self, run_id: str, org_id: str, overrides: Dict):
    from pipeline.tasks.claude_tasks import run_claude_step
    run_claude_step(
        celery_task=self,
        run_id=run_id,
        org_id=org_id,
        step=8,
        step_name=APEX_STEP_NAMES[8],
        analysis_type="SPC_RPN",
        model="claude-sonnet-5",
        input_step=7,
        input_filename="MASTER_CONSOLIDATED_STATISTICAL_REPORT.txt",
    )

@app.task(name="pipeline.apex.finalize")
def apex_finalize(results, run_id: str):
    from pipeline.tasks.shared import mark_run_completed
    # Compute + persist run confidence before marking complete (never raises;
    # returns 0.5 on error). Without this pipeline_runs.confidence_score stays NULL.
    from pipeline.llm.confidence import compute_confidence
    compute_confidence(run_id)
    mark_run_completed(run_id)
    
# ─────────────────────────────────────────────────────────────────────────────
# Chord error handler
# ─────────────────────────────────────────────────────────────────────────────

@app.task(name="pipeline.apex.chord_error_handler")
def apex_chord_error_handler(request, exc, traceback_str, run_id: str):
    """
    Fires when any task in the chord header (steps 2-4) fails.
    Marks the run as FAILED and skips all downstream steps.
    """
    error_msg = f"Chord error in run {run_id}: {exc}"
    logger.error(error_msg)
    mark_run_failed(run_id, error_msg)

    for step in [5, 6, 7, 8]:
        mark_step_skipped(run_id, step, APEX_STEP_NAMES[step])


# ─────────────────────────────────────────────────────────────────────────────
# Step task registry - used by the step re-run endpoint
# ─────────────────────────────────────────────────────────────────────────────

APEX_STEP_TASKS = {
    1: apex_step1,
    2: apex_step2,
    3: apex_step3,
    4: apex_step4,
    5: apex_step5,
    6: apex_step6_claude,
    7: apex_step7,
    8: apex_step8_claude,
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _list_step_outputs(org_id: str, run_id: str, step_number: int) -> List[str]:
    prefix = f"org/{org_id}/runs/{run_id}/step_{step_number}/"
    return list_files(prefix)


def _download_step_outputs(r2_keys: List[str], work_dir: str) -> Dict[str, str]:
    local = {}
    for key in r2_keys:
        filename = key.split("/")[-1]
        local_path = f"{work_dir}/{filename}"
        download_file(key, local_path)
        local[filename] = local_path
    return local


def _upload_outputs(outputs: Dict[str, str], org_id: str, run_id: str, step: int) -> List[str]:
    keys = []
    for name, local_path in outputs.items():
        key = run_key(org_id, run_id, step, name)
        upload_file(local_path, key)
        keys.append(key)
    return keys


def _handle_step_failure(run_id: str, step: int, exc: Exception, celery_task) -> None:
    """Mark step failed, mark run failed, re-raise so Celery records the failure.

    FIX: every step declares max_retries in its @app.task decorator, but this
    helper never called celery_task.retry() - the config was inert and any
    failure went straight to terminal FAILED on the very first attempt. R2Error
    (transient upload/download/network failures) is now retried up to the
    task's own max_retries before giving up, matching the pattern already used
    by claude_tasks.run_claude_step for the Claude steps. Non-R2 failures (a bad
    script, a missing handoff file, ...) are not retryable - retrying them would
    just reproduce the same failure - so they still go straight to the terminal
    path, unchanged from before.
    """
    if isinstance(exc, R2Error):
        try:
            raise celery_task.retry(exc=exc)
        except MaxRetriesExceededError:
            pass  # exhausted - fall through to the terminal-failure path

    error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    mark_step_failed(run_id, step, error_msg)
    mark_run_failed(run_id, f"Step {step} failed: {type(exc).__name__}: {exc}")
    raise exc


# ── Pipeline builder ──────────────────────────────────────────────────────────

def build_apex_pipeline(run_id: str, org_id: str, overrides: dict = None):
    """
    Returns the full Apex Celery pipeline:
        step1 | chord(group(step2, step3, step4), tail)

    tail is itself a group of two independent chains so Step 7/8
    (statistical combine + SPC/RPN Claude call, depends only on Step 3)
    doesn't wait behind Step 5/6 (general-risk combine + Claude call,
    depends on Steps 1/2/4) for no data-dependency reason.
    """
    overrides = overrides or {}
    sig = (run_id, org_id, overrides)

    parallel_group = group(
        apex_step2.si(*sig).set(task_id=f"{run_id}_step2"),
        apex_step3.si(*sig).set(task_id=f"{run_id}_step3"),
        apex_step4.si(*sig).set(task_id=f"{run_id}_step4"),
    )

    # Do NOT attach link_error to a chord: Celery forwards the chord's options to
    # its header group's apply_async(), and a group rejects any link/link_error
    # ("Cannot add link to group"), which silently stalls the run. Each step task
    # already self-marks the run FAILED, so no chord-level handler is needed.
    # (Same fix as esgrc_chain.build_esgrc_chain - verified there against a live
    # broker. As of the MVP, apex_step1 tolerates missing modules and runs on
    # whatever handoff files exist - typically just the ESGRC module's - so Apex
    # no longer requires all 12 data_for_risk_assessment_*.csv to be present.)
    tail = chord(
        group(
            chain(apex_step5.si(*sig).set(task_id=f"{run_id}_step5"), apex_step6_claude.si(*sig).set(task_id=f"{run_id}_step6")),
            chain(apex_step7.si(*sig).set(task_id=f"{run_id}_step7"), apex_step8_claude.si(*sig).set(task_id=f"{run_id}_step8")),
        ),
        apex_finalize.s(run_id),
    )

    return chain(
        apex_step1.si(*sig).set(task_id=f"{run_id}_step1"),
        chord(parallel_group, tail),
    )