"""
pipeline/tasks/esgrc_chain.py
ESGRC Module Pipeline - 7-step Celery chain (hybrid parallel structure).

Steps 1-6: analytics script wrappers (this file).
Step 7:    Claude Haiku call (pipeline/tasks/claude_tasks.py - Dev C).

Chain entry point: build_esgrc_chain(run_id, org_id, overrides)

CORRECTIONS APPLIED (June 2026 audit):
1. esgrc_step1: input filenames fixed. "input_metrics_data.csv" was wrong -
   the real script (AI_ready_Low_Performing_M_G_SM_ESGRC_4_0.py) reads
   "input_metric_values_esgrc.csv". The separate "low_performing_json_file.json"
   input was removed - confirmed the real script only reads
   "esgrc_performance_json_file.json"; there is no second JSON input.
2. esgrc_step4: re-reads the original input file, same filename fix as Step 1
   (was "input_metrics_data.csv", now "input_metric_values_esgrc.csv"), and
   downloaded from the stable reference path (it's a user upload, not a
   step output) rather than from Step 2's outputs.
3. esgrc_step6: report filenames corrected to match actual lowercase script
   output. RPN output is a PDF, not text, and is excluded from the combine
   (Claude never receives PDFs - confirmed in requirements doc, PDFs are
   user-download-only deliverables).
4. mark_run_running(run_id) added to esgrc_step1 only. CONFIRMED BUG: neither
   this file nor apex_chord.py ever called mark_run_running anywhere. Without
   it, pipeline_runs.status never transitions PENDING -> RUNNING for the
   entire run - it jumps straight from PENDING to COMPLETED/FAILED. This
   silently broke rerun_step's "cannot rerun while RUNNING" guard (it could
   never fire) and would show the wrong status in the Pipeline Monitor UI.
5. build_esgrc_chain rewritten to a hybrid parallel structure. Steps 4 and 5
   each only depend on Step 1's output (module_values_esgrc.csv / the raw
   upload) - neither depends on Step 2's filtered CSVs. Step 3 is the only
   one that depends on Step 2. The original code ran all of 2-3-4-5 as one
   strict sequential chain, serializing work that doesn't need to be
   serialized. ACTUAL structure built by build_esgrc_chain (see the code):
       Step 1
         -> chord(
              group(Step 2, Step 4, Step 5),   # parallel header tasks
              chain(Step 3, Step 6),           # chord body: 3 (needs 2) then combine
            )
   Step 3 lives in the chord *body* (chained before Step 6) rather than in a
   chain inside the header group: Celery rejects a chain-in-a-group header with
   "Cannot add link to group", so the 2->3 dependency is expressed by placing
   Step 3 immediately before the Step 6 combine in the body. Step 7 (Claude) is
   appended by the caller (pipeline_router), not by build_esgrc_chain. Tasks use
   .si() (immutable signature) since none need the previous task's return value -
   run_id/org_id/overrides are passed explicitly and all state lives in
   Postgres/Redis via mark_step_*.
6. esgrc_chord_error_handler is defined (mirroring apex_chord.py) but is NOT
   attached via link_error - wiring it onto the hybrid chord reintroduced
   Celery's "Cannot add link to group" error, so failure handling relies on
   each task's own _handle_step_failure (which marks the step + run FAILED and
   re-raises). The handler is retained as a tested, ready-to-wire fallback but
   never fires in the current structure.
"""
import logging
import os
import time
import traceback
from typing import Dict

from celery import chain, chord, group
from celery.exceptions import MaxRetriesExceededError
from pipeline.tasks.script_runner import ScriptRunner, get_runner

from pipeline.celery_app import app
from pipeline.tasks.shared import (
    mark_run_running,
    mark_run_failed,
    mark_step_completed,
    mark_step_failed,
    mark_step_running,
    mark_step_skipped,
    pipeline_work_dir,
)
from pipeline.tasks.r2 import (
    R2Error,
    download_file,
    list_files,
    reference_key,
    run_key,
    upload_file,
    write_module_handoff,
)

logger = logging.getLogger(__name__)

