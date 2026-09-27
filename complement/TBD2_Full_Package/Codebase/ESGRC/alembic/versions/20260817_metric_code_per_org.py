"""make esg_categories.metric_code unique per-org, not globally

metric_code was globally unique across every organisation, but every org
imports the same fixed set of pipeline codes (e.g. "ESU10102") via the
standard CSV - so only the first org to ever create a category with a given
code could use it; every other org's import 409'd on every standard code.
Composite (org_id, metric_code) is what was actually intended: the code
stays unique within an org, but the same code can exist across orgs.

Revision ID: 20260817_metric_code_per_org
Revises: 20260807_brand_mkts_types
Create Date: 2026-08-17
"""
from alembic import op

revision = "20260817_metric_code_per_org"
down_revision = "20260807_brand_mkts_types"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("esg_categories") as batch_op:
        batch_op.drop_index("ix_esg_categories_metric_code")
        batch_op.create_unique_constraint(
            "uq_esg_categories_org_metric_code", ["org_id", "metric_code"]
        )


def downgrade() -> None:
    with op.batch_alter_table("esg_categories") as batch_op:
        batch_op.drop_constraint("uq_esg_categories_org_metric_code", type_="unique")
        batch_op.create_index(
            "ix_esg_categories_metric_code", ["metric_code"], unique=True
        )
