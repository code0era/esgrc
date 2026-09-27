"""add INTEGRATION_MODULE to pipelinetypeenum

The 12th and final business module. Data (input_metric_values_integration.csv
+ integration_performance_json_file.json) supplied by Praveen via Repo-01 on
2026-08-18; its module code INTG_001 was already seeded in
pipeline/llm/data/module_mapping.csv ahead of the module existing. Analytics
scripts generated from the Shared template rather than his upload - see
modules/integration/analytics_scripts/README.md.

On PostgreSQL this needs ALTER TYPE ... ADD VALUE (PG 12+ permits it inside a
transaction). On SQLite the column is a VARCHAR with a CHECK constraint rebuilt
from the ORM on create_all, so no DDL is required.

Revision ID: 20260822_add_intg_pipeline_type
Revises: 20260817_metric_code_per_org
Create Date: 2026-08-22
"""
from alembic import op

revision = "20260822_add_intg_pipeline_type"
down_revision = "20260817_metric_code_per_org"
branch_labels = None
depends_on = None

NEW_VALUES = ("INTEGRATION_MODULE",)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for value in NEW_VALUES:
            op.execute(
                f"ALTER TYPE pipelinetypeenum ADD VALUE IF NOT EXISTS '{value}'"
            )
    # SQLite / other: enum enforced as VARCHAR+CHECK generated from the ORM.


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column, so this is intentionally a no-op.
    pass
