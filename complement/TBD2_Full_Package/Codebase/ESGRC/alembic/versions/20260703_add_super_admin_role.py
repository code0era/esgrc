"""add super_admin to user_role_enum

Adds the SUPER_ADMIN value to the user_role_enum type so platform owners can be
provisioned. On PostgreSQL this requires ALTER TYPE ... ADD VALUE (PG 12+ allows
this inside a transaction). On SQLite the role column is a VARCHAR with a CHECK
constraint rebuilt from the ORM on create_all, so no DDL is needed here.

Revision ID: 20260703_add_super_admin_role
Revises: 20260622_add_prompt_id_to_llm_outputs
Create Date: 2026-07-03
Revises: 20260622_add_prompt_id
"""
from alembic import op

revision = "20260703_add_super_admin_role"
down_revision = "20260622_add_prompt_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # IF NOT EXISTS makes this idempotent; PG 12+ permits it in a transaction.
        op.execute("ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'super_admin'")
    # SQLite / other: enum enforced as VARCHAR+CHECK generated from the ORM;
    # nothing to alter here.


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type without recreating it and
    # rewriting every dependent column. Removing 'super_admin' is intentionally a
    # no-op - reversing it safely is a manual, data-dependent operation.
    pass
