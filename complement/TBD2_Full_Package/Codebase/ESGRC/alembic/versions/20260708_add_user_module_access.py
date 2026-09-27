"""add module_access to users (module-scoped RBAC)

Adds a per-user `module_access` JSON list holding the module keys a user may
see/act on (e.g. ["esgrc"], ["apex"]). Empty for a SUPER_ADMIN, who bypasses
module scope. Enforced by app.dependencies.auth.require_module /
allowed_pipeline_types and the pipeline + business-data routers.

Revision ID: 20260708_add_user_module_access
Revises: 20260705_add_metric_code
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa

revision = "20260708_add_user_module_access"
down_revision = "20260705_add_metric_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "module_access",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("module_access")
