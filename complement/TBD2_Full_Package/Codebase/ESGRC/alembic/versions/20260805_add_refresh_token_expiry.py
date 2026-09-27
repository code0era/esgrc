"""add users.refresh_token_expires_at

settings.REFRESH_TOKEN_EXPIRE_DAYS existed since the initial auth work but was
never read anywhere: generate_refresh_token embeds no timestamp and
verify_and_rotate_refresh_token only compared hashes. A refresh token was
therefore valid until the user next logged in or out - indefinitely in practice,
which is the part that made theft costly.

This adds the absolute expiry that auth_crud now stamps on issue and enforces on
use. Existing rows get NULL, which the application treats as expired: everyone
with a live session logs in once more, and no credential outlives the policy.

Revision ID: 20260805_refresh_expiry
Revises: 20260805_drop_global_uniques
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "20260805_refresh_expiry"
down_revision = "20260805_drop_global_uniques"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "refresh_token_expires_at",
                sa.DateTime(timezone=True),
                nullable=True,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("refresh_token_expires_at")
