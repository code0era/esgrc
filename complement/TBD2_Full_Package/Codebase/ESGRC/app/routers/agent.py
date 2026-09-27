"""
Agent router - view run history and trigger manual runs.

Endpoints:
  GET  /agent/runs        - list recent batch run logs (ADMIN only)
  GET  /agent/runs/{id}   - get a single run log with full details
  GET  /agent/status      - scheduler status + next run time
  POST /agent/run         - trigger an immediate batch run (ADMIN only)
"""

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import require_role
from app.models.models import AgentRunLog, UserRole
from app.schemas.schemas import (
    AgentRunLogOut,
    AgentTriggerOut,
    ErrorDetail,
    PaginationParams,
)
from pipeline.middleware import limiter, rate_limit_trigger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["Agent"])

DB = Annotated[Session, Depends(get_db)]
AdminOnly = Annotated[object, Depends(require_role(UserRole.ADMIN))]
# AgentRunLog is a PLATFORM-WIDE log - one row per batch run, whose `details`
# JSON holds per-org results for ALL organisations (no org_id column). Reading
# it therefore exposes every tenant's data, so it is restricted to the platform
# operator (SUPER_ADMIN), not per-org admins. `/agent/status` stays ADMIN since
# it returns only scheduler health, no cross-org data.
SuperAdminOnly = Annotated[object, Depends(require_role(UserRole.SUPER_ADMIN))]
Pagination = Annotated[PaginationParams, Depends()]


@router.get(
    "/runs",
    response_model=list[AgentRunLogOut],
    summary="List agent batch run logs (newest first)",
)
def list_runs(
    _: SuperAdminOnly,
    pagination: Pagination,
    db: DB,
) -> list[AgentRunLogOut]:
    stmt = (
        select(AgentRunLog)
        .order_by(AgentRunLog.started_at.desc())
        .offset(pagination.skip)
        .limit(pagination.limit)
    )
    return list(db.scalars(stmt).all())


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunLogOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a single agent run log with full per-org details",
)
def get_run(run_id: int, _: SuperAdminOnly, db: DB) -> AgentRunLogOut:
    obj = db.scalar(select(AgentRunLog).where(AgentRunLog.id == run_id))
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Run log not found.",
        )
    return obj


@router.get(
    "/status",
    summary="Scheduler status and next scheduled run time",
)
def scheduler_status(_: AdminOnly, db: DB) -> dict:
    """
    Report agent scheduler status.

    The response schema is stable regardless of AGENT_ENABLED: both scheduled
    jobs are always described (their schedule comes from config), so consumers
    get a consistent shape. When the scheduler is disabled or not yet started,
    `scheduler_running` is False and each job's `next_run` is null.

    Also surfaces the most recent batch run's summary (last_run_at,
    last_run_status, metrics_scored, requirements_flagged) so the dashboard
    "Scoring Agent" card reflects what the agent actually did. These are
    aggregate counters only - no cross-org `details` are exposed.
    """
    from app.agent.scheduler import get_scheduler
    from app.config import settings

    enabled = settings.AGENT_ENABLED
    # Only touch the scheduler when the agent is enabled; otherwise report idle.
    scheduler = get_scheduler() if enabled else None
    running = bool(scheduler and scheduler.running)
    daily_job = scheduler.get_job("esgrc_daily_batch") if running else None
    compliance_job = scheduler.get_job("esgrc_compliance_batch") if running else None

    # Newest batch run (if any) for the last-run summary.
    last = db.scalar(
        select(AgentRunLog).order_by(AgentRunLog.started_at.desc()).limit(1)
    )
    last_run_ts = (last.finished_at or last.started_at) if last is not None else None
    last_status = None
    if last is not None:
        last_status = last.status.value if hasattr(last.status, "value") else last.status

    return {
        "agent_enabled": enabled,
        "scheduler_running": running,
        "schedule": f"{settings.AGENT_HOUR:02d}:{settings.AGENT_MINUTE:02d} {settings.AGENT_TIMEZONE}",
        "last_run_at": last_run_ts.isoformat() if last_run_ts else None,
        "last_run_status": last_status,
        "metrics_scored": last.metrics_scored if last is not None else 0,
        "requirements_flagged": last.requirements_flagged if last is not None else 0,
        "daily_esg_risk": {
            "schedule": f"Daily at {settings.AGENT_HOUR:02d}:{settings.AGENT_MINUTE:02d} {settings.AGENT_TIMEZONE}",
            "next_run": daily_job.next_run_time.isoformat() if daily_job and daily_job.next_run_time else None,
        },
        "compliance_check": {
            "schedule": f"Every {settings.COMPLIANCE_CHECK_DAYS} days at {settings.AGENT_HOUR:02d}:{settings.AGENT_MINUTE:02d} {settings.AGENT_TIMEZONE}",
            "next_run": compliance_job.next_run_time.isoformat() if compliance_job and compliance_job.next_run_time else None,
        },
    }


