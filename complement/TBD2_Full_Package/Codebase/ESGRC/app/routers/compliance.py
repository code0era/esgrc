"""
Compliance router - frameworks and requirements.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.crud import crud
from app.database import get_db
from app.dependencies.auth import get_current_org, require_role, require_module
from app.models.models import Organisation, UserRole
from app.models.models import ComplianceStatus
from app.schemas.schemas import (
    BulkRequirementResult,
    BulkRequirementUpdate,
    ComplianceFrameworkCreate,
    ComplianceFrameworkOut,
    ComplianceFrameworkUpdate,
    ComplianceRequirementCreate,
    ComplianceRequirementOut,
    ComplianceRequirementUpdate,
    ComplianceSummaryOut,
    ErrorDetail,
    GlobalComplianceSummaryOut,
    PaginationParams,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/compliance", tags=["Compliance"],
    dependencies=[Depends(require_module("esgrc"))],
)

DB = Annotated[Session, Depends(get_db)]
Pagination = Annotated[PaginationParams, Depends()]
CurrentOrg = Annotated[Organisation, Depends(get_current_org)]
# Write access requires ANALYST+; destructive deletes require ADMIN+.
WriteRole = Depends(require_role(UserRole.ANALYST))
AdminRole = Depends(require_role(UserRole.ADMIN))


# ── Frameworks ────────────────────────────────────────────────────────────────

@router.post(
    "/frameworks",
    response_model=ComplianceFrameworkOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Create a compliance framework",
)
def create_framework(data: ComplianceFrameworkCreate, db: DB, org: CurrentOrg) -> ComplianceFrameworkOut:
    try:
        return crud.create_framework(db, data, org_id=org.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.get(
    "/frameworks",
    response_model=list[ComplianceFrameworkOut],
    summary="List compliance frameworks",
)
def list_frameworks(
    active_only: Annotated[
        bool, Query(description="Return only active frameworks")
    ] = True,
    pagination: Pagination = ...,
    db: DB = ...,
    org: CurrentOrg = ...,
) -> list[ComplianceFrameworkOut]:
    return crud.get_frameworks(
        db, org_id=org.id, active_only=active_only, skip=pagination.skip, limit=pagination.limit
    )


@router.get(
    "/frameworks/{framework_id}",
    response_model=ComplianceFrameworkOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a single compliance framework",
)
def get_framework(framework_id: int, db: DB, org: CurrentOrg) -> ComplianceFrameworkOut:
    obj = crud.get_framework(db, framework_id, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    return obj


@router.patch(
    "/frameworks/{framework_id}",
    response_model=ComplianceFrameworkOut,
    responses={404: {"model": ErrorDetail}, 409: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Partially update a compliance framework",
)
def update_framework(
    framework_id: int, data: ComplianceFrameworkUpdate, db: DB, org: CurrentOrg
) -> ComplianceFrameworkOut:
    try:
        obj = crud.update_framework(db, framework_id, data, org_id=org.id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    return obj


@router.delete(
    "/frameworks/{framework_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorDetail}},
    dependencies=[AdminRole],
    summary="Delete a framework and its requirements",
)
def delete_framework(framework_id: int, db: DB, org: CurrentOrg) -> None:
    if not crud.delete_framework(db, framework_id, org_id=org.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get(
    "/summary",
    response_model=GlobalComplianceSummaryOut,
    summary="Global compliance summary across all active frameworks",
    description=(
        "Returns aggregated compliance counts and a compliance rate for every "
        "active framework, plus rolled-up totals across all of them. "
        "Single SQL query - no N+1 regardless of framework or requirement count."
    ),
)
def global_summary(db: DB, org: CurrentOrg) -> GlobalComplianceSummaryOut:
    return crud.get_global_compliance_summary(db, org_id=org.id)


@router.get(
    "/frameworks/{framework_id}/summary",
    response_model=ComplianceSummaryOut,
    responses={404: {"model": ErrorDetail}},
    summary="Compliance summary for a single framework",
    description=(
        "Returns total, per-status counts, and compliance_rate "
        "(compliant / total × 100, rounded to 1 dp) for the given framework. "
        "compliance_rate is 0.0 when the framework has no requirements."
    ),
)
def framework_summary(framework_id: int, db: DB, org: CurrentOrg) -> ComplianceSummaryOut:
    result = crud.get_framework_summary(db, framework_id, org_id=org.id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found"
        )
    return result


# ── Requirements ──────────────────────────────────────────────────────────────

@router.post(
    "/requirements",
    response_model=ComplianceRequirementOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Create a compliance requirement",
)
def create_requirement(data: ComplianceRequirementCreate, db: DB, org: CurrentOrg) -> ComplianceRequirementOut:
    if crud.get_framework(db, data.framework_id, org_id=org.id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Framework not found")
    return crud.create_requirement(db, data)


@router.get(
    "/requirements",
    response_model=list[ComplianceRequirementOut],
    summary="List compliance requirements",
)
def list_requirements(
    framework_id: Annotated[int | None, Query()] = None,
    status_filter: Annotated[
        ComplianceStatus | None,
        Query(alias="status", description="compliant | non_compliant | partial | not_assessed"),
    ] = None,
    pagination: Pagination = ...,
    db: DB = ...,
    org: CurrentOrg = ...,
) -> list[ComplianceRequirementOut]:
    return crud.get_requirements(
        db,
        org_id=org.id,
        framework_id=framework_id,
        status=status_filter,
        skip=pagination.skip,
        limit=pagination.limit,
    )



# ── Bulk Requirement Update ───────────────────────────────────────────────────

@router.patch(
    "/requirements/bulk",
    response_model=BulkRequirementResult,
    summary="Bulk update compliance requirement statuses",
    description=(
        "Update the status (and optionally evidence) of multiple compliance "
        "requirements in a single request. "
        "Used by the LLM agent after batch classification - reduces N PATCH calls to one. "
        "Requirements not found or belonging to another org are skipped."
    ),
    dependencies=[WriteRole],
)
def bulk_update_requirements(
    updates: list[BulkRequirementUpdate] = Body(...),
    db: DB = ...,
    org: CurrentOrg = ...,
) -> BulkRequirementResult:
    result = crud.bulk_update_requirements(db, updates, org_id=org.id)
    return BulkRequirementResult(**result)

@router.get(
    "/requirements/{req_id}",
    response_model=ComplianceRequirementOut,
    responses={404: {"model": ErrorDetail}},
    summary="Get a single compliance requirement",
)
def get_requirement(req_id: int, db: DB, org: CurrentOrg) -> ComplianceRequirementOut:
    obj = crud.get_requirement(db, req_id, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")
    return obj


@router.patch(
    "/requirements/{req_id}",
    response_model=ComplianceRequirementOut,
    responses={404: {"model": ErrorDetail}},
    dependencies=[WriteRole],
    summary="Partially update a compliance requirement",
)
def update_requirement(
    req_id: int, data: ComplianceRequirementUpdate, db: DB, org: CurrentOrg
) -> ComplianceRequirementOut:
    obj = crud.update_requirement(db, req_id, data, org_id=org.id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requirement not found")
    return obj