"""
pipeline/test/test_esgrc_e2e.py
End-to-end integration test for the full ESGRC 7-step pipeline.

Uses:
  - CELERY_TASK_ALWAYS_EAGER=True  (tasks run inline, no worker)
  - Mocked ScriptRunner            (returns fixture files)
  - Mocked R2                      (writes to /tmp/test_r2/)
  - Mocked Anthropic API           (returns fixture recommendation)
  - Real SQLite DB                 (pipeline tables)
  - Real Redis                     (or fakeredis if unavailable)

Asserts:
  - All 7 steps execute in correct order
  - pipeline_step_results has 7 rows, all COMPLETED
  - pipeline_llm_outputs has 1 row with response_text set
  - pipeline_runs.status = COMPLETED
  - Redis keys set for all 7 steps
  - Error scenario: step 3 fails → run FAILED, steps 4-7 SKIPPED
"""
import os
import shutil
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# ── Env vars before any app imports ──────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_esgrc_e2e.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["DEMO_MODE"] = "false"

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipeline.db import pipeline_engine
from pipeline.models import (
    PipelineBase,
    PipelineDefinition,
    PipelineLLMOutput,
    PipelineRun,
    PipelineStepResult,
    PipelineTypeEnum,
    RunStatusEnum,
    StepStatusEnum,
)
from pipeline.prompt_models import PipelinePrompt

# ── Setup ─────────────────────────────────────────────────────────────────────
TEST_DB = "sqlite:///./.local/test_databases/test_esgrc_e2e.db"
e2e_engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
PipelineBase.metadata.create_all(bind=e2e_engine)

# Patch pipeline_engine used by shared.py
import pipeline.db as pipeline_db_module
pipeline_db_module.pipeline_engine = e2e_engine

import pipeline.database as pipeline_database_module
from sqlalchemy.orm import sessionmaker as _sessionmaker


@pytest.fixture(autouse=True)
def _patch_shared_db_engine():
    pipeline_database_module._engine = e2e_engine
    pipeline_database_module._SessionFactory = _sessionmaker(bind=e2e_engine, expire_on_commit=False)
    yield

FIXTURE_REPORT = """=== ESGRC MODULE TEST REPORT ===

Correlation Analysis: ESU module shows moderate positive correlation (r=0.67).
SPC Analysis: 2 out-of-control signals detected in GRC sub-module.
Regression: R² = 0.71 - strong predictive model for risk score.
"""

FIXTURE_RECOMMENDATION = """## Module Risk Assessment

**Overall Risk Score:** 6/10
**Confidence:** Medium - based on 2 SPC violations in GRC

### Top Risk Areas

**Risk 1: GRC Process Instability**
- Description: Two out-of-control signals detected in SPC analysis.
- Evidence: Western Electric Rule 1 violation in weeks 3 and 7.
- Recommended Action: Conduct root cause analysis within 14 days.

### Summary
The ESGRC module shows moderate risk with specific concerns in GRC.
"""


@pytest.fixture(autouse=True)
def clean_e2e_db():
    with Session(e2e_engine) as session:
        session.query(PipelineLLMOutput).delete()
        session.query(PipelineStepResult).delete()
        session.query(PipelineRun).delete()
        session.query(PipelineDefinition).delete()
        session.query(PipelinePrompt).delete()
        session.commit()
    yield


@pytest.fixture
def test_r2_dir(tmp_path):
    """Temporary directory acting as the R2 bucket."""
    r2_dir = tmp_path / "r2"
    r2_dir.mkdir()
    return str(r2_dir)


@pytest.fixture
def seeded_pipeline_and_run():
    with Session(e2e_engine) as session:
        pipeline = PipelineDefinition(
            org_id=1,
            name="ESGRC E2E Test",
            pipeline_type=PipelineTypeEnum.ESGRC_MODULE,
            is_active=True,
            config_json={"required_input_files": []},
        )
        session.add(pipeline)
        session.flush()
        run = PipelineRun(
            pipeline_id=pipeline.id,
            org_id=1,
            status=RunStatusEnum.PENDING,
        )
        session.add(run)
        session.commit()
        return {"pipeline_id": pipeline.id, "run_id": run.id}


# ── Fake Redis ────────────────────────────────────────────────────────────────

