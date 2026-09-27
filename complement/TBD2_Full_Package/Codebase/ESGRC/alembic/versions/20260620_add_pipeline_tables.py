"""Add pipeline tables

Revision ID: 20260620_add_pipeline_tables
Revises: 737db0c70862
Create Date: 2026-06-20 00:00:00.000000

CORRECTIONS APPLIED (against pipeline/models.py as ground truth):
1. down_revision set to 737db0c70862 (confirmed real head of ESGRC's
   5-migration chain as of 2026-06-17 read-through). VERIFY with
   `alembic heads` before running upgrade - if a 6th migration exists
   that chains off 737db0c70862, this must point at that one instead.
2. All pipeline-internal PKs/FKs (pipeline_definitions.id, pipeline_runs.id,
   pipeline_runs.pipeline_id, pipeline_step_results.id/.run_id,
   pipeline_llm_outputs.id/.run_id/.step_result_id) changed from
   postgresql.UUID(as_uuid=True) to sa.String(36), matching
   pipeline/models.py's String(36) + Python-side str(uuid.uuid4()) default.
   No server_default gen_random_uuid() since the ID is generated in Python,
   not in Postgres - server_default removed accordingly.
3. org_id (on pipeline_definitions and pipeline_runs) and triggered_by
   (on pipeline_runs) changed from postgresql.UUID(as_uuid=True) to
   sa.Integer(), matching pipeline/models.py's explicit comment that
   organisations.id and users.id are integer PKs in the ESGRC backend.
4. prompt_id FK intentionally NOT added to pipeline_llm_outputs - this
   table has no prompt_id column in pipeline/models.py, only prompt_hash.
   Open decision, not resolved here: either add prompt_id to both the
   ORM and this migration as a follow-up, or treat hash-only linkage as
   final and correct the requirements doc instead. Do not add the column
   here without updating pipeline/models.py in the same change, or the
   ORM and database will disagree again.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "20260620_add_pipeline_tables"
down_revision = "737db0c70862"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ENUM types ─────────────────────────────────────────────────────────
    # create_type=False + explicit .create(checkfirst=True): the enum is created
    # exactly once here (idempotently), and reused on the columns below so
    # op.create_table never re-emits CREATE TYPE (which fails on PostgreSQL -
    # SQLite has no CREATE TYPE, so the tests never exercised this path).
    pipeline_type_enum = postgresql.ENUM(
        "ESGRC_MODULE", "APEX_ENTERPRISE",
        name="pipelinetypeenum", create_type=False
    )
    pipeline_type_enum.create(op.get_bind(), checkfirst=True)

    run_status_enum = postgresql.ENUM(
        "PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED",
        name="runstatusenum", create_type=False
    )
    run_status_enum.create(op.get_bind(), checkfirst=True)

    step_status_enum = postgresql.ENUM(
        "PENDING", "RUNNING", "COMPLETED", "FAILED", "SKIPPED",
        name="stepstatusenum", create_type=False
    )
    step_status_enum.create(op.get_bind(), checkfirst=True)

    analysis_type_enum = postgresql.ENUM(
        "GENERAL_RISK", "SPC_RPN", "MODULE_UNIFIED",
        name="analysistypeenum", create_type=False
    )
    analysis_type_enum.create(op.get_bind(), checkfirst=True)

    # ── pipeline_definitions ───────────────────────────────────────────────
    op.create_table(
        "pipeline_definitions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.Integer(),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("pipeline_type", pipeline_type_enum, nullable=False),
        sa.Column("schedule_cron", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("config_json", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
          nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("org_id", "pipeline_type", name="uq_pipeline_def_org_type"),
    )
    op.create_index("ix_pipeline_definitions_org_id", "pipeline_definitions", ["org_id"])

    # ── pipeline_runs ──────────────────────────────────────────────────────
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pipeline_id", sa.String(36),
                  sa.ForeignKey("pipeline_definitions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", sa.Integer(),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by", sa.Integer(),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", run_status_enum,
                  nullable=False, server_default="PENDING"),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("progress_pct", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_chord_id", sa.String(255), nullable=True),
    )
    op.create_index("ix_pipeline_runs_org_status", "pipeline_runs", ["org_id", "status"])
    op.create_index("ix_pipeline_runs_pipeline_current", "pipeline_runs",
                    ["pipeline_id", "is_current"])
    op.create_index("ix_pipeline_runs_org_id", "pipeline_runs", ["org_id"])

    # ── pipeline_step_results ──────────────────────────────────────────────
    op.create_table(
        "pipeline_step_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36),
                  sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False, server_default=""),
        sa.Column("status", step_status_enum,
                  nullable=False, server_default="PENDING"),
        sa.Column("input_files_json", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("output_files_json", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.UniqueConstraint("run_id", "step_number", name="uq_step_result_run_step"),
    )
    op.create_index("ix_pipeline_step_results_run_step", "pipeline_step_results",
                    ["run_id", "step_number"])

    # ── pipeline_llm_outputs ───────────────────────────────────────────────
    op.create_table(
        "pipeline_llm_outputs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36),
                  sa.ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_result_id", sa.String(36),
                  sa.ForeignKey("pipeline_step_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_type", analysis_type_enum,
                  nullable=False),
        # NOTE: no prompt_id column - see module docstring. prompt_hash only.
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("model_used", sa.String(50), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("output_file_r2_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                  server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),      
    )
    op.create_index("ix_pipeline_llm_outputs_run_id", "pipeline_llm_outputs", ["run_id"])


def downgrade() -> None:
    op.drop_table("pipeline_llm_outputs")
    op.drop_table("pipeline_step_results")
    op.drop_table("pipeline_runs")
    op.drop_table("pipeline_definitions")

    op.execute("DROP TYPE IF EXISTS analysistypeenum")
    op.execute("DROP TYPE IF EXISTS stepstatusenum")
    op.execute("DROP TYPE IF EXISTS runstatusenum")
    op.execute("DROP TYPE IF EXISTS pipelinetypeenum")