# ── Step metadata ─────────────────────────────────────────────────────────────
ESGRC_STEP_NAMES = {
    1: "Data Preparation 1",
    2: "Data Preparation 2",
    3: "Correlation CHAID FT Analysis",
    4: "SPC RPN Analysis",
    5: "Regression Analysis",
    6: "Combine Reports",
    7: "AI Risk Assessment (Claude)",
}

SCRIPTS_DIR = os.environ.get("SCRIPTS_DIR", "/app/pipeline/scripts")


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 - Data Preparation 1
# ─────────────────────────────────────────────────────────────────────────────

@app.task(
    bind=True,
    name="pipeline.esgrc.step1",
    max_retries=2,
    default_retry_delay=30,
)
def esgrc_step1(self, run_id: str, org_id: str, overrides: Dict):
    step = 1
    step_name = ESGRC_STEP_NAMES[step]

    # FIX: mark_run_running was never called anywhere in this file or
    # apex_chord.py. Without this, pipeline_runs.status never becomes
    # RUNNING - it stays PENDING until COMPLETED/FAILED. Called once,
    # here, at the true entry point of the pipeline.
    mark_run_running(run_id)

    step_result_id = mark_step_running(run_id, step, self.request.id, step_name)
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        # ── Download inputs ───────────────────────────────────────────────
        # FIX: filename was "input_metrics_data.csv" - wrong. The real
        # script reads "input_metric_values_esgrc.csv".
        input_r2_key = overrides.get(
            "input_metrics_data",
            reference_key(org_id, "input_metric_values_esgrc.csv"),
        )
        local_input = f"{work_dir}/input_metric_values_esgrc.csv"
        download_file(input_r2_key, local_input)

        # FIX: there is no separate "low_performing_json_file.json" input.
        # The real script only reads esgrc_performance_json_file.json.
        perf_key = overrides.get(
            "esgrc_performance_json",
            reference_key(org_id, "esgrc_performance_json_file.json"),
        )
        local_perf = f"{work_dir}/esgrc_performance_json_file.json"
        download_file(perf_key, local_perf)

        # ── Run script ────────────────────────────────────────────────────
        runner = get_runner()
        outputs = runner.run(
            script_name="data_prep_1",
            input_paths={
                "input_metric_values_esgrc.csv": local_input,
                "esgrc_performance_json_file.json": local_perf,
            },
            output_dir=work_dir,
        )

        # ── Upload outputs ────────────────────────────────────────────────
        output_keys = []
        for name, local_path in outputs.items():
            key = run_key(org_id, run_id, step, name)
            upload_file(local_path, key)
            output_keys.append(key)

        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, [input_r2_key, perf_key], output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 - Data Preparation 2
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.esgrc.step2", max_retries=2, default_retry_delay=30)
def esgrc_step2(self, run_id: str, org_id: str, overrides: Dict):
    step = 2
    step_name = ESGRC_STEP_NAMES[step]
    mark_step_running(run_id, step, self.request.id, step_name)
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        # Step 2 consumes Step 1's outputs (module_values_esgrc.csv)
        step1_outputs = _list_step_outputs(org_id, run_id, step_number=1)
        local_inputs = _download_step_outputs(step1_outputs, work_dir)

        esgrc_perf_key = overrides.get(
            "esgrc_performance_json",
            reference_key(org_id, "esgrc_performance_json_file.json"),
        )
        local_perf = f"{work_dir}/esgrc_performance_json_file.json"
        download_file(esgrc_perf_key, local_perf)

        # Real script: M_G_Sub_M_split_ESGRC_1_0.py
        runner = get_runner()
        outputs = runner.run(
            script_name="data_prep_2",
            input_paths={**local_inputs, "esgrc_performance_json_file.json": local_perf},
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        input_keys = step1_outputs + [esgrc_perf_key]
        mark_step_completed(run_id, step, input_keys, output_keys, duration_ms)

        # ── Handoff: copy data_for_risk_assessment_esgrc.csv to the stable Apex
        # path + write a provenance manifest (source run + timestamp) beside it,
        # so Apex Step 1 auto-picks the latest and the UI can show data freshness.
        for name, local_path in outputs.items():
            if "data_for_risk_assessment" in name:
                write_module_handoff(local_path, org_id, "esgrc", run_id)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 - Correlation CHAID FT Analysis
# Depends on Step 2's filtered CSVs. Runs inside the chord's parallel group,
# chained after Step 2 specifically (see build_esgrc_chain below).
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.esgrc.step3", max_retries=2, default_retry_delay=30)
def esgrc_step3(self, run_id: str, org_id: str, overrides: Dict):
    step = 3
    step_name = ESGRC_STEP_NAMES[step]
    mark_step_running(run_id, step, self.request.id, step_name)
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        step2_outputs = _list_step_outputs(org_id, run_id, step_number=2)
        local_inputs = _download_step_outputs(step2_outputs, work_dir)

        # The correlation script also reads esgrc_performance_json_file.json for
        # the metric/group/sub-module NAME lookup (build_metric_lookup). Without
        # it the script silently falls back to raw IDs in reports #2-#5. Steps 2
        # and 5 already stage this file; stage it here too so the reports carry
        # human-readable names.
        esgrc_perf_key = overrides.get(
            "esgrc_performance_json",
            reference_key(org_id, "esgrc_performance_json_file.json"),
        )
        local_perf = f"{work_dir}/esgrc_performance_json_file.json"
        download_file(esgrc_perf_key, local_perf)

        # Real script: Correlation_CHAID_FT_Analysis_ESGRC_8_0.py
        outputs = get_runner().run(
            script_name="correlation_CHAID_FT",
            input_paths={**local_inputs, "esgrc_performance_json_file.json": local_perf},
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, step2_outputs + [esgrc_perf_key], output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 - SPC RPN Analysis
# FIX: this re-reads the ORIGINAL uploaded input file, not Step 2's output.
# Independent of Steps 2/3 - runs in parallel with them.
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.esgrc.step4", max_retries=2, default_retry_delay=30)
def esgrc_step4(self, run_id: str, org_id: str, overrides: Dict):
    step = 4
    step_name = ESGRC_STEP_NAMES[step]
    mark_step_running(run_id, step, self.request.id, step_name)
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        # FIX: was downloading from Step 2's outputs using the wrong
        # filename ("input_metrics_data.csv"). The real script
        # (x_bar_r_chart_fmea_esg_5_0.py) re-reads the ORIGINAL uploaded
        # file, "input_metric_values_esgrc.csv", from the stable reference
        # path - it does not depend on Step 2 at all.
        input_key = overrides.get(
            "input_metrics_data",
            reference_key(org_id, "input_metric_values_esgrc.csv"),
        )
        local_input = f"{work_dir}/input_metric_values_esgrc.csv"
        download_file(input_key, local_input)

        outputs = get_runner().run(
            script_name="SPC_RPN",
            input_paths={"input_metric_values_esgrc.csv": local_input},
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, [input_key], output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 5 - Regression Analysis
# Depends only on Step 1's module_values_esgrc.csv output and the original
# performance JSON. Independent of Steps 2/3 - runs in parallel with them.
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.esgrc.step5", max_retries=2, default_retry_delay=30)
def esgrc_step5(self, run_id: str, org_id: str, overrides: Dict):
    step = 5
    step_name = ESGRC_STEP_NAMES[step]
    mark_step_running(run_id, step, self.request.id, step_name)
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        # FIX: depends on STEP 1's output (module_values_esgrc.csv), not
        # Step 2's. The original code pulled from step2_outputs, which
        # would never contain module_values_esgrc.csv (that's a Step 1
        # output, consumed but not re-emitted by Step 2).
        step1_outputs = _list_step_outputs(org_id, run_id, step_number=1)
        local_inputs = _download_step_outputs(step1_outputs, work_dir)

        esgrc_perf_key = overrides.get(
            "esgrc_performance_json",
            reference_key(org_id, "esgrc_performance_json_file.json"),
        )
        local_perf = f"{work_dir}/esgrc_performance_json_file.json"
        download_file(esgrc_perf_key, local_perf)

        # Real script: AI_ready_Mutiple_Regression_Model_implementation_ESGRC_5_0.py
        outputs = get_runner().run(
            script_name="regression_esgrc",
            input_paths={**local_inputs, "esgrc_performance_json_file.json": local_perf},
            output_dir=work_dir,
        )

        output_keys = _upload_outputs(outputs, org_id, run_id, step)
        duration_ms = int((time.time() - t0) * 1000)
        input_keys = step1_outputs + [esgrc_perf_key]
        mark_step_completed(run_id, step, input_keys, output_keys, duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 6 - Combine reports into MASTER (chord callback)
# Runs only after the parallel branch (Step2->Step3, Step4, Step5) completes.
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.esgrc.step6", max_retries=1, default_retry_delay=10)
def esgrc_step6(self, run_id: str, org_id: str, overrides: Dict):
    step = 6
    step_name = ESGRC_STEP_NAMES[step]
    mark_step_running(run_id, step, self.request.id, step_name)
    t0 = time.time()

    try:
        work_dir = pipeline_work_dir(run_id, step)

        input_keys = []
        local_reports = []

        # FIX: Step 1's report is now included (it was previously skipped
        # - the original loop only checked steps 3,4,5, dropping the
        # low-performing entities report entirely from the combine).
        for src_step in [1, 3, 4, 5]:
            step_outputs = _list_step_outputs(org_id, run_id, src_step)
            for key in step_outputs:
                filename = key.split("/")[-1]
                # .txt filter includes Step 4's metrics_summary.txt (#6) AND
                # rpn_summary.txt (#7) - both real .txt outputs - completing the
                # documented 8-input combine. The Step 4 RPN + SPC-charts PDFs are
                # user-download-only and excluded here.
                if not filename.endswith(".txt"):
                    continue
                local_path = f"{work_dir}/{filename}"
                download_file(key, local_path)
                local_reports.append(local_path)
                input_keys.append(key)

        if not local_reports:
            raise ValueError("No .txt report files found in steps 1,3-5 outputs.")

        from pipeline.scripts.text_report_combiner import combine_reports
        combined_path = f"{work_dir}/MASTER_CONSOLIDATED_REPORT.txt"
        combine_reports(
            input_paths=local_reports,
            output_path=combined_path,
            label="ESGRC Module Unified Report",
        )

        master_key = run_key(org_id, run_id, step, "MASTER_CONSOLIDATED_REPORT.txt")
        upload_file(combined_path, master_key)

        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, input_keys, [master_key], duration_ms)

    except Exception as exc:
        _handle_step_failure(run_id, step, exc, self)


# ─────────────────────────────────────────────────────────────────────────────
# Step 7 - Claude Haiku (imported from claude_tasks.py)
# ─────────────────────────────────────────────────────────────────────────────

@app.task(bind=True, name="pipeline.esgrc.step7", max_retries=3, default_retry_delay=60)
def esgrc_step7_claude(self, run_id: str, org_id: str, overrides: Dict):
    """Delegates to the shared Claude task."""
    from pipeline.tasks.claude_tasks import run_claude_step
    from pipeline.tasks.shared import mark_run_completed
    run_claude_step(
        celery_task=self,
        run_id=run_id,
        org_id=org_id,
        step=7,
        step_name=ESGRC_STEP_NAMES[7],
        analysis_type="MODULE_UNIFIED",
        model="claude-haiku-4-5",
        input_step=6,
        input_filename="MASTER_CONSOLIDATED_REPORT.txt",
    )
    # Compute + persist the run confidence score (never raises; returns 0.5 on
    # any error). Without this call pipeline_runs.confidence_score stays NULL.
    from pipeline.llm.confidence import compute_confidence
    compute_confidence(run_id)
    mark_run_completed(run_id)


# ─────────────────────────────────────────────────────────────────────────────
# Chord error handler - mirrors apex_chord.py's pattern.
# REQUIRED because a chord, unlike a chain, does not automatically stop
# downstream steps when one header task fails.
# ─────────────────────────────────────────────────────────────────────────────

@app.task(name="pipeline.esgrc.chord_error_handler")
def esgrc_chord_error_handler(request, exc, traceback_str, run_id: str):
    """
    Fires when any task in the parallel group (Step2->Step3 chain, Step4,
    or Step5) fails. Marks the run FAILED and skips remaining steps.
    """
    error_msg = f"Chord error in ESGRC run {run_id}: {exc}"
    logger.error(error_msg)
    mark_run_failed(run_id, error_msg)

    for step in [6, 7]:
        mark_step_skipped(run_id, step, ESGRC_STEP_NAMES[step])


# ─────────────────────────────────────────────────────────────────────────────
# Step task registry - used by the step re-run endpoint
# ─────────────────────────────────────────────────────────────────────────────

ESGRC_STEP_TASKS = {
    1: esgrc_step1,
    2: esgrc_step2,
    3: esgrc_step3,
    4: esgrc_step4,
    5: esgrc_step5,
    6: esgrc_step6,
    7: esgrc_step7_claude,
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _list_step_outputs(org_id: str, run_id: str, step_number: int):
    """List all R2 keys produced by a previous step."""
    prefix = f"org/{org_id}/runs/{run_id}/step_{step_number}/"
    return list_files(prefix)


def _download_step_outputs(r2_keys: list, work_dir: str) -> Dict[str, str]:
    """Download a list of R2 keys to work_dir. Returns {filename: local_path}."""
    local = {}
    for key in r2_keys:
        filename = key.split("/")[-1]
        local_path = f"{work_dir}/{filename}"
        download_file(key, local_path)
        local[filename] = local_path
    return local


def _upload_outputs(outputs: Dict[str, str], org_id: str, run_id: str, step: int) -> list:
    """Upload all script outputs to R2. Returns list of R2 keys."""
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


# ── Chain builder - called by the trigger endpoint ────────────────────────────

def build_esgrc_chain(run_id: str, org_id: str, overrides: dict = None):
    """
    Hybrid parallel ESGRC structure:

        Step 1
          -> chord(
               group(
                 chain(Step 2, Step 3),   # Step 3 needs Step 2's filtered CSVs
                 Step 4,                  # independent - only needs Step 1
                 Step 5,                  # independent - only needs Step 1
               ),
               Step 6 callback
             )

    Step 7 (Claude) is appended by the caller (pipeline_router.py), same as
    before - this function still only returns steps 1-6.

    CHANGED FROM ORIGINAL: was a strict sequential chain
    (1|2|3|4|5|6). Steps 4 and 5 do not depend on Steps 2/3's output and
    were being serialized for no reason. This costs real wall-clock time
    on every run with no correctness benefit.

    Uses .si() (immutable signature) throughout since no task here passes
    its return value to the next - all state lives in Postgres/Redis via
    the mark_step_* helpers, matching the existing pattern in apex_chord.py.
    """
    overrides = overrides or {}
    sig = (run_id, org_id, overrides)

    # NOTE: a chord header must be a *group of individual tasks* - a group that
    # contains a chain (the old `group(chain(step2,step3), step4, step5)`) makes
    # Celery raise "Cannot add link to group" when the chord is chained after
    # step1 (the nested chain is mis-upgraded during link dispatch). So the
    # parallel header holds only plain tasks (step2/step4/step5), and step3 -
    # which only needs step2's filtered CSVs (persisted to R2 by step2) - runs in
    # the chord BODY, right before the combine. step6 reads steps 3/4/5 outputs
    # from R2 by run+step, so ordering step3 before step6 preserves all inputs.
    parallel_group = group(
        esgrc_step2.si(*sig).set(task_id=f"{run_id}_step2"),
        esgrc_step4.si(*sig).set(task_id=f"{run_id}_step4"),
        esgrc_step5.si(*sig).set(task_id=f"{run_id}_step5"),
    )

    combine_tail = chain(
        esgrc_step3.si(*sig).set(task_id=f"{run_id}_step3"),
        esgrc_step6.si(*sig).set(task_id=f"{run_id}_step6"),
    )

    # IMPORTANT: do NOT attach link_error to the chord. Celery forwards the
    # chord's options to `header.apply_async()`, and a group rejects any
    # link/link_error ("Cannot add link to group") - which silently stalls the
    # run right after step1. Each step task already self-marks the run FAILED via
    # _handle_step_failure, so no chord-level error handler is needed.
    return chain(
        esgrc_step1.si(*sig).set(task_id=f"{run_id}_step1"),
        chord(parallel_group, combine_tail),
    )