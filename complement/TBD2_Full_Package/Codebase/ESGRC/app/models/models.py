"""
ORM models for the ESGRC module - SQLAlchemy 2.x API.

Patterns used
─────────────
- DeclarativeBase subclass: the SA 2.x recommended base class (not the
  deprecated declarative_base() function).
- Mapped[] + mapped_column(): typed column API; gives IDE inference and avoids
  the legacy Column() instrumentation path.
- server_default on ALL default values (timestamps, enums, booleans) so the
  DB enforces them regardless of how rows are inserted (ORM, raw SQL, Alembic).
- updated_at on EVERY mutable model; server_default=func.now() so it is never
  NULL on first insert; onupdate=func.now() keeps it current on every UPDATE.
- cascade="all, delete-orphan" on every one-to-many relationship.
- ondelete="CASCADE" on every FK column so referential integrity is enforced
  at the DB level independently of the ORM.
- Composite indexes on columns used in WHERE / ORDER BY clauses.
- Enums inherit (str, enum.Enum) for transparent JSON serialisation.
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class ESGPillar(str, enum.Enum):
    ENVIRONMENTAL = "environmental"
    SOCIAL = "social"
    GOVERNANCE = "governance"


class RiskLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    MITIGATED = "mitigated"
    CLOSED = "closed"


class ComplianceStatus(str, enum.Enum):
    COMPLIANT = "compliant"
    NON_COMPLIANT = "non_compliant"
    PARTIAL = "partial"
    NOT_ASSESSED = "not_assessed"


class ScoringDirection(str, enum.Enum):
    """
    Controls how a metric value maps to a 0-100 score.

    LOWER_IS_BETTER: e.g. carbon emissions - lower value = higher score.
    HIGHER_IS_BETTER: e.g. renewable energy % - higher value = higher score.
    """
    LOWER_IS_BETTER = "lower_is_better"
    HIGHER_IS_BETTER = "higher_is_better"


class UserRole(str, enum.Enum):
    """
    Role controls what a user can do within their organisation.

    SUPER_ADMIN: Platform owner - everything an ADMIN can do, plus manage
                 platform-owned resources (AI pipeline prompts). Not grantable
                 by a regular ADMIN; provisioned out-of-band.
    ADMIN:   Full access - manage users, create/edit/delete all data.
    ANALYST: Read + write all data. Cannot manage users or org settings.
    VIEWER:  Read-only access to all data.
    """
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    ANALYST = "analyst"
    VIEWER = "viewer"


# ─── Auth Models ──────────────────────────────────────────────────────────────

class Organisation(Base):
    """
    Tenant boundary. All resources (ESG, Risk, Compliance) are scoped to one
    organisation. A user belongs to exactly one organisation.
    """

    __tablename__ = "organisations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True,
        comment="URL-safe identifier, e.g. 'acme-corp'"
    )
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    users: Mapped[list["User"]] = relationship(
        "User", back_populates="organisation", cascade="all, delete-orphan"
    )


class User(Base):
    """
    Application user. Belongs to one organisation; has one role.
    Passwords are stored as bcrypt hashes - never in plaintext.
    Refresh tokens are stored as SHA-256 hashes for secure rotation.
    """

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email"),
        Index("ix_users_org_id", "organisation_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    organisation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=UserRole.ANALYST.value,
    )
    # Module-scoped access: list of module keys (e.g. ["esgrc"], ["apex"]) the
    # user may see/act on. Empty for a super_admin (who bypasses module scope and
    # sees everything). See app.dependencies.auth.MODULE_PIPELINE_TYPES.
    module_access: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1"
    )
    # Hashed refresh token - NULL when no active session.
    # Stored as a hash so a DB leak cannot be used to forge tokens.
    hashed_refresh_token: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )
    # Absolute expiry for the stored refresh token, set from
    # settings.REFRESH_TOKEN_EXPIRE_DAYS when the token is issued. The token
    # itself carries no timestamp, so without this column a stolen refresh token
    # stayed valid forever. NULL means "no usable session": sessions predating
    # this column fail closed and simply require one more login.
    refresh_token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    organisation: Mapped["Organisation"] = relationship(
        "Organisation", back_populates="users"
    )


# ─── ESG Models ───────────────────────────────────────────────────────────────

class ESGCategory(Base):
    """
    Reusable ESG measurement category, e.g. 'Carbon Emissions'.
    Scoped to a single ESG pillar. Name is unique within an organisation
    (enforced by UniqueConstraint on org_id + name).
    """

    __tablename__ = "esg_categories"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_esg_categories_org_name"),
        UniqueConstraint("org_id", "metric_code", name="uq_esg_categories_org_metric_code"),
        Index("ix_esg_categories_pillar", "pillar"),
        Index("ix_esg_categories_org_id", "org_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # External pipeline code e.g. "ESU10102" from esgrc_performance_json_file.json.
    # Used by bulk import to map CSV columns → categories without name lookups.
    # Unique PER-ORG, not globally: every org imports the same fixed set of
    # pipeline codes via the standard CSV, so a global unique constraint let
    # only the first org ever use each code - every other org's import 409'd
    # on every standard code. See uq_esg_categories_org_metric_code above.
    metric_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )
    pillar: Mapped[ESGPillar] = mapped_column(
        SAEnum(ESGPillar, name="esg_pillar_enum", values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    metrics: Mapped[list["ESGMetric"]] = relationship(
        "ESGMetric", back_populates="category", cascade="all, delete-orphan"
    )

    benchmark: Mapped["ESGScoreBenchmark | None"] = relationship(
        "ESGScoreBenchmark", back_populates="category", uselist=False,
        cascade="all, delete-orphan"
    )


class ESGMetric(Base):
    """
    A single ESG data point submitted by an organisation for a reporting period.
    The optional score (0-100) is populated by the scoring engine.
    """

    __tablename__ = "esg_metrics"
    __table_args__ = (
        Index("ix_esg_metrics_organisation", "organisation"),
        Index("ix_esg_metrics_period", "period"),
        Index("ix_esg_metrics_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("esg_categories.id", ondelete="CASCADE"), nullable=False
    )
    organisation: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    period: Mapped[str] = mapped_column(String(20), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped["ESGCategory"] = relationship(
        "ESGCategory", back_populates="metrics"
    )


# ─── ESG Scoring Benchmark ────────────────────────────────────────────────────

class ESGScoreBenchmark(Base):
    """
    Scoring benchmark for an ESG category.

    Defines the linear scale used to convert a raw metric value into a
    normalised 0-100 score.

    For HIGHER_IS_BETTER (e.g. renewable energy %):
        score = clamp((value - baseline_value) / (target_value - baseline_value) * 100, 0, 100)

    For LOWER_IS_BETTER (e.g. carbon emissions):
        score = clamp((baseline_value - value) / (baseline_value - target_value) * 100, 0, 100)

    One benchmark per category (enforced by unique=True on category_id).
    """

    __tablename__ = "esg_score_benchmarks"
    __table_args__ = (
        Index("ix_esg_score_benchmarks_category_id", "category_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    category_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("esg_categories.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one benchmark per category
    )
    target_value: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Best-case value → score 100"
    )
    baseline_value: Mapped[float] = mapped_column(
        Float, nullable=False, comment="Worst-case value → score 0"
    )
    direction: Mapped[ScoringDirection] = mapped_column(
        SAEnum(
            ScoringDirection,
            name="scoring_direction_enum",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        server_default=ScoringDirection.LOWER_IS_BETTER.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    category: Mapped["ESGCategory"] = relationship(
        "ESGCategory", back_populates="benchmark"
    )


# ─── Risk Models ──────────────────────────────────────────────────────────────

class Risk(Base):
    """
    Risk register entry.
    risk_score (computed property) = likelihood x impact on a 1-5 scale (max 25).
    """

    __tablename__ = "risks"
    __table_args__ = (
        Index("ix_risks_org_id", "org_id"),
        Index("ix_risks_status", "status"),
        Index("ix_risks_level", "level"),
        Index("ix_risks_owner", "owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    level: Mapped[RiskLevel] = mapped_column(
        SAEnum(RiskLevel, name="risk_level_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=RiskLevel.MEDIUM.value,
    )
    status: Mapped[RiskStatus] = mapped_column(
        SAEnum(RiskStatus, name="risk_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=RiskStatus.OPEN.value,
    )
    likelihood: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    impact: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mitigation_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    @property
    def risk_score(self) -> int | None:
        """
        Computed likelihood x impact score (max 25).
        Uses `is not None` guards - a falsy 0 would incorrectly return None
        with a truthiness check.
        """
        if self.likelihood is not None and self.impact is not None:
            return self.likelihood * self.impact
        return None


# ─── Compliance Models ────────────────────────────────────────────────────────

class ComplianceFramework(Base):
    """
    A compliance framework, e.g. ISO 14001, GRI Standards, TCFD, SOC 2.
    """

    __tablename__ = "compliance_frameworks"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_compliance_frameworks_org_name"),
        Index("ix_compliance_frameworks_org_id", "org_id"),
        Index("ix_compliance_frameworks_active", "active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    org_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    requirements: Mapped[list["ComplianceRequirement"]] = relationship(
        "ComplianceRequirement",
        back_populates="framework",
        cascade="all, delete-orphan",
    )


class ComplianceRequirement(Base):
    """
    A specific requirement within a compliance framework, e.g. "GRI 302-1".
    """

    __tablename__ = "compliance_requirements"
    __table_args__ = (
        Index("ix_compliance_requirements_framework_id", "framework_id"),
        Index("ix_compliance_requirements_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    framework_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("compliance_frameworks.id", ondelete="CASCADE"),
        nullable=False,
    )
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        SAEnum(ComplianceStatus, name="compliance_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=ComplianceStatus.NOT_ASSESSED.value,
    )
    owner: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    review_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    framework: Mapped["ComplianceFramework"] = relationship(
        "ComplianceFramework", back_populates="requirements"
    )


class AgentRunStatus(str, enum.Enum):
    """Status of a scheduled agent batch run."""
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"   # completed but some orgs had errors
    FAILED  = "failed"


class AgentRunLog(Base):
    """
    Audit record for every scheduled agent batch run.

    One row is written per run (not per org). The JSON `details` column
    holds a structured breakdown: counts of metrics scored, risks escalated,
    and requirements flagged per organisation.

    Keeping this in the same DB as the business data means no extra
    infrastructure and the data is queryable via standard SQL.
    """

    __tablename__ = "agent_run_logs"
    __table_args__ = (
        Index("ix_agent_run_logs_started_at", "started_at"),
        Index("ix_agent_run_logs_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(AgentRunStatus, name="agent_run_status_enum",
               values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=AgentRunStatus.RUNNING.value,
    )
    # Total counts across all orgs
    orgs_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    metrics_scored: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    risks_escalated: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    requirements_flagged: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Structured per-org breakdown stored as JSON string
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Error message if status == FAILED
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


__all__ = [
    "UserRole",
    "Organisation",
    "User",
    "ESGPillar",
    "RiskLevel",
    "RiskStatus",
    "ComplianceStatus",
    "ESGCategory",
    "ESGMetric",
    "ESGScoreBenchmark",
    "ScoringDirection",
    "Risk",
    "ComplianceFramework",
    "ComplianceRequirement",
    "AgentRunStatus",
    "AgentRunLog",
]
