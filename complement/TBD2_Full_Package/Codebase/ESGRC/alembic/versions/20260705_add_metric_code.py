"""add metric_code to esg_categories

The ESGCategory ORM model has had a `metric_code` column (String(20), unique,
indexed) for a long time, but no Alembic migration ever added it - the column
only existed on the create_all() path used by the tests (SQLite). On a real
Alembic-migrated PostgreSQL database the column was missing, so bulk import /
export and the org snapshot broke. This migration brings the schema in line
with the model.

Revision ID: 20260705_add_metric_code
Revises: 20260703_add_super_admin_role
Create Date: 2026-07-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260705_add_metric_code"
down_revision = "20260703_add_super_admin_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("esg_categories") as batch_op:
        batch_op.add_column(sa.Column("metric_code", sa.String(20), nullable=True))
        batch_op.create_index(
            "ix_esg_categories_metric_code", ["metric_code"], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table("esg_categories") as batch_op:
        batch_op.drop_index("ix_esg_categories_metric_code")
        batch_op.drop_column("metric_code")
