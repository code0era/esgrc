"""
APScheduler setup for the ESGRC agent.

Uses APScheduler 3.x with SQLAlchemyJobStore so scheduled jobs persist
across restarts - the job schedule is stored in the same database as the
business data. No Redis, no separate process, no extra infrastructure.

Scheduler lifecycle:
  - Created and started inside FastAPI lifespan (startup)
  - Stopped cleanly on shutdown
  - Jobs are registered once; APScheduler skips re-adding if the job
    already exists in the store (idempotent on restart)

Misfire grace:
  - If the server is down at the scheduled time, APScheduler will run the
    job as soon as the server comes back up, provided it missed by less
    than MISFIRE_GRACE_SECONDS (default: 1 hour).
  - Set misfire_grace_time=None to skip misfires entirely.
"""

import logging
import threading

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pytz import timezone as pytz_timezone

from app.config import settings
from app.services import single_instance

logger = logging.getLogger(__name__)

# Grace period: if the job was missed by less than this, run it immediately
MISFIRE_GRACE_SECONDS = 3600  # 1 hour

# Global scheduler instance - created once, shared across the process
_scheduler: BackgroundScheduler | None = None

# Held for the process lifetime by whichever worker owns the schedule.
# Closing it releases the lock, so the reference must outlive start_scheduler().
SCHEDULER_LOCK_NAME = "esgrc-agent-scheduler.lock"
_lock_handle = None


def get_scheduler() -> BackgroundScheduler:
    """Return the global scheduler instance (create if not yet created)."""
    global _scheduler
    if _scheduler is None:
        jobstores = {
            "default": SQLAlchemyJobStore(url=settings.DATABASE_URL),
        }
        executors = {
            # Thread pool: batch tasks are I/O bound (DB reads/writes), not CPU bound
            "default": ThreadPoolExecutor(max_workers=2),
        }
        job_defaults = {
            "coalesce": True,          # if multiple runs were missed, fire only once
            "max_instances": 1,        # never run the same job twice simultaneously
            "misfire_grace_time": MISFIRE_GRACE_SECONDS,
        }
        _scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=pytz_timezone(settings.AGENT_TIMEZONE),
        )
        logger.info(
            "Scheduler created - timezone=%s store=SQLAlchemy db=%s",
            settings.AGENT_TIMEZONE,
            settings.DATABASE_URL.split("@")[-1] if "@" in settings.DATABASE_URL
            else settings.DATABASE_URL,
        )
    return _scheduler


def _run_batch_job() -> None:
    """
    Daily batch: score unscored ESG metrics + escalate critical risks.
    Compliance flagging is handled by the separate 15-day job below.
    """
    from app.agent.runner import run_batch_esg_risk
    try:
        run_batch_esg_risk()
    except Exception as exc:
        logger.exception("Daily ESG/risk batch failed: %s", exc)


def _run_full_batch_job() -> None:
    """
    Full batch: score ESG metrics + escalate risks + flag overdue compliance.
    Used by the manual trigger (POST /agent/run) so an admin clicking "run now"
    gets a complete pass - the scheduled daily job deliberately runs only the
    ESG/Risk half, with compliance on its own 15-day cadence.
    """
    from app.agent.runner import run_batch
    try:
        run_batch()
    except Exception as exc:
        logger.exception("Manual full batch failed: %s", exc)


def _run_llm_batch_job() -> None:
    """
    LLM-powered batch (manual trigger via POST /agent/llm-run).
    Module-level so APScheduler's SQLAlchemyJobStore can serialize it - a local
    closure cannot be stored and raises "This Job cannot be serialized".
    """
    from app.agent.runner import run_llm_batch
    try:
        run_llm_batch()
    except Exception as exc:
        logger.exception("Manual LLM agent batch failed: %s", exc)


