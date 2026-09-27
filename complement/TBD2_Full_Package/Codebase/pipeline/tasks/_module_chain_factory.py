"""
pipeline/tasks/_module_chain_factory.py

Builds a module's 7 Celery tasks and its chain builder from a ModuleSpec, so a
new module needs a ~20-line chain file instead of a ~365-line copy.

This replaces the copy-the-template workflow for factory-built modules. The step
bodies here are the template's, verbatim in behaviour, with one deliberate
change described under LATE BINDING below. ESGRC is NOT built here: its chain
predates the template and is hand-written (see pipeline/modules.py).

Task names are unchanged - ``pipeline.{token}.step1`` .. ``.step7`` and
``pipeline.{token}.chord_error_handler`` - so queued tasks, the worker's routing
and the emergency-stop task_ids (``{run_id}_step{n}``) all behave exactly as
before.

LATE BINDING (the one behavioural change, and it fixes a real bug):
the old per-module chain files did ``from pipeline.tasks.r2 import download_file``,
binding the name at import time. That made ``patch("pipeline.tasks.r2.download_file")``
effective only while the chain had not yet been imported, so the module e2e tests
passed or failed depending on pytest collection order - adding a test that
imported a chain earlier broke them (fixed once already on 2026-08-04). Here the
helpers are reached through the module object (``r2.download_file(...)``), which
is resolved per call, so patching ``pipeline.tasks.r2`` always works and order
stops mattering.

Shape, identical to ESGRC:
    step1 -> chord( group( step2, step4, step5 ), chain(step3, step6) ) -> step7
Step 2 writes the Apex handoff, so Apex picks the module up with no Apex change.
"""
from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Dict

from celery import chain, chord, group
from celery.exceptions import MaxRetriesExceededError

from pipeline.celery_app import app
from pipeline.modules import ModuleSpec
from pipeline.tasks import r2, script_runner
from pipeline.tasks.shared import (
    mark_run_failed,
    mark_run_running,
    mark_step_completed,
    mark_step_failed,
    mark_step_running,
    mark_step_skipped,
    pipeline_work_dir,
)

logger = logging.getLogger(__name__)

CLAUDE_ANALYSIS_TYPE = "MODULE_UNIFIED"
CLAUDE_MODEL = "claude-haiku-4-5"


def step_names(spec: ModuleSpec) -> Dict[int, str]:
    """Run-timeline step names. Uses the display label, not the routing token."""
    return {
        1: f"{spec.label} Data Preparation 1 (low-performing)",
        2: f"{spec.label} Data Preparation 2 (hierarchy split + handoff)",
        3: f"{spec.label} Correlation / CHAID Analysis",
        4: f"{spec.label} SPC / RPN Analysis",
        5: f"{spec.label} Regression Analysis",
        6: f"{spec.label} Combine Reports",
        7: f"{spec.label} AI Module Assessment (Claude)",
    }


# ── Shared helpers (were duplicated verbatim in every chain file) ─────────────

def _list_step_outputs(org_id: str, run_id: str, step_number: int):
    return r2.list_files(f"org/{org_id}/runs/{run_id}/step_{step_number}/")


def _download_step_outputs(r2_keys, work_dir: str) -> Dict[str, str]:
    local = {}
    for key in r2_keys:
        local_path = f"{work_dir}/{key.split('/')[-1]}"
        r2.download_file(key, local_path)
        local[key.split("/")[-1]] = local_path
    return local


def _upload_outputs(outputs: Dict[str, str], org_id: str, run_id: str, step: int) -> list:
    keys = []
    for name, local_path in outputs.items():
        key = r2.run_key(org_id, run_id, step, name)
        r2.upload_file(local_path, key)
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
    if isinstance(exc, r2.R2Error):
        try:
            raise celery_task.retry(exc=exc)
        except MaxRetriesExceededError:
            pass  # exhausted - fall through to the terminal-failure path

    error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    mark_step_failed(run_id, step, error_msg)
    mark_run_failed(run_id, f"Step {step} failed: {type(exc).__name__}: {exc}")
    raise exc


