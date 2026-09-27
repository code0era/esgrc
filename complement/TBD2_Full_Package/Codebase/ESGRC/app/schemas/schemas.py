"""
Pydantic v2 schemas for the ESGRC module.

Naming convention
─────────────────
  <Model>Create  - POST payload (required fields explicit)
  <Model>Update  - PATCH payload (every field Optional; CRUD uses
                   model_dump(exclude_unset=True) so explicit null clears
                   the column; exclude_none would silently drop it)
  <Model>Out     - response shape; from_attributes=True builds from ORM objects

Python 3.12 type syntax used throughout:
  X | None  instead of Optional[X]
  list[X]   instead of List[X]

Period validation
─────────────────
  ESGMetricCreate.period is validated against the pattern "^\\d{4}(-Q[1-4])?$"
  so only "YYYY" or "YYYY-QN" are accepted.
"""

import re
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.models import (
    AgentRunStatus,
    ComplianceStatus,
    ESGPillar,
    RiskLevel,
    RiskStatus,
    ScoringDirection,
    UserRole,
)

# ─── Email validation helper ──────────────────────────────────────────────────
# Lightweight, dependency-free check (avoids pulling in email-validator). Accepts
# the common local@domain.tld shape; rejects whitespace and missing @/domain.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(v: str) -> str:
    v = v.strip()
    if not _EMAIL_RE.match(v):
        raise ValueError("Invalid email address.")
    return v


# ─── Period validation helper ─────────────────────────────────────────────────

_PERIOD_RE = re.compile(r"^\d{4}(-Q[1-4])?$")


# ─── ESG Category ─────────────────────────────────────────────────────────────

class ESGCategoryCreate(BaseModel):
    name: str = Field(..., max_length=200, description="Unique category name")
    pillar: ESGPillar = Field(..., description="ESG pillar")
    description: str | None = Field(None, description="Optional longer description")
    unit: str | None = Field(None, max_length=50, description="Measurement unit, e.g. 'tonnes CO2'")
    metric_code: str | None = Field(
        None, max_length=20,
        description="Pipeline metric code e.g. 'ESU10102'. Unique globally. Used by bulk import."
    )


class ESGCategoryUpdate(BaseModel):
    """All fields optional. Only sent fields are applied (exclude_unset in CRUD)."""
    name: str | None = Field(None, max_length=200)
    description: str | None = None
    unit: str | None = Field(None, max_length=50)
    metric_code: str | None = Field(None, max_length=20, description="Pipeline metric code e.g. 'ESU10102'.")


class ESGCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    pillar: ESGPillar
    description: str | None = None
    unit: str | None = None
    metric_code: str | None = None
    created_at: datetime
    updated_at: datetime


# ─── ESG Metric ───────────────────────────────────────────────────────────────

