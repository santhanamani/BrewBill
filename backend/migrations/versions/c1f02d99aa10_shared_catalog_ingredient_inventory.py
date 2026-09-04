"""shared catalogue and outlet ingredient inventory

Revision ID: c1f02d99aa10
Revises: b7e913ca4d11
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa

revision = 'c1f02d99aa10'
down_revision = 'b7e913ca4d11'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ingredients',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('code', sa.String(80), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('category', sa.String(120), nullable=False),
        sa.Column('unit', sa.String(24), nullable=False),
        sa.Column('image_path', sa.String(512), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.UniqueConstraint('tenant_id', 'code', name='uq_ingredient_tenant_code'),
    )
    op.create_index('ix_ingredients_tenant_id', 'ingredients', ['tenant_id'])
    op.create_table(
        'ingredient_stocks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False),
        sa.Column('ingredient_id', sa.String(36), nullable=False),
        sa.Column('opening_quantity', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('stock_added', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('stock_used', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('available_quantity', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('low_stock_limit', sa.Numeric(18, 3), nullable=False, server_default='0.000'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id']),
        sa.UniqueConstraint('tenant_id', 'outlet_id', 'ingredient_id', name='uq_ingredient_stock_outlet_item'),
    )
    for column in ('tenant_id', 'outlet_id', 'ingredient_id'):
        op.create_index(f'ix_ingredient_stocks_{column}', 'ingredient_stocks', [column])
    op.create_table(
        'ingredient_transactions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False),
        sa.Column('ingredient_id', sa.String(36), nullable=False),
        sa.Column('transaction_type', sa.String(48), nullable=False),
        sa.Column('quantity_delta', sa.Numeric(18, 3), nullable=False),
        sa.Column('balance_after', sa.Numeric(18, 3), nullable=False),
        sa.Column('reference', sa.String(120), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['ingredient_id'], ['ingredients.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
    )
    for column in ('tenant_id', 'outlet_id', 'ingredient_id', 'transaction_type', 'created_at'):
        op.create_index(f'ix_ingredient_transactions_{column}', 'ingredient_transactions', [column])

    # Existing menu rows become tenant-shared. Their former product stock is
    # copied into a separate balance for every existing tenant outlet.
    op.execute(sa.text("""
        INSERT INTO inventory (
            id, tenant_id, outlet_id, product_id, opening_quantity,
            stock_added, stock_sold, available_quantity, low_stock_limit
        )
        SELECT
            substr(md5(p.id || o.id), 1, 8) || '-' || substr(md5(p.id || o.id), 9, 4) || '-' ||
            substr(md5(p.id || o.id), 13, 4) || '-' || substr(md5(p.id || o.id), 17, 4) || '-' ||
            substr(md5(p.id || o.id), 21, 12),
            p.tenant_id, o.id, p.id, p.stock_quantity, 0, 0, p.stock_quantity, p.low_stock_limit
        FROM products p
        JOIN outlets o ON o.tenant_id = p.tenant_id
        WHERE NOT EXISTS (
            SELECT 1 FROM inventory i
            WHERE i.tenant_id = p.tenant_id AND i.outlet_id = o.id AND i.product_id = p.id
        )
    """))
    op.execute(sa.text('UPDATE products SET outlet_id = NULL'))


def downgrade() -> None:
    for column in ('created_at', 'transaction_type', 'ingredient_id', 'outlet_id', 'tenant_id'):
        op.drop_index(f'ix_ingredient_transactions_{column}', table_name='ingredient_transactions')
    op.drop_table('ingredient_transactions')
    for column in ('ingredient_id', 'outlet_id', 'tenant_id'):
        op.drop_index(f'ix_ingredient_stocks_{column}', table_name='ingredient_stocks')
    op.drop_table('ingredient_stocks')
    op.drop_index('ix_ingredients_tenant_id', table_name='ingredients')
    op.drop_table('ingredients')