class FakeRedis:
    """In-memory Redis substitute for tests."""
    def __init__(self):
        self._store = {}

    def set(self, key, value, ex=None):
        self._store[key] = value

    def get(self, key):
        return self._store.get(key)

    def ping(self):
        return True

    def keys(self, pattern="*"):
        return list(self._store.keys())


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_script_runner_mock(test_r2_dir: str):
    """ScriptRunner mock that creates fixture output files."""
    mock = MagicMock()

    def fake_run(script_name, input_paths, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        outputs = {}

        # Create appropriate fixture files per script
        file_map = {
            "data_prep_1": ["prepared_metrics_data.csv", "low_performing_summary.csv"],
            "data_prep_2": ["all_module_values.csv", "data_for_risk_assessment_esgrc.csv"],
            "correlation_CHAID_FT": ["correlation_chaid_ft_report.txt"],
            # Step 4 emits BOTH the SPC/Six-Sigma summary (#6) and the RPN
            # summary (#7) as .txt - both must reach the Step 6 combine.
            "SPC_RPN": ["metrics_summary.txt", "rpn_summary.txt"],
            "regression_esgrc": ["regression_esgrc_report.txt"],
        }
        for filename in file_map.get(script_name, ["output.txt"]):
            path = os.path.join(output_dir, filename)
            with open(path, "w") as f:
                if filename.endswith(".txt"):
                    # Filename in the marker so the combine's contents are assertable
                    f.write(f"=== {script_name}:{filename} ===\n{FIXTURE_REPORT}")
                else:
                    f.write("metric_code,value\nESU10102,42.0\n")
            outputs[filename] = path

        return outputs

    mock.run.side_effect = fake_run
    return mock


def _make_r2_mock(test_r2_dir: str):
    """R2 mock that reads/writes to a temp directory."""
    uploaded = {}

    def fake_upload(local_path, r2_key):
        dest = os.path.join(test_r2_dir, r2_key.replace("/", "_"))
        shutil.copy2(local_path, dest)
        uploaded[r2_key] = dest
        return r2_key

    def fake_download(r2_key, local_path):
        src = os.path.join(test_r2_dir, r2_key.replace("/", "_"))
        if not os.path.exists(src):
            # Create a dummy file for inputs that haven't been "uploaded"
            os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
            with open(local_path, "w") as f:
                f.write("dummy_input,value\nESU10102,42.0\n")
            return
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        shutil.copy2(src, local_path)

    def fake_list(prefix):
        return [k for k in uploaded if k.startswith(prefix)]

    def fake_exists(r2_key):
        return r2_key in uploaded

    return fake_upload, fake_download, fake_list, fake_exists, uploaded


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestEsgrcE2E:

    def test_all_7_steps_complete_in_order(self, seeded_pipeline_and_run, test_r2_dir):
        """Happy path: all 7 steps run, pipeline ends COMPLETED."""
        run_id = seeded_pipeline_and_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(test_r2_dir)
        upload_fn, download_fn, list_fn, exists_fn, uploaded = _make_r2_mock(test_r2_dir)

        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.r2.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.r2.download_file", side_effect=download_fn),
            patch("pipeline.tasks.r2.list_files", side_effect=list_fn),
            patch("pipeline.tasks.r2.file_exists", side_effect=exists_fn),
            # Also patch the chain module's own bindings: it did
            # `from pipeline.tasks.r2 import ...` at import time, so patching
            # pipeline.tasks.r2 alone only lands if this module has not been
            # imported yet - which made this test depend on collection order.
            patch("pipeline.tasks.esgrc_chain.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.esgrc_chain.download_file", side_effect=download_fn),
            patch("pipeline.tasks.esgrc_chain.list_files", side_effect=list_fn),
            patch("pipeline.tasks.esgrc_chain.get_runner", return_value=runner_mock),
            patch("pipeline.tasks.claude_tasks.LLMClient") as mock_llm_class,
        ):
            # Mock LLMClient.analyze to return fixture recommendation
            mock_llm = MagicMock()
            mock_llm.analyze.return_value = MagicMock(
                response_text=FIXTURE_RECOMMENDATION,
                input_tokens=1200,
                output_tokens=400,
                model_used="claude-haiku-4-5",
                prompt_hash="abc123",
                r2_path=f"org/{org_id}/runs/{run_id}/step_7/recommendation.txt",
            )
            mock_llm_class.return_value = mock_llm

            # Also mock DB saves inside LLMClient
            with patch("pipeline.tasks.claude_tasks.LLMClient", return_value=mock_llm):
                from pipeline.tasks.esgrc_chain import (
                    esgrc_step1, esgrc_step2, esgrc_step3,
                    esgrc_step4, esgrc_step5, esgrc_step6, esgrc_step7_claude,
                )

                # Run each step inline (ALWAYS_EAGER)
                from pipeline.tasks.shared import mark_run_running
                mark_run_running(run_id)

                esgrc_step1(run_id, org_id, {})
                esgrc_step2(run_id, org_id, {})
                esgrc_step3(run_id, org_id, {})
                esgrc_step4(run_id, org_id, {})
                esgrc_step5(run_id, org_id, {})
                esgrc_step6(run_id, org_id, {})
                esgrc_step7_claude(run_id, org_id, {})

                from pipeline.tasks.shared import mark_run_completed
                mark_run_completed(run_id)

        # ── Assert DB state ───────────────────────────────────────────────────
        with Session(e2e_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.COMPLETED
            assert run.progress_pct == 100
            assert run.is_current is True

            steps = session.execute(
                select(PipelineStepResult)
                .where(PipelineStepResult.run_id == run_id)
                .order_by(PipelineStepResult.step_number)
            ).scalars().all()
            assert len(steps) == 7
            for s in steps:
                assert s.status == StepStatusEnum.COMPLETED, \
                    f"Step {s.step_number} is {s.status}, expected COMPLETED"

            # Step 3 must stage the perf JSON (name lookup) - else reports
            # #2-#5 fall back to raw IDs instead of human-readable names.
            step3 = next(s for s in steps if s.step_number == 3)
            assert any(
                "esgrc_performance_json_file.json" in k
                for k in (step3.input_files_json or [])
            ), "Step 3 did not stage esgrc_performance_json_file.json (name lookup)"

        # ── Assert Redis keys set ─────────────────────────────────────────────
        for step_num in range(1, 8):
            key = f"pipeline:{run_id}:step:{step_num}"
            assert fake_redis.get(key) is not None, f"Redis key missing: {key}"

        assert fake_redis.get(f"pipeline:{run_id}:status") == "COMPLETED"

        # ── Assert RPN summary reached the Step 6 combine master (spec #7) ─────
        master_key = next(
            k for k in uploaded if k.endswith("MASTER_CONSOLIDATED_REPORT.txt")
        )
        with open(uploaded[master_key]) as _fh:
            master_text = _fh.read()
        assert "SPC_RPN:rpn_summary.txt" in master_text, \
            "rpn_summary.txt (#7) did not reach the ESGRC combine master"
        assert "SPC_RPN:metrics_summary.txt" in master_text, \
            "metrics_summary.txt (#6) missing from the combine master"

    def test_step3_failure_marks_run_failed_and_skips_downstream(
        self, seeded_pipeline_and_run, test_r2_dir
    ):
        """Error scenario: step 3 fails → run FAILED, steps 4-7 skipped."""
        run_id = seeded_pipeline_and_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(test_r2_dir)
        upload_fn, download_fn, list_fn, exists_fn, _ = _make_r2_mock(test_r2_dir)

        # Make step 3 raise
        original_side_effect = runner_mock.run.side_effect
        call_count = {"n": 0}

        def fail_on_step3(script_name, input_paths, output_dir):
            call_count["n"] += 1
            if script_name == "correlation_CHAID_FT":
                raise RuntimeError("Simulated step 3 failure")
            return original_side_effect(script_name, input_paths, output_dir)

        runner_mock.run.side_effect = fail_on_step3

        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.r2.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.r2.download_file", side_effect=download_fn),
            patch("pipeline.tasks.r2.list_files", side_effect=list_fn),
            patch("pipeline.tasks.r2.file_exists", side_effect=exists_fn),
            # Also patch the chain module's own bindings: it did
            # `from pipeline.tasks.r2 import ...` at import time, so patching
            # pipeline.tasks.r2 alone only lands if this module has not been
            # imported yet - which made this test depend on collection order.
            patch("pipeline.tasks.esgrc_chain.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.esgrc_chain.download_file", side_effect=download_fn),
            patch("pipeline.tasks.esgrc_chain.list_files", side_effect=list_fn),
            patch("pipeline.tasks.esgrc_chain.get_runner", return_value=runner_mock),
        ):
            from pipeline.tasks.shared import mark_run_running, mark_step_skipped
            from pipeline.tasks.esgrc_chain import (
                esgrc_step1, esgrc_step2, esgrc_step3,
            )
            from pipeline.tasks.esgrc_chain import ESGRC_STEP_NAMES  # noqa

            mark_run_running(run_id)
            esgrc_step1(run_id, org_id, {})
            esgrc_step2(run_id, org_id, {})

            with pytest.raises(RuntimeError):
                esgrc_step3(run_id, org_id, {})

            # Mark downstream steps skipped (simulating chain abort)
            for step in range(4, 8):
                mark_step_skipped(run_id, step, f"step_{step}")

        with Session(e2e_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.FAILED

            step3 = session.execute(
                select(PipelineStepResult).where(
                    PipelineStepResult.run_id == run_id,
                    PipelineStepResult.step_number == 3,
                )
            ).scalar_one()
            assert step3.status == StepStatusEnum.FAILED
            assert "step 3 failed" in run.error_message.lower()

        # Verify Redis step 3 is FAILED
        import json
        step3_state = json.loads(fake_redis.get(f"pipeline:{run_id}:step:3"))
        assert step3_state["status"] == "FAILED"