class ESGCategoryEmbed(BaseModel):
    """Lightweight category snapshot embedded in ESGMetricOut to avoid round-trips."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    pillar: ESGPillar
    unit: str | None = None


class ESGMetricCreate(BaseModel):
    category_id: int = Field(..., gt=0, description="ID of the ESG category")
    organisation: str = Field(..., max_length=200, description="Reporting organisation")
    value: float = Field(..., description="Measured numeric value")
    period: str = Field(
        ...,
        max_length=20,
        description="Reporting period: 'YYYY' or 'YYYY-QN'",
        json_schema_extra={"example": "2024-Q1"},
    )
    notes: str | None = Field(None, description="Optional contextual notes")

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if not _PERIOD_RE.match(v):
            raise ValueError(
                f"'{v}' is not a valid period. Use 'YYYY' (e.g. '2024') "
                "or 'YYYY-QN' (e.g. '2024-Q3')."
            )
        return v


class ESGMetricUpdate(BaseModel):
    # score is deliberately NOT client-settable here. It used to accept an
    # arbitrary 0-100 value from any ANALYST+, completely bypassing
    # compute_score()/the benchmark formula that the batch agent and the LLM
    # tool both go through (app/services/scoring.py, app/agent/tools.py) -
    # a manual PATCH could silently poison it with no trace that it was
    # overridden rather than computed. Scores are set only by re-scoring
    # against the benchmark; a client can update value/notes here and get a
    # freshly computed score back through the scoring endpoints.
    value: float | None = None
    notes: str | None = None


class ESGMetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    category: ESGCategoryEmbed | None = None
    organisation: str
    value: float
    period: str
    notes: str | None = None
    score: float | None = None
    created_at: datetime
    updated_at: datetime


# ─── Risk ─────────────────────────────────────────────────────────────────────

class RiskCreate(BaseModel):
    title: str = Field(..., max_length=300)
    description: str | None = None
    category: str | None = Field(None, max_length=100, description="e.g. Operational, ESG, Regulatory")
    owner: str | None = Field(None, max_length=200)
    level: RiskLevel = Field(RiskLevel.MEDIUM, description="Inherent risk level")
    likelihood: int | None = Field(None, ge=1, le=5, description="Likelihood 1-5")
    impact: int | None = Field(None, ge=1, le=5, description="Impact 1-5")
    mitigation_plan: str | None = None
    due_date: datetime | None = None


class RiskUpdate(BaseModel):
    title: str | None = Field(None, max_length=300)
    description: str | None = None
    category: str | None = Field(None, max_length=100)
    owner: str | None = Field(None, max_length=200)
    level: RiskLevel | None = None
    status: RiskStatus | None = None
    likelihood: int | None = Field(None, ge=1, le=5)
    impact: int | None = Field(None, ge=1, le=5)
    mitigation_plan: str | None = None
    due_date: datetime | None = None


class RiskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None = None
    category: str | None = None
    owner: str | None = None
    level: RiskLevel
    status: RiskStatus
    likelihood: int | None = None
    impact: int | None = None
    risk_score: int | None = None
    mitigation_plan: str | None = None
    due_date: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ─── Compliance Framework ─────────────────────────────────────────────────────

class ComplianceFrameworkCreate(BaseModel):
    name: str = Field(..., max_length=200, description="Framework name, e.g. 'GRI Standards'")
    version: str | None = Field(None, max_length=50, description="Version, e.g. '2021'")
    description: str | None = None


class ComplianceFrameworkUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    version: str | None = Field(None, max_length=50)
    description: str | None = None
    active: bool | None = None


class ComplianceFrameworkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str | None = None
    description: str | None = None
    active: bool
    created_at: datetime
    updated_at: datetime


# ─── Compliance Requirement ───────────────────────────────────────────────────

class ComplianceRequirementCreate(BaseModel):
    framework_id: int = Field(..., gt=0)
    code: str | None = Field(None, max_length=50, description="e.g. 'GRI 302-1'")
    title: str = Field(..., max_length=300)
    description: str | None = None
    owner: str | None = Field(None, max_length=200)


class ComplianceRequirementUpdate(BaseModel):
    status: ComplianceStatus | None = None
    owner: str | None = Field(None, max_length=200)
    evidence: str | None = None
    review_date: datetime | None = None


class ComplianceRequirementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    framework_id: int
    code: str | None = None
    title: str
    description: str | None = None
    status: ComplianceStatus
    owner: str | None = None
    evidence: str | None = None
    review_date: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ─── ESG Score Benchmark ──────────────────────────────────────────────────────

class ESGScoreBenchmarkCreate(BaseModel):
    """
    Create or replace the scoring benchmark for a category.
    target_value and baseline_value must differ (non-degenerate benchmark).
    """
    category_id: int = Field(..., gt=0, description="Category to benchmark")
    target_value: float = Field(
        ..., description="Best-case value - maps to score 100"
    )
    baseline_value: float = Field(
        ..., description="Worst-case value - maps to score 0"
    )
    direction: ScoringDirection = Field(
        ScoringDirection.LOWER_IS_BETTER,
        description="lower_is_better (e.g. emissions) or higher_is_better (e.g. renewable %)",
    )

    @model_validator(mode="after")
    def target_differs_from_baseline(self) -> "ESGScoreBenchmarkCreate":
        if self.target_value == self.baseline_value:
            raise ValueError("target_value must differ from baseline_value.")
        return self


class ESGScoreBenchmarkUpdate(BaseModel):
    target_value: float | None = None
    baseline_value: float | None = None
    direction: ScoringDirection | None = None


class ESGScoreBenchmarkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    target_value: float
    baseline_value: float
    direction: ScoringDirection
    created_at: datetime
    updated_at: datetime


class ScoreResultOut(BaseModel):
    """Returned by POST /esg/metrics/{id}/score after computing a score."""
    metric_id: int
    value: float
    score: float
    benchmark_id: int
    direction: ScoringDirection


# ─── Risk Heatmap ─────────────────────────────────────────────────────────────

class RiskHeatmapCellOut(BaseModel):
    """
    A single cell in the 5x5 risk heatmap.

    likelihood and impact are both on a 1-5 scale.
    count is the number of risks at this (likelihood, impact) coordinate.
    risk_score = likelihood * impact; range 1-25.
    """
    likelihood: int   # 1-5
    impact: int       # 1-5
    risk_score: int   # likelihood * impact
    count: int        # number of risks at this cell


class RiskHeatmapOut(BaseModel):
    """
    Full 5x5 risk heatmap with summary statistics.

    cells: all 25 cells of the matrix, including zero-count cells,
           ordered by risk_score descending (highest risk first).

    unscored_count: risks excluded from the heatmap because they have
                    NULL likelihood or NULL impact. Nothing is silently lost.

    critical_zone_count: risks with likelihood >= 4 AND impact >= 4
                         (the top-right danger zone of the matrix).
    """
    cells: list[RiskHeatmapCellOut]
    total_scored: int
    unscored_count: int
    highest_risk_score: int   # max(likelihood * impact) across all non-empty cells; 0 if none
    critical_zone_count: int  # count of risks where likelihood >= 4 AND impact >= 4


# ─── Compliance Summary ───────────────────────────────────────────────────────

class ComplianceSummaryOut(BaseModel):
    """
    Aggregated compliance status for a single framework.

    compliance_rate: percentage of requirements that are COMPLIANT,
    rounded to 1 decimal place. 0.0 when total == 0.
    """
    framework_id: int
    framework_name: str
    total: int
    compliant: int
    non_compliant: int
    partial: int
    not_assessed: int
    compliance_rate: float  # 0.0 – 100.0


class GlobalComplianceSummaryOut(BaseModel):
    """
    Aggregated compliance summary across all active frameworks.
    Includes per-framework breakdown and rolled-up totals.
    """
    total_frameworks: int
    total_requirements: int
    total_compliant: int
    total_non_compliant: int
    total_partial: int
    total_not_assessed: int
    overall_compliance_rate: float  # 0.0 – 100.0
    frameworks: list[ComplianceSummaryOut]


# ─── Bulk Import ──────────────────────────────────────────────────────────────

class BulkImportRow(BaseModel):
    """
    One row in a bulk import request.
    metric_code must match a category's metric_code field (e.g. 'ESU10102').
    """
    metric_code: str = Field(..., max_length=20, description="Pipeline metric code e.g. 'ESU10102'")
    value: float = Field(..., description="Measured numeric value")
    period: str = Field(
        ..., max_length=20,
        description="Reporting period: 'YYYY' or 'YYYY-QN'",
        json_schema_extra={"example": "2024-Q1"},
    )
    organisation: str = Field(..., max_length=200, description="Reporting organisation name")
    notes: str | None = Field(None, description="Optional notes")

    @field_validator("period")
    @classmethod
    def validate_period(cls, v: str) -> str:
        if not _PERIOD_RE.match(v):
            raise ValueError(
                f"'{v}' is not a valid period. Use 'YYYY' or 'YYYY-QN'."
            )
        return v


class BulkImportResult(BaseModel):
    """Summary returned after a bulk import request."""
    imported: int = Field(..., description="Number of metric rows successfully written")
    skipped: int = Field(..., description="Rows skipped due to unknown metric_code")
    errors: list[str] = Field(default_factory=list, description="Per-row error messages for skipped rows")


class BulkRequirementUpdate(BaseModel):
    """One item in a bulk compliance requirement status update."""
    id: int = Field(..., description="Requirement ID")
    status: ComplianceStatus = Field(..., description="New compliance status")
    evidence: str | None = Field(None, description="Optional evidence note")


class BulkRequirementResult(BaseModel):
    """Summary returned after a bulk requirement update."""
    updated: int = Field(..., description="Number of requirements successfully updated")
    skipped: int = Field(..., description="Requirements not found or belonging to another org")
    errors: list[str] = Field(default_factory=list)


class ESGMetricSummary(BaseModel):
    """Latest scored metric for one category - used in the dashboard."""
    model_config = ConfigDict(from_attributes=True)
    category_id: int
    category_name: str
    pillar: ESGPillar
    metric_code: str | None = None
    latest_period: str | None = None
    latest_value: float | None = None
    latest_score: float | None = None
    metric_count: int


class ESGDashboardOut(BaseModel):
    """
    ESG dashboard - latest scored metric per category with sub-module rollup.
    Single endpoint for the frontend main screen and the LLM agent first call.
    """
    org_id: int
    org_name: str
    categories: list[ESGMetricSummary]
    total_categories: int
    categories_with_data: int
    categories_scored: int
    overall_avg_score: float | None = None
    generated_at: datetime


# ─── Org Snapshot ─────────────────────────────────────────────────────────────

class SubModuleSnapshotOut(BaseModel):
    """Average ESG performance for one sub-module (L2 level)."""
    sub_module_id: str
    sub_module_name: str
    average_score: float | None = None
    metric_count: int
    scored_count: int


class OrgSnapshotOut(BaseModel):
    """
    Full organisation snapshot - used by dashboard and LLM agent.
    Returns all key metrics in one call to avoid multiple round-trips.
    """
    org_id: int
    org_name: str
    esg: dict
    risk: dict
    compliance: dict
    sub_module_averages: list[SubModuleSnapshotOut]
    generated_at: datetime


# ─── Auth / Organisation / User ───────────────────────────────────────────────

class OrganisationCreate(BaseModel):
    name: str = Field(..., max_length=200, description="Organisation display name")
    slug: str = Field(
        ...,
        max_length=100,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
        description="URL-safe identifier, e.g. 'acme-corp'",
    )
    # Optional first-admin bootstrap. When all three are supplied, the org is
    # created together with an ADMIN user that has access to every module - the
    # only API path to mint an org's first admin. Omit them to create an empty
    # org (unchanged legacy behaviour).
    admin_email: str | None = Field(
        None, max_length=320, description="Email for the org's first admin user"
    )
    admin_full_name: str | None = Field(None, max_length=200)
    admin_password: str | None = Field(
        None, min_length=8, max_length=128,
        description="Password for the first admin (min 8 chars)"
    )

    @field_validator("admin_email")
    @classmethod
    def _valid_admin_email(cls, v: str | None) -> str | None:
        # Validate here (422) rather than letting the router build a UserRegister
        # whose validator would raise a 500 *after* the org row is committed.
        return _validate_email(v) if v else v

    @model_validator(mode="after")
    def _admin_all_or_none(self):
        provided = [self.admin_email, self.admin_full_name, self.admin_password]
        if any(provided) and not all(provided):
            raise ValueError(
                "admin_email, admin_full_name and admin_password must all be "
                "supplied together (or all omitted)."
            )
        return self


class OrganisationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    active: bool
    created_at: datetime


class UserRegister(BaseModel):
    """Payload for registering a new user within an existing organisation."""
    email: str = Field(..., max_length=320, description="User email address")
    full_name: str = Field(..., max_length=200)
    password: str = Field(..., min_length=8, max_length=128, description="Minimum 8 characters")
    organisation_slug: str = Field(
        ..., description="Slug of the organisation to join"
    )

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        return _validate_email(v)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    role: UserRole
    is_active: bool
    organisation_id: int
    module_access: list[str] = []
    created_at: datetime


class UserUpdateRole(BaseModel):
    """ADMIN-only: change a user's role within the same organisation."""
    role: UserRole


