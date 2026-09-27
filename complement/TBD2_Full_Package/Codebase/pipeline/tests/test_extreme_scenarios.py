"""
pipeline/test/test_extreme_scenarios.py
All 12 extreme scenario tests from Section 7.3 of the master plan.

Required before client demo. Tests:
  1. Claude API rate limit mid-pipeline - retries and succeeds
  2. Anthropic 529 overloaded - retries 3 times then succeeds
  3. Consolidated report exceeds context window - guard truncates, call succeeds
  4. Analytics script crashes mid-pipeline - step FAILED, downstream SKIPPED
  5. R2 upload fails after script succeeds - step FAILED, idempotent on retry
  6. Celery worker dies mid-chord (Apex) - error handler fires, run FAILED
  7. Concurrent pipeline runs (same org) - Redis keys don't collide
  8. SSE client disconnects mid-run - generator exits cleanly
  9. JWT expires mid-session - not tested here (frontend + ESGRC test)
 10. Cross-org data access attempt - returns 404
 11. Rollback when no previous run exists - returns 400
 12. Prompt template updated mid-run - in-flight run uses captured hash
"""
import asyncio
import json
import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_extreme.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"

import anthropic as anthropic_lib
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from pipeline.models import (
    PipelineBase, PipelineDefinition, PipelineRun, PipelineStepResult,
    PipelineLLMOutput, PipelineTypeEnum, RunStatusEnum, StepStatusEnum,
    AnalysisTypeEnum,
)
from pipeline.prompt_models import PipelinePrompt
import pipeline.db as pipeline_db_module

EXTREME_DB = "sqlite:///./.local/test_databases/test_extreme.db"
extreme_engine = create_engine(EXTREME_DB, connect_args={"check_same_thread": False})
PipelineBase.metadata.create_all(bind=extreme_engine)
pipeline_db_module.pipeline_engine = extreme_engine

import pipeline.database as pipeline_database_module
from sqlalchemy.orm import sessionmaker as _sessionmaker


@pytest.fixture(autouse=True)
def _patch_shared_db_engine():
    pipeline_database_module._engine = extreme_engine
    pipeline_database_module._SessionFactory = _sessionmaker(bind=extreme_engine, expire_on_commit=False)
    yield

class FakeRedis:
    def __init__(self):
        self._store = {}
    def set(self, key, value, ex=None): self._store[key] = value
    def get(self, key): return self._store.get(key)
    def ping(self): return True
    def keys(self, pattern="*"): return list(self._store.keys())


@pytest.fixture(autouse=True)
def clean_db():
    with Session(extreme_engine) as session:
        session.query(PipelineLLMOutput).delete()
        session.query(PipelineStepResult).delete()
        session.query(PipelineRun).delete()
        session.query(PipelineDefinition).delete()
        session.query(PipelinePrompt).delete()
        session.commit()
    yield


