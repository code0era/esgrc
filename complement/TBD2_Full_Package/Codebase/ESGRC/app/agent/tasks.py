"""
Agent batch tasks - the actual work performed each scheduled run.

Each task function:
- Accepts a SQLAlchemy Session and an org_id
- Returns a dict of counts (what was done)
- Is pure business logic - no scheduler, no HTTP, no FastAPI
- Is independently testable

Tasks run in this order each cycle:
  1. score_unscored_metrics   - score any ESGMetric where score IS NULL
  2. flag_overdue_requirements - mark requirements where review_date has passed
  3. escalate_critical_risks  - elevate status of overdue high-risk items

Design: tasks are intentionally separated so the runner can:
  - Skip a task if it errors without cancelling the others
  - Record per-task counts in the run log
  - Be extended with new tasks without touching existing ones
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import (
    ComplianceRequirement,
    ComplianceStatus,
    ESGMetric,
    ESGCategory,
    Risk,
    RiskLevel,
    RiskStatus,
)
from app.services.scoring import compute_score
from app.services.risk_thresholds import RISK_ESCALATION_SCORE
from app.crud.crud import get_benchmark_by_category

logger = logging.getLogger(__name__)


# ─── Task 1: Score unscored ESG metrics ──────────────────────────────────────

def score_unscored_metrics(db: Session, org_id: int) -> dict:
    """
    Find all ESGMetric rows where score IS NULL and a benchmark exists
    for their category. Compute and persist the score.

    Returns:
        {"scored": int, "skipped_no_benchmark": int}
    """
    stmt = (
        select(ESGMetric)
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .where(
            ESGCategory.org_id == org_id,
            ESGMetric.score.is_(None),
        )
    )
    unscored = list(db.scalars(stmt).all())

    scored = 0
    skipped = 0
    # Cache benchmark lookups per category - many unscored metrics typically
    # share the same handful of categories, so without this a batch of N
    # metrics across K categories issued N benchmark queries instead of K.
    benchmark_cache: dict[int, object] = {}

    for metric in unscored:
        if metric.category_id not in benchmark_cache:
            benchmark_cache[metric.category_id] = get_benchmark_by_category(
                db, metric.category_id
            )
        benchmark = benchmark_cache[metric.category_id]
        if benchmark is None:
            skipped += 1
            continue
        try:
            metric.score = compute_score(metric.value, benchmark)
            scored += 1
        except Exception as exc:
            logger.warning(
                "Failed to score metric id=%s org_id=%s: %s",
                metric.id, org_id, exc,
            )
            skipped += 1

    if scored > 0:
        db.commit()
        logger.info("org_id=%s scored %s metrics (%s skipped, no benchmark)", org_id, scored, skipped)

    return {"scored": scored, "skipped_no_benchmark": skipped}


# ─── Task 2: Flag overdue compliance requirements ────────────────────────────

def flag_overdue_requirements(db: Session, org_id: int) -> dict:
    """
    Find ComplianceRequirement rows where:
      - review_date is in the past (overdue)
      - status is NOT already compliant

    Mark them as 'not_assessed' to trigger re-review.
    Requirements inherit org scope via their parent framework.

    Returns:
        {"flagged": int}
    """
    from app.models.models import ComplianceFramework

    now = datetime.now(timezone.utc)

    stmt = (
        select(ComplianceRequirement)
        .join(ComplianceFramework, ComplianceRequirement.framework_id == ComplianceFramework.id)
        .where(
            ComplianceFramework.org_id == org_id,
            ComplianceRequirement.review_date.is_not(None),
            ComplianceRequirement.review_date < now,
            ComplianceRequirement.status != ComplianceStatus.COMPLIANT,
        )
    )

    overdue = list(db.scalars(stmt).all())
    flagged = 0

    for req in overdue:
        if req.status != ComplianceStatus.NOT_ASSESSED:
            req.status = ComplianceStatus.NOT_ASSESSED
            flagged += 1

    if flagged > 0:
        db.commit()
        logger.info("org_id=%s flagged %s overdue requirements for re-review", org_id, flagged)

    return {"flagged": flagged}


# ─── Task 3: Escalate critical overdue risks ─────────────────────────────────

def escalate_critical_risks(db: Session, org_id: int) -> dict:
    """
    Find Risk rows where:
      - risk_score (likelihood * impact) >= 20  (critical zone)
      - status is still OPEN (not being actioned)
      - due_date has passed

    Escalate their level to CRITICAL to ensure they surface in dashboards.

    Returns:
        {"escalated": int}
    """
    now = datetime.now(timezone.utc)

    stmt = (
        select(Risk)
        .where(
            Risk.org_id == org_id,
            Risk.status == RiskStatus.OPEN,
            Risk.likelihood.is_not(None),
            Risk.impact.is_not(None),
            Risk.likelihood * Risk.impact >= RISK_ESCALATION_SCORE,
            Risk.due_date.is_not(None),
            Risk.due_date < now,
            Risk.level != RiskLevel.CRITICAL,  # avoid no-op updates
        )
    )

    overdue_critical = list(db.scalars(stmt).all())
    escalated = 0

    for risk in overdue_critical:
        risk.level = RiskLevel.CRITICAL
        escalated += 1
        logger.warning(
            "org_id=%s escalating risk id=%s '%s' to CRITICAL (overdue, score=%s)",
            org_id, risk.id, risk.title,
            (risk.likelihood or 0) * (risk.impact or 0),
        )

    if escalated > 0:
        db.commit()
        logger.info("org_id=%s escalated %s risks to CRITICAL", org_id, escalated)

    return {"escalated": escalated}
