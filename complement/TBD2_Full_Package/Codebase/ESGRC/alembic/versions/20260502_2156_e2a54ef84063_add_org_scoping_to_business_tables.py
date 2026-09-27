"""add_org_scoping_to_business_tables

Revision ID: e2a54ef84063
Revises: 0c004981e01c
Create Date: 2026-05-02 21:56:05.812201+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2a54ef84063'
down_revision: Union[str, None] = '0c004981e01c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Explicit FK constraint names required by SQLite batch mode (render_as_batch=True).
    # The naming convention fk_{table}_{column}_{reftable} is used throughout.
    with op.batch_alter_table('compliance_frameworks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('org_id', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index('ix_compliance_frameworks_org_id', ['org_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_compliance_frameworks_org_id_organisations',
            'organisations', ['org_id'], ['id'], ondelete='CASCADE'
        )

    with op.batch_alter_table('esg_categories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('org_id', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index('ix_esg_categories_org_id', ['org_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_esg_categories_org_id_organisations',
            'organisations', ['org_id'], ['id'], ondelete='CASCADE'
        )

    with op.batch_alter_table('risks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('org_id', sa.Integer(), nullable=False, server_default='0'))
        batch_op.create_index('ix_risks_org_id', ['org_id'], unique=False)
        batch_op.create_foreign_key(
            'fk_risks_org_id_organisations',
            'organisations', ['org_id'], ['id'], ondelete='CASCADE'
        )


def downgrade() -> None:
    with op.batch_alter_table('risks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_risks_org_id_organisations', type_='foreignkey')
        batch_op.drop_index('ix_risks_org_id')
        batch_op.drop_column('org_id')

    with op.batch_alter_table('esg_categories', schema=None) as batch_op:
        batch_op.drop_constraint('fk_esg_categories_org_id_organisations', type_='foreignkey')
        batch_op.drop_index('ix_esg_categories_org_id')
        batch_op.drop_column('org_id')

    with op.batch_alter_table('compliance_frameworks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_compliance_frameworks_org_id_organisations', type_='foreignkey')
        batch_op.drop_index('ix_compliance_frameworks_org_id')
        batch_op.drop_column('org_id')
