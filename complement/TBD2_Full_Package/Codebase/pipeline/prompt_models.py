"""
pipeline/prompt_models.py
ORM model for the pipeline_prompts table.

Separate from pipeline/models.py to keep concerns clean.
The three seed prompts (ESGRC_MODULE_UNIFIED, APEX_GENERAL_RISK, APEX_SPC_RPN)
are inserted via an Alembic data migration.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from pipeline.models import PipelineBase


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PipelinePrompt(PipelineBase):
    """
    Versioned prompt templates for Claude API calls.
    Only one version per name is active at a time.
    Updating a prompt creates a new row (version + 1) and deactivates the old one.
    The running pipeline captures prompt_hash at trigger time - version changes
    mid-run do not affect in-flight runs.
    """
    __tablename__ = "pipeline_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )

    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_prompt_name_version"),
    )

    def __repr__(self) -> str:
        return f"<PipelinePrompt name={self.name} v{self.version} active={self.is_active}>"
