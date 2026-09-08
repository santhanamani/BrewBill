from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import (
    Category,
    Inventory,
    Order,
    Outlet,
    PosTerminal,
    Product,
    Role,
    Subscription,
    SubscriptionPlan,
    Tenant,
    TenantSetting,
    User,
)


def test_tenant_payment_policy_permissions_isolation_and_order_enforcement() -> None:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        platform = Tenant(id=str(uuid4()), code='PLATFORM', name='Platform', status='ACTIVE')
        tenant = Tenant(id=str(uuid4()), code='CAFE-ONE', name='Cafe One', status='ACTIVE')
        other = Tenant(id=str(uuid4()), code='CAFE-TWO', name='Cafe Two', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MAIN', name='Main')
        admin_role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Admin')
        cashier_role = Role(id=str(uuid4()), code='CASHIER', name='Cashier')
        super_role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Super Admin')
        admin = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=admin_role.id,
            username='admin', display_name='Admin', password_hash='x', is_active=True,
        )
        cashier = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=cashier_role.id,
            username='cashier', display_name='Cashier', password_hash='x', is_active=True,
        )
        super_admin = User(
            id=str(uuid4()), tenant_id=platform.id, role_id=super_role.id,
            username='owner', display_name='Owner', password_hash='x', is_active=True,
        )
        plan = SubscriptionPlan(
            id=str(uuid4()), code='POLICY', name='Policy', max_terminals=2, feature_json='{}',
        )
        subscription = Subscription(
            id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
            starts_at=datetime.now(UTC) - timedelta(days=1),
            ends_at=datetime.now(UTC) + timedelta(days=30),
        )
        terminal = PosTerminal(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id,
            terminal_code='POS01', terminal_name='Counter', device_key_hash='test', status='ACTIVE',
        )
        category = Category(id=str(uuid4()), tenant_id=tenant.id, code='COFFEE', name='Coffee')
        product = Product(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, category_id=category.id,
            code='COFFEE', name='Coffee', selling_price=Decimal('100.00'),
            purchase_price=Decimal('40.00'), gst_percent=Decimal('0.00'),
            stock_quantity=Decimal('10.000'), low_stock_limit=Decimal('1.000'),
            is_available=True, is_active=True,
        )
        session.add_all([
            platform, tenant, other, outlet, admin_role, cashier_role, super_role,
            admin, cashier, super_admin, plan, subscription, terminal, category, product,
        ])
        session.commit()
    admin.role = admin_role
    cashier.role = cashier_role
    super_admin.role = super_role

    def test_session():
        with sessions() as session:
            yield session

    def use_user(user: User) -> None:
        app.dependency_overrides[current_user] = lambda: user

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            use_user(admin)
            assert client.get('/api/payment-policy').json() == {
                'payment_processing_mode': 'MANUAL_ALLOWED'
            }
            saved = client.put('/api/payment-policy', json={
                'payment_processing_mode': 'TERMINAL_REQUIRED'
            })
            assert saved.status_code == 200, saved.text

            use_user(cashier)
            assert client.get('/api/payment-policy').json()['payment_processing_mode'] == 'TERMINAL_REQUIRED'
            assert client.put('/api/payment-policy', json={
                'payment_processing_mode': 'MANUAL_ALLOWED'
            }).status_code == 403

            manual = client.post('/api/orders', json={
                'order_id': str(uuid4()), 'terminal_code': 'POS01',
                'items': [{'product_id': product.id, 'variant_id': None, 'quantity': 1}],
                'payments': [{'mode': 'CASH', 'amount': '100.00', 'capture_source': 'MANUAL'}],
                'order_type': 'DIRECT',
            })
            assert manual.status_code == 409
            assert 'terminal-approved' in manual.json()['detail']

            approved = client.post('/api/orders', json={
                'order_id': str(uuid4()), 'terminal_code': 'POS01',
                'items': [{'product_id': product.id, 'variant_id': None, 'quantity': 1}],
                'payments': [{
                    'mode': 'CARD', 'amount': '100.00',
                    'capture_source': 'PAYMENT_TERMINAL', 'provider': 'TEST', 'reference': 'TXN-1',
                }],
                'order_type': 'DIRECT',
            })
            assert approved.status_code == 201, approved.text

            use_user(super_admin)
            assert client.get(
                f'/api/platform/admin/tenants/{other.id}/payment-policy'
            ).json()['payment_processing_mode'] == 'MANUAL_ALLOWED'
            changed = client.put(
                f'/api/platform/admin/tenants/{other.id}/payment-policy',
                json={'payment_processing_mode': 'TERMINAL_REQUIRED'},
            )
            assert changed.status_code == 200, changed.text

        with sessions() as session:
            assert session.get(TenantSetting, (tenant.id, 'payment_processing_mode')).setting_value == 'TERMINAL_REQUIRED'
            assert session.get(TenantSetting, (other.id, 'payment_processing_mode')).setting_value == 'TERMINAL_REQUIRED'
            assert session.query(Order).filter(Order.tenant_id == tenant.id).count() == 1
            inventory = session.query(Inventory).filter(
                Inventory.tenant_id == tenant.id,
                Inventory.outlet_id == outlet.id,
                Inventory.product_id == product.id,
            ).one()
            assert inventory.available_quantity == Decimal('9.000')
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
