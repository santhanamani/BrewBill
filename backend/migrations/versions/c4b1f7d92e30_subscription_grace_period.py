"""Add tenant subscription grace period.

Revision ID: c4b1f7d92e30
Revises: 6d0a9c4f2e11
"""

from alembic import op
import sqlalchemy as sa


revision = 'c4b1f7d92e30'
down_revision = '6d0a9c4f2e11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('grace_ends_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_subscriptions_grace_ends_at', 'subscriptions', ['grace_ends_at'])
    op.execute("UPDATE subscriptions SET grace_ends_at = ends_at + INTERVAL '7 days' WHERE grace_ends_at IS NULL")


def downgrade() -> None:
    op.drop_index('ix_subscriptions_grace_ends_at', table_name='subscriptions')
    op.drop_column('subscriptions', 'grace_ends_at')
