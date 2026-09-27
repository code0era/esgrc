"""add SHARED_MODULE and BSPT_MODULE to pipelinetypeenum

Adds the SHARED_MODULE and BSPT_MODULE values to the pipelinetypeenum type so
the Shared (pipeline/tasks/shared_chain.py) and Business Partner
(pipeline/tasks/bspt_chain.py) module pipelines can be stored in
pipeline_definitions.pipeline_type. On PostgreSQL this requires
ALTER TYPE ... ADD VALUE (PG 12+ allows this inside a transaction). On SQLite
the column is a VARCHAR with a CHECK constraint rebuilt from the ORM on
create_all, so no DDL is needed here.

Mirrors 20260731_add_customer_pipeline_type, which did the same for
CUSTOMER_MODULE.

Revision ID: 20260804_shared_bspt_types
Revises: 20260731_customer_pipeline_type
Create Date: 2026-08-04
"""
from alembic import op

revision = "20260804_shared_bspt_types"
down_revision = "20260731_customer_pipeline_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS makes this idempotent; PG 12+ permits it in a transaction.
        for value in ("SHARED_MODULE", "BSPT_MODULE"):
            op.execute(
                f"ALTER TYPE pipelinetypeenum ADD VALUE IF NOT EXISTS '{value}'"
            )
    # SQLite / other: enum enforced as VARCHAR+CHECK generated from the ORM;
    # nothing to alter here.


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column. Removing these values is intentionally
    # a no-op - reversing it safely is a manual, data-dependent operation.
    pass
