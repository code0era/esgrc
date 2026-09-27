"""
Risk register router.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud import crud
from app.database import get_db
from app.dependencies.auth import get_current_org, require_role, require_module
from app.models.models import Organisation, UserRole
from app.models.models import RiskLevel, RiskStatus
from app.schemas.schemas import ErrorDetail, PaginationParams, RiskCreate, RiskHeatmapOut, RiskOut, RiskUpdate

logger = logging.getLogger(__name__)

# Risk data belongs to the ESGRC module - gate the whole router by module scope
# (SUPER_ADMIN bypasses). An Apex-only user gets 403 here.
router = APIRouter(
    prefix="/risks", tags=["Risk"],
    dependencies=[Depends(require_module("esgrc"))],
)

DB = Annotated[Session, Depends(get_db)]
Pagination = Annotated[PaginationParams, Depends()]
CurrentOrg = Annotated[Organisation, Depends(get_current_org)]
# Write access requires ANALYST+; destructive deletes require ADMIN+.
# The frontend hides edit controls from viewers, but the API is the real
# security boundary - enforce role here, not just in the UI.
WriteRole = Depends(require_role(UserRole.ANALYST))
AdminRole = Depends(require_role(UserRole.ADMIN))


@router.post(
    "",
    response_model=RiskOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WriteRole],
    summary="Create a risk register entry",
)
def create_risk(data: RiskCreate, db: DB, org: CurrentOrg) -> RiskOut:
    return crud.create_risk(db, data, org_id=org.id)


@router.get(
    "",
    response_model=list[RiskOut],
    summary="List risks",
)
def list_risks(
    status_filter: Annotated[
        RiskStatus | None,
        Query(alias="status", description="open | in_progress | mitigated | closed"),
    ] = None,
    level: Annotated[
        RiskLevel | None,
        Query(description="low | medium | high | critical"),
    ] = None,
    pagination: Pagination = ...,
    db: DB = ...,
    org: CurrentOrg = ...,
) -> list[RiskOut]:
    return crud.get_risks(
        db,
        org_id=org.id,
        status=status_filter,
        level=level,
        skip=pagination.skip,
        limit=pagination.limit,
    )


@router.get(
    "/heatmap",
    response_model=RiskHeatmapOut,
    summary="5×5 risk heatmap aggregated by likelihood × impact",
    description=(
        "Returns a complete 25-cell matrix of risk counts grouped by "
        "likelihood (1–5) × impact (1–5). All 25 cells are always present - "
        "zero-count cells included - so frontends can render the full grid. "
        "Cells are ordered by risk_score descending. "
        "Risks with NULL likelihood or impact are excluded from the matrix "
        "but reported in unscored_count so nothing is silently lost."
    ),
)
def risk_heatmap(
    status_filter: Annotated[
        RiskStatus | None,
        Query(alias="status", description="Filter by status - typically 'open' for active heatmap"),
    ] = None,
    category: Annotated[
        str | None,
        Query(description="Filter by risk category"),
    ] = None,
    db: DB = ...,
    org: CurrentOrg = ...,
) -> RiskHeatmapOut:
    return crud.get_risk_heatmap(db, org_id=org.id, status=status_filter, category=category)


@router.get(
    "/{risk_id}",
    response_model=RiskOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a single risk entry",
)
def get_risk(risk_id: int, db: DB, org: CurrentOrg) -> RiskOut:
    obj = crud.get_risk(db, risk_id, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    return obj


@router.patch(
    "/{risk_id}",
    response_model=RiskOut,
    responses={404: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Partially update a risk entry",
)
def update_risk(risk_id: int, data: RiskUpdate, db: DB, org: CurrentOrg) -> RiskOut:
    obj = crud.update_risk(db, risk_id, data, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
    return obj


@router.delete(
    "/{risk_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorDetail}},
    dependencies=[AdminRole],
    summary="Delete a risk entry",
)
def delete_risk(risk_id: int, db: DB, org: CurrentOrg) -> None:
    if not crud.delete_risk(db, risk_id, org_id=org.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Risk not found")
