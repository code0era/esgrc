"""Tests for the cross-process locks that de-duplicate worker startup work.

The bug these exist for: `uvicorn --workers 2` runs the FastAPI lifespan once per
worker process, so both workers started an APScheduler over the same jobstore and
both fired the daily batch. APScheduler's max_instances=1 does not help - it is
scoped to a single scheduler instance.

Two open() calls produce two independent open file descriptions, so these locks
genuinely conflict even within one process, which is what makes the duplicate
case testable here without spawning workers.
"""
import threading
import time

import pytest

from app.services import single_instance


@pytest.fixture
def lock_path(tmp_path):
    return tmp_path / "test.lock"


def test_second_acquire_is_refused_while_held(lock_path):
    first = single_instance.acquire_forever(lock_path)
    assert first is not None, "first caller should win the lock"
    try:
        assert single_instance.acquire_forever(lock_path) is None, (
            "a second worker acquired the same lock; both would schedule jobs"
        )
    finally:
        first.close()


def test_lock_is_reusable_after_release(lock_path):
    """A restarting worker must be able to take over the schedule."""
    first = single_instance.acquire_forever(lock_path)
    assert first is not None
    first.close()

    second = single_instance.acquire_forever(lock_path)
    assert second is not None, "lock was not released when the handle closed"
    second.close()


def test_exclusive_releases_on_exit(lock_path):
    with single_instance.exclusive(lock_path):
        pass
    handle = single_instance.acquire_forever(lock_path)
    assert handle is not None, "exclusive() did not release its lock"
    handle.close()


def test_exclusive_releases_when_body_raises(lock_path):
    """A failed migration must not wedge every other worker forever."""
    with pytest.raises(ValueError):
        with single_instance.exclusive(lock_path):
            raise ValueError("migration blew up")

    handle = single_instance.acquire_forever(lock_path)
    assert handle is not None, "lock survived an exception in the body"
    handle.close()


def test_unwritable_lock_path_fails_open(tmp_path):
    """Degrade to the old duplicate-work behaviour, never to 'no jobs at all'.

    A lock file that cannot be created is an environment problem. Silently
    disabling the scheduler would be a worse outcome than running it twice.
    """
    impossible = tmp_path / "nope.txt" / "child" / "test.lock"
    (tmp_path / "nope.txt").write_text("I am a file, not a directory")

    handle = single_instance.acquire_forever(impossible)
    assert handle is not None
    handle.close()


def test_default_lock_path_honours_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("ESGRC_LOCK_DIR", str(tmp_path))
    assert single_instance.default_lock_path("x.lock").parent == tmp_path


def test_scheduler_skips_when_another_worker_holds_the_lock(tmp_path, monkeypatch):
    """The whole point: worker two must not register jobs."""
    monkeypatch.setenv("ESGRC_LOCK_DIR", str(tmp_path))
    from app.agent import scheduler as sched

    held = single_instance.acquire_forever(
        single_instance.default_lock_path(sched.SCHEDULER_LOCK_NAME)
    )
    assert held is not None
    monkeypatch.setattr(sched, "_scheduler", None)
    monkeypatch.setattr(sched, "_lock_handle", None)
    try:
        sched.start_scheduler()
        assert sched._scheduler is None, (
            "second worker built a scheduler despite the lock being held"
        )
    finally:
        held.close()


def test_manual_trigger_does_not_build_scheduler_when_lock_held_elsewhere(tmp_path, monkeypatch):
    """POST /agent/run (trigger_immediate_run) on a worker that lost the
    scheduler-lock race must not build a second live BackgroundScheduler -
    that duplicates polling of the shared SQLAlchemyJobStore and resurrects
    the exact bug this lock exists to prevent (see module docstring above and
    the guard in scheduler.start_scheduler()). It must still run the batch,
    just directly on a background thread instead of via a second scheduler.
    """
    monkeypatch.setenv("ESGRC_LOCK_DIR", str(tmp_path))
    from app.agent import scheduler as sched

    held = single_instance.acquire_forever(
        single_instance.default_lock_path(sched.SCHEDULER_LOCK_NAME)
    )
    assert held is not None
    monkeypatch.setattr(sched, "_scheduler", None)
    monkeypatch.setattr(sched, "_lock_handle", None)
    monkeypatch.setattr(sched.settings, "AGENT_ENABLED", True)

    ran = threading.Event()
    monkeypatch.setattr(sched, "_run_full_batch_job", ran.set)

    try:
        sched.trigger_immediate_run()
        assert ran.wait(timeout=2), "manual run never executed on the fallback thread"
        assert sched._scheduler is None, (
            "trigger_immediate_run() built a second scheduler despite another "
            "worker holding the lock"
        )
    finally:
        held.close()


