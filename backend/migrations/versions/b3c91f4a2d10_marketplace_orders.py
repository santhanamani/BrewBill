"""tenant marketplace order workflow

Revision ID: b3c91f4a2d10
Revises: f4a91c73d620
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa

revision = 'b3c91f4a2d10'
down_revision = 'f4a91c73d620'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('marketplace_orders',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('outlet_id', sa.String(36), sa.ForeignKey('outlets.id'), nullable=False),
        sa.Column('provider', sa.String(24), nullable=False),
        sa.Column('external_order_id', sa.String(100), nullable=False),
        sa.Column('merchant_id', sa.String(120), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='RECEIVED'),
        sa.Column('currency_code', sa.String(3), nullable=False, server_default='INR'),
        sa.Column('subtotal', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('tax', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('packaging_charge', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('discount', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('commission', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('grand_total', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('net_settlement', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('food_cost', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('estimated_profit', sa.Numeric(18,2), nullable=False, server_default='0'),
        sa.Column('customer_name', sa.String(120)), sa.Column('customer_phone_masked', sa.String(32)),
        sa.Column('instructions', sa.Text()), sa.Column('stock_committed', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('placed_at', sa.DateTime(timezone=True), nullable=False), sa.Column('accepted_at', sa.DateTime(timezone=True)),
        sa.Column('ready_at', sa.DateTime(timezone=True)), sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('cancelled_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id','provider','external_order_id',name='uq_marketplace_external_order'))
    for column in ('tenant_id','outlet_id','provider','status','placed_at'):
        op.create_index(f'ix_marketplace_orders_{column}', 'marketplace_orders', [column])
    op.create_table('marketplace_order_items',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('order_id', sa.String(36), sa.ForeignKey('marketplace_orders.id'), nullable=False),
        sa.Column('product_id', sa.String(36), sa.ForeignKey('products.id')),
        sa.Column('variant_id', sa.String(36), sa.ForeignKey('product_variants.id')),
        sa.Column('external_item_id', sa.String(120), nullable=False), sa.Column('product_name', sa.String(180), nullable=False),
        sa.Column('variant_name', sa.String(120)), sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(18,2), nullable=False), sa.Column('line_total', sa.Numeric(18,2), nullable=False),
        sa.Column('unit_cost', sa.Numeric(18,2), nullable=False, server_default='0'))
    op.create_index('ix_marketplace_order_items_order_id','marketplace_order_items',['order_id'])
    op.create_index('ix_marketplace_order_items_product_id','marketplace_order_items',['product_id'])


def downgrade() -> None:
    op.drop_table('marketplace_order_items')
    op.drop_table('marketplace_orders')
