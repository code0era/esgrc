"""
pipeline/models.py
SQLAlchemy ORM models for the 4 pipeline tables.

FK types match the ESGRC backend (integer PKs on organisations and users).
Pipeline-internal PKs use UUID so run IDs are unguessable and safe to expose
in SSE streams and API responses.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, event,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# ── Shared base (separate from ESGRC's Base so there are no import cycles) ──
class PipelineBase(DeclarativeBase):
    pass


# ── Enums ────────────────────────────────────────────────────────────────────

class PipelineTypeEnum(str, enum.Enum):
    # Kept literal on purpose: enum members are class attributes and SQLAlchemy
    # resolves them statically, so this cannot be generated from
    # pipeline/modules.py. test_modules_registry.py asserts the two never diverge.
    ESGRC_MODULE = "ESGRC_MODULE"
    APEX_ENTERPRISE = "APEX_ENTERPRISE"
    CUSTOMER_MODULE = "CUSTOMER_MODULE"
    SHARED_MODULE = "SHARED_MODULE"
    BSPT_MODULE = "BSPT_MODULE"  # Business Partner
    ENTERPRISE_MODULE = "ENTERPRISE_MODULE"
    ICTM_MODULE = "ICTM_MODULE"  # IT Processes; module code is PRCY_001
    PRODUCT_MODULE = "PRODUCT_MODULE"
    RESOURCE_MODULE = "RESOURCE_MODULE"
    SERVICE_MODULE = "SERVICE_MODULE"
    BRAND_MODULE = "BRAND_MODULE"  # Brand Management; module code is BRDM_001
    MKTS_MODULE = "MKTS_MODULE"  # Market and Sales
    INTEGRATION_MODULE = "INTEGRATION_MODULE"  # Integration; module code is INTG_001


class RunStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class StepStatusEnum(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AnalysisTypeEnum(str, enum.Enum):
    GENERAL_RISK = "GENERAL_RISK"
    SPC_RPN = "SPC_RPN"
    MODULE_UNIFIED = "MODULE_UNIFIED"


# ── Helper ───────────────────────────────────────────────────────────────────

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Models ───────────────────────────────────────────────────────────────────

class PipelineDefinition(PipelineBase):
    """
    A reusable pipeline template scoped to one organisation.
    One org can have both an ESGRC_MODULE and an APEX_ENTERPRISE pipeline.
    config_json holds the step list, input file patterns, and combine-step
    input lists - admin-editable via PUT /prompts/{id}.
    """
    __tablename__ = "pipeline_definitions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_uuid
    )
    # Integer FK → organisations.id (ESGRC integer PK)
    # No ORM-level ForeignKey() here on purpose - organisations lives in
    # ESGRC's separate SQLAlchemy Base, not PipelineBase. An ORM FK object
    # forces SQLAlchemy to resolve "organisations" inside PipelineBase's
    # own metadata, which crashes metadata.create_all() in tests (and would
    # crash ORM flush too, per the existing cross-Base pattern). The real
    # DB-level FK constraint is created by the Alembic migration's raw DDL
    # instead, which has no ORM metadata dependency.
    org_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    pipeline_type: Mapped[PipelineTypeEnum] = mapped_column(
        Enum(PipelineTypeEnum, name="pipelinetypeenum"), nullable=False
    )
    schedule_cron: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # JSONB on PostgreSQL, JSON on SQLite (works transparently with SQLAlchemy)
    config_json: Mapped[dict] = mapped_column(
    JSON().with_variant(JSONB, "postgresql"), nullable=False, default=dict
)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now, nullable=False
    )

    # Relationships
    runs: Mapped[list["PipelineRun"]] = relationship(
        "PipelineRun", back_populates="pipeline", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("org_id", "pipeline_type", name="uq_pipeline_def_org_type"),
    )

    def __repr__(self) -> str:
        return f"<PipelineDefinition id={self.id} type={self.pipeline_type} org={self.org_id}>"


class PipelineRun(PipelineBase):
    """
    One execution of a PipelineDefinition.
    is_current=True marks the most recent successful run - used by the
    rollback endpoint to flip which run the UI displays.
    """
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pipeline_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), nullable=False
    )
    # Denormalised for fast org-scoped queries without joining pipeline_definitions
    # No ORM-level ForeignKey() - see PipelineDefinition.org_id comment above.
    org_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # NULL = scheduled run. No ORM-level ForeignKey() - same reason.
    triggered_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[RunStatusEnum] = mapped_column(
        Enum(RunStatusEnum, name="runstatusenum"),
        nullable=False,
        default=RunStatusEnum.PENDING,
        index=True,
    )
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    progress_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Root Celery task ID - used by emergency-stop to call revoke()
    celery_chord_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    pipeline: Mapped["PipelineDefinition"] = relationship(
        "PipelineDefinition", back_populates="runs"
    )
    step_results: Mapped[list["PipelineStepResult"]] = relationship(
        "PipelineStepResult", back_populates="run", cascade="all, delete-orphan",
        order_by="PipelineStepResult.step_number",
    )
    llm_outputs: Mapped[list["PipelineLLMOutput"]] = relationship(
        "PipelineLLMOutput", back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<PipelineRun id={self.id} status={self.status} org={self.org_id}>"


class PipelineStepResult(PipelineBase):
    """
    One step within a pipeline run.
    input_files_json / output_files_json hold lists of R2 key strings.
    """
    __tablename__ = "pipeline_step_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_name: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    status: Mapped[StepStatusEnum] = mapped_column(
        Enum(StepStatusEnum, name="stepstatusenum"),
        nullable=False,
        default=StepStatusEnum.PENDING,
    )
    input_files_json: Mapped[list | None] = mapped_column(
    JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    output_files_json: Mapped[list | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="step_results")
    llm_outputs: Mapped[list["PipelineLLMOutput"]] = relationship(
        "PipelineLLMOutput", back_populates="step_result", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("run_id", "step_number", name="uq_step_result_run_step"),
    )

    def __repr__(self) -> str:
        return f"<PipelineStepResult run={self.run_id} step={self.step_number} status={self.status}>"


class PipelineLLMOutput(PipelineBase):
    """
    One Claude API call result attached to a step.
    ESGRC runs produce 1 row (MODULE_UNIFIED).
    Apex runs produce 2 rows (GENERAL_RISK + SPC_RPN).
    response_text is retained in PostgreSQL even after R2 file deletion
    (GDPR erasure of R2 files does not delete this column - null it separately).
    """
    __tablename__ = "pipeline_llm_outputs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_result_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("pipeline_step_results.id", ondelete="CASCADE"), nullable=False
    )
    analysis_type: Mapped[AnalysisTypeEnum] = mapped_column(
        Enum(AnalysisTypeEnum, name="analysistypeenum"), nullable=False
    )
    # FK to the exact prompt version used - added alongside prompt_hash.
    # Both PipelineLLMOutput and PipelinePrompt live in PipelineBase, so
    # this FK has none of the cross-metadata issues organisations.id/users.id
    # have. SET NULL on delete: never lose a Claude output's history just
    # because a prompt row was hard-deleted (prompts are normally
    # deactivated, not deleted, but this is a safety net).
    prompt_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pipeline_prompts.id", ondelete="SET NULL"), nullable=True
    )
    # SHA-256 of rendered prompt - used for cache invalidation when prompt changes
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_used: Mapped[str] = mapped_column(String(50), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_file_r2_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    # Relationships
    run: Mapped["PipelineRun"] = relationship("PipelineRun", back_populates="llm_outputs")
    step_result: Mapped["PipelineStepResult"] = relationship(
        "PipelineStepResult", back_populates="llm_outputs"
    )

    def __repr__(self) -> str:
        return f"<PipelineLLMOutput run={self.run_id} type={self.analysis_type}>"
