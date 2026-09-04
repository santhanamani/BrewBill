"""cloud order cashier and KOT queue

Revision ID: 9c81a7e4b260
Revises: f2d81339c041
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

revision = '9c81a7e4b260'
down_revision = 'f2d81339c041'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('cashier_id', sa.String(length=36), nullable=True))
    op.create_foreign_key('fk_orders_cashier_id', 'orders', 'users', ['cashier_id'], ['id'])
    op.create_index('ix_orders_cashier_id', 'orders', ['cashier_id'])
    op.create_table(
        'kot_headers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('outlet_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('kot_number', sa.String(length=80), nullable=False),
        sa.Column('station', sa.String(length=80), nullable=False, server_default='Hot Kitchen'),
        sa.Column('status', sa.String(length=24), nullable=False, server_default='NEW'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('order_id'),
        sa.UniqueConstraint('kot_number'),
    )
    op.create_index('ix_kot_headers_tenant_id', 'kot_headers', ['tenant_id'])
    op.create_index('ix_kot_headers_outlet_id', 'kot_headers', ['outlet_id'])
    op.create_index('ix_kot_headers_order_id', 'kot_headers', ['order_id'])
    op.create_index('ix_kot_headers_status', 'kot_headers', ['status'])
    op.create_table(
        'kot_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('kot_id', sa.String(length=36), nullable=False),
        sa.Column('order_item_id', sa.String(length=36), nullable=False),
        sa.Column('product_name', sa.String(length=180), nullable=False),
        sa.Column('variant_name', sa.String(length=120), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['kot_id'], ['kot_headers.id']),
        sa.ForeignKeyConstraint(['order_item_id'], ['order_items.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_kot_items_kot_id', 'kot_items', ['kot_id'])


def downgrade() -> None:
    op.drop_index('ix_kot_items_kot_id', table_name='kot_items')
    op.drop_table('kot_items')
    op.drop_index('ix_kot_headers_status', table_name='kot_headers')
    op.drop_index('ix_kot_headers_order_id', table_name='kot_headers')
    op.drop_index('ix_kot_headers_outlet_id', table_name='kot_headers')
    op.drop_index('ix_kot_headers_tenant_id', table_name='kot_headers')
    op.drop_table('kot_headers')
    op.drop_index('ix_orders_cashier_id', table_name='orders')
    op.drop_constraint('fk_orders_cashier_id', 'orders', type_='foreignkey')
    op.drop_column('orders', 'cashier_id')
