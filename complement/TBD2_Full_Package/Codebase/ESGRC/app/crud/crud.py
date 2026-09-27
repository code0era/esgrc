"""
CRUD layer for the ESGRC module - SQLAlchemy 2.x API throughout.

Key patterns
────────────
- select() + session.scalars() / session.scalar(): the SA 2.x recommended
  query API. The legacy db.query() (SA 1.x) is not used anywhere.
- model_dump(exclude_unset=True) on every PATCH: a client sending
  {"field": null} explicitly clears the column. exclude_none=True would
  silently drop null values - a common but critical PATCH semantics bug.
- IntegrityError caught on unique-constraint writes, rolled back, and
  re-raised as ValueError; routers translate it to HTTP 409 Conflict.
- Keyword-only filter args (*, kwarg=...) prevent silent positional mistakes.
- All list queries include order_by + offset/limit for deterministic pagination.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import joinedload, Session
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.services.risk_thresholds import RISK_CRITICAL_ZONE_MIN
from app.models.models import (
    ComplianceFramework,
    ComplianceRequirement,
    ComplianceStatus,
    ESGCategory,
    ESGMetric,
    ESGPillar,
    ESGScoreBenchmark,
    Organisation,
    Risk,
    RiskLevel,
    RiskStatus,
)
from app.schemas.schemas import (
    ComplianceFrameworkCreate,
    ComplianceFrameworkUpdate,
    ComplianceRequirementCreate,
    ComplianceRequirementUpdate,
    ESGCategoryCreate,
    ESGCategoryUpdate,
    ESGMetricCreate,
    ESGMetricUpdate,
    ComplianceSummaryOut,
    ESGScoreBenchmarkCreate,
    RiskHeatmapCellOut,
    RiskHeatmapOut,
    ESGScoreBenchmarkUpdate,
    GlobalComplianceSummaryOut,
    RiskCreate,
    RiskUpdate,
)

logger = logging.getLogger(__name__)


# ─── ESG Category ─────────────────────────────────────────────────────────────

def create_esg_category(db: Session, data: ESGCategoryCreate, *, org_id: int) -> ESGCategory:
    obj = ESGCategory(**data.model_dump(), org_id=org_id)
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"ESG category '{data.name}' already exists in your organisation.")
    db.refresh(obj)
    logger.debug("Created ESGCategory id=%s name=%s org_id=%s", obj.id, obj.name, org_id)
    return obj


def get_esg_categories(
    db: Session,
    *,
    org_id: int,
    pillar: ESGPillar | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ESGCategory]:
    stmt = (
        select(ESGCategory)
        .where(ESGCategory.org_id == org_id)
        .order_by(ESGCategory.id)
        .offset(skip)
        .limit(limit)
    )
    if pillar is not None:
        stmt = stmt.where(ESGCategory.pillar == pillar)
    return list(db.scalars(stmt).all())


def get_esg_category(db: Session, category_id: int, *, org_id: int) -> ESGCategory | None:
    """Returns None if the category does not exist OR belongs to a different org."""
    return db.scalar(
        select(ESGCategory).where(
            ESGCategory.id == category_id,
            ESGCategory.org_id == org_id,
        )
    )


def update_esg_category(
    db: Session, category_id: int, data: ESGCategoryUpdate, *, org_id: int
) -> ESGCategory | None:
    obj = get_esg_category(db, category_id, org_id=org_id)
    if obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("An ESG category with that name already exists.")
    db.refresh(obj)
    return obj


def delete_esg_category(db: Session, category_id: int, *, org_id: int) -> bool:
    obj = get_esg_category(db, category_id, org_id=org_id)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    logger.debug("Deleted ESGCategory id=%s", category_id)
    return True


# ─── ESG Metric ───────────────────────────────────────────────────────────────

def create_esg_metric(db: Session, data: ESGMetricCreate, *, org_name: str) -> ESGMetric:
    payload = data.model_dump()
    payload["organisation"] = org_name   # enforce - don't trust client-supplied string
    obj = ESGMetric(**payload)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.debug("Created ESGMetric id=%s org=%s period=%s", obj.id, obj.organisation, obj.period)
    return obj


def get_esg_metrics(
    db: Session,
    *,
    org_id: int,
    organisation: str | None = None,
    category_id: int | None = None,
    period: str | None = None,
    skip: int = 0,
    limit: int | None = 50,
) -> list[ESGMetric]:
    # Scope to org via join - metrics inherit tenancy from their category
    stmt = (
        select(ESGMetric)
        .options(joinedload(ESGMetric.category))
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .where(ESGCategory.org_id == org_id)
        .order_by(ESGMetric.id)
        .offset(skip)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    if organisation is not None:
        stmt = stmt.where(ESGMetric.organisation == organisation)
    if category_id is not None:
        stmt = stmt.where(ESGMetric.category_id == category_id)
    if period is not None:
        stmt = stmt.where(ESGMetric.period == period)
    return list(db.scalars(stmt).all())


def get_esg_metric(db: Session, metric_id: int, *, org_id: int) -> ESGMetric | None:
    """Returns None if the metric does not exist OR belongs to a different org."""
    return db.scalar(
        select(ESGMetric)
        .options(joinedload(ESGMetric.category))
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .where(ESGMetric.id == metric_id, ESGCategory.org_id == org_id)
    )


def update_esg_metric(
    db: Session, metric_id: int, data: ESGMetricUpdate, *, org_id: int
) -> ESGMetric | None:
    obj = get_esg_metric(db, metric_id, org_id=org_id)
    if obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


# ─── Risk ─────────────────────────────────────────────────────────────────────

def create_risk(db: Session, data: RiskCreate, *, org_id: int) -> Risk:
    obj = Risk(**data.model_dump(), org_id=org_id)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.debug("Created Risk id=%s title=%s level=%s org_id=%s", obj.id, obj.title, obj.level, org_id)
    return obj


def get_risks(
    db: Session,
    *,
    org_id: int,
    status: RiskStatus | None = None,
    level: RiskLevel | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Risk]:
    stmt = (
        select(Risk)
        .where(Risk.org_id == org_id)
        .order_by(Risk.id)
        .offset(skip)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Risk.status == status)
    if level is not None:
        stmt = stmt.where(Risk.level == level)
    return list(db.scalars(stmt).all())


def get_risk(db: Session, risk_id: int, *, org_id: int) -> Risk | None:
    """Returns None if the risk does not exist OR belongs to a different org."""
    return db.scalar(
        select(Risk).where(Risk.id == risk_id, Risk.org_id == org_id)
    )


def update_risk(db: Session, risk_id: int, data: RiskUpdate, *, org_id: int) -> Risk | None:
    obj = get_risk(db, risk_id, org_id=org_id)
    if obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


def delete_risk(db: Session, risk_id: int, *, org_id: int) -> bool:
    obj = get_risk(db, risk_id, org_id=org_id)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    logger.debug("Deleted Risk id=%s", risk_id)
    return True


# ─── Compliance Framework ─────────────────────────────────────────────────────

def create_framework(db: Session, data: ComplianceFrameworkCreate, *, org_id: int) -> ComplianceFramework:
    obj = ComplianceFramework(**data.model_dump(), org_id=org_id)
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"Compliance framework '{data.name}' already exists in your organisation.")
    db.refresh(obj)
    logger.debug("Created ComplianceFramework id=%s name=%s org_id=%s", obj.id, obj.name, org_id)
    return obj


def get_frameworks(
    db: Session,
    *,
    org_id: int,
    active_only: bool = True,
    skip: int = 0,
    limit: int = 50,
) -> list[ComplianceFramework]:
    stmt = (
        select(ComplianceFramework)
        .where(ComplianceFramework.org_id == org_id)
        .order_by(ComplianceFramework.id)
        .offset(skip)
        .limit(limit)
    )
    if active_only:
        stmt = stmt.where(ComplianceFramework.active.is_(True))
    return list(db.scalars(stmt).all())


def get_framework(db: Session, framework_id: int, *, org_id: int) -> ComplianceFramework | None:
    """Returns None if the framework does not exist OR belongs to a different org."""
    return db.scalar(
        select(ComplianceFramework).where(
            ComplianceFramework.id == framework_id,
            ComplianceFramework.org_id == org_id,
        )
    )


def update_framework(
    db: Session, framework_id: int, data: ComplianceFrameworkUpdate, *, org_id: int
) -> ComplianceFramework | None:
    obj = get_framework(db, framework_id, org_id=org_id)
    if obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError("A compliance framework with that name already exists.")
    db.refresh(obj)
    return obj


def delete_framework(db: Session, framework_id: int, *, org_id: int) -> bool:
    obj = get_framework(db, framework_id, org_id=org_id)
    if obj is None:
        return False
    db.delete(obj)
    db.commit()
    logger.debug("Deleted ComplianceFramework id=%s", framework_id)
    return True


# ─── Compliance Requirement ───────────────────────────────────────────────────

def create_requirement(
    db: Session, data: ComplianceRequirementCreate
) -> ComplianceRequirement:
    """
    Requirements inherit org scope from their parent framework.
    The router verifies the framework belongs to the caller's org before
    calling this function, so no separate org_id injection is needed here.
    """
    obj = ComplianceRequirement(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    logger.debug("Created ComplianceRequirement id=%s code=%s", obj.id, obj.code)
    return obj


def get_requirements(
    db: Session,
    *,
    org_id: int,
    framework_id: int | None = None,
    status: ComplianceStatus | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ComplianceRequirement]:
    # Scope to org via join - requirements inherit tenancy from their framework
    stmt = (
        select(ComplianceRequirement)
        .join(ComplianceFramework, ComplianceRequirement.framework_id == ComplianceFramework.id)
        .where(ComplianceFramework.org_id == org_id)
        .order_by(ComplianceRequirement.id)
        .offset(skip)
        .limit(limit)
    )
    if framework_id is not None:
        stmt = stmt.where(ComplianceRequirement.framework_id == framework_id)
    if status is not None:
        stmt = stmt.where(ComplianceRequirement.status == status)
    return list(db.scalars(stmt).all())


def get_requirement(db: Session, req_id: int, *, org_id: int) -> ComplianceRequirement | None:
    """Returns None if the requirement does not exist OR belongs to a different org."""
    return db.scalar(
        select(ComplianceRequirement)
        .join(ComplianceFramework, ComplianceRequirement.framework_id == ComplianceFramework.id)
        .where(
            ComplianceRequirement.id == req_id,
            ComplianceFramework.org_id == org_id,
        )
    )


def update_requirement(
    db: Session, req_id: int, data: ComplianceRequirementUpdate, *, org_id: int
) -> ComplianceRequirement | None:
    obj = get_requirement(db, req_id, org_id=org_id)
    if obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    db.commit()
    db.refresh(obj)
    return obj


# ─── ESG Score Benchmark ──────────────────────────────────────────────────────

def create_or_replace_benchmark(
    db: Session, data: ESGScoreBenchmarkCreate
) -> ESGScoreBenchmark:
    """
    Upsert: if a benchmark already exists for the category, update it.
    Otherwise create a new one.
    This is intentional - each category has at most one benchmark.
    """
    existing = get_benchmark_by_category(db, data.category_id)
    if existing is not None:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        logger.debug("Updated ESGScoreBenchmark id=%s category_id=%s", existing.id, existing.category_id)
        return existing

    obj = ESGScoreBenchmark(**data.model_dump())
    db.add(obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ValueError(f"A benchmark for category {data.category_id} already exists.")
    db.refresh(obj)
    logger.debug("Created ESGScoreBenchmark id=%s category_id=%s", obj.id, obj.category_id)
    return obj


def get_benchmark_by_category(
    db: Session, category_id: int
) -> ESGScoreBenchmark | None:
    return db.scalar(
        select(ESGScoreBenchmark).where(ESGScoreBenchmark.category_id == category_id)
    )


def get_benchmark(db: Session, benchmark_id: int) -> ESGScoreBenchmark | None:
    return db.scalar(
        select(ESGScoreBenchmark).where(ESGScoreBenchmark.id == benchmark_id)
    )


def update_benchmark(
    db: Session, benchmark_id: int, data: ESGScoreBenchmarkUpdate
) -> ESGScoreBenchmark | None:
    obj = get_benchmark(db, benchmark_id)
    if obj is None:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    # Validate non-degenerate after partial update
    if abs(obj.target_value - obj.baseline_value) < 1e-9:
        raise ValueError("target_value must differ from baseline_value after update.")
    db.commit()
    db.refresh(obj)
    return obj


def apply_score_to_metric(
    db: Session, metric_id: int, *, org_id: int
) -> tuple["ESGMetric", "ESGScoreBenchmark"] | None:
    """
    Load the metric and its category benchmark, compute the score,
    persist it, and return (metric, benchmark).
    Returns None if the metric does not exist.
    Raises ValueError if no benchmark is configured for the category.
    """
    from app.services.scoring import compute_score

    metric = get_esg_metric(db, metric_id, org_id=org_id)
    if metric is None:
        return None

    benchmark = get_benchmark_by_category(db, metric.category_id)
    if benchmark is None:
        raise ValueError(
            f"No scoring benchmark configured for category {metric.category_id}. "
            "Create one via POST /esg/benchmarks before scoring metrics."
        )

    score = compute_score(metric.value, benchmark)
    metric.score = score
    db.commit()
    db.refresh(metric)
    logger.debug(
        "Scored ESGMetric id=%s value=%.4f → score=%.2f benchmark_id=%s",
        metric.id, metric.value, score, benchmark.id,
    )
    return metric, benchmark


# ─── Risk Heatmap ─────────────────────────────────────────────────────────────

def get_risk_heatmap(
    db: Session,
    *,
    org_id: int,
    status: RiskStatus | None = None,
    category: str | None = None,
) -> RiskHeatmapOut:
    """
    Build a complete 5x5 risk heatmap in a single SQL query.

    Strategy:
    1. One GROUP BY query returns counts per (likelihood, impact) pair for
       scored risks (both columns non-NULL).
    2. One COUNT query returns the number of unscored risks (NULL likelihood
       or NULL impact) so nothing is silently discarded.
    3. Python fills in zero-count cells for the full 25-cell grid so the
       frontend always receives a complete matrix without inferring gaps.

    Args:
        status:   Optional RiskStatus filter - typically "open" for active heatmap.
        category: Optional category string filter.
    """
    # ── Base filter predicate ─────────────────────────────────────────────────
    # Build a reusable list of WHERE conditions applied to both queries.
    filters = [
        Risk.org_id == org_id,
        Risk.likelihood.is_not(None),
        Risk.impact.is_not(None),
    ]
    unscored_filters = [Risk.org_id == org_id]

    if status is not None:
        filters.append(Risk.status == status)
        unscored_filters.append(Risk.status == status)
    if category is not None:
        filters.append(Risk.category == category)
        unscored_filters.append(Risk.category == category)

    # ── Query 1: grouped counts for scored risks ──────────────────────────────
    scored_stmt = (
        select(
            Risk.likelihood,
            Risk.impact,
            func.count(Risk.id).label("count"),
        )
        .where(*filters)
        .group_by(Risk.likelihood, Risk.impact)
    )
    scored_rows = db.execute(scored_stmt).all()

    # Build a lookup dict: (likelihood, impact) → count
    cell_map: dict[tuple[int, int], int] = {
        (row.likelihood, row.impact): row.count
        for row in scored_rows
    }

    # ── Query 2: count of unscored risks (NULL likelihood OR NULL impact) ─────
    null_filter = (Risk.likelihood.is_(None)) | (Risk.impact.is_(None))
    unscored_base = [null_filter] + unscored_filters
    unscored_stmt = select(func.count(Risk.id)).where(*unscored_base)
    unscored_count: int = db.scalar(unscored_stmt) or 0

    # ── Build complete 25-cell grid ───────────────────────────────────────────
    # Always emit all 25 cells so the frontend never has to infer missing ones.
    # Order by risk_score descending - highest-risk cells first.
    cells: list[RiskHeatmapCellOut] = []
    for likelihood in range(1, 6):
        for impact in range(1, 6):
            cells.append(
                RiskHeatmapCellOut(
                    likelihood=likelihood,
                    impact=impact,
                    risk_score=likelihood * impact,
                    count=cell_map.get((likelihood, impact), 0),
                )
            )

    # Sort by risk_score descending, then likelihood desc as tiebreak
    cells.sort(key=lambda c: (c.risk_score, c.likelihood), reverse=True)

    total_scored = sum(c.count for c in cells)
    non_empty = [c for c in cells if c.count > 0]
    highest_risk_score = max((c.risk_score for c in non_empty), default=0)
    critical_zone_count = sum(
        c.count for c in cells
        if c.likelihood >= RISK_CRITICAL_ZONE_MIN and c.impact >= RISK_CRITICAL_ZONE_MIN
    )

    logger.debug(
        "Heatmap: total_scored=%s unscored=%s critical_zone=%s",
        total_scored, unscored_count, critical_zone_count,
    )

    return RiskHeatmapOut(
        cells=cells,
        total_scored=total_scored,
        unscored_count=unscored_count,
        highest_risk_score=highest_risk_score,
        critical_zone_count=critical_zone_count,
    )


# ─── Compliance Summary ───────────────────────────────────────────────────────

def _build_summary_from_row(
    framework_id: int,
    framework_name: str,
    total: int,
    compliant: int,
    non_compliant: int,
    partial: int,
    not_assessed: int,
) -> ComplianceSummaryOut:
    """
    Construct a ComplianceSummaryOut from raw count values.
    Centralises the compliance_rate calculation so it is consistent
    between the per-framework and global summary endpoints.
    """
    rate = round(compliant / total * 100, 1) if total > 0 else 0.0
    return ComplianceSummaryOut(
        framework_id=framework_id,
        framework_name=framework_name,
        total=total,
        compliant=compliant,
        non_compliant=non_compliant,
        partial=partial,
        not_assessed=not_assessed,
        compliance_rate=rate,
    )


def get_framework_summary(
    db: Session, framework_id: int, *, org_id: int
) -> ComplianceSummaryOut | None:
    """
    Return aggregated compliance counts for a single framework.
    Uses a single SQL query with CASE WHEN expressions - no N+1,
    no Python-side counting, one round-trip regardless of requirement volume.
    Returns None if the framework does not exist.
    """
    stmt = (
        select(
            ComplianceFramework.id,
            ComplianceFramework.name,
            func.count(ComplianceRequirement.id).label("total"),
            func.count(
                case((ComplianceRequirement.status == "compliant", 1))
            ).label("compliant"),
            func.count(
                case((ComplianceRequirement.status == "non_compliant", 1))
            ).label("non_compliant"),
            func.count(
                case((ComplianceRequirement.status == "partial", 1))
            ).label("partial"),
            func.count(
                case((ComplianceRequirement.status == "not_assessed", 1))
            ).label("not_assessed"),
        )
        .outerjoin(
            ComplianceRequirement,
            ComplianceRequirement.framework_id == ComplianceFramework.id,
        )
        .where(ComplianceFramework.id == framework_id, ComplianceFramework.org_id == org_id)
        .group_by(ComplianceFramework.id, ComplianceFramework.name)
    )

    row = db.execute(stmt).first()
    if row is None:
        return None

    return _build_summary_from_row(
        framework_id=row.id,
        framework_name=row.name,
        total=row.total,
        compliant=row.compliant,
        non_compliant=row.non_compliant,
        partial=row.partial,
        not_assessed=row.not_assessed,
    )


def get_global_compliance_summary(db: Session, *, org_id: int) -> GlobalComplianceSummaryOut:
    """
    Return aggregated compliance counts across ALL active frameworks.
    Uses a single SQL query - one round-trip for the entire dashboard view.
    """
    stmt = (
        select(
            ComplianceFramework.id,
            ComplianceFramework.name,
            func.count(ComplianceRequirement.id).label("total"),
            func.count(
                case((ComplianceRequirement.status == "compliant", 1))
            ).label("compliant"),
            func.count(
                case((ComplianceRequirement.status == "non_compliant", 1))
            ).label("non_compliant"),
            func.count(
                case((ComplianceRequirement.status == "partial", 1))
            ).label("partial"),
            func.count(
                case((ComplianceRequirement.status == "not_assessed", 1))
            ).label("not_assessed"),
        )
        .outerjoin(
            ComplianceRequirement,
            ComplianceRequirement.framework_id == ComplianceFramework.id,
        )
        .where(ComplianceFramework.org_id == org_id, ComplianceFramework.active.is_(True))
        .group_by(ComplianceFramework.id, ComplianceFramework.name)
        .order_by(ComplianceFramework.id)
    )

    rows = db.execute(stmt).all()

    frameworks = [
        _build_summary_from_row(
            framework_id=row.id,
            framework_name=row.name,
            total=row.total,
            compliant=row.compliant,
            non_compliant=row.non_compliant,
            partial=row.partial,
            not_assessed=row.not_assessed,
        )
        for row in rows
    ]

    # Roll up totals across all frameworks
    total_reqs = sum(f.total for f in frameworks)
    total_compliant = sum(f.compliant for f in frameworks)
    total_non_compliant = sum(f.non_compliant for f in frameworks)
    total_partial = sum(f.partial for f in frameworks)
    total_not_assessed = sum(f.not_assessed for f in frameworks)
    overall_rate = round(total_compliant / total_reqs * 100, 1) if total_reqs > 0 else 0.0

    return GlobalComplianceSummaryOut(
        total_frameworks=len(frameworks),
        total_requirements=total_reqs,
        total_compliant=total_compliant,
        total_non_compliant=total_non_compliant,
        total_partial=total_partial,
        total_not_assessed=total_not_assessed,
        overall_compliance_rate=overall_rate,
        frameworks=frameworks,
    )


__all__ = [
    "get_risk_heatmap",
    "get_framework_summary", "get_global_compliance_summary",
    "create_or_replace_benchmark", "get_benchmark_by_category", "get_benchmark",
    "update_benchmark", "apply_score_to_metric",
    "create_esg_category", "get_esg_categories", "get_esg_category",
    "update_esg_category", "delete_esg_category",
    "create_esg_metric", "get_esg_metrics", "get_esg_metric",
    "update_esg_metric",
    "create_risk", "get_risks", "get_risk", "update_risk", "delete_risk",
    "create_framework", "get_frameworks", "get_framework",
    "update_framework", "delete_framework",
    "create_requirement", "get_requirements", "get_requirement",
    "update_requirement",
    "bulk_import_metrics",
    "export_metrics_csv",
    "get_org_snapshot",
    "bulk_update_requirements",
    "get_esg_dashboard",
]


# ─── Bulk Import ──────────────────────────────────────────────────────────────

def bulk_import_metrics(
    db: Session,
    rows: list,          # list of BulkImportRow
    *,
    org_id: int,
) -> dict:
    """
    Import multiple ESG metric rows in a single transaction.

    Each row is matched to an ESGCategory via metric_code.
    Rows with unknown metric_code are skipped and reported.
    Returns {"imported": N, "skipped": M, "errors": [...]}
    """
    from sqlalchemy import select as sa_select

    # Tenant integrity: stamp every imported row with the org's own name rather
    # than trusting the client-supplied `organisation` field (single-create does
    # the same via org.name). The label feeds CSV export + snapshot grouping.
    org_name = db.scalar(sa_select(Organisation.name).where(Organisation.id == org_id))

    # Build metric_code → category_id map for this org (only categories with a code)
    code_map_rows = db.execute(
        sa_select(ESGCategory.metric_code, ESGCategory.id)
        .where(ESGCategory.org_id == org_id, ESGCategory.metric_code.is_not(None))
    ).all()
    code_to_cat: dict[str, int] = {row.metric_code: row.id for row in code_map_rows}

    imported = 0
    skipped = 0
    errors: list[str] = []

    for row in rows:
        cat_id = code_to_cat.get(row.metric_code)
        if cat_id is None:
            skipped += 1
            errors.append(
                f"metric_code '{row.metric_code}' not found in your organisation's categories. "
                "Create the category with this metric_code first."
            )
            continue

        metric = ESGMetric(
            category_id=cat_id,
            organisation=org_name,
            value=row.value,
            period=row.period,
            notes=row.notes,
        )
        db.add(metric)
        imported += 1

    if imported > 0:
        db.commit()

    logger.info(
        "Bulk import: org_id=%s imported=%s skipped=%s", org_id, imported, skipped
    )
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ─── CSV Export ───────────────────────────────────────────────────────────────

def export_metrics_csv(db: Session, *, org_id: int, period: str | None = None) -> str:
    """
    Export all ESG metrics for an org as a CSV string.

    Format matches input_metric_values_esgrc.csv from the pipeline repos:
    - Columns: all metric codes belonging to this org's categories, alphabetically sorted
    - Rows: one row per unique (period, organisation) combination
    - Values: the metric value for that code/period/org combination; empty if missing

    The ML engineer's scripts can consume this directly instead of static CSV files.
    """
    import csv, io

    # Get all categories with metric codes for this org
    cat_rows = db.execute(
        select(ESGCategory.id, ESGCategory.metric_code, ESGCategory.name)
        .where(ESGCategory.org_id == org_id, ESGCategory.metric_code.is_not(None))
        .order_by(ESGCategory.metric_code)
    ).all()

    if not cat_rows:
        # No coded categories at all - nothing to build even a header from
        # (there are no metric_code columns to name), so return a fully
        # empty body rather than a misleading header-only CSV.
        # See tests/test_phase7.py::test_export_empty_when_no_coded_categories.
        return ""

    cat_id_to_code: dict[int, str] = {r.id: r.metric_code for r in cat_rows}
    ordered_codes = [r.metric_code for r in cat_rows]

    # Fetch all metrics for these categories
    stmt = (
        select(ESGMetric.category_id, ESGMetric.period, ESGMetric.organisation, ESGMetric.value)
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .where(ESGCategory.org_id == org_id, ESGCategory.metric_code.is_not(None))
        .order_by(ESGMetric.period, ESGMetric.organisation)
    )
    if period:
        stmt = stmt.where(ESGMetric.period == period)

    metric_rows = db.execute(stmt).all()

    # Pivot: (period, org) → {metric_code: value}
    pivot: dict[tuple, dict[str, float]] = {}
    for row in metric_rows:
        key = (row.period, row.organisation)
        code = cat_id_to_code.get(row.category_id)
        if code:
            pivot.setdefault(key, {})[code] = row.value

    # Write CSV
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["period", "organisation"] + ordered_codes)
    writer.writeheader()
    for (p, org), values in sorted(pivot.items()):
        row_dict = {"period": p, "organisation": org}
        for code in ordered_codes:
            row_dict[code] = values.get(code, "")
        writer.writerow(row_dict)

    return output.getvalue()


# ─── Org Snapshot ─────────────────────────────────────────────────────────────

def get_org_snapshot(db: Session, *, org_id: int, org_name: str) -> dict:
    """
    Return a complete org snapshot in one function call.

    Aggregates ESG scores, risk heatmap, compliance summary, and
    per-sub-module averages (L2 level, using metric_code prefixes).

    The sub-module average is computed by grouping categories whose
    metric_code starts with the same 3-char prefix (e.g. "ESU" for
    Environmental & Sustainability Unit).
    """
    from app.models.models import RiskStatus

    # ── ESG summary ───────────────────────────────────────────────────────────
    all_metrics = get_esg_metrics(db, org_id=org_id, limit=None)
    scored = [m for m in all_metrics if m.score is not None]
    unscored = [m for m in all_metrics if m.score is None]
    avg_score = round(sum(m.score for m in scored) / len(scored), 2) if scored else None

    # ── Risk summary ──────────────────────────────────────────────────────────
    heatmap = get_risk_heatmap(db, org_id=org_id, status=RiskStatus.OPEN)

    # ── Compliance summary ────────────────────────────────────────────────────
    compliance = get_global_compliance_summary(db, org_id=org_id)

    # ── Sub-module averages (L2) ──────────────────────────────────────────────
    # Group categories by the 3-char prefix of their metric_code.
    # e.g. "ESU10102" → prefix "ESU" → sub-module ESU10000
    from collections import defaultdict

    cat_rows = db.execute(
        select(ESGCategory.id, ESGCategory.metric_code, ESGCategory.name)
        .where(ESGCategory.org_id == org_id, ESGCategory.metric_code.is_not(None))
    ).all()

    # Map category id → metric_code
    cat_code_map: dict[int, str] = {r.id: r.metric_code for r in cat_rows}

    # Sub-module definitions from the canonical pipeline JSON prefix convention
    SUBMODULE_NAMES: dict[str, str] = {
        "ESU": "Environmental & Sustainability Unit",
        "SSU": "Social & Safety Unit",
        "CSU": "Cybersecurity Unit",
        "GNT": "General Notes & Training",
        "CGS": "Corporate Governance Systems",
        "GRC": "Governance, Risk & Compliance",
        "ERM": "Enterprise Risk Management",
        "AUD": "Audit",
        "POL": "Policy Management",
        "REG": "Regulatory Compliance",
        "ETI": "Ethics & Integrity",
        "CGV": "Corporate Governance",
        "IGV": "Information Governance",
        "CPI": "Corporate Social Programs",
    }

    # Group scored metrics by sub-module prefix
    prefix_scores: dict[str, list[float]] = defaultdict(list)
    prefix_total: dict[str, int] = defaultdict(int)
    for m in all_metrics:
        code = cat_code_map.get(m.category_id)
        if code and len(code) >= 3:
            prefix = code[:3]
            prefix_total[prefix] += 1
            if m.score is not None:
                prefix_scores[prefix].append(m.score)

    sub_module_averages = []
    for prefix, name in SUBMODULE_NAMES.items():
        scores = prefix_scores.get(prefix, [])
        total = prefix_total.get(prefix, 0)
        avg = round(sum(scores) / len(scores), 2) if scores else None
        sub_module_averages.append({
            "sub_module_id": f"{prefix}10000",
            "sub_module_name": name,
            "average_score": avg,
            "metric_count": total,
            "scored_count": len(scores),
        })

    return {
        "org_id": org_id,
        "org_name": org_name,
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
        "sub_module_averages": sub_module_averages,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ─── Bulk Requirement Update ──────────────────────────────────────────────────

def bulk_update_requirements(
    db: Session,
    updates: list,   # list of BulkRequirementUpdate
    *,
    org_id: int,
) -> dict:
    """
    Update the status (and optionally evidence) of multiple compliance
    requirements in a single transaction.

    Only requirements belonging to the caller's org are updated.
    Requirements not found or from another org are skipped and reported.
    """
    updated = 0
    skipped = 0
    errors: list[str] = []

    for item in updates:
        req = get_requirement(db, item.id, org_id=org_id)
        if req is None:
            skipped += 1
            errors.append(
                f"Requirement id={item.id} not found in your organisation."
            )
            continue
        req.status = item.status
        if item.evidence is not None:
            req.evidence = item.evidence
        updated += 1

    if updated > 0:
        db.commit()

    logger.info(
        "Bulk requirement update: org_id=%s updated=%s skipped=%s",
        org_id, updated, skipped,
    )
    return {"updated": updated, "skipped": skipped, "errors": errors}


# ─── ESG Dashboard ────────────────────────────────────────────────────────────

def get_esg_dashboard(db: Session, *, org_id: int, org_name: str) -> dict:
    """
    Return the latest scored metric per ESG category for the dashboard.

    Two queries total regardless of category count (was N+1):
      1. All categories for the org.
      2. All metrics for those categories, ordered newest-first.
    Metrics are grouped in Python; no per-category SELECT loop.

    latest_value, latest_score, and latest_period all reference the same row:
    the most-recent scored metric when one exists, otherwise the most-recent
    unscored metric. This avoids the prior mismatch where an unscored latest
    metric produced a value from one period and a score from an earlier period.
    """
    from collections import defaultdict

    # 1. All categories (no artificial row cap)
    categories = list(db.scalars(
        select(ESGCategory)
        .where(ESGCategory.org_id == org_id)
        .order_by(ESGCategory.id)
    ).all())

    # 2. All metrics for this org in one query, newest-first per category
    all_metric_rows = list(db.scalars(
        select(ESGMetric)
        .join(ESGCategory, ESGMetric.category_id == ESGCategory.id)
        .where(ESGCategory.org_id == org_id)
        .order_by(ESGMetric.period.desc(), ESGMetric.created_at.desc())
    ).all())

    metrics_by_cat: dict[int, list] = defaultdict(list)
    for m in all_metric_rows:
        metrics_by_cat[m.category_id].append(m)

    cat_summaries = []
    total_scored = 0
    all_scores = []

    for cat in categories:
        metrics = metrics_by_cat.get(cat.id, [])
        scored_metrics = [m for m in metrics if m.score is not None]
        latest_scored = scored_metrics[0] if scored_metrics else None
        display = latest_scored if latest_scored else (metrics[0] if metrics else None)

        if latest_scored:
            total_scored += 1
            all_scores.append(latest_scored.score)

        cat_summaries.append({
            "category_id": cat.id,
            "category_name": cat.name,
            "pillar": cat.pillar.value,
            "metric_code": cat.metric_code,
            "latest_period": display.period if display else None,
            "latest_value": display.value if display else None,
            "latest_score": latest_scored.score if latest_scored else None,
            "metric_count": len(metrics),
        })

    overall_avg = round(sum(all_scores) / len(all_scores), 2) if all_scores else None

    return {
        "org_id": org_id,
        "org_name": org_name,
        "categories": cat_summaries,
        "total_categories": len(categories),
        "categories_with_data": sum(1 for s in cat_summaries if s["metric_count"] > 0),
        "categories_scored": total_scored,
        "overall_avg_score": overall_avg,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
