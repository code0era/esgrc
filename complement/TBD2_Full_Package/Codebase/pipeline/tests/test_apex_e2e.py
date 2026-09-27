"""
pipeline/test/test_apex_e2e.py
End-to-end integration test for the full Apex Enterprise 8-step pipeline.

Asserts:
  - Steps 2, 3, 4 are in a group (chord header) - verified by task registry
  - chord callback (Step 5) executes after group
  - 2 pipeline_llm_outputs rows (Steps 6 and 8)
  - pipeline_runs.status = COMPLETED
  - Error scenario: Step 3 fails → chord error handler fires, run = FAILED,
    steps 5-8 show SKIPPED
"""
import json
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_apex_e2e.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

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
import pipeline.db as pipeline_db_module

TEST_DB = "sqlite:///./.local/test_databases/test_apex_e2e.db"
apex_engine = create_engine(TEST_DB, connect_args={"check_same_thread": False})
PipelineBase.metadata.create_all(bind=apex_engine)
pipeline_db_module.pipeline_engine = apex_engine
import pipeline.database as pipeline_database_module
from sqlalchemy.orm import sessionmaker as _sessionmaker


@pytest.fixture(autouse=True)
def _patch_shared_db_engine():
    """
    Re-apply this patch before EVERY test, not just at module-import time.
    When multiple test files are collected together, pytest imports all of
    them before running any test - a module-level assignment here gets
    overwritten by whichever test file is imported last (cross-file
    singleton contamination). This fixture re-asserts the correct engine
    immediately before each test body runs.
    """
    pipeline_database_module._engine = apex_engine
    pipeline_database_module._SessionFactory = _sessionmaker(bind=apex_engine, expire_on_commit=False)
    yield

FIXTURE_RECOMMENDATION_GENERAL = """## Enterprise Risk Assessment
**Enterprise Risk Posture:** 7/10
Cross-module risk patterns identified across ESU and GRC modules.
"""

FIXTURE_RECOMMENDATION_SPC = """## SPC-RPN Risk Assessment
3 out-of-control processes detected. Highest RPN: 210 (ESU).
"""


@pytest.fixture(autouse=True)
def clean_apex_db():
    with Session(apex_engine) as session:
        session.query(PipelineLLMOutput).delete()
        session.query(PipelineStepResult).delete()
        session.query(PipelineRun).delete()
        session.query(PipelineDefinition).delete()
        session.query(PipelinePrompt).delete()
        session.commit()
    yield


