"""
pipeline/test/test_pipeline_endpoints.py
30+ tests for all pipeline FastAPI endpoints.

Uses:
  - In-memory SQLite database
  - CELERY_TASK_ALWAYS_EAGER=True (tasks run inline, no worker needed)
  - Mocked R2 (boto3 patched)
  - Mocked Celery enqueue (tasks don't actually run in endpoint tests)
"""
import os
import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch
from app.models.models import UserRole

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event as sa_event, select
from sqlalchemy.orm import Session

# ── Set env vars before any app imports ──────────────────────────────────────
os.environ["DATABASE_URL"] = "sqlite:///./.local/test_databases/test_pipeline.db"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["CLOUDFLARE_R2_BUCKET"] = "test-bucket"
os.environ["CLOUDFLARE_R2_ENDPOINT"] = "https://test.r2.example.com"
os.environ["CLOUDFLARE_R2_ACCESS_KEY"] = "test-key"
os.environ["CLOUDFLARE_R2_SECRET_KEY"] = "test-secret"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!!"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key"

from pipeline.db import pipeline_engine, get_pipeline_db
from pipeline.models import (
    PipelineBase,
    PipelineDefinition,
    PipelineLLMOutput,
    PipelineRun,
    PipelineStepResult,
    PipelineTypeEnum,
    RunStatusEnum,
    StepStatusEnum,
    AnalysisTypeEnum,
)
from pipeline.prompt_models import PipelinePrompt


# ── Test database setup ───────────────────────────────────────────────────────

TEST_DB_URL = "sqlite:///./.local/test_databases/test_pipeline.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
PipelineBase.metadata.create_all(bind=test_engine)

# Also create prompt table
from pipeline.prompt_models import PipelineBase as PB2  # same base
PB2.metadata.create_all(bind=test_engine)


def override_get_pipeline_db():
    with Session(test_engine) as session:
        yield session


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clean_db():
    """Truncate all pipeline tables before each test."""
    with Session(test_engine) as session:
        session.query(PipelineLLMOutput).delete()
        session.query(PipelineStepResult).delete()
        session.query(PipelineRun).delete()
        session.query(PipelineDefinition).delete()
        session.query(PipelinePrompt).delete()
        session.commit()
    yield


@pytest.fixture
def client() -> Generator:
    """FastAPI TestClient with pipeline router mounted and DB overridden."""
    from fastapi import FastAPI
    from pipeline.routers.pipeline_router import router

    app = FastAPI()
    app.include_router(router, prefix="/pipelines")
    app.dependency_overrides[get_pipeline_db] = override_get_pipeline_db

    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_current_user():
    """Patch get_current_user to return a mock analyst user."""
    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.organisation_id = 42
    mock_user.role = UserRole.ANALYST
    # Module-scoped access (see app.dependencies.auth.require_module). Grant both
    # so existing pipeline tests (ESGRC + Apex) aren't gated out.
    mock_user.module_access = ["esgrc", "apex"]
    return mock_user


@pytest.fixture
def mock_admin_user():
    mock_user = MagicMock()
    mock_user.id = 2
    mock_user.organisation_id = 42
    mock_user.role = UserRole.ADMIN
    mock_user.module_access = ["esgrc", "apex"]
    return mock_user


@pytest.fixture
def mock_apex_user():
    """A user scoped to the Apex module only - must NOT see ESGRC pipelines."""
    mock_user = MagicMock()
    mock_user.id = 3
    mock_user.organisation_id = 42
    mock_user.role = UserRole.ADMIN
    mock_user.module_access = ["apex"]
    return mock_user


class TestModuleScoping:
    """Module-scoped RBAC: a user only sees/acts on pipelines in their modules."""

    def test_apex_user_does_not_see_esgrc_pipeline_in_list(self, client, mock_apex_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_apex_user
        resp = client.get("/pipelines", headers=auth_header())
        assert resp.status_code == 200
        # seeded_pipeline is ESGRC_MODULE → filtered out for an apex-only user
        assert all(p["pipeline_type"] != "ESGRC_MODULE" for p in resp.json())

    def test_apex_user_gets_404_on_esgrc_pipeline_by_id(self, client, mock_apex_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_apex_user
        # 404 (not 403) so a scoped user can't even confirm the id exists.
        resp = client.get(f"/pipelines/{seeded_pipeline['id']}", headers=auth_header())
        assert resp.status_code == 404

    def test_esgrc_user_can_access_esgrc_pipeline(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        resp = client.get(f"/pipelines/{seeded_pipeline['id']}", headers=auth_header())
        assert resp.status_code == 200

    def test_apex_user_gets_404_on_esgrc_run(self, client, mock_apex_user, seeded_run):
        # Run-level module scope: an apex-only user must not reach an ESGRC run's
        # detail or recommendations (404, not 403 - can't even probe the id).
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_apex_user
        detail = client.get(f"/pipelines/runs/{seeded_run['id']}", headers=auth_header())
        recs = client.get(f"/pipelines/runs/{seeded_run['id']}/recommendations", headers=auth_header())
        assert detail.status_code == 404
        assert recs.status_code == 404

    def test_esgrc_user_can_access_esgrc_run(self, client, mock_current_user, seeded_run):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        resp = client.get(f"/pipelines/runs/{seeded_run['id']}", headers=auth_header())
        assert resp.status_code == 200


def _insert_def(org_id=42, ptype="ESGRC_MODULE", active=True, config=None):
    import json as _json, uuid as _uuid
    from sqlalchemy import text
    pid = str(_uuid.uuid4())
    with test_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO pipeline_definitions (id, org_id, name, pipeline_type, is_active, config_json, created_at, updated_at)
            VALUES (:id, :org_id, :name, :ptype, :active, :config, datetime('now'), datetime('now'))
        """), {"id": pid, "org_id": org_id, "name": "Test ESGRC Pipeline", "ptype": ptype,
               "active": int(active), "config": _json.dumps(config or {})})
    return pid


def _insert_run(pipeline_id, org_id=42, status="COMPLETED", **kw):
    import uuid as _uuid
    from sqlalchemy import text
    rid = str(_uuid.uuid4())
    with test_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO pipeline_runs (id, pipeline_id, org_id, status, is_current, progress_pct, triggered_by, celery_chord_id)
            VALUES (:id, :pid, :org_id, :status, :cur, :pct, :tb, :cid)
        """), {"id": rid, "pid": pipeline_id, "org_id": org_id, "status": status,
               "cur": int(kw.get("is_current", False)), "pct": kw.get("progress_pct", 0),
               "tb": kw.get("triggered_by"), "cid": kw.get("celery_chord_id")})
    return rid


@pytest.fixture
def seeded_pipeline() -> dict:
    pipeline_id = _insert_def()
    return {"id": pipeline_id, "type": PipelineTypeEnum.ESGRC_MODULE, "name": "Test ESGRC Pipeline"}

@pytest.fixture
def seeded_run(seeded_pipeline) -> dict:
    run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED",
                          triggered_by=1, is_current=True, progress_pct=100)
    return {"id": run_id, "pipeline_id": seeded_pipeline["id"]}


