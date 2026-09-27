"""Add prompt_id FK to pipeline_llm_outputs

Revision ID: 20260622_add_prompt_id
Revises: 20260621_seed_pipeline_prompts
Create Date: 2026-06-22

Adds the prompt_id column to pipeline_llm_outputs, matching the FK already
present in pipeline/models.py's PipelineLLMOutput. Nullable + ON DELETE
SET NULL, per the ORM comment: a prompt row being deactivated (the normal
path) never touches this; only a hard delete of a prompt row (not expected
in normal operation) would null it out, preserving the LLM output's history.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260622_add_prompt_id"
down_revision = "20260621_seed_pipeline_prompts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pipeline_llm_outputs") as batch_op:
        batch_op.add_column(
            sa.Column("prompt_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_pipeline_llm_outputs_prompt_id",
            "pipeline_prompts",
            ["prompt_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_pipeline_llm_outputs_prompt_id",
        "pipeline_llm_outputs",
        ["prompt_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pipeline_llm_outputs_prompt_id", table_name="pipeline_llm_outputs")
    with op.batch_alter_table("pipeline_llm_outputs") as batch_op:
        batch_op.drop_constraint("fk_pipeline_llm_outputs_prompt_id", type_="foreignkey")
        batch_op.drop_column("prompt_id")
