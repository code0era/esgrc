"""
pipeline/test/test_customer_e2e.py
End-to-end integration test for the full Customer 7-step pipeline.

Mirrors test_esgrc_e2e.py (same harness: eager Celery, mocked ScriptRunner / R2 /
Anthropic, real SQLite). What is Customer-specific and worth asserting here:

  - the chain resolves the customer_* registry keys, not ESGRC's
  - step 2 writes the Apex handoff for module "customer" (the definition-of-done
    item in docs/analytics/MODULE_REPLICATION_TEMPLATE.md - Apex needs no code change, so
    this call is the ONLY thing making Customer visible to the Apex roll-up)
  - step 3 stages customer_performance_json_file.json for name lookup
  - rpn_summary_customer.txt (spec report #7) reaches the step 6 combine master.
    This is the report Praveen's uploaded SPC script did not produce at all;
    see Customer/analytics_scripts/README.md delta #2.
"""
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

# ── Env vars before any app imports ──────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_customer_e2e.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["DEMO_MODE"] = "false"

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker as _sessionmaker

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
TEST_DB = "sqlite:///./.local/test_databases/test_customer_e2e.db"
e2e_engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
PipelineBase.metadata.create_all(bind=e2e_engine)

import pipeline.db as pipeline_db_module
pipeline_db_module.pipeline_engine = e2e_engine

import pipeline.database as pipeline_database_module


@pytest.fixture(autouse=True)
def _patch_shared_db_engine():
    pipeline_database_module._engine = e2e_engine
    pipeline_database_module._SessionFactory = _sessionmaker(
        bind=e2e_engine, expire_on_commit=False
    )
    yield


FIXTURE_REPORT = """=== CUSTOMER MODULE TEST REPORT ===

Correlation Analysis: CSR sub-module shows moderate positive correlation (r=0.61).
SPC Analysis: 3 out-of-control signals detected in the RTN sub-module.
Regression: R2 = 0.68 - moderate predictive model for the customer score.
"""