def _run_compliance_job() -> None:
    """
    Compliance batch (every COMPLIANCE_CHECK_DAYS days):
    flags overdue requirements for re-review.
    Runs less frequently than the daily job - compliance reviews have a
    longer natural cadence (Praveen's recommendation: 15 days).
    """
    from app.agent.runner import run_batch_compliance
    try:
        run_batch_compliance()
    except Exception as exc:
        logger.exception("Compliance batch failed: %s", exc)


def start_scheduler() -> None:
    """
    Start the scheduler and register the daily batch job.
    Safe to call multiple times - APScheduler skips job registration
    if a job with the same ID already exists in the job store.
    """
    if not settings.AGENT_ENABLED:
        logger.info("Agent scheduler is disabled (AGENT_ENABLED=false). Skipping.")
        return

    # The API runs with `uvicorn --workers 2`, and every worker executes the
    # lifespan. Without this guard each worker built its own BackgroundScheduler
    # over the same jobstore and both fired the daily and compliance batches:
    # max_instances=1 bounds concurrency inside one scheduler, not across
    # processes. First worker to claim the lock owns the schedule; the others
    # serve HTTP only.
    #
    # Host-scoped: this does not coordinate multiple API containers. Scaling the
    # api service past one replica needs the scheduler split into its own
    # single-replica service. See app/services/single_instance.py.
    global _lock_handle
    _lock_handle = single_instance.acquire_forever(
        single_instance.default_lock_path(SCHEDULER_LOCK_NAME)
    )
    if _lock_handle is None:
        logger.info(
            "Another process owns the agent scheduler; this worker will not "
            "schedule jobs."
        )
        return

    scheduler = get_scheduler()

    # ── Job 1: Daily ESG + Risk batch ─────────────────────────────────────────
    daily_trigger = CronTrigger(
        hour=settings.AGENT_HOUR,
        minute=settings.AGENT_MINUTE,
        timezone=pytz_timezone(settings.AGENT_TIMEZONE),
    )
    scheduler.add_job(
        _run_batch_job,
        trigger=daily_trigger,
        id="esgrc_daily_batch",
        name="ESGRC Daily ESG + Risk Batch",
        replace_existing=True,
    )

    # ── Job 2: Compliance check every N days ──────────────────────────────────
    # Praveen's recommendation: 15-day cadence avoids alert fatigue while
    # still catching overdue compliance requirements promptly.
    compliance_trigger = IntervalTrigger(
        days=settings.COMPLIANCE_CHECK_DAYS,
        timezone=pytz_timezone(settings.AGENT_TIMEZONE),
    )
    
    scheduler.add_job(
        _run_compliance_job,
        trigger=compliance_trigger,
        id="esgrc_compliance_batch",
        name=f"ESGRC Compliance Check (every {settings.COMPLIANCE_CHECK_DAYS} days)",
        replace_existing=True,
    )

    scheduler.start()
    next_daily = scheduler.get_job("esgrc_daily_batch").next_run_time
    next_compliance = scheduler.get_job("esgrc_compliance_batch").next_run_time
    logger.info(
        "Scheduler started. "
        "Daily ESG/Risk: %02d:%02d %s (next: %s). "
        "Compliance: every %s days (next: %s).",
        settings.AGENT_HOUR,
        settings.AGENT_MINUTE,
        settings.AGENT_TIMEZONE,
        next_daily,
        settings.COMPLIANCE_CHECK_DAYS,
        next_compliance,
    )


def stop_scheduler() -> None:
    """Stop the scheduler cleanly on application shutdown."""
    global _scheduler, _lock_handle
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped.")
    _scheduler = None
    # Release the single-instance claim so a restarting worker can take over
    # without waiting for the kernel to reap this process.
    if _lock_handle is not None:
        _lock_handle.close()
        _lock_handle = None


