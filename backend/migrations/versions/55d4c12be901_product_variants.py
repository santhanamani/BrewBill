"""product variants and order item snapshots

Revision ID: 55d4c12be901
Revises: 34ac68df019e
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = '55d4c12be901'
down_revision = '34ac68df019e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'product_variants',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('product_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('price_adjustment', sa.Numeric(18, 2), nullable=False, server_default='0.00'),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('product_id', 'name', name='uq_variant_product_name'),
    )
    op.create_index('ix_product_variants_tenant_id', 'product_variants', ['tenant_id'])
    op.create_index('ix_product_variants_product_id', 'product_variants', ['product_id'])
    op.add_column('order_items', sa.Column('variant_id', sa.String(36), nullable=True))
    op.add_column('order_items', sa.Column('variant_name', sa.String(120), nullable=True))
    op.create_foreign_key('fk_order_items_variant_id', 'order_items', 'product_variants', ['variant_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_order_items_variant_id', 'order_items', type_='foreignkey')
    op.drop_column('order_items', 'variant_name')
    op.drop_column('order_items', 'variant_id')
    op.drop_index('ix_product_variants_product_id', table_name='product_variants')
    op.drop_index('ix_product_variants_tenant_id', table_name='product_variants')
    op.drop_table('product_variants')