class LoginRequest(BaseModel):
    email: str = Field(..., max_length=320)
    # Capped rather than unbounded: bcrypt.checkpw silently truncates beyond
    # 72 bytes anyway, so an unbounded field only invites oversized request
    # bodies on an unauthenticated, if rate-limited, endpoint.
    password: str = Field(..., max_length=128)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        return _validate_email(v)


class TokenOut(BaseModel):
    """Response returned on successful login or token refresh."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


# ─── Agent Run Log ────────────────────────────────────────────────────────────

class AgentRunLogOut(BaseModel):
    """Response shape for a single agent batch run record."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: AgentRunStatus
    orgs_processed: int
    metrics_scored: int
    risks_escalated: int
    requirements_flagged: int
    details: str | None = None   # JSON string - parse client-side for per-org breakdown
    error_message: str | None = None


class AgentTriggerOut(BaseModel):
    """Returned immediately when a manual run is triggered."""
    message: str
    queued_at: datetime


# ─── Pagination ───────────────────────────────────────────────────────────────

class PaginationParams(BaseModel):
    """
    Shared pagination dependency.
    Usage in routes: pagination: Annotated[PaginationParams, Depends()]
    """
    skip: int = Field(0, ge=0, description="Records to skip")
    limit: int = Field(50, ge=1, le=500, description="Max records to return (cap 500)")


