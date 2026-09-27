"""
pipeline/tasks/shared.py
Pipeline state helpers - raw SQL writes to PostgreSQL + Redis on every transition.

WHY RAW SQL (not ORM update()):
  ORM update(PipelineRun).values(...) resolves ForeignKey("organisations.id") at
  flush time. organisations table only exists in ESGRC's SQLAlchemy metadata, not
  in pipeline's standalone Base. This causes NoReferencedTableError at runtime.
  Raw text() SQL bypasses FK resolution entirely - safe and correct.

Redis keys:
  pipeline:{run_id}:step:{n}      → JSON step state (SSE polling)
  pipeline:{run_id}:status        → run-level status string
  pipeline:{run_id}:llm:step{n}   → recommendation text (immediate UI display)
"""
import json
import uuid
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import List, Optional

import redis as redis_lib
from sqlalchemy import text

from pipeline.database import session_ctx

logger = logging.getLogger(__name__)

REDIS_TTL = 60 * 60 * 25  # 25 hours

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis_lib.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://redis:6379/0"),
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _redis_client


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def pipeline_work_dir(run_id: str, step: int) -> str:
    """
    Return the per-step scratch directory and ensure it exists.

    Base dir comes from PIPELINE_WORK_DIR, defaulting to <system-temp>/tbd2.
    On the Linux worker containers this resolves to /tmp/tbd2 (matching the
    docker-compose volume mount), so behaviour is unchanged; the value is now
    configurable and no longer a hardcoded world-writable /tmp literal
    (addresses bandit B108 / CWE-377).
    """
    base = os.environ.get(
        "PIPELINE_WORK_DIR", os.path.join(tempfile.gettempdir(), "tbd2")
    )
    work_dir = os.path.join(base, str(run_id), f"step_{step}")
    os.makedirs(work_dir, exist_ok=True)
    return work_dir


def _redis_step_key(run_id: str, step: int) -> str:
    return f"pipeline:{run_id}:step:{step}"


def _redis_run_key(run_id: str) -> str:
    return f"pipeline:{run_id}:status"


# ── Public API ────────────────────────────────────────────────────────────────

def mark_run_running(run_id: str) -> None:
    """
    Called when the first step begins. Sets run to RUNNING.

    Guarded against CANCELLED: emergency-stop can only revoke a task once it
    reaches a Celery worker, so a task already dispatched before the stop can
    still start running afterward. Without this guard, that straggler would
    silently resurrect a run the operator explicitly cancelled.
    """
    with session_ctx() as s:
        result = s.execute(
            text("""
                UPDATE pipeline_runs
                SET status = 'RUNNING', started_at = :now
                WHERE id = :run_id AND status != 'CANCELLED'
            """),
            {"run_id": run_id, "now": datetime.now(timezone.utc)},
        )
        if result.rowcount == 0:
            logger.info("run %s stayed CANCELLED - ignoring a stale start", run_id)
            return
    _get_redis().set(_redis_run_key(run_id), "RUNNING", ex=REDIS_TTL)
    logger.info("run %s → RUNNING", run_id)


def mark_step_running(run_id: str, step: int, task_id: str, step_name: str = "") -> str:
    """
    Upsert a step result row to RUNNING.
    Returns the step_result_id for use by LLMClient.
    """
    with session_ctx() as s:
        # Check if row already exists (re-run scenario)
        row = s.execute(
            text("SELECT id FROM pipeline_step_results WHERE run_id=:r AND step_number=:n"),
            {"r": run_id, "n": step},
        ).fetchone()

        if row is None:
            step_result_id = str(uuid.uuid4())
            s.execute(
                text("""
                    INSERT INTO pipeline_step_results
                        (id, run_id, step_number, step_name, status, celery_task_id, started_at)
                    VALUES
                        (:id, :run_id, :step, :name, 'RUNNING', :task_id, :now)
                """),
                {
                    "id": step_result_id, "run_id": run_id, "step": step,
                    "name": step_name, "task_id": task_id,
                    "now": datetime.now(timezone.utc),
                },
            )
        else:
            step_result_id = str(row[0])
            s.execute(
                text("""
                    UPDATE pipeline_step_results
                    SET status='RUNNING', celery_task_id=:task_id,
                        started_at=:now, completed_at=NULL, error_detail=NULL
                    WHERE id=:id
                """),
                {"task_id": task_id, "now": datetime.now(timezone.utc), "id": step_result_id},
            )

    payload = {
        "step": step, "step_name": step_name, "status": "RUNNING",
        "task_id": task_id, "started_at": _now_iso(),
        "step_result_id": step_result_id,
    }
    _get_redis().set(_redis_step_key(run_id, step), json.dumps(payload), ex=REDIS_TTL)
    logger.info("run %s step %d → RUNNING (task=%s)", run_id, step, task_id)
    return step_result_id


