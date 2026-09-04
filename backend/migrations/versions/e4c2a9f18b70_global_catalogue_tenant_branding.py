"""global catalogue, outlet mappings and tenant branding

Revision ID: e4c2a9f18b70
Revises: d9e42f7a1b33
"""

from alembic import op
import sqlalchemy as sa


revision = 'e4c2a9f18b70'
down_revision = 'd9e42f7a1b33'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tenants', sa.Column('code', sa.String(32), nullable=True))
    op.add_column('tenants', sa.Column('logo_url', sa.String(512), nullable=True))
    op.add_column('tenants', sa.Column('cover_image_url', sa.String(512), nullable=True))
    op.add_column('tenants', sa.Column('primary_color', sa.String(16), nullable=False, server_default='#5A2D18'))
    op.add_column('tenants', sa.Column('secondary_color', sa.String(16), nullable=False, server_default='#C8874A'))
    op.add_column('tenants', sa.Column('tagline', sa.String(240), nullable=True))
    op.add_column('tenants', sa.Column('phone', sa.String(32), nullable=True))
    op.add_column('tenants', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('tenants', sa.Column('website', sa.String(255), nullable=True))
    op.execute("UPDATE tenants SET code = 'TEN-' || upper(substring(replace(id, '-', ''), 1, 8)) WHERE code IS NULL")
    op.create_index('ix_tenants_code', 'tenants', ['code'], unique=True)

    op.create_table(
        'global_products',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('code', sa.String(80), nullable=False),
        sa.Column('name', sa.String(180), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category_name', sa.String(160), nullable=False),
        sa.Column('base_unit', sa.String(24), nullable=False, server_default='pcs'),
        sa.Column('default_gst', sa.Numeric(5, 2), nullable=False, server_default='5.00'),
        sa.Column('image_path', sa.String(512), nullable=True),
        sa.Column('status', sa.String(24), nullable=False, server_default='ACTIVE'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_global_products_code', 'global_products', ['code'], unique=True)
    op.create_index('ix_global_products_category_name', 'global_products', ['category_name'])
    op.create_index('ix_global_products_status', 'global_products', ['status'])

    op.create_table(
        'outlet_product_mappings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('tenant_id', sa.String(36), sa.ForeignKey('tenants.id'), nullable=False),
        sa.Column('outlet_id', sa.String(36), sa.ForeignKey('outlets.id'), nullable=False),
        sa.Column('global_product_id', sa.String(36), sa.ForeignKey('global_products.id'), nullable=False),
        sa.Column('legacy_product_id', sa.String(36), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('selling_price', sa.Numeric(18, 2), nullable=False),
        sa.Column('favourite', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('kot_required', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('display_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('outlet_specific_name', sa.String(180), nullable=True),
        sa.Column('tax_override', sa.Numeric(5, 2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('outlet_id', 'global_product_id', name='uq_outlet_global_product'),
        sa.UniqueConstraint('outlet_id', 'legacy_product_id', name='uq_outlet_legacy_product'),
    )
    for column in ('tenant_id', 'outlet_id', 'global_product_id', 'legacy_product_id'):
        op.create_index(f'ix_outlet_product_mappings_{column}', 'outlet_product_mappings', [column])

    # Non-destructive bridge: use a representative legacy row as the master
    # definition, then retain each outlet's product/inventory rows unchanged.
    op.execute("""
        INSERT INTO global_products
            (id, code, name, description, category_name, base_unit, default_gst,
             image_path, status, created_at, updated_at)
        SELECT DISTINCT ON (upper(p.code))
            p.id, upper(p.code), p.name, p.description, coalesce(c.name, 'Uncategorised'),
            p.unit, p.gst_percent, p.image_path,
            CASE WHEN p.is_active THEN 'ACTIVE' ELSE 'INACTIVE' END,
            p.created_at, p.updated_at
        FROM products p
        LEFT JOIN categories c ON c.id = p.category_id
        ORDER BY upper(p.code), p.created_at
        ON CONFLICT (code) DO NOTHING
    """)
    op.execute("""
        INSERT INTO outlet_product_mappings
            (id, tenant_id, outlet_id, global_product_id, legacy_product_id,
             selling_price, favourite, kot_required, is_available, is_active,
             display_order, created_at, updated_at)
        SELECT
            substring(md5(i.id || gp.id), 1, 8) || '-' ||
            substring(md5(i.id || gp.id), 9, 4) || '-' ||
            substring(md5(i.id || gp.id), 13, 4) || '-' ||
            substring(md5(i.id || gp.id), 17, 4) || '-' ||
            substring(md5(i.id || gp.id), 21, 12),
            i.tenant_id, i.outlet_id, gp.id, p.id, p.selling_price,
            p.is_favourite, p.kot_required, p.is_available, p.is_active,
            0, p.created_at, p.updated_at
        FROM inventory i
        JOIN products p ON p.id = i.product_id AND p.tenant_id = i.tenant_id
        JOIN global_products gp ON gp.code = upper(p.code)
        ON CONFLICT (outlet_id, global_product_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('outlet_product_mappings')
    op.drop_table('global_products')
    op.drop_index('ix_tenants_code', table_name='tenants')
    for column in ('website', 'email', 'phone', 'tagline', 'secondary_color', 'primary_color', 'cover_image_url', 'logo_url', 'code'):
        op.drop_column('tenants', column)