def build_module_chain(spec: ModuleSpec) -> Dict[str, Any]:
    """
    Create and register one module's tasks. Called once per module, at import of
    that module's thin chain file. Returns the namespace the chain file re-exports.
    """
    MODULE = spec.token
    METRICS_CSV = spec.metrics_csv
    PERF_JSON = spec.perf_json
    STEP_NAMES = step_names(spec)
    KEY = spec.script_key

    # Step 1 - Data Preparation 1 (low-performing roll-up). The true entry point.
    @app.task(bind=True, name=f"pipeline.{MODULE}.step1", max_retries=2, default_retry_delay=30)
    def step1(self, run_id: str, org_id: str, overrides: Dict):
        step = 1
        mark_run_running(run_id)  # entry point - flips the run to RUNNING
        mark_step_running(run_id, step, self.request.id, STEP_NAMES[step])
        t0 = time.time()
        try:
            work_dir = pipeline_work_dir(run_id, step)

            input_key = overrides.get("input_metrics_data", r2.reference_key(org_id, METRICS_CSV))
            local_input = f"{work_dir}/{METRICS_CSV}"
            r2.download_file(input_key, local_input)

            perf_key = overrides.get("performance_json", r2.reference_key(org_id, PERF_JSON))
            local_perf = f"{work_dir}/{PERF_JSON}"
            r2.download_file(perf_key, local_perf)

            outputs = script_runner.get_runner().run(
                script_name=KEY("data_prep_1"),
                input_paths={METRICS_CSV: local_input, PERF_JSON: local_perf},
                output_dir=work_dir,
            )
            output_keys = _upload_outputs(outputs, org_id, run_id, step)
            mark_step_completed(run_id, step, [input_key, perf_key], output_keys,
                                int((time.time() - t0) * 1000))
        except Exception as exc:
            _handle_step_failure(run_id, step, exc, self)

    # Step 2 - Data Preparation 2 (hierarchy split). Produces the Apex handoff CSV.
    @app.task(bind=True, name=f"pipeline.{MODULE}.step2", max_retries=2, default_retry_delay=30)
    def step2(self, run_id: str, org_id: str, overrides: Dict):
        step = 2
        mark_step_running(run_id, step, self.request.id, STEP_NAMES[step])
        t0 = time.time()
        try:
            work_dir = pipeline_work_dir(run_id, step)
            step1_outputs = _list_step_outputs(org_id, run_id, 1)
            local_inputs = _download_step_outputs(step1_outputs, work_dir)

            perf_key = overrides.get("performance_json", r2.reference_key(org_id, PERF_JSON))
            local_perf = f"{work_dir}/{PERF_JSON}"
            r2.download_file(perf_key, local_perf)

            outputs = script_runner.get_runner().run(
                script_name=KEY("data_prep_2"),
                input_paths={**local_inputs, PERF_JSON: local_perf},
                output_dir=work_dir,
            )
            output_keys = _upload_outputs(outputs, org_id, run_id, step)
            mark_step_completed(run_id, step, step1_outputs + [perf_key], output_keys,
                                int((time.time() - t0) * 1000))

            # Apex handoff: copy data_for_risk_assessment_{MODULE}.csv to the stable
            # path + provenance manifest, so Apex step 1 auto-picks the latest.
            for name, local_path in outputs.items():
                if "data_for_risk_assessment" in name:
                    r2.write_module_handoff(local_path, org_id, MODULE, run_id)
        except Exception as exc:
            _handle_step_failure(run_id, step, exc, self)

    # Step 3 - Correlation / CHAID (needs step 2's filtered CSVs).
    @app.task(bind=True, name=f"pipeline.{MODULE}.step3", max_retries=2, default_retry_delay=30)
    def step3(self, run_id: str, org_id: str, overrides: Dict):
        step = 3
        mark_step_running(run_id, step, self.request.id, STEP_NAMES[step])
        t0 = time.time()
        try:
            work_dir = pipeline_work_dir(run_id, step)
            step2_outputs = _list_step_outputs(org_id, run_id, 2)
            local_inputs = _download_step_outputs(step2_outputs, work_dir)

            perf_key = overrides.get("performance_json", r2.reference_key(org_id, PERF_JSON))
            local_perf = f"{work_dir}/{PERF_JSON}"
            r2.download_file(perf_key, local_perf)  # name lookup for human-readable reports

            outputs = script_runner.get_runner().run(
                script_name=KEY("correlation"),
                input_paths={**local_inputs, PERF_JSON: local_perf},
                output_dir=work_dir,
            )
            output_keys = _upload_outputs(outputs, org_id, run_id, step)
            mark_step_completed(run_id, step, step2_outputs + [perf_key], output_keys,
                                int((time.time() - t0) * 1000))
        except Exception as exc:
            _handle_step_failure(run_id, step, exc, self)

    # Step 4 - SPC / RPN (re-reads the ORIGINAL upload; independent of steps 2/3).
    @app.task(bind=True, name=f"pipeline.{MODULE}.step4", max_retries=2, default_retry_delay=30)
    def step4(self, run_id: str, org_id: str, overrides: Dict):
        step = 4
        mark_step_running(run_id, step, self.request.id, STEP_NAMES[step])
        t0 = time.time()
        try:
            work_dir = pipeline_work_dir(run_id, step)
            input_key = overrides.get("input_metrics_data", r2.reference_key(org_id, METRICS_CSV))
            local_input = f"{work_dir}/{METRICS_CSV}"
            r2.download_file(input_key, local_input)

            outputs = script_runner.get_runner().run(
                script_name=KEY("spc_rpn"),
                input_paths={METRICS_CSV: local_input},
                output_dir=work_dir,
            )
            output_keys = _upload_outputs(outputs, org_id, run_id, step)
            mark_step_completed(run_id, step, [input_key], output_keys,
                                int((time.time() - t0) * 1000))
        except Exception as exc:
            _handle_step_failure(run_id, step, exc, self)

    # Step 5 - Regression (needs step 1's module_values_{MODULE}.csv; independent of 2/3).
    @app.task(bind=True, name=f"pipeline.{MODULE}.step5", max_retries=2, default_retry_delay=30)
    def step5(self, run_id: str, org_id: str, overrides: Dict):
        step = 5
        mark_step_running(run_id, step, self.request.id, STEP_NAMES[step])
        t0 = time.time()
        try:
            work_dir = pipeline_work_dir(run_id, step)
            step1_outputs = _list_step_outputs(org_id, run_id, 1)
            local_inputs = _download_step_outputs(step1_outputs, work_dir)

            perf_key = overrides.get("performance_json", r2.reference_key(org_id, PERF_JSON))
            local_perf = f"{work_dir}/{PERF_JSON}"
            r2.download_file(perf_key, local_perf)

            outputs = script_runner.get_runner().run(
                script_name=KEY("regression"),
                input_paths={**local_inputs, PERF_JSON: local_perf},
                output_dir=work_dir,
            )
            output_keys = _upload_outputs(outputs, org_id, run_id, step)
            mark_step_completed(run_id, step, step1_outputs + [perf_key], output_keys,
                                int((time.time() - t0) * 1000))
        except Exception as exc:
            _handle_step_failure(run_id, step, exc, self)

    # Step 6 - Combine reports into MASTER (chord callback; runs after 2->3, 4, 5).
    @app.task(bind=True, name=f"pipeline.{MODULE}.step6", max_retries=1, default_retry_delay=10)
    def step6(self, run_id: str, org_id: str, overrides: Dict):
        step = 6
        mark_step_running(run_id, step, self.request.id, STEP_NAMES[step])
        t0 = time.time()
        try:
            work_dir = pipeline_work_dir(run_id, step)
            input_keys, local_reports = [], []
            for src_step in [1, 3, 4, 5]:
                for key in _list_step_outputs(org_id, run_id, src_step):
                    if not key.endswith(".txt"):
                        continue
                    local_path = f"{work_dir}/{key.split('/')[-1]}"
                    r2.download_file(key, local_path)
                    local_reports.append(local_path)
                    input_keys.append(key)

            if not local_reports:
                raise ValueError(f"No .txt reports found in {MODULE} steps 1,3-5 outputs.")

            from pipeline.scripts.text_report_combiner import combine_reports
            combined_path = f"{work_dir}/MASTER_CONSOLIDATED_REPORT.txt"
            combine_reports(input_paths=local_reports, output_path=combined_path,
                            label=f"{spec.label} Module Unified Report")

            master_key = r2.run_key(org_id, run_id, step, "MASTER_CONSOLIDATED_REPORT.txt")
            r2.upload_file(combined_path, master_key)
            mark_step_completed(run_id, step, input_keys, [master_key],
                                int((time.time() - t0) * 1000))
        except Exception as exc:
            _handle_step_failure(run_id, step, exc, self)

    # Step 7 - Claude module assessment (delegates to the shared claude bridge).
    @app.task(bind=True, name=f"pipeline.{MODULE}.step7", max_retries=3, default_retry_delay=60)
    def step7_claude(self, run_id: str, org_id: str, overrides: Dict):
        from pipeline.tasks.claude_tasks import run_claude_step
        from pipeline.tasks.shared import mark_run_completed
        run_claude_step(
            celery_task=self,
            run_id=run_id,
            org_id=org_id,
            step=7,
            step_name=STEP_NAMES[7],
            analysis_type=CLAUDE_ANALYSIS_TYPE,
            model=CLAUDE_MODEL,
            input_step=6,
            input_filename="MASTER_CONSOLIDATED_REPORT.txt",
        )
        # Module pipelines have no separate finalize task (unlike Apex): step 7 must
        # finalize the run, or it stays RUNNING forever. Mirrors esgrc_step7_claude.
        from pipeline.llm.confidence import compute_confidence
        compute_confidence(run_id)
        mark_run_completed(run_id)

    # Chord error handler - a chord (unlike a chain) does not auto-skip downstream.
    @app.task(name=f"pipeline.{MODULE}.chord_error_handler")
    def chord_error_handler(request, exc, traceback_str, run_id: str):
        mark_run_failed(run_id, f"Chord error in {MODULE} run {run_id}: {exc}")
        for step in [6, 7]:
            mark_step_skipped(run_id, step, STEP_NAMES[step])

    STEP_TASKS = {1: step1, 2: step2, 3: step3, 4: step4, 5: step5, 6: step6, 7: step7_claude}

    def build_chain(run_id: str, org_id: str, overrides: dict = None):
        """
        Hybrid parallel chain; mirrors build_esgrc_chain.
            step1 -> chord( group( step2, step4, step5 ), chain(step3, step6) )
        step7 (Claude) is appended by the caller (pipeline_router), same as ESGRC.
        """
        overrides = overrides or {}
        sig = (run_id, org_id, overrides)
        # A chord header must be a group of PLAIN tasks - a group containing a chain
        # makes Celery raise "Cannot add link to group" when the chord is chained
        # after step1 (see esgrc_chain.build_esgrc_chain's note). So step2/step4/step5
        # run in the header; step3 (needs step2's filtered CSVs, persisted to R2) runs
        # in the chord BODY before the combine. Deterministic task_ids let the
        # emergency-stop endpoint revoke each step.
        parallel_group = group(
            step2.si(*sig).set(task_id=f"{run_id}_step2"),
            step4.si(*sig).set(task_id=f"{run_id}_step4"),
            step5.si(*sig).set(task_id=f"{run_id}_step5"),
        )
        combine_tail = chain(
            step3.si(*sig).set(task_id=f"{run_id}_step3"),
            step6.si(*sig).set(task_id=f"{run_id}_step6"),
        )
        return chain(
            step1.si(*sig).set(task_id=f"{run_id}_step1"),
            chord(parallel_group, combine_tail),
        )

    return {
        "MODULE": MODULE,
        "SPEC": spec,
        "STEP_NAMES": STEP_NAMES,
        "STEP_TASKS": STEP_TASKS,
        "step1": step1,
        "step2": step2,
        "step3": step3,
        "step4": step4,
        "step5": step5,
        "step6": step6,
        "step7_claude": step7_claude,
        "chord_error_handler": chord_error_handler,
        "build_chain": build_chain,
    }