FIXTURE_RECOMMENDATION = """## Module Risk Assessment

**Overall Risk Score:** 5/10
**Confidence:** Medium - based on 3 SPC violations in RTN

### Summary
The Customer module shows moderate risk concentrated in retention metrics.
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
    r2_dir = tmp_path / "r2"
    r2_dir.mkdir()
    return str(r2_dir)


@pytest.fixture
def seeded_pipeline_and_run():
    with Session(e2e_engine) as session:
        pipeline = PipelineDefinition(
            org_id=1,
            name="Customer E2E Test",
            pipeline_type=PipelineTypeEnum.CUSTOMER_MODULE,
            is_active=True,
            config_json={"required_input_files": []},
        )
        session.add(pipeline)
        session.flush()
        run = PipelineRun(pipeline_id=pipeline.id, org_id=1, status=RunStatusEnum.PENDING)
        session.add(run)
        session.commit()
        return {"pipeline_id": pipeline.id, "run_id": run.id}


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

# Output filenames per registry key - these MUST match the customer_* entries in
# pipeline/scripts/scripts_registry.json, so a rename there fails this test.
CUSTOMER_SCRIPT_OUTPUTS = {
    "customer_data_prep_1": [
        "low_performing_entities_report_customer.txt",
        "module_values_customer.csv",
    ],
    "customer_data_prep_2": [
        "filtered_metrics_data_customer.csv",
        "filtered_groups_data_customer.csv",
        "filtered_sub_modules_data_customer.csv",
        "data_for_risk_assessment_customer.csv",
    ],
    "customer_correlation": [
        "M_G_SM_correlation_report_customer.txt",
        "trends_and_repetitions_report_customer.txt",
        "inconsistencies_report_customer.txt",
        "chaid_risk_segmentation_report_customer.txt",
    ],
    "customer_spc_rpn": [
        "metrics_summary_customer.txt",
        "rpn_summary_customer.txt",
    ],
    "customer_regression": ["Customer_Module_model_summary.txt"],
}


def _make_script_runner_mock():
    """ScriptRunner mock that creates the real Customer output filenames."""
    mock = MagicMock()

    def fake_run(script_name, input_paths, output_dir):
        assert script_name in CUSTOMER_SCRIPT_OUTPUTS, \
            f"Customer chain asked for unknown registry key {script_name!r}"
        os.makedirs(output_dir, exist_ok=True)
        outputs = {}
        for filename in CUSTOMER_SCRIPT_OUTPUTS[script_name]:
            path = os.path.join(output_dir, filename)
            with open(path, "w") as f:
                if filename.endswith(".txt"):
                    f.write(f"=== {script_name}:{filename} ===\n{FIXTURE_REPORT}")
                else:
                    f.write("metric_code,value\nCSR10101,42.0\n")
            outputs[filename] = path
        return outputs

    mock.run.side_effect = fake_run
    return mock


def _make_r2_mock(test_r2_dir: str):
    uploaded = {}

    def fake_upload(local_path, r2_key):
        dest = os.path.join(test_r2_dir, r2_key.replace("/", "_"))
        shutil.copy2(local_path, dest)
        uploaded[r2_key] = dest
        return r2_key

    def fake_download(r2_key, local_path):
        src = os.path.join(test_r2_dir, r2_key.replace("/", "_"))
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        if not os.path.exists(src):
            with open(local_path, "w") as f:
                f.write("dummy_input,value\nCSR10101,42.0\n")
            return
        shutil.copy2(src, local_path)

    def fake_list(prefix):
        return [k for k in uploaded if k.startswith(prefix)]

    def fake_exists(r2_key):
        return r2_key in uploaded

    return fake_upload, fake_download, fake_list, fake_exists, uploaded


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCustomerE2E:

    def test_all_7_steps_complete_in_order(self, seeded_pipeline_and_run, test_r2_dir):
        """Happy path: all 7 steps run, pipeline ends COMPLETED."""
        run_id = seeded_pipeline_and_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock()
        upload_fn, download_fn, list_fn, exists_fn, uploaded = _make_r2_mock(test_r2_dir)

        mock_llm = MagicMock()
        mock_llm.analyze.return_value = MagicMock(
            response_text=FIXTURE_RECOMMENDATION,
            input_tokens=1200,
            output_tokens=400,
            model_used="claude-haiku-4-5",
            prompt_hash="abc123",
            r2_path=f"org/{org_id}/runs/{run_id}/step_7/recommendation.txt",
        )

        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.r2.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.r2.download_file", side_effect=download_fn),
            patch("pipeline.tasks.r2.list_files", side_effect=list_fn),
            patch("pipeline.tasks.r2.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.script_runner.get_runner", return_value=runner_mock),
            patch("pipeline.tasks.r2.write_module_handoff") as handoff_mock,
            patch("pipeline.tasks.claude_tasks.LLMClient", return_value=mock_llm),
        ):
            from pipeline.tasks.customer_chain import (
                step1, step2, step3, step4, step5, step6, step7_claude,
            )
            from pipeline.tasks.shared import mark_run_running, mark_run_completed

            mark_run_running(run_id)
            step1(run_id, org_id, {})
            step2(run_id, org_id, {})
            step3(run_id, org_id, {})
            step4(run_id, org_id, {})
            step5(run_id, org_id, {})
            step6(run_id, org_id, {})
            step7_claude(run_id, org_id, {})
            mark_run_completed(run_id)

        # ── The Apex handoff: the definition-of-done for a new module ─────────
        assert handoff_mock.call_count == 1, \
            "step 2 must call write_module_handoff exactly once"
        handoff_args = handoff_mock.call_args.args
        assert "data_for_risk_assessment_customer.csv" in handoff_args[0]
        assert handoff_args[1] == org_id
        assert handoff_args[2] == "customer", \
            "handoff module key must be 'customer' (matches APEX_MODULE_NAMES)"
        assert handoff_args[3] == run_id

        # ── DB state ──────────────────────────────────────────────────────────
        with Session(e2e_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.COMPLETED
            assert run.progress_pct == 100

            steps = session.execute(
                select(PipelineStepResult)
                .where(PipelineStepResult.run_id == run_id)
                .order_by(PipelineStepResult.step_number)
            ).scalars().all()
            assert len(steps) == 7
            for s in steps:
                assert s.status == StepStatusEnum.COMPLETED, \
                    f"Step {s.step_number} is {s.status}, expected COMPLETED"

            # Step 3 must stage the perf JSON, else the correlation report falls
            # back to raw IDs instead of business names.
            step3_row = next(s for s in steps if s.step_number == 3)
            assert any(
                "customer_performance_json_file.json" in k
                for k in (step3_row.input_files_json or [])
            ), "Step 3 did not stage customer_performance_json_file.json"

        # ── Redis ─────────────────────────────────────────────────────────────
        for step_num in range(1, 8):
            assert fake_redis.get(f"pipeline:{run_id}:step:{step_num}") is not None, \
                f"Redis key missing for step {step_num}"
        assert fake_redis.get(f"pipeline:{run_id}:status") == "COMPLETED"

        # ── Both SPC text reports reached the combine master ──────────────────
        master_key = next(
            k for k in uploaded if k.endswith("MASTER_CONSOLIDATED_REPORT.txt")
        )
        with open(uploaded[master_key]) as fh:
            master_text = fh.read()
        assert "customer_spc_rpn:rpn_summary_customer.txt" in master_text, \
            "rpn_summary_customer.txt (#7) did not reach the Customer combine master"
        assert "customer_spc_rpn:metrics_summary_customer.txt" in master_text, \
            "metrics_summary_customer.txt (#6) missing from the combine master"

    def test_step3_failure_marks_run_failed_and_skips_downstream(
        self, seeded_pipeline_and_run, test_r2_dir
    ):
        """Error scenario: step 3 fails -> run FAILED, steps 4-7 skipped."""
        run_id = seeded_pipeline_and_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock()
        upload_fn, download_fn, list_fn, exists_fn, _ = _make_r2_mock(test_r2_dir)

        original_side_effect = runner_mock.run.side_effect

        def fail_on_step3(script_name, input_paths, output_dir):
            if script_name == "customer_correlation":
                raise RuntimeError("Simulated step 3 failure")
            return original_side_effect(script_name, input_paths, output_dir)

        runner_mock.run.side_effect = fail_on_step3

        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.r2.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.r2.download_file", side_effect=download_fn),
            patch("pipeline.tasks.r2.list_files", side_effect=list_fn),
            patch("pipeline.tasks.r2.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.script_runner.get_runner", return_value=runner_mock),
            patch("pipeline.tasks.r2.write_module_handoff"),
        ):
            from pipeline.tasks.customer_chain import step1, step2, step3
            from pipeline.tasks.shared import mark_run_running, mark_step_skipped

            mark_run_running(run_id)
            step1(run_id, org_id, {})
            step2(run_id, org_id, {})

            with pytest.raises(RuntimeError):
                step3(run_id, org_id, {})

            for step in range(4, 8):
                mark_step_skipped(run_id, step, f"step_{step}")

        with Session(e2e_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.FAILED

            step3_row = session.execute(
                select(PipelineStepResult).where(
                    PipelineStepResult.run_id == run_id,
                    PipelineStepResult.step_number == 3,
                )
            ).scalar_one()
            assert step3_row.status == StepStatusEnum.FAILED
            assert "step 3 failed" in run.error_message.lower()

        import json
        step3_state = json.loads(fake_redis.get(f"pipeline:{run_id}:step:3"))
        assert step3_state["status"] == "FAILED"