def mark_step_completed(
    run_id: str,
    step: int,
    input_files: List[str],
    output_files: List[str],
    duration_ms: int,
) -> None:
    now = datetime.now(timezone.utc)
    with session_ctx() as s:
        row = s.execute(
            text("SELECT id, step_name FROM pipeline_step_results WHERE run_id=:r AND step_number=:n"),
            {"r": run_id, "n": step},
        ).fetchone()

        if row:
            s.execute(
                text("""
                    UPDATE pipeline_step_results
                    SET status='COMPLETED',
                        input_files_json=:inputs,
                        output_files_json=:outputs,
                        completed_at=:now,
                        duration_ms=:dur
                    WHERE id=:id
                """),
                {
                    "inputs": json.dumps(input_files),
                    "outputs": json.dumps(output_files),
                    "now": now, "dur": duration_ms,
                    "id": str(row[0]),
                },
            )
            step_name = row[1] or ""
        else:
            step_name = ""

        # Update run progress
        # Update run progress. "total" must be the pipeline's real step
        # count (7 for ESGRC, 8 for Apex) - NOT a COUNT(*) of
        # pipeline_step_results rows, which are inserted lazily as steps
        # start and would undercount early in the run (e.g. 100% after
        # just Step 1 completes, since only 1 row exists yet).
        pipeline_type = s.execute(
            text("""
                SELECT pd.pipeline_type
                FROM pipeline_runs pr
                JOIN pipeline_definitions pd ON pd.id = pr.pipeline_id
                WHERE pr.id = :r
            """),
            {"r": run_id},
        ).scalar()
        total = 8 if pipeline_type == "APEX_ENTERPRISE" else 7

        # Single atomic UPDATE: compute the done-count inside the statement so
        # concurrent step completions (ESGRC 2/4/5, Apex 2/3/4 + the two Claude
        # branches) can't interleave a stale SELECT with a later UPDATE and
        # momentarily under-report progress. Each write reflects the live count.
        # (done can never exceed total - one row per step - so no cap needed,
        # which also keeps the SQL portable across SQLite tests and Postgres.)
        s.execute(
            text("""
                UPDATE pipeline_runs
                SET progress_pct = (
                    SELECT COUNT(*) FROM pipeline_step_results
                    WHERE run_id = :r AND status IN ('COMPLETED','SKIPPED','FAILED')
                ) * 100 / :total
                WHERE id = :r
            """),
            {"r": run_id, "total": total},
        )

        # Self-heal a stale FAILED run status after a step-level repair.
        #
        # mark_step_failed() unconditionally sets pipeline_runs.status='FAILED'
        # the moment any one step fails - there is no symmetric check here to
        # flip it back. A normal full-pipeline run doesn't need one: a
        # dedicated finalize task (e.g. apex_finalize) runs once the whole
        # chord succeeds and calls mark_run_completed() itself. But the
        # /steps/{n}/rerun endpoint calls this function directly, outside
        # that chord, so a run repaired step-by-step after a failure was
        # confirmed (2026-09-11, live) to stay stuck at status='FAILED'
        # forever even after every step genuinely completed.
        #
        # Guard is deliberately COMPLETED-only, not SKIPPED-tolerant: a run
        # whose failure left downstream steps SKIPPED (mark_step_failed's
        # skip-the-rest behavior) must NOT be waved through as complete just
        # because nothing is FAILED anymore - those SKIPPED steps never
        # actually ran and still need their own reruns. mark_run_completed()
        # is idempotent and CANCELLED-guarded, so calling it here alongside
        # the normal finalize-task path (which will also call it moments
        # later for a real full run) is harmless.
        all_completed = s.execute(
            text("""
                SELECT COUNT(*) = :total FROM pipeline_step_results
                WHERE run_id = :r AND status = 'COMPLETED'
            """),
            {"r": run_id, "total": total},
        ).scalar()

    payload = {
        "step": step, "step_name": step_name, "status": "COMPLETED",
        "outputs": output_files, "duration_ms": duration_ms,
        "completed_at": now.isoformat(),
    }
    _get_redis().set(_redis_step_key(run_id, step), json.dumps(payload), ex=REDIS_TTL)
    logger.info("run %s step %d → COMPLETED (%dms)", run_id, step, duration_ms)

    if all_completed:
        mark_run_completed(run_id)


