from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import (
    Category,
    InventoryTransaction,
    Outlet,
    PosTerminal,
    Product,
    ProductVariant,
    Role,
    Subscription,
    SubscriptionPlan,
    Tenant,
    User,
)


def test_order_is_listed_and_creates_a_kot() -> None:
    engine = create_engine(
        'sqlite+pysqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as session:
        tenant = Tenant(id=str(uuid4()), name='Test Tenant', status='ACTIVE')
        plan = SubscriptionPlan(
            id=str(uuid4()), code='TEST', name='Test Plan', max_terminals=2, feature_json='{}'
        )
        subscription = Subscription(
            id=str(uuid4()),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status='ACTIVE',
            starts_at=datetime.now(UTC) - timedelta(days=1),
            ends_at=datetime.now(UTC) + timedelta(days=30),
        )
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='TEST', name='Test Outlet')
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        user = User(
            id=str(uuid4()),
            tenant_id=tenant.id,
            outlet_id=outlet.id,
            role_id=role.id,
            username='tester',
            display_name='Test Cashier',
            password_hash='not-used',
            is_active=True,
        )
        terminal = PosTerminal(
            id=str(uuid4()),
            tenant_id=tenant.id,
            outlet_id=outlet.id,
            terminal_code='POS01',
            terminal_name='Test POS',
            device_key_hash='test-device',
            status='ACTIVE',
        )
        category = Category(id=str(uuid4()), tenant_id=tenant.id, code='COFFEE', name='Coffee')
        product = Product(
            id=str(uuid4()),
            tenant_id=tenant.id,
            outlet_id=outlet.id,
            category_id=category.id,
            code='FILTER_COFFEE',
            name='Filter Coffee',
            selling_price=Decimal('40.00'),
            purchase_price=Decimal('18.00'),
            gst_percent=Decimal('5.00'),
            stock_quantity=Decimal('10.000'),
            low_stock_limit=Decimal('2.000'),
            kot_required=True,
            is_available=True,
            is_active=True,
        )
        variant = ProductVariant(
            id=str(uuid4()),
            tenant_id=tenant.id,
            product_id=product.id,
            name='Large',
            price_adjustment=Decimal('10.00'),
            display_order=1,
            is_active=True,
        )
        session.add_all(
            [tenant, plan, subscription, outlet, role, user, terminal, category, product, variant]
        )
        session.commit()
    user.role = role

    def test_session():
        with TestingSession() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            held_response = client.post(
                '/api/holds',
                json={
                    'terminal_code': 'POS01',
                    'items': [{'product_id': product.id, 'variant_id': variant.id, 'quantity': 1}],
                },
            )
            assert held_response.status_code == 201, held_response.text
            held = held_response.json()
            assert held['items'][0]['product_name'] == 'Filter Coffee'
            assert held['items'][0]['variant_name'] == 'Large'
            assert client.get('/api/holds').json()[0]['hold_number'] == held['hold_number']

            cancelled_response = client.post(
                '/api/holds',
                json={
                    'terminal_code': 'POS01',
                    'items': [{'product_id': product.id, 'variant_id': None, 'quantity': 1}],
                },
            )
            assert cancelled_response.status_code == 201
            cancelled_id = cancelled_response.json()['id']
            assert client.delete(f'/api/holds/{cancelled_id}').status_code == 204
            assert all(row['id'] != cancelled_id for row in client.get('/api/holds').json())

            response = client.post(
                '/api/orders',
                json={
                    'order_id': str(uuid4()),
                    'terminal_code': 'POS01',
                    'items': [{'product_id': product.id, 'variant_id': variant.id, 'quantity': 2}],
                    'payments': [
                        {'mode': 'CASH', 'amount': '30.00'},
                        {'mode': 'UPI', 'amount': '65.00'},
                    ],
                    'held_order_id': held['id'],
                    'discount_percent': '10.00',
                },
            )
            assert response.status_code == 201, response.text
            assert response.json()['grand_total'] == '95.00'
            assert response.json()['invoice_number'].startswith('BH-TEST-POS01-')
            assert client.get('/api/holds').json() == []

            orders = client.get('/api/orders')
            assert orders.status_code == 200
            assert orders.json()[0]['cashier_name'] == 'Test Cashier'
            assert orders.json()[0]['item_count'] == 2
            assert orders.json()[0]['items'][0]['product_name'] == 'Filter Coffee'

            kots = client.get('/api/kot')
            assert kots.status_code == 200
            ticket = kots.json()[0]
            assert ticket['items'][0]['product_name'] == 'Filter Coffee'
            assert ticket['items'][0]['variant_name'] == 'Large'
            assert ticket['status'] == 'NEW'

            started = client.patch(f"/api/kot/{ticket['id']}/status", json={'status': 'PREPARING'})
            assert started.status_code == 200
            assert started.json()['status'] == 'PREPARING'

            assert client.patch(f"/api/kot/{ticket['id']}/status", json={'status': 'READY'}).status_code == 200
            assert client.patch(f"/api/kot/{ticket['id']}/status", json={'status': 'SERVED'}).status_code == 200
            india_today = datetime.now(UTC).astimezone(ZoneInfo('Asia/Kolkata')).date()
            completed_today = client.get('/api/kot', params={'completed_date': india_today.isoformat()})
            assert completed_today.status_code == 200
            assert [row['id'] for row in completed_today.json()] == [ticket['id']]
            completed_tomorrow = client.get(
                '/api/kot', params={'completed_date': (india_today + timedelta(days=1)).isoformat()}
            )
            assert completed_tomorrow.status_code == 200
            assert completed_tomorrow.json() == []

            voided = client.post(
                f"/api/orders/{response.json()['id']}/void",
                json={'reason': 'Customer requested cancellation'},
            )
            assert voided.status_code == 200, voided.text
            assert voided.json()['status'] == 'VOID'
            assert client.get('/api/orders').json()[0]['status'] == 'VOID'

            direct = client.post(
                '/api/orders',
                json={
                    'order_id': str(uuid4()),
                    'terminal_code': 'POS01',
                    'order_type': 'DIRECT',
                    'service_reference': 'COUNTER-1',
                    'items': [{'product_id': product.id, 'variant_id': None, 'quantity': 1}],
                    'payments': [
                        {
                            'mode': 'CARD',
                            'amount': '42.00',
                            'capture_source': 'PAYMENT_TERMINAL',
                            'provider': 'TEST_TERMINAL',
                            'reference': 'TXN-001',
                        }
                    ],
                },
            )
            assert direct.status_code == 201, direct.text
            assert direct.json()['order_type'] == 'DIRECT'
            assert direct.json()['service_reference'] == 'COUNTER-1'
            assert len(client.get('/api/kot').json()) == 1
            assert client.post(
                f"/api/orders/{direct.json()['id']}/void",
                json={'reason': 'Direct billing mode verification'},
            ).status_code == 200

            takeaway = client.post(
                '/api/orders',
                json={
                    'order_id': str(uuid4()),
                    'terminal_code': 'POS01',
                    'order_type': 'TAKEAWAY',
                    'service_reference': 'TOKEN-12',
                    'items': [{'product_id': product.id, 'variant_id': None, 'quantity': 1}],
                    'payments': [{'mode': 'CASH', 'amount': '42.00'}],
                },
            )
            assert takeaway.status_code == 201, takeaway.text
            assert takeaway.json()['order_type'] == 'TAKEAWAY'
            takeaway_kots = client.get('/api/kot').json()
            assert len(takeaway_kots) == 2
            assert any(ticket['station'] == 'Takeaway Counter' for ticket in takeaway_kots)
            assert client.post(
                f"/api/orders/{takeaway.json()['id']}/void",
                json={'reason': 'Takeaway billing mode verification'},
            ).status_code == 200

        with TestingSession() as session:
            assert session.get(Product, product.id).stock_quantity == Decimal('10.000')
            movements = session.scalars(
                select(InventoryTransaction).where(InventoryTransaction.product_id == product.id)
            ).all()
            assert [movement.transaction_type for movement in movements] == [
                'SALE', 'VOID_REVERSAL', 'SALE', 'VOID_REVERSAL', 'SALE', 'VOID_REVERSAL'
            ]
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
