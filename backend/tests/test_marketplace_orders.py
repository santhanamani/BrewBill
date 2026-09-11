import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session, settings
from app.main import app
from app.models import (
    Category,
    Inventory,
    InventoryTransaction,
    Outlet,
    OutletProductMapping,
    Product,
    Role,
    Subscription,
    SubscriptionPlan,
    Tenant,
    TenantSetting,
    User,
)


def test_marketplace_order_lifecycle_uses_outlet_price_and_audited_stock(monkeypatch) -> None:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with testing_session() as session:
        tenant = Tenant(id=str(uuid4()), code='MARKET', name='Marketplace Tenant', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MARK', name='Marketplace Outlet')
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        user = User(
            id=str(uuid4()),
            tenant_id=tenant.id,
            outlet_id=outlet.id,
            role_id=role.id,
            username='market-admin',
            display_name='Marketplace Admin',
            password_hash='not-used',
            is_active=True,
        )
        user.role = role
        plan = SubscriptionPlan(
            id=str(uuid4()),
            code='ULTRA_PROFESSIONAL',
            name='Ultra Professional',
            feature_json=json.dumps({'marketplace_integrations': True}),
        )
        subscription = Subscription(
            id=str(uuid4()),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status='ACTIVE',
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=30),
        )
        category = Category(id=str(uuid4()), tenant_id=tenant.id, code='FOOD', name='Food')
        product = Product(
            id=str(uuid4()),
            tenant_id=tenant.id,
            outlet_id=outlet.id,
            category_id=category.id,
            code='TEST_MEAL',
            name='Test Meal',
            selling_price=Decimal('90.00'),
            purchase_price=Decimal('40.00'),
            gst_percent=Decimal('5.00'),
            stock_quantity=Decimal('5.000'),
            low_stock_limit=Decimal('1.000'),
            kot_required=True,
            is_available=True,
            is_active=True,
        )
        mapping = OutletProductMapping(
            id=str(uuid4()),
            tenant_id=tenant.id,
            outlet_id=outlet.id,
            global_product_id=None,
            legacy_product_id=product.id,
            selling_price=Decimal('100.00'),
            favourite=False,
            kot_required=True,
            is_available=True,
            is_active=True,
        )
        session.add_all([
            tenant,
            outlet,
            role,
            user,
            plan,
            subscription,
            category,
            product,
            mapping,
            TenantSetting(tenant_id=tenant.id, setting_key='swiggy_enabled', setting_value='true'),
            TenantSetting(tenant_id=tenant.id, setting_key='swiggy_merchant_id', setting_value='SWG-TEST'),
        ])
        session.commit()

    def test_session():
        with testing_session() as session:
            yield session

    monkeypatch.setattr(settings, 'marketplace_mock_enabled', True)
    monkeypatch.setattr(settings, 'marketplace_connector_token', 'connector-test-token')
    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            created = client.post('/api/marketplace/mock-orders', json={'provider': 'SWIGGY'})
            assert created.status_code == 201, created.text
            order = created.json()
            assert order['merchant_id'] == 'SWG-TEST'
            assert order['subtotal'] == '100.00'
            assert order['grand_total'] == '115.00'
            assert order['estimated_profit'] == '52.00'

            accepted = client.put(
                f"/api/marketplace/orders/{order['id']}/status",
                json={'status': 'ACCEPTED'},
            )
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()['status'] == 'ACCEPTED'

            cancelled = client.put(
                f"/api/marketplace/orders/{order['id']}/status",
                json={'status': 'CANCELLED'},
            )
            assert cancelled.status_code == 200, cancelled.text
            assert cancelled.json()['status'] == 'CANCELLED'

            summary = client.get('/api/marketplace/summary')
            assert summary.status_code == 200, summary.text
            assert summary.json()['swiggy_orders'] == 1
            assert summary.json()['cancelled_orders'] == 1

            provider_order = {
                'provider': 'SWIGGY',
                'merchant_id': 'SWG-TEST',
                'outlet_code': 'MARK',
                'external_order_id': 'SWIGGY-LIVE-001',
                'customer_name': 'Provider Customer',
                'customer_phone_masked': '******4321',
                'placed_at': now.isoformat(),
                'tax': '6.00',
                'packaging_charge': '5.00',
                'commission': '20.00',
                'items': [{
                    'external_item_id': 'TEST_MEAL',
                    'product_name': 'Test Meal',
                    'quantity': 2,
                    'unit_price': '100.00',
                }],
            }
            headers = {'X-Marketplace-Connector-Token': 'connector-test-token'}
            ingested = client.post('/api/marketplace/provider-orders', json=provider_order, headers=headers)
            assert ingested.status_code == 201, ingested.text
            assert ingested.json()['grand_total'] == '211.00'
            assert ingested.json()['estimated_profit'] == '111.00'
            retried = client.post('/api/marketplace/provider-orders', json=provider_order, headers=headers)
            assert retried.status_code == 201, retried.text
            assert retried.json()['id'] == ingested.json()['id']
            assert len(client.get('/api/marketplace/orders').json()) == 2

        with testing_session() as session:
            inventory = session.scalar(select(Inventory).where(Inventory.product_id == product.id))
            assert inventory is not None
            assert inventory.available_quantity == Decimal('5.000')
            movements = list(
                session.scalars(
                    select(InventoryTransaction)
                    .where(InventoryTransaction.product_id == product.id)
                    .order_by(InventoryTransaction.created_at)
                )
            )
            assert [movement.transaction_type for movement in movements] == ['SALE', 'VOID_REVERSAL']
            assert [movement.quantity_delta for movement in movements] == [
                Decimal('-1.000'),
                Decimal('1.000'),
            ]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