def mark_step_failed(run_id: str, step: int, error: str) -> None:
    """
    Marks step FAILED, then SKIPs all subsequent PENDING steps,
    then marks the run FAILED.
    """
    now = datetime.now(timezone.utc)
    with session_ctx() as s:
        row = s.execute(
            text("SELECT id, step_name FROM pipeline_step_results WHERE run_id=:r AND step_number=:n"),
            {"r": run_id, "n": step},
        ).fetchone()

        if row:
            s.execute(
                text("""
                    UPDATE pipeline_step_results
                    SET status='FAILED', completed_at=:now, error_detail=:err
                    WHERE id=:id
                """),
                {"now": now, "err": error[:5000], "id": str(row[0])},
            )
            step_name = row[1] or ""

            # SKIP all subsequent PENDING steps
            s.execute(
                text("""
                    UPDATE pipeline_step_results
                    SET status='SKIPPED'
                    WHERE run_id=:r AND step_number > :n AND status='PENDING'
                """),
                {"r": run_id, "n": step},
            )
        else:
            step_name = f"step_{step}"

        # Fail the run
        s.execute(
            text("""
                UPDATE pipeline_runs
                SET status='FAILED', completed_at=:now,
                    error_message=:err
                WHERE id=:r
            """),
            {"now": now, "err": f"Step {step} failed: {error[:2000]}", "r": run_id},
        )

    payload = {"step": step, "step_name": step_name, "status": "FAILED",
               "error": error[:500], "failed_at": now.isoformat()}
    _get_redis().set(_redis_step_key(run_id, step), json.dumps(payload), ex=REDIS_TTL)
    _get_redis().set(_redis_run_key(run_id), "FAILED", ex=REDIS_TTL)
    logger.error("run %s step %d → FAILED: %s", run_id, step, error[:200])


def mark_step_skipped(run_id: str, step: int, step_name: str = "") -> None:
    with session_ctx() as s:
        s.execute(
            text("""
                UPDATE pipeline_step_results SET status='SKIPPED'
                WHERE run_id=:r AND step_number=:n
            """),
            {"r": run_id, "n": step},
        )
    payload = {"step": step, "step_name": step_name, "status": "SKIPPED"}
    _get_redis().set(_redis_step_key(run_id, step), json.dumps(payload), ex=REDIS_TTL)


def mark_run_completed(run_id: str) -> None:
    """
    Sets run COMPLETED + is_current=True, flips other runs to is_current=False.

    Guarded against CANCELLED, same reasoning as mark_run_running: a straggler
    step chain that started before an emergency-stop revoked it must not
    un-cancel the run once it finishes - and must not promote it to is_current
    (which would also wrongly demote the run actually left is_current).
    """
    now = datetime.now(timezone.utc)
    with session_ctx() as s:
        # Get pipeline_id first
        row = s.execute(
            text("SELECT pipeline_id FROM pipeline_runs WHERE id=:r"),
            {"r": run_id},
        ).fetchone()

        result = s.execute(
            text("""
                UPDATE pipeline_runs
                SET status='COMPLETED', completed_at=:now,
                    progress_pct=100, is_current=TRUE
                WHERE id=:r AND status != 'CANCELLED'
            """),
            {"now": now, "r": run_id},
        )
        if result.rowcount == 0:
            logger.info("run %s stayed CANCELLED - ignoring a stale completion", run_id)
            return

        if row:
            # Flip all other runs for same pipeline to is_current=FALSE
            s.execute(
                text("""
                    UPDATE pipeline_runs
                    SET is_current=FALSE
                    WHERE pipeline_id=:pid AND id != :r AND is_current=TRUE
                """),
                {"pid": str(row[0]), "r": run_id},
            )

    _get_redis().set(_redis_run_key(run_id), "COMPLETED", ex=REDIS_TTL)
    logger.info("run %s → COMPLETED", run_id)


def mark_run_failed(run_id: str, error: str) -> None:
    now = datetime.now(timezone.utc)
    with session_ctx() as s:
        s.execute(
            text("""
                UPDATE pipeline_runs
                SET status='FAILED', completed_at=:now, error_message=:err
                WHERE id=:r
            """),
            {"now": now, "err": error[:2000], "r": run_id},
        )
    _get_redis().set(_redis_run_key(run_id), "FAILED", ex=REDIS_TTL)
    logger.error("run %s → FAILED: %s", run_id, error[:200])


def write_llm_to_redis(run_id: str, step: int, text_content: str) -> None:
    """
    Write recommendation text to Redis immediately for UI display.
    Called by LLMClient before the DB write completes.
    """
    key = f"pipeline:{run_id}:llm:step{step}"
    _get_redis().set(key, text_content, ex=REDIS_TTL)


def get_step_state(run_id: str, step: int) -> Optional[dict]:
    raw = _get_redis().get(_redis_step_key(run_id, step))
    return json.loads(raw) if raw else None


def get_run_status(run_id: str) -> Optional[str]:
    return _get_redis().get(_redis_run_key(run_id))