# ── Auth helper ───────────────────────────────────────────────────────────────

def auth_header(token: str = "test-token") -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestProcessLog:
    """Praveen's process-log criteria: user · timestamp · step executed · pass/fail."""

    def test_returns_executed_steps_across_runs(
        self, client, mock_current_user, seeded_run, seeded_pipeline
    ):
        from app.dependencies.auth import get_current_user

        with Session(test_engine) as session:
            session.add(
                PipelineStepResult(
                    run_id=seeded_run["id"],
                    step_number=3,
                    step_name="Correlation CHAID FT Analysis",
                    status=StepStatusEnum.COMPLETED,
                    duration_ms=4200,
                )
            )
            session.add(
                PipelineStepResult(
                    run_id=seeded_run["id"],
                    step_number=4,
                    step_name="SPC RPN Analysis",
                    status=StepStatusEnum.FAILED,
                    error_detail="boom",
                )
            )
            session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        resp = client.get("/pipelines/process-log", headers=auth_header())

        assert resp.status_code == 200
        entries = resp.json()
        by_step = {e["step_number"]: e for e in entries}
        assert {3, 4} <= set(by_step)

        # process step executed + pass/fail + timing
        assert by_step[3]["step_name"] == "Correlation CHAID FT Analysis"
        assert by_step[3]["status"] == "COMPLETED"
        assert by_step[3]["duration_ms"] == 4200
        # a failure is visible as such, with the reason
        assert by_step[4]["status"] == "FAILED"
        assert by_step[4]["error_detail"] == "boom"
        # run context is carried on every line
        assert by_step[3]["run_id"] == seeded_run["id"]

    def test_can_filter_to_one_run(self, client, mock_current_user, seeded_run):
        from app.dependencies.auth import get_current_user

        with Session(test_engine) as session:
            session.add(
                PipelineStepResult(
                    run_id=seeded_run["id"],
                    step_number=1,
                    step_name="Data Preparation 1",
                    status=StepStatusEnum.COMPLETED,
                )
            )
            session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        resp = client.get(
            f"/pipelines/process-log?run_id={seeded_run['id']}", headers=auth_header()
        )
        assert resp.status_code == 200
        assert all(e["run_id"] == seeded_run["id"] for e in resp.json())