def _worker_owns_or_scheduler_is_moot() -> bool:
    """
    True when it is safe for THIS process to build/start a BackgroundScheduler.

    Two cases:
      - AGENT_ENABLED is false: start_scheduler() never ran anywhere, so no
        other worker can possibly own a live scheduler either.
      - _lock_handle is not None: this worker itself won the single-instance
        lock in start_scheduler() and already owns the one live scheduler.

    False means another worker holds SCHEDULER_LOCK_NAME and is already
    polling the shared SQLAlchemyJobStore. Building a second BackgroundScheduler
    here would duplicate that polling - the exact bug single_instance.py exists
    to prevent (see its module docstring and the guard in start_scheduler()).
    """
    return (not settings.AGENT_ENABLED) or (_lock_handle is not None)


def trigger_immediate_run() -> None:
    """
    Run the full batch immediately, in the background (does not block the
    HTTP response). Used by the manual trigger endpoint (POST /agent/run).

    If this worker owns the scheduler lock (or the agent is disabled, so no
    worker owns it), the job is queued on the existing APScheduler instance
    like the scheduled jobs. Otherwise another worker already owns the
    schedule, so we must not build a second BackgroundScheduler here - see
    _worker_owns_or_scheduler_is_moot(). Instead the job runs directly on a
    plain background thread, bypassing the scheduler/jobstore entirely.
    """
    if not _worker_owns_or_scheduler_is_moot():
        logger.info(
            "This worker does not own the agent scheduler lock; running the "
            "manual batch on a background thread instead of building a "
            "second scheduler."
        )
        threading.Thread(
            target=_run_full_batch_job, name="esgrc-manual-run", daemon=True
        ).start()
        return

    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime, timezone

    scheduler = get_scheduler()
    was_running = scheduler.running

    # Add the job BEFORE starting a not-yet-running scheduler, not after.
    # start() then add_job() races APScheduler's own main loop against this
    # call: the loop's first pass can start processing the just-woken
    # scheduler before add_job's row is visible, and/or a wakeup from
    # add_job overlaps the loop's own timer, so the one-shot job's post-run
    # `remove_job()` occasionally fires twice and the second call raises
    # JobLookupError (long-standing upstream race with a persistent
    # jobstore - agronholm/apscheduler#13, agronholm/apscheduler#237).
    # Adding first means the job already exists when start() begins the
    # loop, which avoids the race per the upstream maintainer's own
    # workaround.
    scheduler.add_job(
        _run_full_batch_job,
        trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
        id="esgrc_manual_run",
        name="ESGRC Manual Batch Run",
        replace_existing=True,
        misfire_grace_time=60,
    )
    if not was_running:
        # If scheduler isn't started yet (AGENT_ENABLED=false), start it
        # temporarily just for this manual run
        scheduler.start()
    logger.info("Manual full batch run queued for immediate execution.")


def trigger_immediate_llm_run() -> None:
    """
    Queue an immediate one-shot LLM-powered batch run (POST /agent/llm-run).
    Uses the module-level _run_llm_batch_job so the job is serializable.

    Same worker-ownership guard as trigger_immediate_run(): if another worker
    owns the scheduler lock, run directly on a background thread instead of
    building a second BackgroundScheduler over the shared jobstore.
    """
    if not _worker_owns_or_scheduler_is_moot():
        logger.info(
            "This worker does not own the agent scheduler lock; running the "
            "manual LLM batch on a background thread instead of building a "
            "second scheduler."
        )
        threading.Thread(
            target=_run_llm_batch_job, name="esgrc-manual-llm-run", daemon=True
        ).start()
        return

    from apscheduler.triggers.date import DateTrigger
    from datetime import datetime, timezone

    scheduler = get_scheduler()
    was_running = scheduler.running

    # Add before start() - see the matching comment in trigger_immediate_run().
    scheduler.add_job(
        _run_llm_batch_job,
        trigger=DateTrigger(run_date=datetime.now(timezone.utc)),
        id="esgrc_llm_manual_run",
        name="ESGRC LLM Agent Manual Run",
        replace_existing=True,
        misfire_grace_time=60,
    )
    if not was_running:
        scheduler.start()
    logger.info("Manual LLM agent run queued for immediate execution.")
