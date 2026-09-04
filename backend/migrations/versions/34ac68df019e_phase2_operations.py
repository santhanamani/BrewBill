"""phase two operational modules

Revision ID: 34ac68df019e
Revises: 9c81a7e4b260
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa

revision = '34ac68df019e'
down_revision = '9c81a7e4b260'
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    ]


def upgrade() -> None:
    op.add_column('orders', sa.Column('round_off', sa.Numeric(18, 2), nullable=False, server_default='0.00'))
    op.create_table('suppliers',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(180), nullable=False), sa.Column('contact_person', sa.String(120)),
        sa.Column('phone', sa.String(32)), sa.Column('email', sa.String(255)), sa.Column('tax_number', sa.String(64)),
        sa.Column('address', sa.Text()), sa.Column('status', sa.String(24), nullable=False, server_default='ACTIVE'), *timestamps(),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']), sa.UniqueConstraint('tenant_id', 'name', name='uq_supplier_tenant_name'))
    op.create_index('ix_suppliers_tenant_id', 'suppliers', ['tenant_id'])
    op.create_table('purchases',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False), sa.Column('supplier_id', sa.String(36), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=False), sa.Column('invoice_number', sa.String(100), nullable=False),
        sa.Column('purchase_date', sa.DateTime(timezone=True), nullable=False), sa.Column('subtotal', sa.Numeric(18, 2), nullable=False),
        sa.Column('tax', sa.Numeric(18, 2), nullable=False), sa.Column('total', sa.Numeric(18, 2), nullable=False),
        sa.Column('payment_status', sa.String(24), nullable=False), sa.Column('notes', sa.Text()), *timestamps(),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']), sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id']), sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.UniqueConstraint('tenant_id', 'invoice_number', name='uq_purchase_tenant_invoice'))
    for name, columns in [('tenant_id', ['tenant_id']), ('outlet_id', ['outlet_id']), ('supplier_id', ['supplier_id']), ('purchase_date', ['purchase_date'])]: op.create_index(f'ix_purchases_{name}', 'purchases', columns)
    op.create_table('purchase_items',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('purchase_id', sa.String(36), nullable=False),
        sa.Column('product_id', sa.String(36), nullable=False), sa.Column('product_name', sa.String(180), nullable=False),
        sa.Column('quantity', sa.Numeric(18, 3), nullable=False), sa.Column('unit_cost', sa.Numeric(18, 2), nullable=False),
        sa.Column('tax_percent', sa.Numeric(5, 2), nullable=False), sa.Column('line_total', sa.Numeric(18, 2), nullable=False),
        sa.ForeignKeyConstraint(['purchase_id'], ['purchases.id']), sa.ForeignKeyConstraint(['product_id'], ['products.id']))
    op.create_index('ix_purchase_items_purchase_id', 'purchase_items', ['purchase_id'])
    op.create_index('ix_purchase_items_product_id', 'purchase_items', ['product_id'])
    op.create_table('expenses',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False), sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('expense_date', sa.DateTime(timezone=True), nullable=False), sa.Column('category', sa.String(100), nullable=False),
        sa.Column('description', sa.String(300), nullable=False), sa.Column('amount', sa.Numeric(18, 2), nullable=False),
        sa.Column('payment_mode', sa.String(24), nullable=False), sa.Column('remarks', sa.Text()), *timestamps(),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']), sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']), sa.ForeignKeyConstraint(['created_by'], ['users.id']))
    for name in ['tenant_id', 'outlet_id', 'expense_date', 'category']: op.create_index(f'ix_expenses_{name}', 'expenses', [name])
    op.create_table('customers',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('name', sa.String(160), nullable=False), sa.Column('mobile', sa.String(32)), sa.Column('email', sa.String(255)),
        sa.Column('loyalty_points', sa.Integer(), nullable=False, server_default='0'), *timestamps(),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']), sa.UniqueConstraint('tenant_id', 'mobile', name='uq_customer_tenant_mobile'))
    op.create_index('ix_customers_tenant_id', 'customers', ['tenant_id'])
    op.create_table('daily_closings',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False), sa.Column('closed_by', sa.String(36), nullable=False),
        sa.Column('business_date', sa.String(10), nullable=False), sa.Column('order_count', sa.Integer(), nullable=False),
        sa.Column('gross_sales', sa.Numeric(18, 2), nullable=False), sa.Column('cash_sales', sa.Numeric(18, 2), nullable=False),
        sa.Column('upi_sales', sa.Numeric(18, 2), nullable=False), sa.Column('card_sales', sa.Numeric(18, 2), nullable=False),
        sa.Column('expenses', sa.Numeric(18, 2), nullable=False), sa.Column('expected_cash', sa.Numeric(18, 2), nullable=False),
        sa.Column('counted_cash', sa.Numeric(18, 2), nullable=False), sa.Column('variance', sa.Numeric(18, 2), nullable=False),
        sa.Column('status', sa.String(24), nullable=False), *timestamps(),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']), sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']), sa.ForeignKeyConstraint(['closed_by'], ['users.id']),
        sa.UniqueConstraint('tenant_id', 'outlet_id', 'business_date', name='uq_closing_outlet_date'))
    for name in ['tenant_id', 'outlet_id', 'business_date']: op.create_index(f'ix_daily_closings_{name}', 'daily_closings', [name])
    op.create_table('tenant_settings',
        sa.Column('tenant_id', sa.String(36), primary_key=True), sa.Column('setting_key', sa.String(120), primary_key=True),
        sa.Column('setting_value', sa.Text(), nullable=False), *timestamps(), sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']))
    op.create_table('held_orders',
        sa.Column('id', sa.String(36), primary_key=True), sa.Column('tenant_id', sa.String(36), nullable=False),
        sa.Column('outlet_id', sa.String(36), nullable=False), sa.Column('order_id', sa.String(36), nullable=False),
        sa.Column('cashier_id', sa.String(36), nullable=False), sa.Column('hold_number', sa.String(80), nullable=False),
        sa.Column('status', sa.String(24), nullable=False, server_default='HELD'),
        sa.Column('held_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('reopened_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']), sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']), sa.ForeignKeyConstraint(['cashier_id'], ['users.id']),
        sa.UniqueConstraint('order_id'), sa.UniqueConstraint('hold_number'))
    for name in ['tenant_id', 'outlet_id', 'order_id', 'status']: op.create_index(f'ix_held_orders_{name}', 'held_orders', [name])


def downgrade() -> None:
    for name in ['status', 'order_id', 'outlet_id', 'tenant_id']: op.drop_index(f'ix_held_orders_{name}', table_name='held_orders')
    op.drop_table('held_orders')
    op.drop_table('tenant_settings')
    for name in ['business_date', 'outlet_id', 'tenant_id']: op.drop_index(f'ix_daily_closings_{name}', table_name='daily_closings')
    op.drop_table('daily_closings')
    op.drop_index('ix_customers_tenant_id', table_name='customers'); op.drop_table('customers')
    for name in ['category', 'expense_date', 'outlet_id', 'tenant_id']: op.drop_index(f'ix_expenses_{name}', table_name='expenses')
    op.drop_table('expenses')
    op.drop_index('ix_purchase_items_product_id', table_name='purchase_items'); op.drop_index('ix_purchase_items_purchase_id', table_name='purchase_items'); op.drop_table('purchase_items')
    for name in ['purchase_date', 'supplier_id', 'outlet_id', 'tenant_id']: op.drop_index(f'ix_purchases_{name}', table_name='purchases')
    op.drop_table('purchases')
    op.drop_index('ix_suppliers_tenant_id', table_name='suppliers'); op.drop_table('suppliers')
    op.drop_column('orders', 'round_off')
