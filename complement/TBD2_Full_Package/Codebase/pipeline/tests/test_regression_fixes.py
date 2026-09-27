"""
Regression tests for the 2026-07-11 audit fixes.

- Per-step re-run must pass the third positional `overrides` arg to the step
  task, or the worker raises TypeError and the step silently never runs.
- A Claude step must reach a terminal FAILED state when retries are exhausted,
  instead of leaving the run stuck in RUNNING forever.
"""
import os

# Env vars must be set before importing pipeline modules.
os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_pipeline.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-anthropic-key")

from unittest.mock import MagicMock, patch

import pytest
from celery.exceptions import MaxRetriesExceededError

from pipeline.routers import pipeline_router
from pipeline.tasks import claude_tasks, esgrc_chain, apex_chord, _module_chain_factory
from pipeline.tasks.r2 import R2Error


# ── Step re-run enqueue signature ─────────────────────────────────────────────

class TestEnqueueSingleStepOverrides:
    def test_esgrc_enqueue_passes_overrides(self):
        fake_task = MagicMock()
        with patch("pipeline.tasks.esgrc_chain.ESGRC_STEP_TASKS", {1: fake_task}):
            pipeline_router._enqueue_single_step("ESGRC_MODULE", "run-1", "42", 1)
        # The third positional arg is the required `overrides` dict.
        fake_task.apply_async.assert_called_once_with(args=["run-1", "42", {}])

    def test_apex_enqueue_passes_overrides(self):
        fake_task = MagicMock()
        with patch("pipeline.tasks.apex_chord.APEX_STEP_TASKS", {3: fake_task}):
            pipeline_router._enqueue_single_step("APEX_ENTERPRISE", "run-2", "42", 3)
        fake_task.apply_async.assert_called_once_with(args=["run-2", "42", {}])


# ── Claude retry exhaustion → terminal FAILED ─────────────────────────────────

class TestClaudeRetryExhaustion:
    def test_exhausted_retries_mark_run_failed(self):
        celery_task = MagicMock()
        celery_task.request.id = "task-1"
        # Simulate Celery having exhausted its retries.
        celery_task.retry.side_effect = MaxRetriesExceededError()

        boom = RuntimeError("transient upstream error")

        with (
            patch.object(claude_tasks, "mark_step_running", return_value="sr-1"),
            patch.object(claude_tasks, "_is_retryable", return_value=True),
            patch.object(
                claude_tasks.r2, "list_files",
                return_value=["org/42/runs/r1/step_5/MASTER_CONSOLIDATED_REPORT.txt"],
            ),
            patch.object(claude_tasks.r2, "download_text", return_value="report text"),
            patch.object(claude_tasks, "LLMClient") as MockClient,
            patch.object(claude_tasks, "mark_step_failed") as m_step_failed,
            patch.object(claude_tasks, "mark_run_failed") as m_run_failed,
            patch.object(claude_tasks, "mark_step_completed") as m_completed,
        ):
            MockClient.return_value.analyze.side_effect = boom
            with pytest.raises(RuntimeError):
                claude_tasks.run_claude_step(
                    celery_task=celery_task,
                    run_id="r1",
                    org_id="42",
                    step=6,
                    step_name="AI General Risk Assessment (Claude)",
                    analysis_type="GENERAL_RISK",
                    model="claude-sonnet-4-6",
                    input_step=5,
                    input_filename="MASTER_CONSOLIDATED_REPORT.txt",
                )

        celery_task.retry.assert_called_once()
        # The run reaches a terminal FAILED state instead of staying RUNNING.
        m_step_failed.assert_called_once()
        m_run_failed.assert_called_once()
        m_completed.assert_not_called()


# ── Script-step retry: max_retries was declared but never used ──────────────

