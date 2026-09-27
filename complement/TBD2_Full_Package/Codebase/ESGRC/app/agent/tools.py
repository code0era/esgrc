"""
Tool functions for the LLM agent layer.

Each function here wraps existing CRUD/service logic and returns
clean, LLM-friendly data structures (plain dicts, not ORM objects).

Design principles:
- Every tool returns a dict or list of dicts - never ORM objects
- Tool names match exactly what is registered in the tool schema
- Side-effect tools (write operations) log what they do
- All tools are synchronous - the agent loop is synchronous
- Tools are thin wrappers - no business logic lives here

Timezone note:
  SQLite stores datetimes as naive strings. SQLAlchemy returns them as
  naive datetime objects (no tzinfo). All comparisons against "now" use
  datetime.utcnow() (also naive) to avoid TypeError when comparing
  naive and aware datetimes. PostgreSQL in production returns tz-aware
  objects, so we use .replace(tzinfo=None) to normalise both cases.
"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.crud.crud import (
    get_risk_heatmap,
    get_risks,
    get_requirements,
    get_global_compliance_summary,
    get_esg_metrics,
    update_risk as crud_update_risk,
    update_requirement as crud_update_requirement,
)
from app.models.models import (
    ComplianceFramework,
    ComplianceStatus,
    ESGCategory,
    ESGMetric,
    ESGScoreBenchmark,
    RiskLevel,
    RiskStatus,
)
from app.schemas.schemas import ComplianceRequirementUpdate, RiskUpdate

logger = logging.getLogger(__name__)


def _naive_utcnow() -> datetime:
    """
    Return the current UTC time as a NAIVE datetime.

    SQLite stores naive datetimes. PostgreSQL returns tz-aware datetimes.
    To avoid TypeError when comparing, we always work with naive UTC here.
    datetime.utcnow() is deprecated in 3.12 - use datetime.now(UTC).replace(tzinfo=None).
    """
    from datetime import timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _strip_tz(dt: datetime | None) -> datetime | None:
    """Strip tzinfo from a datetime so it is always naive for comparison."""
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


# ─── Read tools ───────────────────────────────────────────────────────────────

def read_org_snapshot(db: Session, org_id: int) -> dict:
    """
    Return a compact snapshot of the organisation's current ESGRC state.
    Designed to fit in a single LLM context window entry.
    """
    heatmap = get_risk_heatmap(db, org_id=org_id, status=RiskStatus.OPEN)
    compliance = get_global_compliance_summary(db, org_id=org_id)

    all_metrics = get_esg_metrics(db, org_id=org_id, limit=500)
    scored = [m for m in all_metrics if m.score is not None]
    unscored = [m for m in all_metrics if m.score is None]
    avg_score = round(sum(m.score for m in scored) / len(scored), 1) if scored else None

    return {
        "esg": {
            "total_metrics": len(all_metrics),
            "scored_metrics": len(scored),
            "unscored_metrics": len(unscored),
            "avg_score": avg_score,
        },
        "risk": {
            "total_open": heatmap.total_scored,
            "critical_zone_count": heatmap.critical_zone_count,
            "unscored_risks": heatmap.unscored_count,
            "highest_risk_score": heatmap.highest_risk_score,
        },
        "compliance": {
            "overall_rate": compliance.overall_compliance_rate,
            "total_requirements": compliance.total_requirements,
            "compliant": compliance.total_compliant,
            "non_compliant": compliance.total_non_compliant,
            "not_assessed": compliance.total_not_assessed,
            "frameworks": len(compliance.frameworks),
        },
    }


def read_unscored_metrics(db: Session, org_id: int) -> list[dict]:
    """Return metrics with no score, with category and benchmark info for the LLM."""
    stmt = (
        select(ESGMetric, ESGCategory, ESGScoreBenchmark)
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .outerjoin(ESGScoreBenchmark, ESGScoreBenchmark.category_id == ESGCategory.id)
        .where(
            ESGCategory.org_id == org_id,
            ESGMetric.score.is_(None),
        )
        .limit(50)  # cap to avoid overwhelming the LLM context
    )
    rows = db.execute(stmt).all()
    return [
        {
            "metric_id": metric.id,
            "category_id": cat.id,
            "category_name": cat.name,
            "pillar": cat.pillar.value,
            "value": metric.value,
            "period": metric.period,
            "organisation": metric.organisation,
            "has_benchmark": bench is not None,
            "benchmark": {
                "target_value": bench.target_value,
                "baseline_value": bench.baseline_value,
                "direction": bench.direction.value,
            } if bench else None,
        }
        for metric, cat, bench in rows
    ]


def read_open_risks(db: Session, org_id: int) -> list[dict]:
    """
    Return open risks with score and days overdue.

    Uses naive UTC comparison (_strip_tz) to handle both SQLite (naive)
    and PostgreSQL (tz-aware) datetime returns uniformly.
    """
    risks = get_risks(db, org_id=org_id, status=RiskStatus.OPEN, limit=100)
    now = _naive_utcnow()
    return [
        {
            "risk_id": r.id,
            "title": r.title,
            "description": r.description,
            "level": r.level.value,
            "risk_score": r.risk_score,
            "likelihood": r.likelihood,
            "impact": r.impact,
            "due_date": r.due_date.isoformat() if r.due_date else None,
            "days_overdue": (
                max(0, (now - _strip_tz(r.due_date)).days)
                if r.due_date and _strip_tz(r.due_date) < now
                else 0
            ),
        }
        for r in risks
        if r.risk_score is not None
    ]


def read_overdue_requirements(db: Session, org_id: int) -> list[dict]:
    """
    Return requirements past their review date that are not compliant.

    Uses naive UTC comparison (_strip_tz) to handle both SQLite (naive)
    and PostgreSQL (tz-aware) datetime returns uniformly.
    """
    reqs = get_requirements(db, org_id=org_id, limit=100)
    now = _naive_utcnow()
    result = []
    for r in reqs:
        review = _strip_tz(r.review_date)
        if (
            review is not None
            and review < now
            and r.status != ComplianceStatus.COMPLIANT
        ):
            result.append({
                "req_id": r.id,
                "code": r.code,
                "title": r.title,
                "description": r.description,
                "status": r.status.value,
                "evidence": r.evidence,
                "days_overdue": max(0, (now - review).days),
            })
    return result[:50]  # cap to 50 for context window management


# ─── Write tools ──────────────────────────────────────────────────────────────

def apply_metric_score(db: Session, org_id: int, metric_id: int, score: float) -> dict:
    """
    Persist a score for a metric.

    If the metric's category has a scoring benchmark, the score is recomputed
    deterministically from the benchmark (compute_score) and the model-supplied
    `score` is ignored - this keeps the LLM path consistent and reproducible with
    the rule-based batch (tasks.score_unscored_metrics) and the POST /score
    endpoint, all three of which derive the score from target/baseline. Only when
    no benchmark exists do we fall back to the model's judgment (clamped), since
    there is no formula to apply.
    """
    from app.services.scoring import compute_score

    metric = db.execute(
        select(ESGMetric)
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .where(ESGMetric.id == metric_id, ESGCategory.org_id == org_id)
    ).scalar_one_or_none()

    if metric is None:
        return {"success": False, "error": f"Metric {metric_id} not found for this org"}

    benchmark = db.execute(
        select(ESGScoreBenchmark).where(ESGScoreBenchmark.category_id == metric.category_id)
    ).scalar_one_or_none()

    if benchmark is not None and metric.value is not None:
        final = compute_score(metric.value, benchmark)
        source = "benchmark"
    else:
        final = max(0.0, min(100.0, round(float(score), 2)))
        source = "llm"

    metric.score = final
    db.commit()
    logger.info(
        "LLM agent scored metric id=%s score=%.2f org_id=%s source=%s",
        metric_id, final, org_id, source,
    )
    return {"success": True, "metric_id": metric_id, "score": final, "score_source": source}


def apply_requirement_status(
    db: Session, org_id: int, req_id: int, status: str, reasoning: str = ""
) -> dict:
    """Persist a compliance classification made by the specialist agent."""
    try:
        compliance_status = ComplianceStatus(status)
    except ValueError:
        valid = [e.value for e in ComplianceStatus]
        return {"success": False, "error": f"Invalid status '{status}'. Valid: {valid}"}

    update = ComplianceRequirementUpdate(status=compliance_status)
    result = crud_update_requirement(db, req_id, update, org_id=org_id)
    if result is None:
        return {"success": False, "error": f"Requirement {req_id} not found for this org"}

    logger.info(
        "LLM agent classified requirement id=%s status=%s org_id=%s",
        req_id, status, org_id,
    )
    return {"success": True, "req_id": req_id, "status": status, "reasoning": reasoning}


def apply_risk_level(
    db: Session, org_id: int, risk_id: int, level: str, action_note: str = ""
) -> dict:
    """Persist a risk level recommendation made by the specialist agent."""
    try:
        risk_level = RiskLevel(level)
    except ValueError:
        valid = [e.value for e in RiskLevel]
        return {"success": False, "error": f"Invalid level '{level}'. Valid: {valid}"}

    update = RiskUpdate(level=risk_level)
    result = crud_update_risk(db, risk_id, update, org_id=org_id)
    if result is None:
        return {"success": False, "error": f"Risk {risk_id} not found for this org"}

    logger.info(
        "LLM agent updated risk id=%s level=%s org_id=%s action=%s",
        risk_id, level, org_id, action_note,
    )
    return {"success": True, "risk_id": risk_id, "level": level, "action": action_note}
