"""customer credit ledger and ultra professional plan

Revision ID: f4a91c73d620
Revises: e8b71a2c4d90
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'f4a91c73d620'
down_revision = 'e8b71a2c4d90'
branch_labels = None
depends_on = None


PROFESSIONAL_FEATURES = {
    'inventory': True,
    'purchases': True,
    'customer_credit': True,
    'expenses': True,
    'reports': True,
    'tenant_user_management': False,
    'marketplace_integrations': False,
    'scheduled_reports': False,
}
ULTRA_FEATURES = {
    **PROFESSIONAL_FEATURES,
    'tenant_user_management': True,
    'marketplace_integrations': True,
    'scheduled_reports': True,
}


def upgrade() -> None:
    op.add_column('orders', sa.Column('customer_id', sa.String(length=36), nullable=True))
    op.add_column(
        'orders',
        sa.Column('payment_status', sa.String(length=24), nullable=False, server_default='PAID'),
    )
    op.create_index('ix_orders_customer_id', 'orders', ['customer_id'])
    op.create_index('ix_orders_payment_status', 'orders', ['payment_status'])
    op.create_foreign_key('fk_orders_customer_id', 'orders', 'customers', ['customer_id'], ['id'])

    op.create_table(
        'customer_credit_entries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('tenant_id', sa.String(length=36), nullable=False),
        sa.Column('outlet_id', sa.String(length=36), nullable=False),
        sa.Column('customer_id', sa.String(length=36), nullable=False),
        sa.Column('order_id', sa.String(length=36), nullable=True),
        sa.Column('entry_type', sa.String(length=24), nullable=False),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('payment_mode', sa.String(length=24), nullable=True),
        sa.Column('reference', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_by', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['outlet_id'], ['outlets.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    for column in ('tenant_id', 'outlet_id', 'customer_id', 'order_id', 'entry_type', 'due_date', 'created_at'):
        op.create_index(f'ix_customer_credit_entries_{column}', 'customer_credit_entries', [column])

    professional_json = (
        "CAST(json_build_object('inventory',true,'purchases',true,'customer_credit',true,"
        "'expenses',true,'reports',true,'tenant_user_management',false,"
        "'marketplace_integrations',false,'scheduled_reports',false) AS text)"
    )
    ultra_json = (
        "CAST(json_build_object('inventory',true,'purchases',true,'customer_credit',true,"
        "'expenses',true,'reports',true,'tenant_user_management',true,"
        "'marketplace_integrations',true,'scheduled_reports',true) AS text)"
    )
    op.execute(sa.text(
        "UPDATE subscription_plans "
        f"SET name='Professional', feature_json={professional_json} "
        "WHERE code='PROFESSIONAL'"
    ))
    op.execute(sa.text(
        "INSERT INTO subscription_plans (id, code, name, max_terminals, feature_json) "
        "SELECT '00000000-0000-4000-8000-000000000002', "
        f"'ULTRA_PROFESSIONAL', 'Ultra Professional', 10, {ultra_json} "
        "WHERE NOT EXISTS (SELECT 1 FROM subscription_plans WHERE code='ULTRA_PROFESSIONAL')"
    ))


def downgrade() -> None:
    op.execute(
        "UPDATE subscriptions SET plan_id=(SELECT id FROM subscription_plans WHERE code='PROFESSIONAL') "
        "WHERE plan_id=(SELECT id FROM subscription_plans WHERE code='ULTRA_PROFESSIONAL')"
    )
    op.execute("DELETE FROM subscription_plans WHERE code='ULTRA_PROFESSIONAL'")
    for column in ('created_at', 'due_date', 'entry_type', 'order_id', 'customer_id', 'outlet_id', 'tenant_id'):
        op.drop_index(f'ix_customer_credit_entries_{column}', table_name='customer_credit_entries')
    op.drop_table('customer_credit_entries')
    op.drop_constraint('fk_orders_customer_id', 'orders', type_='foreignkey')
    op.drop_index('ix_orders_payment_status', table_name='orders')
    op.drop_index('ix_orders_customer_id', table_name='orders')
    op.drop_column('orders', 'payment_status')
    op.drop_column('orders', 'customer_id')