# ─── Error response ───────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Structured error body returned by exception handlers and 4xx responses."""
    detail: str


__all__ = [
    "ESGCategoryCreate",
    "ESGCategoryUpdate",
    "ESGCategoryOut",
    "BulkImportRow",
    "BulkImportResult",
    "BulkRequirementUpdate",
    "BulkRequirementResult",
    "ESGMetricSummary",
    "ESGDashboardOut",
    "OrgSnapshotOut",
    "SubModuleSnapshotOut",
    "ESGCategoryEmbed",
    "ESGMetricCreate",
    "ESGMetricUpdate",
    "ESGMetricOut",
    "RiskCreate",
    "RiskUpdate",
    "RiskOut",
    "ComplianceFrameworkCreate",
    "ComplianceFrameworkUpdate",
    "ComplianceFrameworkOut",
    "ComplianceRequirementCreate",
    "ComplianceRequirementUpdate",
    "ComplianceRequirementOut",
    "ESGScoreBenchmarkCreate",
    "ESGScoreBenchmarkUpdate",
    "ESGScoreBenchmarkOut",
    "ScoreResultOut",
    "RiskHeatmapCellOut",
    "RiskHeatmapOut",
    "ComplianceSummaryOut",
    "GlobalComplianceSummaryOut",
    "PaginationParams",
    "OrganisationCreate",
    "OrganisationOut",
    "UserRegister",
    "UserOut",
    "UserUpdateRole",
    "LoginRequest",
    "TokenOut",
    "RefreshRequest",
    "AgentRunLogOut",
    "AgentTriggerOut",
    "ErrorDetail",
]
