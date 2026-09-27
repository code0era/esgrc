"""
Org router - organisation-level snapshot and utility endpoints.

GET /org/snapshot
    Returns everything the dashboard and LLM agent need in a single call:
    ESG summary, risk heatmap summary, compliance rate, and per-sub-module
    averages at the L2 level (matching the pipeline's 14 sub-module hierarchy).
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.crud import crud
from app.database import get_db
from app.dependencies.auth import get_current_org, require_module
from app.models.models import Organisation
from app.schemas.schemas import OrgSnapshotOut, SubModuleSnapshotOut

logger = logging.getLogger(__name__)

# Module-gated like every other business-data router: the snapshot exposes the
# org's aggregate ESG/risk/compliance figures, so a user must hold the 'esgrc'
# module (SUPER_ADMIN bypasses). Without this, a self-registered user with empty
# module_access could read the whole org snapshot even though the sibling
# /esg, /risks and /compliance routers correctly 403 them.
router = APIRouter(
    prefix="/org",
    tags=["Organisation"],
    dependencies=[Depends(require_module("esgrc"))],
)

DB = Annotated[Session, Depends(get_db)]
CurrentOrg = Annotated[Organisation, Depends(get_current_org)]


@router.get(
    "/snapshot",
    response_model=OrgSnapshotOut,
    summary="Full organisation snapshot - dashboard and LLM agent feed",
    description=(
        "Returns ESG performance summary, risk heatmap summary, compliance rate, "
        "and average scores for all 14 ESGRC sub-modules (L2 level) in a single API call. "
        "Use this to populate the main dashboard and to feed the LLM agent context."
    ),
)
def get_snapshot(db: DB, org: CurrentOrg) -> OrgSnapshotOut:
    data = crud.get_org_snapshot(db, org_id=org.id, org_name=org.name)

    sub_modules = [
        SubModuleSnapshotOut(
            sub_module_id=sm["sub_module_id"],
            sub_module_name=sm["sub_module_name"],
            average_score=sm["average_score"],
            metric_count=sm["metric_count"],
            scored_count=sm["scored_count"],
        )
        for sm in data["sub_module_averages"]
    ]

    return OrgSnapshotOut(
        org_id=data["org_id"],
        org_name=data["org_name"],
        esg=data["esg"],
        risk=data["risk"],
        compliance=data["compliance"],
        sub_module_averages=sub_modules,
        generated_at=datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00")),
    )
