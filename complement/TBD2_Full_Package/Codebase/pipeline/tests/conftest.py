"""
pipeline/test/conftest.py
Shared pytest fixtures for all pipeline tests.

Provides:
  - In-memory SQLite engine (pipeline tables only)
  - FakeRedis implementation
  - Common mock factories for R2, ScriptRunner, LLMClient
  - autouse clean_tables fixture
"""
"""
pipeline/test/conftest.py
Shared pytest fixtures for all pipeline tests.
...
"""
import sys
from pathlib import Path

# ── Make TBD2 root and ESGRC importable without manual $env:PYTHONPATH ───────
# conftest.py is at <ROOT>/pipeline/test/conftest.py
_ROOT = Path(__file__).resolve().parents[2]
_ESGRC = _ROOT / "ESGRC"
_TEST_DB_DIR = _ROOT / ".local" / "test_databases"
_TEST_DB_DIR.mkdir(parents=True, exist_ok=True)
for _p in (str(_ROOT), str(_ESGRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import json
import os
import shutil
import uuid
...
import json
import os
import shutil
import uuid
from typing import Generator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# ── Set env vars before any app imports ──────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "sqlite:///./.local/test_databases/test_pipeline_shared.db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key")
os.environ.setdefault("CLOUDFLARE_R2_BUCKET", "test-bucket")
os.environ.setdefault("CLOUDFLARE_R2_ENDPOINT", "https://test.r2.example.com")
os.environ.setdefault("CLOUDFLARE_R2_ACCESS_KEY", "test-key")
os.environ.setdefault("CLOUDFLARE_R2_SECRET_KEY", "test-secret")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")  # don't throttle / require Redis in tests
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["DEMO_MODE"] = "false"

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

# ── Shared test engine ────────────────────────────────────────────────────────
TEST_ENGINE = create_engine(
    "sqlite:///./.local/test_databases/test_pipeline_shared.db",
    connect_args={"check_same_thread": False},
)
PipelineBase.metadata.create_all(bind=TEST_ENGINE)

# Patch pipeline_db_module so shared.py uses the test engine
pipeline_db_module.pipeline_engine = TEST_ENGINE


# ── FakeRedis ─────────────────────────────────────────────────────────────────

class FakeRedis:
    """Thread-safe in-memory Redis substitute."""

    def __init__(self):
        self._store: dict = {}

    def set(self, key, value, ex=None):
        self._store[key] = value

    def get(self, key):
        return self._store.get(key)

    def delete(self, key):
        self._store.pop(key, None)

    def keys(self, pattern="*"):
        return list(self._store.keys())

    def ping(self):
        return True

    def clear(self):
        self._store.clear()

def _insert_pipeline_and_run(engine, org_id=1, ptype="ESGRC_MODULE", status="PENDING", **run_kw):
    import json as _json
    from sqlalchemy import text
    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO pipeline_definitions (id, org_id, name, pipeline_type, is_active, config_json, created_at, updated_at)
            VALUES (:id, :org_id, :name, :ptype, 1, :config, datetime('now'), datetime('now'))
        """), {"id": pid, "org_id": org_id, "name": "Test Pipeline", "ptype": ptype,
               "config": _json.dumps(run_kw.pop("config_json", {}))})
        conn.execute(text("""
            INSERT INTO pipeline_runs (id, pipeline_id, org_id, status, is_current, progress_pct, triggered_by, celery_chord_id)
            VALUES (:id, :pid, :org_id, :status, :is_current, :pct, :tb, :cid)
        """), {"id": rid, "pid": pid, "org_id": org_id, "status": status,
               "is_current": int(run_kw.get("is_current", False)),
               "pct": run_kw.get("progress_pct", 0),
               "tb": run_kw.get("triggered_by"), "cid": run_kw.get("celery_chord_id")})
    return pid, rid
# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def db_engine():
    """Session-scoped SQLAlchemy engine."""
    return TEST_ENGINE


@pytest.fixture
def db_session(db_engine) -> Generator[Session, None, None]:
    """Function-scoped DB session - rolls back after each test."""
    with Session(db_engine) as session:
        yield session
        session.rollback()


@pytest.fixture(autouse=True)
def clean_tables(db_engine):
    """Truncate all pipeline tables before each test."""
    with Session(db_engine) as session:
        session.query(PipelineLLMOutput).delete()
        session.query(PipelineStepResult).delete()
        session.query(PipelineRun).delete()
        session.query(PipelineDefinition).delete()
        session.query(PipelinePrompt).delete()
        session.commit()
    yield


@pytest.fixture
def fake_redis() -> FakeRedis:
    """Fresh FakeRedis instance per test."""
    return FakeRedis()


@pytest.fixture
def seeded_org_pipeline(db_engine) -> dict:
    """Insert a pipeline definition for org 1 and return ids."""
    import json as _json
    from sqlalchemy import text
    pipeline_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    with db_engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO pipeline_definitions
                    (id, org_id, name, pipeline_type, is_active, config_json,
                     created_at, updated_at)
                VALUES (:id, :org_id, :name, :ptype, :active, :config, :now, :now)
            """),
            {
                "id": pipeline_id, "org_id": 1, "name": "Test ESGRC Pipeline",
                "ptype": PipelineTypeEnum.ESGRC_MODULE.value, "active": True,
                "config": _json.dumps({"required_input_files": [], "steps": 7}),
                "now": "2026-01-01 00:00:00",
            },
        )
        conn.execute(
            text("""
                INSERT INTO pipeline_runs
                    (id, pipeline_id, org_id, status, is_current, progress_pct)
                VALUES (:id, :pipeline_id, :org_id, :status, 0, 0)
            """),
            {"id": run_id, "pipeline_id": pipeline_id, "org_id": 1,
             "status": RunStatusEnum.PENDING.value},
        )
    return {
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "org_id": 1,
    }