def test_manual_llm_trigger_does_not_build_scheduler_when_lock_held_elsewhere(tmp_path, monkeypatch):
    """Same guard as above for POST /agent/llm-run (trigger_immediate_llm_run)."""
    monkeypatch.setenv("ESGRC_LOCK_DIR", str(tmp_path))
    from app.agent import scheduler as sched

    held = single_instance.acquire_forever(
        single_instance.default_lock_path(sched.SCHEDULER_LOCK_NAME)
    )
    assert held is not None
    monkeypatch.setattr(sched, "_scheduler", None)
    monkeypatch.setattr(sched, "_lock_handle", None)
    monkeypatch.setattr(sched.settings, "AGENT_ENABLED", True)

    ran = threading.Event()
    monkeypatch.setattr(sched, "_run_llm_batch_job", ran.set)

    try:
        sched.trigger_immediate_llm_run()
        assert ran.wait(timeout=2), "manual LLM run never executed on the fallback thread"
        assert sched._scheduler is None, (
            "trigger_immediate_llm_run() built a second scheduler despite "
            "another worker holding the lock"
        )
    finally:
        held.close()


# Module-level (not a closure or bound method) so SQLAlchemyJobStore can
# pickle it - the real trigger_immediate_run() path stores the job via
# add_job(), which requires a picklable callable. A bound Event.set method
# fails with "cannot pickle '_thread.lock' object".
_owned_path_ran = threading.Event()


def _mark_owned_path_ran() -> None:
    _owned_path_ran.set()


def test_manual_trigger_uses_scheduler_when_this_worker_owns_the_lock(tmp_path, monkeypatch):
    """The complementary case: when this worker DOES own the schedule (the
    common case, e.g. a single-worker deployment), the manual trigger should
    still go through the real scheduler/jobstore as before - the new guard
    must only redirect the *other* workers, not the owner.
    """
    monkeypatch.setenv("ESGRC_LOCK_DIR", str(tmp_path))
    from app.agent import scheduler as sched

    owned = single_instance.acquire_forever(
        single_instance.default_lock_path(sched.SCHEDULER_LOCK_NAME)
    )
    assert owned is not None
    monkeypatch.setattr(sched, "_scheduler", None)
    monkeypatch.setattr(sched, "_lock_handle", owned)
    monkeypatch.setattr(sched.settings, "AGENT_ENABLED", True)

    _owned_path_ran.clear()
    monkeypatch.setattr(sched, "_run_full_batch_job", _mark_owned_path_ran)

    try:
        sched.trigger_immediate_run()
        assert sched._scheduler is not None, "lock owner should use the real scheduler"
        assert _owned_path_ran.wait(timeout=2), (
            "manual run job never executed via the owned scheduler"
        )
        # The event above only confirms the job FUNCTION ran - APScheduler's
        # own main-loop thread still has to compute the (now-None) next run
        # time and call remove_job() afterward, asynchronously to the
        # function call. If stop_scheduler() (-> scheduler.shutdown()) lands
        # while that's still in flight, the two race and remove_job() can
        # raise an unhandled JobLookupError in the scheduler thread (see the
        # matching fix + comment on test_agent.py::test_trigger_run_accepted).
        # Wait for the job to actually leave the jobstore before shutting
        # down, not just for its body to have run.
        deadline = time.monotonic() + 2
        while sched.get_scheduler().get_job("esgrc_manual_run") is not None:
            if time.monotonic() > deadline:
                break
            time.sleep(0.02)
    finally:
        sched.stop_scheduler()
