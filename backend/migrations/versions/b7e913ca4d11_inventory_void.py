"""inventory ledger and invoice void metadata

Revision ID: b7e913ca4d11
Revises: a8d6c29f3170
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = 'b7e913ca4d11'
down_revision = 'a8d6c29f3170'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('orders', sa.Column('cancellation_reason', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('voided_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('orders', sa.Column('voided_by', sa.String(36), nullable=True))
    op.create_foreign_key('fk_orders_voided_by', 'orders', 'users', ['voided_by'], ['id'])
    op.create_table(
        'inventory',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False),
        sa.Column('product_id', sa.String(36), nullable=False),
        sa.Column('opening_quantity', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('stock_added', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('stock_sold', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('available_quantity', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('low_stock_limit', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.UniqueConstraint('tenant_id', 'outlet_id', 'product_id', name='uq_inventory_outlet_product'),
    )
    for column in ('tenant_id', 'outlet_id', 'product_id'):
        op.create_index(f'ix_inventory_{column}', 'inventory', [column])
    op.create_table(
        'inventory_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False),
        sa.Column('product_id', sa.String(36), nullable=False),
        sa.Column('transaction_type', sa.String(48), nullable=False),
        sa.Column('quantity_delta', sa.Numeric(18, 3), nullable=False),
        sa.Column('reference_type', sa.String(48), nullable=False),
        sa.Column('reference_id', sa.String(100), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )
    for column in ('tenant_id', 'outlet_id', 'product_id', 'transaction_type', 'reference_id', 'created_at'):
        op.create_index(f'ix_inventory_transactions_{column}', 'inventory_transactions', [column])


def downgrade() -> None:
    for column in ('created_at', 'reference_id', 'transaction_type', 'product_id', 'outlet_id', 'tenant_id'):
        op.drop_index(f'ix_inventory_transactions_{column}', table_name='inventory_transactions')
    op.drop_table('inventory_transactions')
    for column in ('product_id', 'outlet_id', 'tenant_id'):
        op.drop_index(f'ix_inventory_{column}', table_name='inventory')
    op.drop_table('inventory')
    op.drop_constraint('fk_orders_voided_by', 'orders', type_='foreignkey')
    op.drop_column('orders', 'voided_by')
    op.drop_column('orders', 'voided_at')
    op.drop_column('orders', 'cancellation_reason')
