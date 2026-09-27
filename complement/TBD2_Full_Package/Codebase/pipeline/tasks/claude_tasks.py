"""
pipeline/tasks/claude_tasks.py
Shared Claude API task logic - called by ESGRC step 7 and Apex steps 6 & 8.

Dev C owns pipeline/llm/client.py (LLMClient).
This module is the bridge between Celery tasks and LLMClient.
"""
import logging
import time
import traceback

from celery.exceptions import MaxRetriesExceededError

from pipeline.llm.client import LLMClient
from pipeline.llm.pricing import estimate_cost_usd
from pipeline.tasks import r2
from pipeline.tasks.shared import mark_run_failed, mark_step_completed, mark_step_failed, mark_step_running
logger = logging.getLogger(__name__)


def run_claude_step(
    celery_task,
    run_id: str,
    org_id: str,
    step: int,
    step_name: str,
    analysis_type: str,
    model: str,
    input_step: int,
    input_filename: str,
) -> None:
    """
    Shared logic for any Claude API step.

    Args:
        celery_task:     The bound Celery task (self) - used for retry.
        run_id:          Pipeline run UUID.
        org_id:          Organisation ID (string).
        step:            Step number (7 for ESGRC, 6 or 8 for Apex).
        step_name:       Human-readable step name for DB + SSE.
        analysis_type:   "MODULE_UNIFIED" | "GENERAL_RISK" | "SPC_RPN"
        model:           "claude-haiku-4-5" | "claude-sonnet-4-6"
        input_step:      Which previous step produced the MASTER report.
        input_filename:  Filename of the MASTER report to read from R2.
    """
    step_result_id = mark_step_running(run_id, step, celery_task.request.id, step_name)
    t0 = time.time()

    try:
        # Find the MASTER report from the previous step
        prefix = f"org/{org_id}/runs/{run_id}/step_{input_step}/"
        step_keys = r2.list_files(prefix)
        master_key = next(
            (k for k in step_keys if input_filename in k),
            None,
        )

        if not master_key:
            raise FileNotFoundError(
                f"Master report not found: {input_filename} "
                f"(searched prefix {prefix})"
            )

        # Pre-flight token + cost check (log-only; must never block the run).
        # Download the report once here; pass it to analyze() to avoid a second
        # R2 round-trip inside LLMClient (double egress + latency).
        preflight_text: str | None = None
        try:
            from pipeline.llm.preflight import preflight_report, log_preflight
            preflight_text = r2.download_text(master_key)
            log_preflight(run_id, step, preflight_report(preflight_text, model))
        except Exception as pf_exc:  # noqa: BLE001 - telemetry is best-effort
            logger.debug("Preflight check skipped for run=%s step=%d: %s", run_id, step, pf_exc)

        # Call LLMClient. Pass preflight_text so analyze() skips a second download
        # (None if preflight failed — analyze() will re-download in that case).
        client = LLMClient()
        result = client.analyze(
            analysis_type=analysis_type,
            consolidated_report_r2_path=master_key,
            run_id=run_id,
            step_result_id=step_result_id,
            model_override=model,
            report_text=preflight_text,
            org_id=org_id,
        )

        # The recommendation text is cached to Redis immediately inside LLMClient.analyze()
        # so the UI can display it before the DB write completes.
        output_keys = [result.r2_path] if result.r2_path else []
        duration_ms = int((time.time() - t0) * 1000)
        mark_step_completed(run_id, step, [master_key], output_keys, duration_ms)

        cost = estimate_cost_usd(result.model_used, result.input_tokens, result.output_tokens)
        cost_str = f"${cost:.4f}" if cost is not None else "n/a"
        logger.info(
            "Claude step %d completed: run=%s model=%s tokens=%d+%d est_cost=%s",
            step, run_id, model,
            result.input_tokens or 0,
            result.output_tokens or 0,
            cost_str,
        )

    except Exception as exc:
        if _is_retryable(exc):
            try:
                # .retry() raises Retry (reschedules) or, once attempts are
                # exhausted, MaxRetriesExceededError. If it reschedules, that
                # exception propagates out of this block untouched. If retries
                # are exhausted we must fall through and mark the run FAILED -
                # otherwise MaxRetriesExceededError escapes and the run/step are
                # left stuck in RUNNING forever with no terminal state.
                raise celery_task.retry(exc=exc)
            except MaxRetriesExceededError:
                pass  # exhausted - fall through to the terminal-failure path

        error_msg = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
        mark_step_failed(run_id, step, error_msg)
        mark_run_failed(run_id, f"Step {step} (Claude) failed: {type(exc).__name__}: {exc}")
        raise exc


def _is_retryable(exc: Exception) -> bool:
    """Return True for Anthropic errors that warrant a retry."""
    import anthropic
    if isinstance(exc, (anthropic.RateLimitError, anthropic.APITimeoutError, anthropic.APIConnectionError)):
        return True
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code == 529:
        return True
    return False