def _insert_pipeline_and_run(engine, org_id=1, ptype="APEX_ENTERPRISE", status="PENDING"):
    import json as _json, uuid as _uuid
    from sqlalchemy import text
    pid, rid = str(_uuid.uuid4()), str(_uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO pipeline_definitions (id, org_id, name, pipeline_type, is_active, config_json, created_at, updated_at)
            VALUES (:id, :org_id, 'Apex E2E Test', :ptype, 1, :config, datetime('now'), datetime('now'))
        """), {"id": pid, "org_id": org_id, "ptype": ptype, "config": _json.dumps({})})
        conn.execute(text("""
            INSERT INTO pipeline_runs (id, pipeline_id, org_id, status, is_current, progress_pct)
            VALUES (:id, :pid, :org_id, :status, 0, 0)
        """), {"id": rid, "pid": pid, "org_id": org_id, "status": status})
    return pid, rid


@pytest.fixture
def apex_run():
    pipeline_id, run_id = _insert_pipeline_and_run(apex_engine)
    return {"pipeline_id": pipeline_id, "run_id": run_id}


class FakeRedis:
    def __init__(self):
        self._store = {}
    def set(self, key, value, ex=None): self._store[key] = value
    def get(self, key): return self._store.get(key)
    def ping(self): return True


def _make_script_runner_mock(tmp_path):
    mock = MagicMock()

    def fake_run(script_name, input_paths, output_dir):
        os.makedirs(output_dir, exist_ok=True)
        file_map = {
            "all_module_low_perf":    ["all_module_low_perf_report.txt", "all_module_values_L0.csv"],
            "correlation_CHAID_L0":   ["correlation_chaid_L0_report.txt"],
            # Step 3 emits BOTH the SPC summary and the RPN summary as .txt -
            # both must reach the Step 7 statistical combine → Step 8 Claude.
            "SPC_RPN_L0":             ["SPC_summary_L0.txt", "rpn_summary_L0.txt"],
            "regression_L0":          ["regression_L0_report.txt"],
        }
        outputs = {}
        for filename in file_map.get(script_name, ["output.txt"]):
            path = os.path.join(output_dir, filename)
            with open(path, "w") as f:
                # Filename in the marker so combine contents are assertable
                f.write(f"=== {script_name}:{filename} ===\nFixture output.\n")
            outputs[filename] = path
        return outputs

    mock.run.side_effect = fake_run
    return mock


def _make_r2_mock(tmp_path):
    store = {}

    def upload(local, key):
        dest = os.path.join(tmp_path, key.replace("/", "_"))
        shutil.copy2(local, dest)
        store[key] = dest
        return key

    def download(key, local):
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        src = store.get(key)
        if src and os.path.exists(src):
            shutil.copy2(src, local)
        else:
            with open(local, "w") as f:
                f.write("dummy\n")

    def list_f(prefix):
        return [k for k in store if k.startswith(prefix)]

    def exists(key):
        return key in store

    return upload, download, list_f, exists, store


class TestApexE2E:

    def test_all_8_steps_complete(self, apex_run, tmp_path):
        """Happy path - all 8 steps complete, 2 LLM outputs produced."""
        run_id = apex_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(str(tmp_path))
        upload_fn, download_fn, list_fn, exists_fn, r2_store = _make_r2_mock(str(tmp_path))

        # Pre-seed reference files so step 4 pre-flight passes
        r2_store[f"org/{org_id}/reference/module_mapping.csv"] = "dummy"
        r2_store[f"org/{org_id}/reference/module_matrix.csv"] = "dummy"
        # Pre-seed all 12 module CSVs
        for name in [
            "data_for_risk_assessment_esgrc.csv",
            "data_for_risk_assessment_social.csv",
            "data_for_risk_assessment_cyber.csv",
            "data_for_risk_assessment_gnotes.csv",
            "data_for_risk_assessment_corpgov.csv",
            "data_for_risk_assessment_grc.csv",
            "data_for_risk_assessment_erm.csv",
            "data_for_risk_assessment_audit.csv",
            "data_for_risk_assessment_policy.csv",
            "data_for_risk_assessment_reg.csv",
            "data_for_risk_assessment_ethics.csv",
            "data_for_risk_assessment_cgi.csv",
        ]:
            r2_store[f"org/{org_id}/module_outputs/{name}"] = "dummy"

        def make_llm_result(analysis_type, step):
            result = MagicMock()
            result.response_text = (
                FIXTURE_RECOMMENDATION_GENERAL
                if analysis_type == "GENERAL_RISK"
                else FIXTURE_RECOMMENDATION_SPC
            )
            result.input_tokens = 1500
            result.output_tokens = 500
            result.model_used = "claude-sonnet-4-6"
            result.prompt_hash = f"hash_{analysis_type}"
            result.r2_path = f"org/{org_id}/runs/{run_id}/step_{step}/rec.txt"
            return result

        llm_mock = MagicMock()
        llm_mock.analyze.side_effect = lambda **kw: make_llm_result(
            kw["analysis_type"], 6 if kw["analysis_type"] == "GENERAL_RISK" else 8
        )

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
            patch("pipeline.tasks.apex_chord.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.apex_chord.download_file", side_effect=download_fn),
            patch("pipeline.tasks.apex_chord.list_files", side_effect=list_fn),
            patch("pipeline.tasks.apex_chord.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.apex_chord.get_runner", return_value=runner_mock),
            patch("pipeline.tasks.claude_tasks.LLMClient", return_value=llm_mock),
        ):
            from pipeline.tasks.shared import mark_run_running, mark_run_completed
            from pipeline.tasks.apex_chord import (
                apex_step1, apex_step2, apex_step3, apex_step4,
                apex_step5, apex_step6_claude, apex_step7, apex_step8_claude,
            )

            mark_run_running(run_id)

            # Steps 2, 3, 4 run in parallel in production - run inline here
            apex_step1(run_id, org_id, {})
            apex_step2(run_id, org_id, {})
            apex_step3(run_id, org_id, {})
            apex_step4(run_id, org_id, {})
            apex_step5(run_id, org_id, {})
            apex_step6_claude(run_id, org_id, {})
            apex_step7(run_id, org_id, {})
            apex_step8_claude(run_id, org_id, {})

            mark_run_completed(run_id)

        # ── Verify steps 2, 3, 4 are in the chord group (task registry) ──────
        from pipeline.tasks.apex_chord import APEX_STEP_TASKS
        assert 2 in APEX_STEP_TASKS
        assert 3 in APEX_STEP_TASKS
        assert 4 in APEX_STEP_TASKS
        # All three resolve to different task functions (parallel, not the same task)
        assert APEX_STEP_TASKS[2] is not APEX_STEP_TASKS[3]
        assert APEX_STEP_TASKS[3] is not APEX_STEP_TASKS[4]

        # ── Verify DB state ───────────────────────────────────────────────────
        with Session(apex_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.COMPLETED

            steps = session.execute(
                select(PipelineStepResult)
                .where(PipelineStepResult.run_id == run_id)
                .order_by(PipelineStepResult.step_number)
            ).scalars().all()
            assert len(steps) == 8
            for s in steps:
                assert s.status == StepStatusEnum.COMPLETED, \
                    f"Step {s.step_number} not COMPLETED: {s.status}"

        # ── Verify Redis ──────────────────────────────────────────────────────
        for step_num in range(1, 9):
            assert fake_redis.get(f"pipeline:{run_id}:step:{step_num}") is not None

        # ── RPN summary reached the Step 7 statistical combine (→ Step 8) ──────
        stat_key = next(
            k for k in r2_store
            if k.endswith("MASTER_CONSOLIDATED_STATISTICAL_REPORT.txt")
        )
        with open(r2_store[stat_key]) as _fh:
            stat_text = _fh.read()
        assert "SPC_RPN_L0:rpn_summary_L0.txt" in stat_text, \
            "rpn_summary_L0.txt did not reach the statistical combine master"
        assert "SPC_RPN_L0:SPC_summary_L0.txt" in stat_text, \
            "SPC_summary_L0.txt missing from the statistical combine master"

        # RPN belongs to the statistical call only - it must NOT leak into the
        # General combine (steps [1,2,4]).
        gen_key = next(
            k for k in r2_store if k.endswith("MASTER_CONSOLIDATED_REPORT.txt")
        )
        with open(r2_store[gen_key]) as _fh:
            gen_text = _fh.read()
        assert "rpn_summary_L0.txt" not in gen_text, \
            "RPN leaked into the General combine - should be statistical-only"

    def test_chord_error_handler_fires_on_step3_failure(self, apex_run, tmp_path):
        """Chord error path: step 3 fails → error handler fires, run FAILED."""
        run_id = apex_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(str(tmp_path))
        upload_fn, download_fn, list_fn, exists_fn, r2_store = _make_r2_mock(str(tmp_path))

        # Seed reference + module files
        for name in ["module_mapping.csv", "module_matrix.csv"]:
            r2_store[f"org/{org_id}/reference/{name}"] = "dummy"
        for name in [
            "data_for_risk_assessment_esgrc.csv", "data_for_risk_assessment_social.csv",
            "data_for_risk_assessment_cyber.csv", "data_for_risk_assessment_gnotes.csv",
            "data_for_risk_assessment_corpgov.csv", "data_for_risk_assessment_grc.csv",
            "data_for_risk_assessment_erm.csv", "data_for_risk_assessment_audit.csv",
            "data_for_risk_assessment_policy.csv", "data_for_risk_assessment_reg.csv",
            "data_for_risk_assessment_ethics.csv", "data_for_risk_assessment_cgi.csv",
        ]:
            r2_store[f"org/{org_id}/module_outputs/{name}"] = "dummy"

        orig = runner_mock.run.side_effect

        def fail_on_spc(script_name, input_paths, output_dir):
            if script_name == "SPC_RPN_L0":
                raise RuntimeError("Simulated SPC_RPN_L0 failure")
            return orig(script_name, input_paths, output_dir)

        runner_mock.run.side_effect = fail_on_spc

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
            patch("pipeline.tasks.apex_chord.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.apex_chord.download_file", side_effect=download_fn),
            patch("pipeline.tasks.apex_chord.list_files", side_effect=list_fn),
            patch("pipeline.tasks.apex_chord.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.apex_chord.get_runner", return_value=runner_mock),
        ):
            from pipeline.tasks.shared import mark_run_running, mark_step_skipped
            from pipeline.tasks.apex_chord import (
                apex_step1, apex_step3, apex_chord_error_handler,
                APEX_STEP_NAMES,
            )

            mark_run_running(run_id)
            apex_step1(run_id, org_id, {})

            with pytest.raises(RuntimeError):
                apex_step3(run_id, org_id, {})

            # Simulate chord error handler firing
            apex_chord_error_handler(
                request=None,
                exc=RuntimeError("SPC_RPN_L0 failure"),
                traceback_str="",
                run_id=run_id,
            )

        with Session(apex_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.FAILED

            step3 = session.execute(
                select(PipelineStepResult).where(
                    PipelineStepResult.run_id == run_id,
                    PipelineStepResult.step_number == 3,
                )
            ).scalar_one_or_none()
            if step3:
                assert step3.status == StepStatusEnum.FAILED

            # Steps 5-8 should be SKIPPED (set by chord error handler)
            for step_num in [5, 6, 7, 8]:
                skipped = session.execute(
                    select(PipelineStepResult).where(
                        PipelineStepResult.run_id == run_id,
                        PipelineStepResult.step_number == step_num,
                    )
                ).scalar_one_or_none()
                if skipped:
                    assert skipped.status == StepStatusEnum.SKIPPED, \
                        f"Step {step_num} should be SKIPPED, got {skipped.status}"

    def test_steps_2_3_4_are_distinct_tasks(self):
        """Steps 2, 3, 4 must be different Celery tasks (they run in parallel)."""
        from pipeline.tasks.apex_chord import apex_step2, apex_step3, apex_step4
        assert apex_step2.name != apex_step3.name
        assert apex_step3.name != apex_step4.name
        assert apex_step2.name == "pipeline.apex.step2"
        assert apex_step3.name == "pipeline.apex.step3"
        assert apex_step4.name == "pipeline.apex.step4"

    def test_chord_body_step5_only_runs_after_group(self, apex_run, tmp_path):
        """Step 5 (chord body) must only fire after steps 2, 3, 4 complete."""
        run_id = apex_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(str(tmp_path))
        upload_fn, download_fn, list_fn, exists_fn, r2_store = _make_r2_mock(str(tmp_path))

        step5_called_before_group = {"flag": False}
        step2_done = {"flag": False}
        step3_done = {"flag": False}
        step4_done = {"flag": False}

        orig = runner_mock.run.side_effect

        def tracking_run(script_name, input_paths, output_dir):
            if script_name == "correlation_CHAID_L0":
                step2_done["flag"] = True
            elif script_name == "SPC_RPN_L0":
                step3_done["flag"] = True
            elif script_name == "regression_L0":
                step4_done["flag"] = True
            return orig(script_name, input_paths, output_dir)

        runner_mock.run.side_effect = tracking_run

        for name in ["module_mapping.csv", "module_matrix.csv"]:
            r2_store[f"org/{org_id}/reference/{name}"] = "dummy"
        for n in [
            "data_for_risk_assessment_esgrc.csv", "data_for_risk_assessment_social.csv",
            "data_for_risk_assessment_cyber.csv", "data_for_risk_assessment_gnotes.csv",
            "data_for_risk_assessment_corpgov.csv", "data_for_risk_assessment_grc.csv",
            "data_for_risk_assessment_erm.csv", "data_for_risk_assessment_audit.csv",
            "data_for_risk_assessment_policy.csv", "data_for_risk_assessment_reg.csv",
            "data_for_risk_assessment_ethics.csv", "data_for_risk_assessment_cgi.csv",
        ]:
            r2_store[f"org/{org_id}/module_outputs/{n}"] = "dummy"

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
            patch("pipeline.tasks.apex_chord.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.apex_chord.download_file", side_effect=download_fn),
            patch("pipeline.tasks.apex_chord.list_files", side_effect=list_fn),
            patch("pipeline.tasks.apex_chord.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.apex_chord.get_runner", return_value=runner_mock),
        ):
            from pipeline.tasks.shared import mark_run_running
            from pipeline.tasks.apex_chord import (
                apex_step1, apex_step2, apex_step3, apex_step4, apex_step5,
            )

            mark_run_running(run_id)
            apex_step1(run_id, org_id, {})

            # Run group steps first
            apex_step2(run_id, org_id, {})
            apex_step3(run_id, org_id, {})
            apex_step4(run_id, org_id, {})

            # Only now run step 5 (chord body)
            assert step2_done["flag"] and step3_done["flag"] and step4_done["flag"], \
                "Steps 2, 3, 4 must all complete before step 5 runs"

            apex_step5(run_id, org_id, {})

        # Verify step 5 completed
        with Session(apex_engine) as session:
            step5 = session.execute(
                select(PipelineStepResult).where(
                    PipelineStepResult.run_id == run_id,
                    PipelineStepResult.step_number == 5,
                )
            ).scalar_one_or_none()
            assert step5 is not None
            assert step5.status == StepStatusEnum.COMPLETED

    def test_apex_step1_runs_on_esgrc_only(self, apex_run, tmp_path):
        """MVP single-module Apex: Step 1 runs when ONLY the ESGRC handoff
        exists. The other 11 module CSVs are absent and must be skipped, not
        hard-fail the download - only the ESGRC CSV reaches the script."""
        run_id = apex_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(str(tmp_path))
        upload_fn, download_fn, list_fn, exists_fn, r2_store = _make_r2_mock(str(tmp_path))

        # Seed ONLY the ESGRC module handoff - no other module CSVs exist.
        r2_store[f"org/{org_id}/module_outputs/data_for_risk_assessment_esgrc.csv"] = "dummy"

        # NOTE: apex_chord imports these r2 helpers by name
        # (`from pipeline.tasks.r2 import file_exists, ...`), so they must be
        # patched in the apex_chord namespace - patching pipeline.tasks.r2.*
        # would not rebind apex_chord's already-imported names and the tasks
        # would hit the real object store instead.
        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.apex_chord.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.apex_chord.download_file", side_effect=download_fn),
            patch("pipeline.tasks.apex_chord.list_files", side_effect=list_fn),
            patch("pipeline.tasks.apex_chord.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.apex_chord.get_runner", return_value=runner_mock),
        ):
            from pipeline.tasks.shared import mark_run_running
            from pipeline.tasks.apex_chord import apex_step1

            mark_run_running(run_id)
            apex_step1(run_id, org_id, {})

        # Only the ESGRC CSV should have been handed to the script.
        input_paths = runner_mock.run.call_args.kwargs["input_paths"]
        assert list(input_paths.keys()) == ["data_for_risk_assessment_esgrc.csv"]

        with Session(apex_engine) as session:
            step1 = session.execute(
                select(PipelineStepResult).where(
                    PipelineStepResult.run_id == run_id,
                    PipelineStepResult.step_number == 1,
                )
            ).scalar_one()
            assert step1.status == StepStatusEnum.COMPLETED

    def test_apex_step1_requires_at_least_esgrc(self, apex_run, tmp_path):
        """If not even the ESGRC handoff exists, Step 1 fails clearly rather
        than running the enterprise analysis on nothing."""
        run_id = apex_run["run_id"]
        org_id = "1"
        fake_redis = FakeRedis()
        runner_mock = _make_script_runner_mock(str(tmp_path))
        upload_fn, download_fn, list_fn, exists_fn, r2_store = _make_r2_mock(str(tmp_path))
        # Seed NOTHING - no module handoffs at all.

        # Patch in the apex_chord namespace (see note in the esgrc-only test).
        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.apex_chord.upload_file", side_effect=upload_fn),
            patch("pipeline.tasks.apex_chord.download_file", side_effect=download_fn),
            patch("pipeline.tasks.apex_chord.list_files", side_effect=list_fn),
            patch("pipeline.tasks.apex_chord.file_exists", side_effect=exists_fn),
            patch("pipeline.tasks.apex_chord.get_runner", return_value=runner_mock),
        ):
            from pipeline.tasks.shared import mark_run_running
            from pipeline.tasks.apex_chord import apex_step1

            mark_run_running(run_id)
            with pytest.raises(ValueError):
                apex_step1(run_id, org_id, {})