class TestScriptStepHandleFailureRetries:
    """FIX: esgrc_chain.py, apex_chord.py and _module_chain_factory.py each
    declare max_retries on every @app.task, but their shared
    _handle_step_failure() helper never called celery_task.retry() - every
    failure went straight to terminal FAILED on the first attempt regardless
    of the decorator's config. R2Error (transient upload/download/network
    failures) must now be retried up to exhaustion before the terminal path
    runs; anything else must still go straight to the terminal path, exactly
    as before (verified so this fix doesn't change behaviour for the far more
    common case of a genuinely broken script)."""

    @pytest.mark.parametrize(
        "handler_module",
        [esgrc_chain, apex_chord, _module_chain_factory],
        ids=["esgrc_chain", "apex_chord", "_module_chain_factory"],
    )
    def test_r2error_is_retried_then_marks_failed_once_exhausted(self, handler_module):
        celery_task = MagicMock()
        celery_task.retry.side_effect = MaxRetriesExceededError()
        boom = R2Error("transient upload failure")

        with (
            patch.object(handler_module, "mark_step_failed") as m_step_failed,
            patch.object(handler_module, "mark_run_failed") as m_run_failed,
        ):
            with pytest.raises(R2Error):
                handler_module._handle_step_failure("run-1", 3, boom, celery_task)

        celery_task.retry.assert_called_once_with(exc=boom)
        # Only reaches the terminal path AFTER retries are exhausted.
        m_step_failed.assert_called_once()
        m_run_failed.assert_called_once()

    @pytest.mark.parametrize(
        "handler_module",
        [esgrc_chain, apex_chord, _module_chain_factory],
        ids=["esgrc_chain", "apex_chord", "_module_chain_factory"],
    )
    def test_non_r2_failure_skips_retry_and_fails_immediately(self, handler_module):
        """Unchanged behaviour: a genuinely broken script must not be retried -
        it would just fail the same way again."""
        celery_task = MagicMock()
        boom = RuntimeError("script exited with code 1")

        with (
            patch.object(handler_module, "mark_step_failed") as m_step_failed,
            patch.object(handler_module, "mark_run_failed") as m_run_failed,
        ):
            with pytest.raises(RuntimeError):
                handler_module._handle_step_failure("run-1", 3, boom, celery_task)

        celery_task.retry.assert_not_called()
        m_step_failed.assert_called_once()
        m_run_failed.assert_called_once()


class TestL0ReportTrim:
    """
    The top-N-at-write-time trim exists in every module-level
    Correlation_CHAID_FT_Analysis_*.py but was never applied to the L0 roll-up.
    It did not matter while Apex rolled up 3 modules (the 2026-08-04 live run
    sent 75,515 tokens). Measured against all 12 handoffs on 2026-08-07 the
    payload was ~909,000 tokens against a 190,000 hard limit, so the guard would
    have truncated about four fifths of the enterprise report.

    These guard the trim's presence and, more importantly, that it stays on the
    WRITE path only.
    """

    L0 = "modules/apex/analytics_scripts/AI_Ready_Correlation_and_CHAID_Analysis_L0_6_0.py"

    def _src(self):
        from pathlib import Path
        return Path(self.L0).read_text(encoding="utf-8")

    def test_l0_has_the_trim_helpers(self):
        src = self._src()
        assert "def write_top_correlations(" in src
        assert "def write_inconsistency_table(" in src
        assert "CORRELATION_TOP_N" in src and "INCONSISTENCY_TOP_N" in src

    def test_l0_no_longer_dumps_the_full_matrix(self):
        """The full n x n dump was 617,972 bytes at 12 modules.

        Checks executable lines only: the replacement comment quotes the old
        call, so a naive substring search matches the explanation rather than
        the code.
        """
        offending = [
            line.strip()
            for line in self._src().splitlines()
            if "to_csv(f)" in line and not line.strip().startswith("#")
        ]
        assert not offending, f"full-matrix dump still written: {offending}"

    def test_bin_features_still_receives_the_full_objects(self):
        """The whole point: the trim must not reach the analysis. CHAID output
        was verified byte-identical before and after, apart from its timestamp."""
        src = self._src()
        assert "bin_features(trends, repetitions, dep_inc, ind_inc, corr_matrix_all)" in src

    def test_every_module_correlation_script_has_the_trim(self):
        """L0 was missed once; catch it if a new module's copy misses it too."""
        from pathlib import Path

        missing = []
        for p in Path(".").glob("modules/*/analytics_scripts/Correlation_CHAID_FT_Analysis_*.py"):
            if "write_top_correlations" not in p.read_text(encoding="utf-8"):
                missing.append(str(p))
        assert not missing, f"correlation scripts without the report trim: {missing}"
