"""add CUSTOMER_MODULE to pipelinetypeenum

Adds the CUSTOMER_MODULE value to the pipelinetypeenum type so the Customer
module pipeline (pipeline/tasks/customer_chain.py) can be stored in
pipeline_definitions.pipeline_type. On PostgreSQL this requires
ALTER TYPE ... ADD VALUE (PG 12+ allows this inside a transaction). On SQLite
the column is a VARCHAR with a CHECK constraint rebuilt from the ORM on
create_all, so no DDL is needed here.

Mirrors 20260703_add_super_admin_role, which does the same for user_role_enum.

Revision ID: 20260731_add_customer_pipeline_type
Revises: 20260709_apex_prompt_v2
Create Date: 2026-07-31
"""
from alembic import op

revision = "20260731_customer_pipeline_type"
down_revision = "20260709_apex_prompt_v2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS makes this idempotent; PG 12+ permits it in a transaction.
        op.execute(
            "ALTER TYPE pipelinetypeenum ADD VALUE IF NOT EXISTS 'CUSTOMER_MODULE'"
        )
    # SQLite / other: enum enforced as VARCHAR+CHECK generated from the ORM;
    # nothing to alter here.


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column. Removing 'CUSTOMER_MODULE' is intentionally
    # a no-op - reversing it safely is a manual, data-dependent operation.
    pass
