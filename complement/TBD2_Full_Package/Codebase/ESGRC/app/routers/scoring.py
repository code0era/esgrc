"""
ESG Scoring router.

Endpoints
─────────
POST /esg/benchmarks              - create or replace a category benchmark
GET  /esg/benchmarks/{id}         - get benchmark by ID
GET  /esg/categories/{id}/benchmark - get benchmark for a category
PATCH /esg/benchmarks/{id}        - partially update a benchmark
POST /esg/metrics/{id}/score      - compute and persist score for a metric
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crud import crud
from app.database import get_db
from app.dependencies.auth import get_current_org, require_role, require_module
from app.models.models import Organisation, UserRole
from app.schemas.schemas import (
    ErrorDetail,
    ESGScoreBenchmarkCreate,
    ESGScoreBenchmarkOut,
    ESGScoreBenchmarkUpdate,
    ScoreResultOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/esg", tags=["ESG Scoring"],
    dependencies=[Depends(require_module("esgrc"))],
)

DB = Annotated[Session, Depends(get_db)]
CurrentOrg = Annotated[Organisation, Depends(get_current_org)]
# Write access requires ANALYST+.
WriteRole = Depends(require_role(UserRole.ANALYST))


# ── Benchmarks ────────────────────────────────────────────────────────────────

@router.post(
    "/benchmarks",
    response_model=ESGScoreBenchmarkOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorDetail}, 409: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Create or replace the scoring benchmark for a category",
)
def create_or_replace_benchmark(
    data: ESGScoreBenchmarkCreate, db: DB, org: CurrentOrg
) -> ESGScoreBenchmarkOut:
    # Verify the category exists AND belongs to the caller's org
    if crud.get_esg_category(db, data.category_id, org_id=org.id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ESG category {data.category_id} not found.",
        )
    try:
        return crud.create_or_replace_benchmark(db, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/benchmarks/{benchmark_id}",
    response_model=ESGScoreBenchmarkOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a benchmark by ID",
)
def get_benchmark(benchmark_id: int, db: DB, org: CurrentOrg) -> ESGScoreBenchmarkOut:
    obj = crud.get_benchmark(db, benchmark_id)
    # Benchmarks have no org_id column - they are tenant-scoped only via their
    # category. Verify the category belongs to the caller's org; otherwise 404
    # (do not reveal another tenant's benchmark). Prevents cross-org IDOR.
    if obj is None or crud.get_esg_category(db, obj.category_id, org_id=org.id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found"
        )
    return obj


@router.get(
    "/categories/{category_id}/benchmark",
    response_model=ESGScoreBenchmarkOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get the scoring benchmark for a category",
)
def get_benchmark_for_category(category_id: int, db: DB, org: CurrentOrg) -> ESGScoreBenchmarkOut:
    if crud.get_esg_category(db, category_id, org_id=org.id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="ESG category not found"
        )
    obj = crud.get_benchmark_by_category(db, category_id)
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No benchmark configured for category {category_id}.",
        )
    return obj


@router.patch(
    "/benchmarks/{benchmark_id}",
    response_model=ESGScoreBenchmarkOut,
    responses={404: {"model": ErrorDetail}, 422: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Partially update a scoring benchmark",
)
def update_benchmark(
    benchmark_id: int, data: ESGScoreBenchmarkUpdate, db: DB, org: CurrentOrg
) -> ESGScoreBenchmarkOut:
    # Tenant-scope via the benchmark's category before allowing any update.
    existing = crud.get_benchmark(db, benchmark_id)
    if existing is None or crud.get_esg_category(db, existing.category_id, org_id=org.id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found"
        )
    try:
        obj = crud.update_benchmark(db, benchmark_id, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Benchmark not found"
        )
    return obj


# ── Scoring ───────────────────────────────────────────────────────────────────

@router.post(
    "/metrics/{metric_id}/score",
    response_model=ScoreResultOut,
    responses={
        404: {"model": ErrorDetail},
        422: {"model": ErrorDetail},
    },
    summary="Compute and persist a score for an ESG metric",
    description=(
        "Looks up the scoring benchmark for the metric's category, applies the "
        "linear interpolation formula, clamps the result to [0, 100], stores it "
        "on the metric, and returns the score result."
    ),
    dependencies=[WriteRole],
)
def score_metric(metric_id: int, db: DB, org: CurrentOrg) -> ScoreResultOut:
    try:
        result = crud.apply_score_to_metric(db, metric_id, org_id=org.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Metric not found"
        )

    metric, benchmark = result
    return ScoreResultOut(
        metric_id=metric.id,
        value=metric.value,
        score=metric.score,
        benchmark_id=benchmark.id,
        direction=benchmark.direction,
    )
