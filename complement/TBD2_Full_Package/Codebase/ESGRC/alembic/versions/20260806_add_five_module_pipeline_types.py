"""add ENTERPRISE/ICTM/PRODUCT/RESOURCE/SERVICE module pipeline types

Adds the five new module values to pipelinetypeenum so their pipelines can be
stored in pipeline_definitions.pipeline_type. These became buildable on
2026-08-06 when the analytics owner supplied input_metric_values_*.csv and
*_performance_json_file.json for each.

On PostgreSQL this needs ALTER TYPE ... ADD VALUE (PG 12+ permits it inside a
transaction). On SQLite the column is a VARCHAR with a CHECK constraint rebuilt
from the ORM on create_all, so no DDL is required.

Note ICTM_MODULE: its token is "ictm" but its module code is PRCY_001 ("IT
Processes"). Token and code differing is normal here - ESGRC is esgrc/ESRC_001.

Mirrors 20260804_add_shared_bspt_pipeline_types.

Revision ID: 20260806_five_module_types
Revises: 20260805_refresh_expiry
Create Date: 2026-08-06
"""
from alembic import op

revision = "20260806_five_module_types"
down_revision = "20260805_refresh_expiry"
branch_labels = None
depends_on = None

NEW_VALUES = (
    "ENTERPRISE_MODULE",
    "ICTM_MODULE",
    "PRODUCT_MODULE",
    "RESOURCE_MODULE",
    "SERVICE_MODULE",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS keeps this idempotent across re-runs.
        for value in NEW_VALUES:
            op.execute(
                f"ALTER TYPE pipelinetypeenum ADD VALUE IF NOT EXISTS '{value}'"
            )
    # SQLite / other: enum enforced as VARCHAR+CHECK generated from the ORM.


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column, so this is intentionally a no-op.
    pass
