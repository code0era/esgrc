"""
pipeline/tests/test_step_lifecycle.py
Regression coverage for pipeline.tasks.shared's run/step bookkeeping helpers -
specifically the "stale FAILED run after a step-level repair" bug.

Bug (found live, 2026-09-11): mark_step_failed() unconditionally sets
pipeline_runs.status='FAILED' the moment any one step fails. There was no
symmetric check anywhere in mark_step_completed() to flip a run back once
every step is genuinely done. A normal full-pipeline run never hit this,
because a dedicated finalize task (apex_finalize / each module chain's own
step7_claude) calls mark_run_completed() itself once the whole chord
succeeds. But POST /pipelines/runs/{id}/steps/{n}/rerun calls
run_claude_step -> mark_step_completed directly, outside that chord - so a
run repaired step-by-step after a real Apex failure (AttributeError:
'ThinkingBlock' object has no attribute 'text', see pipeline/llm/client.py)
stayed stuck at status='FAILED' forever even after both failed steps were
individually rerun and completed.
"""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import pipeline.database as pdb
from pipeline.tasks.shared import mark_step_completed, mark_step_failed


@pytest.fixture
def sqlite_session(db_engine, monkeypatch):
    """Point pipeline.database's session factory at the shared SQLite test engine."""
    monkeypatch.setattr(pdb, "_engine", db_engine)
    monkeypatch.setattr(
        pdb, "_SessionFactory", sessionmaker(bind=db_engine, expire_on_commit=False)
    )
    return db_engine


class _FakeRedis:
    def __init__(self):
        self._store = {}

    def set(self, key, value, ex=None):
        self._store[key] = value

    def get(self, key):
        return self._store.get(key)


def _seed_run(engine, total_steps: int, ptype: str = "APEX_ENTERPRISE") -> str:
    """Create a pipeline_definition + pipeline_run + one PENDING step row per step."""
    pid, rid = str(uuid.uuid4()), str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO pipeline_definitions
                    (id, org_id, name, pipeline_type, is_active, config_json, created_at, updated_at)
                VALUES (:id, 1, 'Test', :ptype, 1, '{}', datetime('now'), datetime('now'))
            """),
            {"id": pid, "ptype": ptype},
        )
        conn.execute(
            text("""
                INSERT INTO pipeline_runs
                    (id, pipeline_id, org_id, status, is_current, progress_pct)
                VALUES (:id, :pid, 1, 'RUNNING', 0, 0)
            """),
            {"id": rid, "pid": pid},
        )
        for n in range(1, total_steps + 1):
            conn.execute(
                text("""
                    INSERT INTO pipeline_step_results (id, run_id, step_number, step_name, status)
                    VALUES (:sid, :rid, :n, :name, 'PENDING')
                """),
                {"sid": str(uuid.uuid4()), "rid": rid, "n": n, "name": f"step_{n}"},
            )
    return rid


def _run_status(engine, run_id: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT status FROM pipeline_runs WHERE id=:r"), {"r": run_id}
        ).scalar_one()


class TestStepLevelRepairFlipsRunStatus:

    def test_repairing_the_only_failed_step_flips_run_back_to_completed(self, sqlite_session):
        """The exact live scenario: Apex steps 6 and 8 both FAILED, nothing
        SKIPPED downstream (they're terminal Claude branches) - rerunning
        both must bring the run back to COMPLETED, not leave it stuck FAILED.
        """
        engine = sqlite_session
        run_id = _seed_run(engine, total_steps=8)

        with patch("pipeline.tasks.shared._get_redis", return_value=_FakeRedis()):
            # Steps 1-5, 7 complete normally.
            for n in [1, 2, 3, 4, 5, 7]:
                mark_step_completed(run_id, n, [], [], 100)

            # Steps 6 and 8 fail (the ThinkingBlock bug, pre-fix).
            mark_step_failed(run_id, 6, "AttributeError: 'ThinkingBlock' object has no attribute 'text'")
            assert _run_status(engine, run_id) == "FAILED"
            mark_step_failed(run_id, 8, "AttributeError: 'ThinkingBlock' object has no attribute 'text'")
            assert _run_status(engine, run_id) == "FAILED"

            # Rerun (repair) step 6 - run must NOT flip yet, step 8 is still FAILED.
            mark_step_completed(run_id, 6, [], [], 72_842)
            assert _run_status(engine, run_id) == "FAILED", (
                "run flipped to COMPLETED with step 8 still FAILED"
            )

            # Rerun (repair) step 8 - now every step is genuinely COMPLETED.
            mark_step_completed(run_id, 8, [], [], 515)
            assert _run_status(engine, run_id) == "COMPLETED", (
                "run stayed FAILED after every step was individually repaired and completed"
            )

    def test_skipped_steps_block_the_self_heal(self, sqlite_session):
        """A failure that SKIPPED downstream steps must not be waved through
        as COMPLETED just because the originally-failed step was repaired -
        the SKIPPED steps never actually ran and still need their own reruns.
        """
        engine = sqlite_session
        run_id = _seed_run(engine, total_steps=7, ptype="SHARED_MODULE")

        with patch("pipeline.tasks.shared._get_redis", return_value=_FakeRedis()):
            mark_step_completed(run_id, 1, [], [], 100)
            mark_step_completed(run_id, 2, [], [], 100)
            # Step 3 fails - mark_step_failed SKIPs steps 4-7 and fails the run.
            mark_step_failed(run_id, 3, "Simulated step 3 failure")
            assert _run_status(engine, run_id) == "FAILED"

            # Repair only step 3. Steps 4-7 are still SKIPPED, not COMPLETED.
            mark_step_completed(run_id, 3, [], [], 100)
            assert _run_status(engine, run_id) == "FAILED", (
                "run flipped to COMPLETED while steps 4-7 are still SKIPPED, "
                "never actually re-run"
            )

    def test_normal_full_run_still_completes_via_the_self_heal_path(self, sqlite_session):
        """Sanity check: a run with no failures at all still reaches
        COMPLETED once its last step completes (the self-heal check must not
        require a prior failure to fire).

        Module pipelines (anything but APEX_ENTERPRISE) are hardcoded to 7
        steps in mark_step_completed's own "total" lookup - matching that
        here, not asserting on it.
        """
        engine = sqlite_session
        run_id = _seed_run(engine, total_steps=7, ptype="SHARED_MODULE")

        with patch("pipeline.tasks.shared._get_redis", return_value=_FakeRedis()):
            for n in range(1, 7):
                mark_step_completed(run_id, n, [], [], 10)
            assert _run_status(engine, run_id) == "RUNNING"
            mark_step_completed(run_id, 7, [], [], 10)
            assert _run_status(engine, run_id) == "COMPLETED"
