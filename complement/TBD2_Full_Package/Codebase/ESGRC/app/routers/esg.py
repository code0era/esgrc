"""
ESG router - categories and metrics.

FastAPI 0.95+ Annotated[..., Depends()] pattern used for all dependencies.
Response types use lowercase list[] (Python 3.9+, we target 3.12).
"""

import io
import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.crud import crud
from app.database import get_db
from app.dependencies.auth import get_current_org, require_role, require_module
from app.models.models import ESGPillar, Organisation, UserRole

from app.schemas.schemas import (
    BulkImportResult,
    BulkImportRow,
    ESGDashboardOut,
    ESGMetricSummary,
    ESGCategoryCreate,
    ESGCategoryOut,
    ESGCategoryUpdate,
    ESGMetricCreate,
    ESGMetricOut,
    ESGMetricUpdate,
    ErrorDetail,
    PaginationParams,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/esg", tags=["ESG"],
    dependencies=[Depends(require_module("esgrc"))],
)

# Shared dependency aliases (Annotated pattern - FastAPI 0.95+ best practice)
DB = Annotated[Session, Depends(get_db)]
Pagination = Annotated[PaginationParams, Depends()]
CurrentOrg = Annotated[Organisation, Depends(get_current_org)]
# Write access requires ANALYST+; destructive deletes require ADMIN+.
WriteRole = Depends(require_role(UserRole.ANALYST))
AdminRole = Depends(require_role(UserRole.ADMIN))


# ── Categories ────────────────────────────────────────────────────────────────

@router.post(
    "/categories",
    response_model=ESGCategoryOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Create an ESG category",
)
def create_category(data: ESGCategoryCreate, db: DB, org: CurrentOrg) -> ESGCategoryOut:
    try:
        return crud.create_esg_category(db, data, org_id=org.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/categories",
    response_model=list[ESGCategoryOut],
    summary="List ESG categories",
)
def list_categories(
    pillar: Annotated[
        ESGPillar | None,
        Query(description="Filter: environmental | social | governance"),
    ] = None,
    pagination: Pagination = ...,
    db: DB = ...,
    org: CurrentOrg = ...,
) -> list[ESGCategoryOut]:
    return crud.get_esg_categories(
        db, org_id=org.id, pillar=pillar, skip=pagination.skip, limit=pagination.limit
    )


@router.get(
    "/categories/{category_id}",
    response_model=ESGCategoryOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a single ESG category",
)
def get_category(category_id: int, db: DB, org: CurrentOrg) -> ESGCategoryOut:
    obj = crud.get_esg_category(db, category_id, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return obj


@router.patch(
    "/categories/{category_id}",
    response_model=ESGCategoryOut,
    responses={404: {"model": ErrorDetail}, 409: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Partially update an ESG category",
)
def update_category(category_id: int, data: ESGCategoryUpdate, db: DB, org: CurrentOrg) -> ESGCategoryOut:
    try:
        obj = crud.update_esg_category(db, category_id, data, org_id=org.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return obj


@router.delete(
    "/categories/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorDetail}},
    dependencies=[AdminRole],
    summary="Delete an ESG category and its metrics",
)
def delete_category(category_id: int, db: DB, org: CurrentOrg) -> None:
    if not crud.delete_esg_category(db, category_id, org_id=org.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")


# ── Metrics ───────────────────────────────────────────────────────────────────

@router.post(
    "/metrics",
    response_model=ESGMetricOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Submit an ESG metric data point",
)
def submit_metric(data: ESGMetricCreate, db: DB, org: CurrentOrg) -> ESGMetricOut:
    if crud.get_esg_category(db, data.category_id, org_id=org.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ESG category not found")
    return crud.create_esg_metric(db, data, org_name=org.name)


@router.get(
    "/metrics",
    response_model=list[ESGMetricOut],
    summary="List ESG metrics",
)
def list_metrics(
    organisation: Annotated[str | None, Query()] = None,
    category_id: Annotated[int | None, Query()] = None,
    period: Annotated[str | None, Query(description="e.g. '2024-Q1'")] = None,
    pagination: Pagination = ...,
    db: DB = ...,
    org: CurrentOrg = ...,
) -> list[ESGMetricOut]:
    return crud.get_esg_metrics(
        db,
        org_id=org.id,
        organisation=organisation,
        category_id=category_id,
        period=period,
        skip=pagination.skip,
        limit=pagination.limit,
    )


@router.get(
    "/metrics/{metric_id}",
    response_model=ESGMetricOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a single ESG metric",
)
def get_metric(metric_id: int, db: DB, org: CurrentOrg) -> ESGMetricOut:
    obj = crud.get_esg_metric(db, metric_id, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric not found")
    return obj


@router.patch(
    "/metrics/{metric_id}",
    response_model=ESGMetricOut,
    responses={404: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Partially update an ESG metric",
)
def update_metric(metric_id: int, data: ESGMetricUpdate, db: DB, org: CurrentOrg) -> ESGMetricOut:
    obj = crud.update_esg_metric(db, metric_id, data, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Metric not found")
    return obj



# ── ESG Dashboard ─────────────────────────────────────────────────────────────

@router.get(
    "/dashboard",
    response_model=ESGDashboardOut,
    summary="ESG dashboard - latest score per category with org-level aggregates",
    description=(
        "Returns the latest scored metric for every ESG category in one call. "
        "Use this for the frontend dashboard screen and as the LLM agent's first "
        "context call - replaces multiple individual metric lookups."
    ),
)
def get_dashboard(db: DB, org: CurrentOrg) -> ESGDashboardOut:
    data = crud.get_esg_dashboard(db, org_id=org.id, org_name=org.name)
    from datetime import datetime
    categories = [ESGMetricSummary(**c) for c in data["categories"]]
    return ESGDashboardOut(
        org_id=data["org_id"],
        org_name=data["org_name"],
        categories=categories,
        total_categories=data["total_categories"],
        categories_with_data=data["categories_with_data"],
        categories_scored=data["categories_scored"],
        overall_avg_score=data["overall_avg_score"],
        generated_at=datetime.fromisoformat(
            data["generated_at"].replace("Z", "+00:00")
        ),
    )


# ── Bulk Import ───────────────────────────────────────────────────────────────

@router.post(
    "/import",
    response_model=BulkImportResult,
    status_code=status.HTTP_200_OK,
    summary="Bulk import ESG metric rows from pipeline CSV data",
    description=(
        "Import multiple ESG metric rows in one call. "
        "Each row must include a metric_code matching a category configured in your org. "
        "Rows with unknown metric_codes are skipped and reported in the errors list."
    ),
    dependencies=[WriteRole],
)
def bulk_import(
    rows: list[BulkImportRow] = Body(...),
    db: DB = ...,
    org: CurrentOrg = ...,
) -> BulkImportResult:
    result = crud.bulk_import_metrics(db, rows, org_id=org.id)
    return BulkImportResult(**result)


# ── CSV Export ────────────────────────────────────────────────────────────────

@router.get(
    "/export",
    summary="Export ESG metrics as CSV (pipeline-compatible format)",
    description=(
        "Returns a CSV file where columns are metric codes (e.g. ESU10102) "
        "and rows are period/organisation combinations. "
        "This matches the input_metric_values_esgrc.csv format consumed by the ML pipeline scripts."
    ),
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "CSV file download",
        }
    },
)
def export_csv(
    period: str | None = None,
    db: DB = ...,
    org: CurrentOrg = ...,
):
    csv_content = crud.export_metrics_csv(db, org_id=org.id, period=period)
    filename = f"esg_metrics_{org.slug}.csv"
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