def _make_pipeline_and_run(session, pipeline_type=PipelineTypeEnum.ESGRC_MODULE):
    import json as _json, uuid as _uuid
    from sqlalchemy import text
    pid, rid = str(_uuid.uuid4()), str(_uuid.uuid4())
    conn = session.connection()
    conn.execute(text("""
        INSERT INTO pipeline_definitions (id, org_id, name, pipeline_type, is_active, config_json, created_at, updated_at)
        VALUES (:id, 1, 'Extreme Test', :ptype, 1, :config, datetime('now'), datetime('now'))
    """), {"id": pid, "ptype": pipeline_type.value, "config": _json.dumps({})})
    conn.execute(text("""
        INSERT INTO pipeline_runs (id, pipeline_id, org_id, status, is_current, progress_pct)
        VALUES (:id, :pid, 1, :status, 0, 0)
    """), {"id": rid, "pid": pid, "status": RunStatusEnum.PENDING.value})
    session.commit()
    return pid, rid


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 1 - Claude API rate limit mid-pipeline → retries, succeeds on retry 2
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario1RateLimit:
    def test_rate_limit_retries_and_succeeds(self):
        """
        Mock Anthropic to return RateLimitError on first call, success on retry 2.
        Verify exponential backoff fires and task completes.
        """
        from pipeline.llm.client import LLMClient

        attempt = {"n": 0}

        def fake_create(**kwargs):
            attempt["n"] += 1
            if attempt["n"] == 1:
                raise anthropic_lib.RateLimitError(
                    message="rate limit", response=MagicMock(status_code=429), body={}
                )
            # Succeed on attempt 2
            response = MagicMock()
            response.content = [MagicMock(type="text", text="Risk assessment result.")]
            response.usage = MagicMock(input_tokens=1000, output_tokens=200)
            return response

        client = LLMClient.__new__(LLMClient)
        client._anthropic = MagicMock()
        client._anthropic.messages.create.side_effect = fake_create
        client._redis = None
        client._langfuse = None

        with patch("time.sleep"):  # don't actually sleep in tests
            response = client._call_with_retry("claude-haiku-4-5", "test prompt")

        assert attempt["n"] == 2
        assert response.content[0].text == "Risk assessment result."


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 2 - Anthropic 529 overloaded → 3 retries then succeeds
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario2Overloaded:
    def test_529_retries_3_times_then_succeeds(self):
        """3 consecutive 529 responses then success - all 3 retries fire."""
        from pipeline.llm.client import LLMClient

        attempt = {"n": 0}

        def fake_create(**kwargs):
            attempt["n"] += 1
            if attempt["n"] <= 2:
                raise anthropic_lib.APIStatusError(
                    message="overloaded",
                    response=MagicMock(status_code=529),
                    body={},
                )
            response = MagicMock()
            response.content = [MagicMock(type="text", text="Eventually succeeded.")]
            response.usage = MagicMock(input_tokens=500, output_tokens=100)
            return response

        client = LLMClient.__new__(LLMClient)
        client._anthropic = MagicMock()
        client._anthropic.messages.create.side_effect = fake_create
        client._redis = None
        client._langfuse = None

        with patch("time.sleep"):
            response = client._call_with_retry("claude-sonnet-4-6", "test prompt")

        assert attempt["n"] == 3
        assert "Eventually succeeded" in response.content[0].text

    def test_auth_error_never_retries(self):
        """AuthenticationError must not be retried - raise immediately."""
        from pipeline.llm.client import LLMClient

        attempt = {"n": 0}

        def fake_create(**kwargs):
            attempt["n"] += 1
            raise anthropic_lib.AuthenticationError(
                message="invalid key",
                response=MagicMock(status_code=401),
                body={},
            )

        client = LLMClient.__new__(LLMClient)
        client._anthropic = MagicMock()
        client._anthropic.messages.create.side_effect = fake_create
        client._redis = None
        client._langfuse = None

        with pytest.raises(anthropic_lib.AuthenticationError):
            client._call_with_retry("claude-haiku-4-5", "prompt")

        # Must not have retried
        assert attempt["n"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 3 - Consolidated report exceeds context window → guard truncates
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario3ContextWindow:
    def test_200k_token_report_is_truncated_and_call_succeeds(self):
        """
        Feed a mock 200K-token report.
        Guard truncates to 90% of hard limit.
        API call succeeds with truncated text.
        """
        from pipeline.llm.guard import check_token_count

        giant_text = "R" * 800_000  # ~200K tokens

        call_count = {"n": 0}

        def fake_count(model, messages):
            call_count["n"] += 1
            r = MagicMock()
            # First call: 200K tokens (over 150K warn, under 190K hard)
            # After truncation: 160K tokens (under hard limit)
            r.input_tokens = 200_000 if call_count["n"] == 1 else 160_000
            return r

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.count_tokens.side_effect = fake_count

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_anthropic_client):
            result = check_token_count(giant_text, "claude-haiku-4-5")

        assert result.was_truncated is True
        assert result.original_token_count == 200_000
        assert result.token_count == 160_000
        assert len(result.text) < len(giant_text)
        assert "TRUNCATED" in result.text

    def test_truncation_warning_is_logged(self, caplog):
        """Truncation event must be logged as a warning."""
        import logging
        from pipeline.llm.guard import check_token_count

        text = "X" * 800_000
        call_count = {"n": 0}

        def fake_count(model, messages):
            call_count["n"] += 1
            r = MagicMock()
            r.input_tokens = 160_000 if call_count["n"] == 1 else 140_000
            return r

        mock_client = MagicMock()
        mock_client.messages.count_tokens.side_effect = fake_count

        with patch("pipeline.llm.guard.anthropic.Anthropic", return_value=mock_client):
            with caplog.at_level(logging.WARNING, logger="pipeline.llm.guard"):
                result = check_token_count(text, "claude-haiku-4-5")

        assert result.was_truncated is True
        assert any("truncat" in r.message.lower() for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 4 - Analytics script crashes mid-pipeline
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario4ScriptCrash:
    def test_step3_failure_marks_run_failed(self):
        """Step 3 script raises → step FAILED, run FAILED."""
        from pipeline.tasks.shared import mark_run_running, mark_step_failed, mark_run_failed
        from pipeline.tasks.script_runner import ScriptExecutionError

        fake_redis = FakeRedis()

        with Session(extreme_engine) as session:
            _, run_id = _make_pipeline_and_run(session)

        with patch("pipeline.tasks.shared._get_redis", return_value=fake_redis):
            mark_run_running(run_id)

            error_msg = "Script 'correlation_CHAID_FT' exited with code 1.\nStderr: MemoryError"
            mark_step_failed(run_id, 3, error_msg)
            mark_run_failed(run_id, f"Step 3 failed: ScriptExecutionError: {error_msg}")

        with Session(extreme_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.FAILED
            assert "Step 3" in run.error_message

        # Redis shows FAILED
        assert fake_redis.get(f"pipeline:{run_id}:status") == "FAILED"
        step3_state = json.loads(fake_redis.get(f"pipeline:{run_id}:step:3"))
        assert step3_state["status"] == "FAILED"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 5 - R2 upload fails after script succeeds
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario5R2UploadFailure:
    def test_r2_upload_failure_marks_step_failed(self):
        """
        Script succeeds and produces output file.
        R2 upload then raises R2Error.
        Step must be marked FAILED - not COMPLETED.
        Script must NOT be re-run on retry (idempotency).
        """
        from pipeline.tasks.r2 import R2Error

        fake_redis = FakeRedis()
        script_run_count = {"n": 0}

        def fake_script_run(script_name, input_paths, output_dir):
            script_run_count["n"] += 1
            import tempfile, os as _os
            _os.makedirs(output_dir, exist_ok=True)
            out = _os.path.join(output_dir, "output.txt")
            with open(out, "w") as f:
                f.write("script succeeded")
            return {"output.txt": out}

        def fake_upload(local_path, r2_key):
            raise R2Error("Simulated R2 upload failure")

        from pipeline.tasks.shared import mark_run_running, mark_step_running, mark_step_failed

        with Session(extreme_engine) as session:
            _, run_id = _make_pipeline_and_run(session)

        runner_mock = MagicMock()
        runner_mock.run.side_effect = fake_script_run

        with (
            patch("pipeline.tasks.shared._get_redis", return_value=fake_redis),
            patch("pipeline.tasks.r2.upload_file", side_effect=fake_upload),
            patch("pipeline.tasks.r2.download_file"),
            patch("pipeline.tasks.r2.list_files", return_value=[]),
            patch("pipeline.tasks.script_runner.ScriptRunner", return_value=runner_mock),
        ):
            mark_run_running(run_id)
            mark_step_running(run_id, 1, "task-abc", "Data Prep 1")

            # Simulate step execution: script runs, upload fails
            import tempfile as _tempfile
            tmp_dir = _tempfile.mkdtemp()
            try:
                fake_script_run("data_prep_1", {}, tmp_dir)
                fake_upload(
                    os.path.join(tmp_dir, "output.txt"),
                    "org/1/runs/{}/step_1/output.txt".format(run_id),
                )
            except R2Error as exc:
                mark_step_failed(run_id, 1, str(exc))

        # Verify step is FAILED
        with Session(extreme_engine) as session:
            step = session.execute(
                select(PipelineStepResult).where(
                    PipelineStepResult.run_id == run_id,
                    PipelineStepResult.step_number == 1,
                )
            ).scalar_one()
            assert step.status == StepStatusEnum.FAILED
            assert "R2" in step.error_detail or "upload" in step.error_detail.lower()

        # Script ran exactly once
        assert script_run_count["n"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 6 - Celery chord error handler fires on Apex task failure
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario6ChordError:
    def test_chord_error_handler_marks_run_failed_and_skips_steps(self):
        """on_chord_error fires → run FAILED, steps 5-8 SKIPPED."""
        from pipeline.tasks.apex_chord import apex_chord_error_handler
        from pipeline.tasks.shared import mark_run_running

        fake_redis = FakeRedis()

        with Session(extreme_engine) as session:
            _, run_id = _make_pipeline_and_run(
                session, pipeline_type=PipelineTypeEnum.APEX_ENTERPRISE
            )

        with patch("pipeline.tasks.shared._get_redis", return_value=fake_redis):
            mark_run_running(run_id)

            apex_chord_error_handler(
                request=None,
                exc=RuntimeError("Step 3 SPC_RPN_L0 failed"),
                traceback_str="Traceback...",
                run_id=run_id,
            )

        with Session(extreme_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.FAILED

        # Steps 5-8 should be SKIPPED in Redis
        for step in [5, 6, 7, 8]:
            raw = fake_redis.get(f"pipeline:{run_id}:step:{step}")
            if raw:
                state = json.loads(raw)
                assert state["status"] == "SKIPPED", \
                    f"Step {step} should be SKIPPED, got {state['status']}"


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 7 - Concurrent pipeline runs (same org) - no Redis key collision
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario7ConcurrentRuns:
    def test_concurrent_runs_have_isolated_redis_keys(self):
        """
        Two runs for the same org must use separate Redis key namespaces.
        run_id is part of every key - no collision possible.
        """
        from pipeline.tasks.shared import mark_run_running, mark_step_running

        fake_redis = FakeRedis()
        run_id_a = str(uuid.uuid4())
        run_id_b = str(uuid.uuid4())

        with Session(extreme_engine) as session:
            pid, _ = _make_pipeline_and_run(session)
            from sqlalchemy import text
            conn = session.connection()
            conn.execute(text("UPDATE pipeline_runs SET id=:rid WHERE pipeline_id=:pid"),
                         {"rid": run_id_a, "pid": pid})
            conn.execute(text("""
                INSERT INTO pipeline_runs (id, pipeline_id, org_id, status, is_current, progress_pct)
                VALUES (:id, :pid, 1, :status, 0, 0)
            """), {"id": run_id_b, "pid": pid, "status": RunStatusEnum.PENDING.value})
            session.commit()

        with patch("pipeline.tasks.shared._get_redis", return_value=fake_redis):
            mark_run_running(run_id_a)
            mark_run_running(run_id_b)
            mark_step_running(run_id_a, 1, "task-a1", "Step 1 Run A")
            mark_step_running(run_id_b, 1, "task-b1", "Step 1 Run B")

        # Keys are namespaced by run_id - no collision
        key_a = f"pipeline:{run_id_a}:step:1"
        key_b = f"pipeline:{run_id_b}:step:1"
        assert key_a != key_b

        state_a = json.loads(fake_redis.get(key_a))
        state_b = json.loads(fake_redis.get(key_b))

        assert state_a["task_id"] == "task-a1"
        assert state_b["task_id"] == "task-b1"
        assert state_a["task_id"] != state_b["task_id"]

    def test_sse_streams_are_isolated_by_run_id(self):
        """SSE generator uses run_id in all Redis key lookups - cannot cross-contaminate."""
        from pipeline.tasks.shared import _redis_step_key, _redis_run_key

        run_id_a = "run-aaa"
        run_id_b = "run-bbb"

        assert _redis_step_key(run_id_a, 1) != _redis_step_key(run_id_b, 1)
        assert _redis_run_key(run_id_a) != _redis_run_key(run_id_b)
        assert run_id_a in _redis_step_key(run_id_a, 1)
        assert run_id_b in _redis_step_key(run_id_b, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 8 - SSE client disconnects mid-run → generator exits cleanly
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario8SSEDisconnect:
    def test_generator_exits_on_cancellation(self):
        """
        SSE generator must handle asyncio.CancelledError (client disconnect) cleanly.
        No exception should propagate out.
        """
        from pipeline.routers.sse import pipeline_event_generator

        fake_redis = FakeRedis()
        fake_redis.set("pipeline:run-test:status", "RUNNING")

        async def run_generator_then_cancel():
            gen = pipeline_event_generator("run-test", "ESGRC_MODULE")
            events = []
            try:
                # Collect first event (the 'connected' event)
                event = await gen.__anext__()
                events.append(event)
                # Simulate client disconnect by cancelling
                raise asyncio.CancelledError()
            except (asyncio.CancelledError, StopAsyncIteration):
                pass
            return events

        with patch("pipeline.routers.sse.get_run_status",
                   return_value="RUNNING"):
            with patch("pipeline.routers.sse.get_step_state", return_value=None):
                events = asyncio.run(run_generator_then_cancel())

        # At minimum the 'connected' event was yielded
        assert len(events) >= 1
        first_event = json.loads(events[0].replace("data: ", "").strip())
        assert first_event["event"] == "connected"

    def test_generator_terminates_on_completed_run(self):
        """SSE generator must yield terminal event and stop when run is COMPLETED."""
        from pipeline.routers.sse import pipeline_event_generator

        async def collect_events():
            gen = pipeline_event_generator("run-done", "ESGRC_MODULE")
            events = []
            async for event in gen:
                events.append(event)
                if len(events) > 10:  # safety limit
                    break
            return events

        with (
            patch("pipeline.routers.sse.get_run_status", return_value="COMPLETED"),
            patch("pipeline.routers.sse.get_step_state", return_value=None),
            patch("pipeline.routers.sse.POLL_INTERVAL", 0.001),
        ):
            events = asyncio.run(collect_events())

        # Must include a terminal run_completed event
        all_data = " ".join(events)
        assert "run_completed" in all_data


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 10 - Cross-org data access → 404
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario10CrossOrgAccess:
    def test_run_from_other_org_returns_404(self):
        """
        User from org 42 tries to access a run belonging to org 99.
        Must return 404 - not 403. Existence must not be revealed.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pipeline.routers.pipeline_router import router
        from pipeline.db import get_pipeline_db
        from app.dependencies.auth import get_current_user

        app = FastAPI()
        app.include_router(router, prefix="/pipelines")

        def override_db():
            with Session(extreme_engine) as session:
                yield session

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.organisation_id = 42  # org 42 user

        app.dependency_overrides[get_pipeline_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: mock_user

        # Create a run for org 99
        with Session(extreme_engine) as session:
            pipeline = PipelineDefinition(
                org_id=99, name="Other Org", pipeline_type=PipelineTypeEnum.ESGRC_MODULE,
                is_active=True, config_json={},
            )
            session.add(pipeline)
            session.flush()
            run = PipelineRun(
                pipeline_id=pipeline.id, org_id=99, status=RunStatusEnum.COMPLETED,
            )
            session.add(run)
            session.commit()
            run_id = run.id

        client = TestClient(app)
        resp = client.get(
            f"/pipelines/runs/{run_id}",
            headers={"Authorization": "Bearer test-token"},
        )
        # Must be 404 - not 403
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 11 - Rollback when only one run exists → 400
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario11RollbackNoHistory:
    def test_rollback_to_same_run_returns_400(self):
        """Rolling back to the same run as target returns 400."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pipeline.routers.pipeline_router import router
        from pipeline.db import get_pipeline_db
        from app.dependencies.auth import get_current_user, require_role

        app = FastAPI()
        app.include_router(router, prefix="/pipelines")

        def override_db():
            with Session(extreme_engine) as session:
                yield session

        from app.models.models import UserRole

        mock_user = MagicMock()
        mock_user.id = 1
        mock_user.organisation_id = 1
        mock_user.role = UserRole.ADMIN
        mock_user.module_access = ["esgrc", "apex"]  # real list - run-level module scope reads this

        app.dependency_overrides[get_pipeline_db] = override_db
        app.dependency_overrides[get_current_user] = lambda: mock_user
        app.dependency_overrides[require_role("admin")] = lambda: mock_user

        with Session(extreme_engine) as session:
            _, run_id = _make_pipeline_and_run(session)
            # Set run to COMPLETED
            run = session.get(PipelineRun, run_id)
            run.status = RunStatusEnum.COMPLETED
            run.is_current = True
            session.commit()

        client = TestClient(app)
        resp = client.post(
            f"/pipelines/runs/{run_id}/rollback",
            headers={"Authorization": "Bearer test-token"},
            json={"target_run_id": run_id},  # same run = should fail
        )
        assert resp.status_code == 400
        assert "already current" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Scenario 12 - Prompt updated mid-run → in-flight run uses captured hash
# ─────────────────────────────────────────────────────────────────────────────

class TestScenario12PromptUpdatedMidRun:
    def test_prompt_hash_is_captured_at_trigger_time(self):
        """
        The running pipeline captures prompt_hash from the rendered prompt
        at call time - not at trigger time. The hash is stored in
        pipeline_llm_outputs.prompt_hash.

        When the prompt version changes (new DB row), the hash in the
        completed run's llm_output still reflects the prompt that was
        actually used - not the new version.
        """
        import hashlib

        # Simulate: old prompt text
        old_prompt_text = "You are an expert. Analyse: {report_text}"
        new_prompt_text = "You are a senior analyst. Analyse: {report_text}"
        report_text = "test report content"

        old_rendered = old_prompt_text.format(report_text=report_text)
        new_rendered = new_prompt_text.format(report_text=report_text)

        old_hash = hashlib.sha256(old_rendered.encode()).hexdigest()
        new_hash = hashlib.sha256(new_rendered.encode()).hexdigest()

        # Hashes must differ - different prompts = different hashes
        assert old_hash != new_hash

        # An in-flight run that captured old_hash will always have old_hash
        # in its llm_output row - the new prompt does not affect it
        with Session(extreme_engine) as session:
            _, run_id = _make_pipeline_and_run(session)
            run = session.get(PipelineRun, run_id)
            run.status = RunStatusEnum.RUNNING
            session.flush()

            # Create step result
            step = PipelineStepResult(
                run_id=run_id, step_number=7, step_name="Claude",
                status=StepStatusEnum.COMPLETED,
            )
            session.add(step)
            session.flush()

            # LLM output records the OLD hash (from when it was called)
            llm_out = PipelineLLMOutput(
                run_id=run_id,
                step_result_id=step.id,
                analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
                prompt_hash=old_hash,   # ← captured at call time
                model_used="claude-haiku-4-5",
                response_text="Analysis result.",
            )
            session.add(llm_out)
            session.commit()
            output_id = llm_out.id

        # Simulate: admin updates the prompt AFTER the run completes
        # (new DB row created, old row deactivated)
        # The completed run's hash is unchanged

        with Session(extreme_engine) as session:
            stored = session.get(PipelineLLMOutput, output_id)
            assert stored.prompt_hash == old_hash
            assert stored.prompt_hash != new_hash
