"""order service modes and payment capture audit

Revision ID: d9e42f7a1b33
Revises: c1f02d99aa10
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = 'd9e42f7a1b33'
down_revision = 'c1f02d99aa10'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('order_type', sa.String(24), nullable=False, server_default='KOT'))
    op.add_column('orders', sa.Column('service_reference', sa.String(80), nullable=True))
    op.create_index('ix_orders_order_type', 'orders', ['order_type'])
    op.add_column('payments', sa.Column('capture_source', sa.String(24), nullable=False, server_default='MANUAL'))
    op.add_column('payments', sa.Column('provider', sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column('payments', 'provider')
    op.drop_column('payments', 'capture_source')
    op.drop_index('ix_orders_order_type', table_name='orders')
    op.drop_column('orders', 'service_reference')
    op.drop_column('orders', 'order_type')
