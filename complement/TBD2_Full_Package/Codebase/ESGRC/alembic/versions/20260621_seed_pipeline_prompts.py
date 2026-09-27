"""Add pipeline prompt seed data

Revision ID: 20260621_seed_pipeline_prompts
Revises: 20260620_add_pipeline_tables
Create Date: 2026-06-21

Inserts the 3 active pipeline prompt records:
  - ESGRC_MODULE_UNIFIED  (Haiku - ESGRC step 7)
  - APEX_GENERAL_RISK     (Sonnet - Apex step 6)
  - APEX_SPC_RPN          (Sonnet - Apex step 8)
"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

revision = "20260621_seed_pipeline_prompts"
down_revision = "20260620_add_pipeline_tables"
branch_labels = None
depends_on = None

# Import prompt text from the prompts module
# (alembic runs in the ESGRC/ context, so pipeline/ must be on PYTHONPATH)
def _get_prompt_text(name: str) -> str:
    # No fallback - if this import fails, the migration must fail loudly,
    # not silently seed placeholder garbage that a real client could see
    # as actual Claude prompt instructions.
    from pipeline.llm.prompts import ESGRC_MODULE_UNIFIED, APEX_GENERAL_RISK, APEX_SPC_RPN
    return {
        "ESGRC_MODULE_UNIFIED": ESGRC_MODULE_UNIFIED,
        "APEX_GENERAL_RISK": APEX_GENERAL_RISK,
        "APEX_SPC_RPN": APEX_SPC_RPN,
    }[name]


def upgrade() -> None:
    # Create the pipeline_prompts table
    op.create_table(
        "pipeline_prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, default=1),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("name", "version", name="uq_prompt_name_version"),
    )

    # Seed the 3 prompt records
    now = datetime.now(timezone.utc)
    op.bulk_insert(
        sa.table(
            "pipeline_prompts",
            sa.column("name", sa.String),
            sa.column("version", sa.Integer),
            sa.column("content", sa.Text),
            sa.column("is_active", sa.Boolean),
            sa.column("created_at", sa.TIMESTAMP),
        ),
        [
        {
            "name": "MODULE_UNIFIED",
            "version": 1,
            "content": _get_prompt_text("ESGRC_MODULE_UNIFIED"),
            "is_active": True,
            "created_at": now,
        },
        {
            "name": "GENERAL_RISK",
            "version": 1,
            "content": _get_prompt_text("APEX_GENERAL_RISK"),
            "is_active": True,
            "created_at": now,
        },
        {
            "name": "SPC_RPN",
            "version": 1,
            "content": _get_prompt_text("APEX_SPC_RPN"),
            "is_active": True,
            "created_at": now,
        },
        ],
    )


def downgrade() -> None:
    op.drop_table("pipeline_prompts")