class TestHandoffProvenance:
    def test_returns_per_module_freshness(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user

        sample = [
            {"module": "esgrc", "present": True,
             "produced_at": "2026-07-15T12:00:00+00:00", "source_run_id": "run-abc"},
            {"module": "brand", "present": False,
             "produced_at": None, "source_run_id": None},
        ]
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        with patch(
            "pipeline.routers.pipeline_router.get_apex_handoff_provenance",
            return_value=sample,
        ) as mock_prov:
            resp = client.get("/pipelines/handoff-provenance", headers=auth_header())

        assert resp.status_code == 200
        data = resp.json()
        assert {d["module"] for d in data} == {"esgrc", "brand"}
        esgrc = next(d for d in data if d["module"] == "esgrc")
        assert esgrc["present"] is True
        assert esgrc["produced_at"] == "2026-07-15T12:00:00+00:00"
        assert esgrc["source_run_id"] == "run-abc"
        # org-scoped: called with the current user's org id
        mock_prov.assert_called_once_with(str(mock_current_user.organisation_id))


# ─────────────────────────────────────────────────────────────────────────────
# Tests - List pipelines (GET /pipelines)
# ─────────────────────────────────────────────────────────────────────────────

class TestListPipelines:
    def test_returns_empty_list_when_no_pipelines(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get("/pipelines", headers=auth_header())
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_pipelines_for_org(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get("/pipelines", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test ESGRC Pipeline"

    def test_does_not_return_other_org_pipelines(self, client, mock_current_user):
        """Pipelines belonging to org 99 must not appear for org 42."""
        _insert_def(org_id=99, ptype=PipelineTypeEnum.APEX_ENTERPRISE.value)

        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get("/pipelines", headers=auth_header())
        assert resp.status_code == 200
        assert resp.json() == []


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Get pipeline (GET /pipelines/{id})
# ─────────────────────────────────────────────────────────────────────────────

class TestGetPipeline:
    def test_returns_pipeline(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(f"/pipelines/{seeded_pipeline['id']}", headers=auth_header())
        assert resp.status_code == 200
        assert resp.json()["id"] == seeded_pipeline["id"]

    def test_returns_404_for_wrong_org(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(f"/pipelines/{uuid.uuid4()}", headers=auth_header())
        assert resp.status_code == 404

    def test_returns_404_for_other_org_pipeline(self, client, mock_current_user):
        other_id = _insert_def(org_id=99)

        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(f"/pipelines/{other_id}", headers=auth_header())
        # Must return 404 - existence of other org's pipeline must not be revealed
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Prompt routes must not be shadowed by GET /pipelines/{pipeline_id}
#
# Regression: GET /pipelines/prompts was previously captured by the
# "/{pipeline_id}" catch-all (pipeline_id="prompts"), returning 404 and silently
# breaking the Settings → Prompts tab. The static /prompts routes are now declared
# before the catch-all; these tests lock that ordering in.
# ─────────────────────────────────────────────────────────────────────────────

def _insert_prompt(name="ESGRC_MODULE_UNIFIED", version=1, content="Prompt body", active=True):
    from sqlalchemy import text
    with test_engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO pipeline_prompts (name, version, content, is_active, created_at)
            VALUES (:name, :version, :content, :active, datetime('now'))
        """), {"name": name, "version": version, "content": content, "active": int(active)})


class TestPromptRouteNotShadowed:
    def test_list_prompts_is_not_captured_by_pipeline_id_catch_all(
        self, client, mock_admin_user
    ):
        # A pipeline definition also exists, to prove /prompts is NOT treated as an id.
        _insert_def(org_id=42)
        _insert_prompt(name="ESGRC_MODULE_UNIFIED")
        _insert_prompt(name="APEX_GENERAL_RISK")

        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        resp = client.get("/pipelines/prompts", headers=auth_header())

        # Must be 200 with the prompt list - NOT 404 from the pipeline lookup.
        assert resp.status_code == 200, resp.text
        data = resp.json()
        names = {p["name"] for p in data}
        assert {"ESGRC_MODULE_UNIFIED", "APEX_GENERAL_RISK"} <= names

    def test_list_prompts_only_returns_active_versions(self, client, mock_admin_user):
        _insert_prompt(name="ESGRC_MODULE_UNIFIED", version=1, active=False)
        _insert_prompt(name="ESGRC_MODULE_UNIFIED", version=2, active=True)

        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        resp = client.get("/pipelines/prompts", headers=auth_header())
        assert resp.status_code == 200, resp.text
        data = resp.json()
        versions = [p["version"] for p in data if p["name"] == "ESGRC_MODULE_UNIFIED"]
        assert versions == [2]


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Trigger pipeline (POST /pipelines/{id}/trigger)
# ─────────────────────────────────────────────────────────────────────────────

class TestTriggerPipeline:
    def test_trigger_returns_202_with_run_id(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router._enqueue_pipeline"):
            resp = client.post(
                f"/pipelines/{seeded_pipeline['id']}/trigger",
                headers=auth_header(),
                json={},
            )

        assert resp.status_code == 202
        data = resp.json()
        assert "run_id" in data
        assert data["status"] == "PENDING"

    def test_trigger_creates_run_in_db(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router._enqueue_pipeline"):
            resp = client.post(
                f"/pipelines/{seeded_pipeline['id']}/trigger",
                headers=auth_header(),
                json={},
            )

        run_id = resp.json()["run_id"]
        with Session(test_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run is not None
            assert run.status == RunStatusEnum.PENDING
            assert run.org_id == 42

    def test_trigger_inactive_pipeline_returns_400(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user, require_role

        inactive_id = _insert_def(org_id=42, active=False)

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        resp = client.post(f"/pipelines/{inactive_id}/trigger", headers=auth_header(), json={})
        assert resp.status_code == 400

    def test_trigger_with_missing_input_file_returns_400(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user, require_role

        pipeline_id = _insert_def(org_id=42, config={
            "required_input_files": ["org/{org_id}/reference/missing_file.csv"]
        })

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router.file_exists", return_value=False):
            resp = client.post(f"/pipelines/{pipeline_id}/trigger", headers=auth_header(), json={})

        assert resp.status_code == 400
        assert "missing" in resp.json()["detail"].lower()

    def test_trigger_nonexistent_pipeline_returns_404(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        resp = client.post(f"/pipelines/{uuid.uuid4()}/trigger", headers=auth_header(), json={})
        assert resp.status_code == 404

    def test_trigger_rejects_cross_org_input_file_override(self, client, mock_current_user, seeded_pipeline):
        # input_file_overrides is a raw R2 key ("Map of input_name -> R2 key",
        # per TriggerRequest's docstring) that every chain task uses verbatim
        # with no org check of its own. mock_current_user's org is 42, so a
        # key scoped to org 99 must be rejected before a run is even created -
        # otherwise any analyst could read another org's ESG/compliance data
        # into their own run's output.
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router._enqueue_pipeline") as mock_enqueue:
            resp = client.post(
                f"/pipelines/{seeded_pipeline['id']}/trigger",
                headers=auth_header(),
                json={"input_file_overrides": {
                    "input_metrics_data": "org/99/reference/input_metric_values_esgrc.csv"
                }},
            )

        assert resp.status_code == 400, resp.text
        assert "own organisation" in resp.json()["detail"]
        mock_enqueue.assert_not_called()

    def test_trigger_accepts_same_org_input_file_override(self, client, mock_current_user, seeded_pipeline):
        # The same shape, scoped to the caller's own org (42), must still work.
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router._enqueue_pipeline"):
            resp = client.post(
                f"/pipelines/{seeded_pipeline['id']}/trigger",
                headers=auth_header(),
                json={"input_file_overrides": {
                    "input_metrics_data": "org/42/reference/input_metric_values_esgrc.csv"
                }},
            )

        assert resp.status_code == 202, resp.text

    def test_trigger_seeds_pending_rows_for_every_step(self, client, mock_current_user, seeded_pipeline):
        # Regression: pipeline_step_results rows used to be created lazily by
        # mark_step_running only as each step actually started, so
        # mark_step_failed's own "SKIP all subsequent PENDING steps" UPDATE
        # (pipeline/tasks/shared.py) had nothing to act on - a header-group
        # step failing left the never-started downstream steps with NO row at
        # all instead of SKIPPED. trigger_pipeline must now seed one PENDING
        # row per step up front so that existing SKIP logic has something to
        # find.
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router._enqueue_pipeline"):
            resp = client.post(
                f"/pipelines/{seeded_pipeline['id']}/trigger",
                headers=auth_header(), json={},
            )
        run_id = resp.json()["run_id"]

        with Session(test_engine) as session:
            rows = session.execute(
                select(PipelineStepResult)
                .where(PipelineStepResult.run_id == run_id)
                .order_by(PipelineStepResult.step_number)
            ).scalars().all()

        # ESGRC_MODULE runs 7 steps (1-6 from build_esgrc_chain + Claude step 7
        # appended by the caller).
        assert [r.step_number for r in rows] == [1, 2, 3, 4, 5, 6, 7]
        assert all(r.status == StepStatusEnum.PENDING for r in rows)

    def test_header_step_failure_skips_downstream_via_seeded_rows(
        self, client, mock_current_user, seeded_pipeline, monkeypatch
    ):
        # pipeline.database.get_engine()/session_ctx() is a process-wide
        # singleton, bound on first use to whatever DATABASE_URL was current
        # at that moment (pipeline/database.py's own docstring: "Engine is
        # created on first access"). Across the full test_pipeline.py suite
        # some earlier test file can win that first call, leaving the
        # singleton pointed at a different engine than this file's own
        # test_engine - so mark_step_failed (which goes through session_ctx)
        # would silently look up run_id in the wrong database and find
        # nothing. test_extreme_scenarios.py hit the identical issue and
        # fixed it by monkeypatching pipeline.database's module globals
        # directly (see its _patch_shared_db_engine fixture); do the same
        # here, scoped to just this test.
        import pipeline.database as pipeline_database_module
        from sqlalchemy.orm import sessionmaker as _sessionmaker

        monkeypatch.setattr(pipeline_database_module, "_engine", test_engine)
        monkeypatch.setattr(
            pipeline_database_module,
            "_SessionFactory",
            _sessionmaker(bind=test_engine, expire_on_commit=False),
        )

        # End-to-end version of the above: after trigger seeds the PENDING
        # rows, simulate step 2 (in the ESGRC header group {2,4,5}) failing
        # exactly like _handle_step_failure does in esgrc_chain.py, and
        # confirm the truly-downstream tail steps (3, 6, and the appended
        # Claude step 7 - none of which can run once the chord header fails)
        # come back SKIPPED, not absent. This is deliberately NOT exercised
        # through apex_chord_error_handler/a real chord dispatch (see
        # TestScenario6ChordError's own comment on why that's dead code in
        # production) - it goes through the real seed-then-fail path.
        #
        # mark_step_failed's SKIP query is step_number-based, not DAG-aware
        # (shared.py: "step_number > :n AND status='PENDING'"), so it also
        # transiently marks steps 4 and 5 SKIPPED even though they are
        # step 2's siblings in the same header group, not its dependents -
        # in a real chord they keep running independently and are expected
        # to self-heal back to COMPLETED when they finish (matching the
        # audit's own note on this: a transient, cosmetic status blip, not a
        # broken run). Assert both halves: the permanent tail SKIPs, and that
        # a sibling's later real completion overwrites the transient SKIP.
        from app.dependencies.auth import get_current_user, require_role
        from pipeline.tasks.shared import mark_step_failed, mark_step_completed

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router._enqueue_pipeline"):
            resp = client.post(
                f"/pipelines/{seeded_pipeline['id']}/trigger",
                headers=auth_header(), json={},
            )
        run_id = resp.json()["run_id"]

        with patch("pipeline.tasks.shared._get_redis", return_value=MagicMock()):
            mark_step_failed(run_id, 2, "simulated header-group failure")

            def _status(step: int) -> StepStatusEnum:
                with Session(test_engine) as session:
                    return session.execute(
                        select(PipelineStepResult.status).where(
                            PipelineStepResult.run_id == run_id,
                            PipelineStepResult.step_number == step,
                        )
                    ).scalar_one()

            assert _status(2) == StepStatusEnum.FAILED
            for tail_step in (3, 6, 7):
                assert _status(tail_step) == StepStatusEnum.SKIPPED, (
                    f"tail step {tail_step} should be SKIPPED, got {_status(tail_step)}"
                )
            # Transient: siblings 4/5 also got swept by the number-based SKIP.
            assert _status(4) == StepStatusEnum.SKIPPED
            assert _status(5) == StepStatusEnum.SKIPPED

            # Self-heal: step 4 was actually still running independently and
            # finishes normally - its real completion must win, not stay SKIPPED.
            mark_step_completed(run_id, 4, input_files=[], output_files=[], duration_ms=100)
            assert _status(4) == StepStatusEnum.COMPLETED

        with Session(test_engine) as session:
            run = session.execute(
                select(PipelineRun).where(PipelineRun.id == run_id)
            ).scalar_one()
            assert run.status == RunStatusEnum.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Get run (GET /pipelines/runs/{run_id})
# ─────────────────────────────────────────────────────────────────────────────

class TestGetRun:
    def test_returns_run_with_steps(self, client, mock_current_user, seeded_run):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(f"/pipelines/runs/{seeded_run['id']}", headers=auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == seeded_run["id"]
        assert data["status"] == "COMPLETED"

    def test_returns_404_for_other_org_run(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        # Create a run for org 99
        pid = _insert_def(org_id=99)
        run_id = _insert_run(pid, org_id=99, status="COMPLETED")

        resp = client.get(f"/pipelines/runs/{run_id}", headers=auth_header())
        # Must be 404 - cross-org access
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Rollback (POST /pipelines/runs/{run_id}/rollback)
# ─────────────────────────────────────────────────────────────────────────────

class TestRollback:
    def test_rollback_flips_is_current_atomically(self, client, mock_admin_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role

        # Create two completed runs
        run_a_id = _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED", is_current=False)
        run_b_id = _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED", is_current=True)

        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        resp = client.post(
            f"/pipelines/runs/{run_a_id}/rollback",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["current_run_id"] == run_a_id

        # Verify DB state
        with Session(test_engine) as session:
            a = session.get(PipelineRun, run_a_id)
            b = session.get(PipelineRun, run_b_id)
            assert a.is_current is True
            assert b.is_current is False

    def test_rollback_to_failed_run_returns_400(self, client, mock_admin_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role

        run_a_id = _insert_run(seeded_pipeline["id"], org_id=42, status="FAILED", is_current=False)
        run_b_id = _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED", is_current=True)

        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        resp = client.post(
            f"/pipelines/runs/{run_b_id}/rollback",
            headers=auth_header(),
            json={"target_run_id": run_a_id},
        )
        assert resp.status_code == 400

    def test_rollback_to_same_run_returns_400(self, client, mock_admin_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED", is_current=True)

        resp = client.post(
            f"/pipelines/runs/{run_id}/rollback",
            headers=auth_header(),
        )
        assert resp.status_code == 400
        assert "already current" in resp.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Emergency stop (POST /pipelines/emergency-stop)
# ─────────────────────────────────────────────────────────────────────────────

class TestEmergencyStop:
    def test_stop_running_run(self, client, mock_admin_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="RUNNING", celery_chord_id="test-chord-id")

        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        with (
            patch("pipeline.celery_app.app.control.revoke") as mock_revoke,
            patch("pipeline.tasks.shared._get_redis") as mock_redis,
        ):
            mock_redis.return_value.set = MagicMock()
            resp = client.post(
                "/pipelines/emergency-stop",
                headers=auth_header(),
                json={"run_id": run_id},
            )

        # Even without the mock working perfectly, the run status should change
        with Session(test_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run.status == RunStatusEnum.CANCELLED

    def test_stop_already_completed_run_returns_400(self, client, mock_admin_user, seeded_run):
        from app.dependencies.auth import get_current_user, require_role
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        resp = client.post(
            "/pipelines/emergency-stop",
            headers=auth_header(),
            json={"run_id": seeded_run["id"]},
        )
        assert resp.status_code == 400

    def test_stop_queued_run_revokes_every_step_with_no_step_rows_yet(
        self, client, mock_admin_user, seeded_pipeline
    ):
        """
        The scenario the old code silently did nothing for: a run that hasn't
        started (no pipeline_step_results rows at all - they're only created
        once mark_step_running fires) is cancelled while still queued. Every
        step's deterministic task id must be revoked up front, not just the
        ones with an existing DB row, and the absence of a celery_chord_id must
        no longer block the stop (it used to 409).
        """
        from app.dependencies.auth import get_current_user, require_role

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="PENDING")
        # No celery_chord_id, no pipeline_step_results rows - genuinely queued.

        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        with (
            patch("pipeline.celery_app.app.control.revoke") as mock_revoke,
            patch("pipeline.tasks.shared._get_redis") as mock_redis,
        ):
            mock_redis.return_value.set = MagicMock()
            resp = client.post(
                "/pipelines/emergency-stop",
                headers=auth_header(),
                json={"run_id": run_id},
            )

        assert resp.status_code == 200

        revoked_ids = {call.args[0] for call in mock_revoke.call_args_list}
        # seeded_pipeline is ESGRC_MODULE - 7 steps.
        assert revoked_ids == {f"{run_id}_step{n}" for n in range(1, 8)}

        with Session(test_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run.status == RunStatusEnum.CANCELLED

    def test_stop_apex_run_revokes_all_eight_steps(self, client, mock_admin_user):
        from app.dependencies.auth import get_current_user, require_role

        apex_pipeline_id = _insert_def(ptype="APEX_ENTERPRISE")
        run_id = _insert_run(apex_pipeline_id, org_id=42, status="PENDING")

        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        client.app.dependency_overrides[require_role("admin")] = lambda: mock_admin_user

        with (
            patch("pipeline.celery_app.app.control.revoke") as mock_revoke,
            patch("pipeline.tasks.shared._get_redis") as mock_redis,
        ):
            mock_redis.return_value.set = MagicMock()
            resp = client.post(
                "/pipelines/emergency-stop",
                headers=auth_header(),
                json={"run_id": run_id},
            )

        assert resp.status_code == 200
        revoked_ids = {call.args[0] for call in mock_revoke.call_args_list}
        assert revoked_ids == {f"{run_id}_step{n}" for n in range(1, 9)}


class TestRunStatusGuards:
    """
    A task queued before emergency-stop can still start executing after the
    run is already marked CANCELLED (revoke() cannot un-queue a task with zero
    latency). mark_run_running/mark_run_completed must not let that straggler
    silently un-cancel the run once it starts or finishes.
    """

    @pytest.fixture(autouse=True)
    def _use_test_engine_for_shared_module(self):
        """
        pipeline.tasks.shared writes through pipeline.database.session_ctx(),
        a lazily-created singleton bound to whatever DATABASE_URL was active on
        its first call anywhere in the test session. test_extreme_scenarios.py
        permanently repoints that singleton at its own engine with no teardown
        (a pre-existing test-isolation gap) - pin it to this file's test_engine
        explicitly instead of assuming nobody else touched it first.
        """
        import pipeline.database as pipeline_database_module
        from sqlalchemy.orm import sessionmaker as _sessionmaker

        original_engine = pipeline_database_module._engine
        original_factory = pipeline_database_module._SessionFactory
        pipeline_database_module._engine = test_engine
        pipeline_database_module._SessionFactory = _sessionmaker(bind=test_engine, expire_on_commit=False)
        yield
        pipeline_database_module._engine = original_engine
        pipeline_database_module._SessionFactory = original_factory

    def test_mark_run_running_does_not_resurrect_a_cancelled_run(self, seeded_pipeline):
        from pipeline.tasks import shared

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="CANCELLED")

        with patch.object(shared, "_get_redis") as mock_redis:
            mock_redis.return_value.set = MagicMock()
            shared.mark_run_running(run_id)
            mock_redis.return_value.set.assert_not_called()

        with Session(test_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run.status == RunStatusEnum.CANCELLED

    def test_mark_run_completed_does_not_resurrect_a_cancelled_run(self, seeded_pipeline):
        from pipeline.tasks import shared

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="CANCELLED")

        with patch.object(shared, "_get_redis") as mock_redis:
            mock_redis.return_value.set = MagicMock()
            shared.mark_run_completed(run_id)
            mock_redis.return_value.set.assert_not_called()

        with Session(test_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run.status == RunStatusEnum.CANCELLED
            assert run.is_current is False

    def test_mark_run_running_still_works_normally(self, seeded_pipeline):
        """The guard must not break the ordinary, non-cancelled path."""
        from pipeline.tasks import shared

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="PENDING")

        with patch.object(shared, "_get_redis") as mock_redis:
            mock_redis.return_value.set = MagicMock()
            shared.mark_run_running(run_id)
            mock_redis.return_value.set.assert_called_once()

        with Session(test_engine) as session:
            run = session.get(PipelineRun, run_id)
            assert run.status == RunStatusEnum.RUNNING


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Step re-run
# ─────────────────────────────────────────────────────────────────────────────

class TestStepRerun:
    def test_rerun_validates_prerequisites(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user, require_role

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="FAILED")
        with Session(test_engine) as session:
            step1 = PipelineStepResult(
                run_id=run_id, step_number=1, step_name="Step 1",
                status=StepStatusEnum.FAILED,
            )
            step2 = PipelineStepResult(
                run_id=run_id, step_number=2, step_name="Step 2",
                status=StepStatusEnum.PENDING,
            )
            session.add_all([step1, step2])
            session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        # Trying to re-run step 2 when step 1 is not COMPLETED should fail
        resp = client.post(
            f"/pipelines/runs/{run_id}/steps/2/rerun",
            headers=auth_header(),
        )
        assert resp.status_code == 400
        assert "prerequisite" in resp.json()["detail"].lower()

    def test_cannot_rerun_step_on_running_pipeline(
        self, client, mock_current_user, seeded_pipeline
    ):
        from app.dependencies.auth import get_current_user, require_role

        run_id = _insert_run(seeded_pipeline["id"], org_id=42, status="RUNNING")

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[require_role("analyst")] = lambda: mock_current_user

        resp = client.post(f"/pipelines/runs/{run_id}/steps/1/rerun", headers=auth_header())
        assert resp.status_code == 400


# ─────────────────────────────────────────────────────────────────────────────
# Tests - LLM outputs
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMOutputs:
    def test_get_recommendations_returns_outputs(
        self, client, mock_current_user, seeded_run, seeded_pipeline
    ):
        from app.dependencies.auth import get_current_user

        # Add a step result and LLM output
        with Session(test_engine) as session:
            step = PipelineStepResult(
                run_id=seeded_run["id"],
                step_number=7,
                step_name="Claude",
                status=StepStatusEnum.COMPLETED,
            )
            session.add(step)
            session.flush()

            llm = PipelineLLMOutput(
                run_id=seeded_run["id"],
                step_result_id=step.id,
                analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
                prompt_hash="abc123",
                model_used="claude-haiku-4-5",
                response_text="Risk assessment: low risk across all modules.",
                input_tokens=1000,
                output_tokens=500,
            )
            session.add(llm)
            session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(
            f"/pipelines/runs/{seeded_run['id']}/recommendations",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["analysis_type"] == "MODULE_UNIFIED"

    def test_recommendations_include_contextual_labels(
        self, client, mock_current_user, seeded_run, seeded_pipeline
    ):
        """The served report exposes business names (labelled view) alongside the
        code-centric response_text, for the frontend to display."""
        from app.dependencies.auth import get_current_user

        with Session(test_engine) as session:
            step = PipelineStepResult(
                run_id=seeded_run["id"],
                step_number=7,
                step_name="Claude",
                status=StepStatusEnum.COMPLETED,
            )
            session.add(step)
            session.flush()
            session.add(
                PipelineLLMOutput(
                    run_id=seeded_run["id"],
                    step_result_id=step.id,
                    analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
                    prompt_hash="lbl123",
                    model_used="claude-haiku-4-5",
                    response_text="ESU10102 scored 72/100; correlates with CSU10102 (r=0.83).",
                    input_tokens=100,
                    output_tokens=50,
                )
            )
            session.commit()

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        resp = client.get(
            f"/pipelines/runs/{seeded_run['id']}/recommendations",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        item = resp.json()[0]
        # source-of-truth code text is preserved untouched
        assert "ESU10102" in item["response_text"]
        # labelled view carries names, no codes, numbers intact
        assert item["labeling_status"] == "ok"
        assert "Emissions Compliance Rate" in item["response_text_labeled"]
        assert "ESU10102" not in item["response_text_labeled"]
        assert "72/100" in item["response_text_labeled"]
        # legend for tooltips / code chips
        legend = {l["code"]: l["name"] for l in item["labels"]}
        assert legend["ESU10102"] == "Emissions Compliance Rate"
        assert legend["CSU10102"] == "Average Patching Time"

    def test_download_returns_text_file(self, client, mock_current_user, seeded_run):
        from app.dependencies.auth import get_current_user

        with Session(test_engine) as session:
            step = PipelineStepResult(
                run_id=seeded_run["id"],
                step_number=7,
                step_name="Claude",
                status=StepStatusEnum.COMPLETED,
            )
            session.add(step)
            session.flush()

            llm = PipelineLLMOutput(
                run_id=seeded_run["id"],
                step_result_id=step.id,
                analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
                prompt_hash="abc123",
                model_used="claude-haiku-4-5",
                response_text="This is the recommendation text.",
            )
            session.add(llm)
            session.commit()
            llm_id = llm.id

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(f"/pipelines/llm-outputs/{llm_id}/download", headers=auth_header())
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        assert "recommendation" in resp.headers["content-disposition"]

    def test_download_cross_org_returns_404(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user

        # Create output owned by org 99
        pid = _insert_def(org_id=99)
        run_id = _insert_run(pid, org_id=99, status="COMPLETED")
        with Session(test_engine) as session:
            step = PipelineStepResult(
                run_id=run_id, step_number=7, step_name="Claude",
                status=StepStatusEnum.COMPLETED,
            )
            session.add(step)
            session.flush()
            llm = PipelineLLMOutput(
                run_id=run_id,
                step_result_id=step.id,
                analysis_type=AnalysisTypeEnum.MODULE_UNIFIED,
                prompt_hash="xyz",
                model_used="claude-haiku-4-5",
                response_text="secret",
            )
            session.add(llm)
            session.commit()
            llm_id = llm.id

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(f"/pipelines/llm-outputs/{llm_id}/download", headers=auth_header())
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests - SSE stream (smoke test - full SSE tested in integration tests)
# ─────────────────────────────────────────────────────────────────────────────

class TestSSEStream:
    def test_stream_nonexistent_run_returns_404(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user, get_current_user_sse
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[get_current_user_sse] = lambda: mock_current_user

        resp = client.get(f"/pipelines/runs/{uuid.uuid4()}/stream", headers=auth_header())
        assert resp.status_code == 404

    def test_stream_cross_org_run_returns_404(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user, get_current_user_sse

        pid = _insert_def(org_id=99)
        run_id = _insert_run(pid, org_id=99, status="RUNNING")

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        client.app.dependency_overrides[get_current_user_sse] = lambda: mock_current_user

        resp = client.get(f"/pipelines/runs/{run_id}/stream", headers=auth_header())
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tests - List runs pagination
# ─────────────────────────────────────────────────────────────────────────────

class TestListRuns:
    def test_list_runs_returns_paginated_results(
        self, client, mock_current_user, seeded_pipeline
    ):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        # Seed 3 runs
        for i in range(3):
            _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED")

        resp = client.get(
            f"/pipelines/{seeded_pipeline['id']}/runs?page=1&page_size=2",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["page"] == 1

    def test_list_runs_wrong_org_returns_404(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        resp = client.get(
            f"/pipelines/{uuid.uuid4()}/runs",
            headers=auth_header(),
        )
        assert resp.status_code == 404

    def test_list_runs_does_not_leak_cross_org(self, client, mock_current_user):
        """Runs from org 99 must not appear in org 42's list."""
        from app.dependencies.auth import get_current_user

        other_pipeline_id = _insert_def(org_id=99)
        _insert_run(other_pipeline_id, org_id=99, status="COMPLETED")

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        # org 42 user tries to list runs for org 99's pipeline
        resp = client.get(
            f"/pipelines/{other_pipeline_id}/runs",
            headers=auth_header(),
        )
        assert resp.status_code == 404

    def test_list_runs_filters_by_run_org_not_just_pipeline_id(
        self, client, mock_current_user, seeded_pipeline
    ):
        """
        FIX: list_runs used to query PipelineRun by pipeline_id alone, with no
        PipelineRun.org_id filter - relying entirely on pipeline_id being a
        globally-unique UUID (so any row referencing it must already belong to
        the caller's org) rather than checking it directly, unlike every other
        run query in this router (get_run, rollback_run, ...). Directly exercise
        that gap: seed a run on the caller's OWN pipeline but stamped with
        another org's id (a data inconsistency, or a future pipeline_id scheme
        that isn't globally unique) and confirm it is excluded rather than
        served to org 42.
        """
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        _insert_run(seeded_pipeline["id"], org_id=42, status="COMPLETED")
        mismatched_run_id = _insert_run(seeded_pipeline["id"], org_id=99, status="COMPLETED")

        resp = client.get(
            f"/pipelines/{seeded_pipeline['id']}/runs",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        returned_ids = {item["id"] for item in data["items"]}
        assert mismatched_run_id not in returned_ids


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Input file check endpoint
# ─────────────────────────────────────────────────────────────────────────────

class TestInputFiles:
    def test_input_files_all_present(self, client, mock_current_user, seeded_pipeline):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        # Pipeline with no required files → all_present=True
        resp = client.get(
            f"/pipelines/{seeded_pipeline['id']}/input-files",
            headers=auth_header(),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["all_present"] is True
        assert data["missing_files"] == []

    def test_input_files_missing_shows_correctly(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user

        pipeline_id = _insert_def(org_id=42, config={
            "required_input_files": ["org/{org_id}/reference/input_metrics_data.csv"]
        })

        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router.file_exists", return_value=False):
            resp = client.get(
                f"/pipelines/{pipeline_id}/input-files",
                headers=auth_header(),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["all_present"] is False
        assert len(data["missing_files"]) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Tests - Data vs backend-provided config file split
# ─────────────────────────────────────────────────────────────────────────────

_SPLIT_CONFIG = {
    "required_input_files": [
        "org/{org_id}/reference/input_metric_values_esgrc.csv",
        "org/{org_id}/reference/esgrc_performance_json_file.json",
    ],
    "user_input_files": ["org/{org_id}/reference/input_metric_values_esgrc.csv"],
    "reference_files": ["org/{org_id}/reference/esgrc_performance_json_file.json"],
}


class TestInputFileSplit:
    def test_input_files_reports_user_and_reference_split(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router.file_exists", return_value=True):
            resp = client.get(f"/pipelines/{pid}/input-files", headers=auth_header())
        assert resp.status_code == 200
        d = resp.json()
        assert len(d["user_input_files"]) == 1 and "input_metric_values_esgrc.csv" in d["user_input_files"][0]
        assert len(d["reference_files"]) == 1 and "esgrc_performance_json_file.json" in d["reference_files"][0]
        assert d["user_files_present"] is True
        assert d["reference_files_present"] is True
        assert d["all_present"] is True

    def test_missing_config_flagged_separately_from_data(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        # Analyst's data present, backend config missing.
        def only_data_present(key):
            return "input_metric_values" in key

        with patch("pipeline.routers.pipeline_router.file_exists", side_effect=only_data_present):
            resp = client.get(f"/pipelines/{pid}/input-files", headers=auth_header())
        d = resp.json()
        assert d["user_files_present"] is True
        assert d["reference_files_present"] is False
        assert len(d["missing_reference_files"]) == 1
        assert d["all_present"] is False


class TestConfigFileUploadGate:
    """Backend-provided config files may only be uploaded by a SUPER_ADMIN; an
    analyst may upload data files but not config."""

    def test_analyst_cannot_upload_config_file(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user  # ANALYST

        with patch("pipeline.routers.pipeline_router.upload_file"):
            resp = client.post(
                f"/pipelines/{pid}/upload-input?filename=esgrc_performance_json_file.json",
                headers=auth_header(), content=b"{}",
            )
        assert resp.status_code == 403
        assert "super admin" in resp.json()["detail"].lower()

    def test_super_admin_can_upload_config_file(self, client):
        from app.dependencies.auth import get_current_user
        su = MagicMock()
        su.id = 9
        su.organisation_id = 42
        su.role = UserRole.SUPER_ADMIN
        su.module_access = []
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: su

        with patch("pipeline.routers.pipeline_router.upload_file"):
            resp = client.post(
                f"/pipelines/{pid}/upload-input?filename=esgrc_performance_json_file.json",
                headers=auth_header(), content=b"{}",
            )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "esgrc_performance_json_file.json"

    def test_analyst_can_upload_data_file(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user  # ANALYST

        with patch("pipeline.routers.pipeline_router.upload_file"):
            resp = client.post(
                f"/pipelines/{pid}/upload-input?filename=input_metric_values_esgrc.csv",
                headers=auth_header(), content=b"col\n1",
            )
        assert resp.status_code == 200
        assert resp.json()["filename"] == "input_metric_values_esgrc.csv"


class TestUploadSizeCap:
    """
    /upload-input used to do `body = await request.body()`, buffering the whole
    upload in the API process before anything checked its size. One large POST
    could exhaust worker memory. The body now streams to a temp file with a
    running total and is abandoned the moment it crosses MAX_UPLOAD_BYTES.
    """

    def test_oversized_upload_is_rejected_with_413(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        # Shrink the cap rather than actually sending 100 MB through the test client.
        with patch("pipeline.routers.pipeline_router.MAX_UPLOAD_BYTES", 1024):
            with patch("pipeline.routers.pipeline_router.upload_file") as mock_upload:
                resp = client.post(
                    f"/pipelines/{pid}/upload-input?filename=input_metric_values_esgrc.csv",
                    headers=auth_header(), content=b"x" * 4096,
                )

        assert resp.status_code == 413
        assert "limit" in resp.json()["detail"].lower()
        mock_upload.assert_not_called()

    def test_upload_at_the_limit_still_succeeds(self, client, mock_current_user):
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        payload = b"y" * 1024
        with patch("pipeline.routers.pipeline_router.MAX_UPLOAD_BYTES", 1024):
            with patch("pipeline.routers.pipeline_router.upload_file"):
                resp = client.post(
                    f"/pipelines/{pid}/upload-input?filename=input_metric_values_esgrc.csv",
                    headers=auth_header(), content=payload,
                )

        assert resp.status_code == 200
        assert resp.json()["size_bytes"] == len(payload)

    def test_empty_body_still_rejected_with_400(self, client, mock_current_user):
        """The empty-body guard must survive the move to streaming."""
        from app.dependencies.auth import get_current_user
        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user

        with patch("pipeline.routers.pipeline_router.upload_file") as mock_upload:
            resp = client.post(
                f"/pipelines/{pid}/upload-input?filename=input_metric_values_esgrc.csv",
                headers=auth_header(), content=b"",
            )

        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()
        mock_upload.assert_not_called()

    def test_rejected_upload_leaves_no_temp_file_behind(self, client, mock_current_user):
        """The 413 path must clean up the partial temp file it was writing."""
        import glob
        import tempfile
        from app.dependencies.auth import get_current_user

        pid = _insert_def(org_id=42, config=_SPLIT_CONFIG)
        client.app.dependency_overrides[get_current_user] = lambda: mock_current_user
        pattern = os.path.join(tempfile.gettempdir(), "*_input_metric_values_esgrc.csv")
        before = set(glob.glob(pattern))

        with patch("pipeline.routers.pipeline_router.MAX_UPLOAD_BYTES", 1024):
            with patch("pipeline.routers.pipeline_router.upload_file"):
                client.post(
                    f"/pipelines/{pid}/upload-input?filename=input_metric_values_esgrc.csv",
                    headers=auth_header(), content=b"z" * 8192,
                )

        assert set(glob.glob(pattern)) == before, "partial upload temp file was left behind"


class TestGdprErasurePurgesRedis:
    """
    Erasure deleted R2 objects and nulled response_text/output_file_r2_path, but
    never touched Redis. Three run-scoped keys survived it:

      pipeline:{run_id}:status        25h TTL, a status string
      copilot:{user}:{run_id}:stream  1h TTL, a LIST holding every token of
                                      Claude's answer about this org's data
      copilot:{user}:{run_id}:done    1h TTL

    The stream list is the point: it is the model's full response text, which is
    exactly what erasure claimed to remove.

    (The audit note described this as "report text in Redis for up to 25h". The
    25h is REDIS_TTL on the status key, which holds only a status string; the
    Celery result backend expires at 24h but every pipeline step task returns
    None. The real exposure was the Co-Pilot stream.)
    """

    @pytest.fixture(autouse=True)
    def _no_real_r2(self):
        """The endpoint imports delete_file and read_module_handoff_manifest
        inside the function body, so they must be patched on pipeline.tasks.r2,
        not on the router. Without this each test spends ~30s in boto3 retries
        against an endpoint that does not exist."""
        with patch("pipeline.tasks.r2.delete_file"), \
             patch("pipeline.tasks.r2.read_module_handoff_manifest", return_value=None):
            yield

    def _erase(self, client, run_id):
        return client.delete(f"/pipelines/runs/{run_id}/files", headers=auth_header())

    def test_run_scoped_redis_keys_are_deleted(self, client, mock_admin_user, seeded_run):
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        run_id = seeded_run["id"]

        fake_redis = MagicMock()
        fake_redis.scan_iter.side_effect = lambda match, count=100: iter(
            [f"copilot:7:{run_id}:stream"] if "stream" in match
            else [f"copilot:7:{run_id}:done"]
        )
        fake_redis.delete.return_value = 3

        with patch("pipeline.tasks.shared._get_redis", return_value=fake_redis):
            resp = self._erase(client, run_id)

        assert resp.status_code in (204, 207), resp.text
        fake_redis.delete.assert_called_once()
        purged = set(fake_redis.delete.call_args.args)
        assert f"pipeline:{run_id}:status" in purged
        assert f"copilot:7:{run_id}:stream" in purged
        assert f"copilot:7:{run_id}:done" in purged

    def test_scan_is_used_rather_than_keys(self, client, mock_admin_user, seeded_run):
        """KEYS blocks the whole Redis server; the purge must use SCAN."""
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user

        fake_redis = MagicMock()
        fake_redis.scan_iter.return_value = iter([])
        fake_redis.delete.return_value = 1

        with patch("pipeline.tasks.shared._get_redis", return_value=fake_redis):
            self._erase(client, seeded_run["id"])

        assert fake_redis.scan_iter.called
        fake_redis.keys.assert_not_called()

    def test_stream_key_pattern_covers_every_user_not_just_the_caller(
        self, client, mock_admin_user, seeded_run
    ):
        """Copilot keys are namespaced by user_id. Erasing only the admin's own
        key would leave other users' copies of the same answer behind."""
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user
        run_id = seeded_run["id"]

        fake_redis = MagicMock()
        fake_redis.scan_iter.return_value = iter([])
        fake_redis.delete.return_value = 1

        with patch("pipeline.tasks.shared._get_redis", return_value=fake_redis):
            self._erase(client, run_id)

        patterns = [c.kwargs.get("match") for c in fake_redis.scan_iter.call_args_list]
        assert f"copilot:*:{run_id}:stream" in patterns
        assert f"copilot:*:{run_id}:done" in patterns

    def test_redis_failure_is_reported_not_swallowed(
        self, client, mock_admin_user, seeded_run
    ):
        """An erasure that silently skipped a copy is the exact failure mode this
        endpoint exists to prevent, so a Redis outage must surface as a 207."""
        from app.dependencies.auth import get_current_user
        client.app.dependency_overrides[get_current_user] = lambda: mock_admin_user

        with patch("pipeline.tasks.shared._get_redis", side_effect=OSError("redis down")):
            resp = self._erase(client, seeded_run["id"])

        assert resp.status_code == 207
        assert any("redis" in e.lower() for e in resp.json()["errors"])