@router.post(
    "/run",
    response_model=AgentTriggerOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Manually trigger an immediate rule-based batch run (runs in background)",
)
@limiter.limit(rate_limit_trigger)
def trigger_run(request: Request, _: SuperAdminOnly) -> AgentTriggerOut:
    """
    Queues the rule-based batch agent to run immediately in the background.
    SUPER_ADMIN only: the batch runs across ALL organisations (see runner.run_batch),
    so a per-org admin must not be able to trigger cross-tenant writes. Rate
    limited (same 10/minute as the pipeline's own /trigger) since this queues
    a platform-wide batch job - matches this endpoint's existing SUPER_ADMIN
    gate, which alone doesn't stop a single compromised/careless super-admin
    token or automation bug from firing it back-to-back.
    Returns 202 Accepted immediately - does not wait for the run to finish.
    Poll GET /agent/runs to see the result once it completes.
    """
    from app.agent.scheduler import trigger_immediate_run

    trigger_immediate_run()
    logger.info("Manual rule-based agent run triggered by admin")
    return AgentTriggerOut(
        message="Rule-based batch run queued. Poll GET /agent/runs for the result.",
        queued_at=datetime.now(timezone.utc),
    )


@router.post(
    "/llm-run",
    response_model=AgentTriggerOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={422: {"model": ErrorDetail}},
    summary="Trigger an LLM-powered agentic batch run (requires ANTHROPIC_API_KEY)",
    description=(
        "Runs the two-LLM orchestrator-specialist agent in the background. "
        "The orchestrator reads all org data, identifies what needs action, "
        "and delegates to the specialist for scoring, classification, and escalation. "
        "Requires ANTHROPIC_API_KEY and LLM_AGENT_ENABLED=true in config."
    ),
)
@limiter.limit(rate_limit_trigger)
def trigger_llm_run(request: Request, _: SuperAdminOnly) -> AgentTriggerOut:
    # SUPER_ADMIN only: runs across ALL organisations and spends the platform-wide
    # Anthropic budget, so this must not be triggerable by a single tenant's admin.
    # Also rate limited (10/minute, matching /agent/run and the pipeline's
    # /trigger) - the SUPER_ADMIN gate alone doesn't cap how many of these
    # real-money LLM batches one token can fire per minute.
    from app.config import settings
    from app.agent.scheduler import get_scheduler

    if not settings.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "ANTHROPIC_API_KEY is not configured. "
                "Set it in your .env file to enable the LLM agent."
            ),
        )

    from app.agent.scheduler import trigger_immediate_llm_run

    # Schedule via a module-level job (see scheduler.trigger_immediate_llm_run).
    # The previous inline closure could not be serialized by APScheduler's
    # SQLAlchemyJobStore and raised "This Job cannot be serialized".
    trigger_immediate_llm_run()
    logger.info("LLM agent run triggered by admin")
    return AgentTriggerOut(
        message=(
            "LLM agent run queued. The orchestrator will analyse all organisations "
            "and take action autonomously. Poll GET /agent/runs for the result."
        ),
        queued_at=datetime.now(timezone.utc),
    )
