"""add BRAND_MODULE and MKTS_MODULE to pipelinetypeenum

The last two of the twelve business modules, both of which needed a correction
from the analytics owner before they could be built:

  - brand shipped with module_id "EBM", which matches neither
    all_module_low_performance_analysis's ^[A-Z]{4}_001$ nor labeling's
    CODE_RE, so it would have dropped out of the L0 roll-up and never been
    labelled. Praveen replaced it with BRDM_001 on 2026-08-07.
  - mkts shipped as Input_metric_values_mkts.csv with a capital I, which loads
    on Windows and fails on the Linux containers. Vendored under the lowercase
    name every other module uses.

On PostgreSQL this needs ALTER TYPE ... ADD VALUE (PG 12+ permits it inside a
transaction). On SQLite the column is a VARCHAR with a CHECK constraint rebuilt
from the ORM on create_all, so no DDL is required.

Revision ID: 20260807_brand_mkts_types
Revises: 20260806_five_module_types
Create Date: 2026-08-07
"""
from alembic import op

revision = "20260807_brand_mkts_types"
down_revision = "20260806_five_module_types"
branch_labels = None
depends_on = None

NEW_VALUES = ("BRAND_MODULE", "MKTS_MODULE")


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
