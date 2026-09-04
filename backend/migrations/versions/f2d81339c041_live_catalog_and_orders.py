"""live catalog and order transaction tables

Revision ID: f2d81339c041
Revises: 7e07a7d0a4be
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa

revision = 'f2d81339c041'
down_revision = '7e07a7d0a4be'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'categories',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('code', sa.String(length=80), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('image_path', sa.String(length=512), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_category_tenant_code'),
    )
    op.create_index('ix_categories_tenant_id', 'categories', ['tenant_id'])
    op.add_column('products', sa.Column('category_id', sa.String(length=36), nullable=True))
    op.add_column('products', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('products', sa.Column('image_path', sa.String(length=512), nullable=True))
    op.add_column('products', sa.Column('unit', sa.String(length=24), nullable=False, server_default='pcs'))
    op.add_column('products', sa.Column('stock_quantity', sa.Numeric(precision=18, scale=3), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('low_stock_limit', sa.Numeric(precision=18, scale=3), nullable=False, server_default='0'))
    op.add_column('products', sa.Column('is_favourite', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('products', sa.Column('kot_required', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('products', sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column('products', sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_foreign_key('fk_products_category_id', 'products', 'categories', ['category_id'], ['id'])
    op.create_index('ix_products_category_id', 'products', ['category_id'])
    op.create_table(
        'order_items',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('product_id', sa.String(length=36), nullable=False),
        sa.Column('product_name', sa.String(length=180), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('rate', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('tax', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('line_total', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_order_items_order_id', 'order_items', ['order_id'])
    op.create_table(
        'payments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=False),
        sa.Column('payment_mode', sa.String(length=24), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('reference', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_payments_order_id', 'payments', ['order_id'])


def downgrade() -> None:
    op.drop_index('ix_payments_order_id', table_name='payments')
    op.drop_table('payments')
    op.drop_index('ix_order_items_order_id', table_name='order_items')
    op.drop_table('order_items')
    op.drop_index('ix_products_category_id', table_name='products')
    op.drop_constraint('fk_products_category_id', 'products', type_='foreignkey')
    op.drop_column('products', 'is_active')
    op.drop_column('products', 'is_available')
    op.drop_column('products', 'kot_required')
    op.drop_column('products', 'is_favourite')
    op.drop_column('products', 'low_stock_limit')
    op.drop_column('products', 'stock_quantity')
    op.drop_column('products', 'unit')
    op.drop_column('products', 'image_path')
    op.drop_column('products', 'description')
    op.drop_column('products', 'category_id')
    op.drop_index('ix_categories_tenant_id', table_name='categories')
    op.drop_table('categories')