@pytest.fixture
def apex_pipeline_and_run(db_engine) -> dict:
    """Insert an Apex pipeline definition for org 1."""
    pipeline_id, run_id = _insert_pipeline_and_run(
        db_engine, org_id=1, ptype=PipelineTypeEnum.APEX_ENTERPRISE.value,
        status=RunStatusEnum.PENDING.value,
        config_json={"required_input_files": [], "steps": 8},
    )
    return {
        "pipeline_id": pipeline_id,
        "run_id": run_id,
        "org_id": 1,
    }


@pytest.fixture
def r2_mock(tmp_path):
    """
    R2 mock that reads/writes to a temp directory.
    Returns a dict with patched functions and the uploaded keys store.
    """
    store = {}

    def fake_upload(local_path, r2_key):
        if not os.path.exists(str(local_path)):
            from pipeline.tasks.r2 import R2Error
            raise R2Error(f"upload_file: local file not found: {local_path}")
        dest = str(tmp_path / r2_key.replace("/", "_"))
        shutil.copy2(str(local_path), dest)
        store[r2_key] = dest
        return r2_key

    def fake_download(r2_key, local_path):
        os.makedirs(os.path.dirname(os.path.abspath(local_path)), exist_ok=True)
        src = store.get(r2_key)
        if src and os.path.exists(src):
            shutil.copy2(src, local_path)
        else:
            # Create dummy file for inputs not yet "uploaded"
            with open(local_path, "w") as f:
                f.write(f"dummy input for {r2_key}\n")

    def fake_list(prefix):
        return [k for k in store if k.startswith(prefix)]

    def fake_exists(r2_key):
        return r2_key in store

    def fake_delete(r2_key):
        store.pop(r2_key, None)

    return {
        "upload": fake_upload,
        "download": fake_download,
        "list": fake_list,
        "exists": fake_exists,
        "delete": fake_delete,
        "store": store,
    }


@pytest.fixture
def script_runner_mock():
    """
    ScriptRunner mock that creates realistic fixture output files.
    Tracks which scripts were called and how many times.
    """
    call_log = []

    def make_runner(output_files_per_script=None):
        output_files_per_script = output_files_per_script or {}
        mock = MagicMock()

        def fake_run(script_name, input_paths, output_dir):
            call_log.append({"script": script_name, "output_dir": output_dir})
            os.makedirs(output_dir, exist_ok=True)

            default_outputs = {
                "data_prep_1":          ["prepared_metrics_data.csv", "low_performing_summary.csv"],
                "data_prep_2":          ["all_module_values.csv", "data_for_risk_assessment_esgrc.csv"],
                "correlation_CHAID_FT": ["correlation_chaid_ft_report.txt"],
                "SPC_RPN":              ["spc_rpn_report.txt"],
                "regression_esgrc":     ["regression_esgrc_report.txt"],
                "all_module_low_perf":  ["all_module_low_perf_report.txt", "all_module_values_L0.csv"],
                "correlation_CHAID_L0": ["correlation_chaid_L0_report.txt"],
                "SPC_RPN_L0":           ["spc_summary_L0.txt"],
                "regression_L0":        ["regression_L0_report.txt"],
            }
            files = output_files_per_script.get(script_name) or default_outputs.get(script_name, ["output.txt"])
            outputs = {}
            for fname in files:
                path = os.path.join(output_dir, fname)
                with open(path, "w") as f:
                    content = f"=== {script_name} output ===\nFixture content.\n"
                    f.write(content)
                outputs[fname] = path
            return outputs

        mock.run.side_effect = fake_run
        mock.call_log = call_log
        return mock

    return make_runner


@pytest.fixture
def llm_client_mock():
    """Mock LLMClient.analyze() returning fixture recommendation text."""
    def make_mock(response_text="Risk assessment completed.", model="claude-haiku-4-5"):
        mock = MagicMock()
        result = MagicMock()
        result.response_text = response_text
        result.input_tokens = 1000
        result.output_tokens = 300
        result.model_used = model
        result.prompt_hash = "test_hash_abc123"
        result.r2_path = "org/1/runs/test-run/step_7/recommendation.txt"
        mock.analyze.return_value = result
        return mock
    return make_mock
