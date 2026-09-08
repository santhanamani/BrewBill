from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Category, Order, OrderItem, Outlet, Payment, Product, Tenant


def test_dashboard_filters_a_tenant_outlet_date_range() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    tenant_id, other_tenant_id, outlet_id = str(uuid4()), str(uuid4()), str(uuid4())
    product_id, category_id = str(uuid4()), str(uuid4())

    with sessions() as session:
        session.add_all([
            Tenant(id=tenant_id, code='RANGE', name='Range Cafe', status='ACTIVE'),
            Tenant(id=other_tenant_id, code='OTHER', name='Other Cafe', status='ACTIVE'),
            Outlet(id=outlet_id, tenant_id=tenant_id, code='MAIN', name='Main'),
            Category(id=category_id, tenant_id=tenant_id, code='COFFEE', name='Coffee'),
            Product(
                id=product_id, tenant_id=tenant_id, outlet_id=outlet_id,
                category_id=category_id, code='LATTE', name='Latte', selling_price=Decimal('100.00'),
            ),
        ])
        orders = [
            ('IN-1', tenant_id, '2026-08-01T10:00:00+00:00', 'CASH', Decimal('105.00')),
            ('IN-2', tenant_id, '2026-08-02T11:00:00+00:00', 'UPI', Decimal('210.00')),
            ('OUT-DATE', tenant_id, '2026-08-03T10:00:00+00:00', 'CARD', Decimal('315.00')),
            ('OUT-TENANT', other_tenant_id, '2026-08-01T10:00:00+00:00', 'CASH', Decimal('999.00')),
        ]
        for invoice, row_tenant, created_at, mode, total in orders:
            order_id = str(uuid4())
            session.add(Order(
                id=order_id, tenant_id=row_tenant, outlet_id=outlet_id, terminal_id=str(uuid4()),
                invoice_number=invoice, order_type='DIRECT', subtotal=total, tax=Decimal('0.00'),
                grand_total=total, status='COMPLETED', created_at=datetime.fromisoformat(created_at),
            ))
            session.add(OrderItem(
                id=str(uuid4()), order_id=order_id, product_id=product_id, product_name='Latte',
                quantity=1, rate=total, tax=Decimal('0.00'), line_total=total,
            ))
            session.add(Payment(
                id=str(uuid4()), order_id=order_id, payment_mode=mode, amount=total,
            ))
        session.commit()

    def test_session():
        with sessions() as session:
            yield session

    user = SimpleNamespace(tenant_id=tenant_id, outlet_id=outlet_id)
    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.get('/api/dashboard?from_date=2026-08-01&to_date=2026-08-02')
            assert response.status_code == 200, response.text
            body = response.json()
            assert body['orders_today'] == 2
            assert body['sales_today'] == '315.00'
            assert body['cash_sales'] == '105.00'
            assert body['upi_sales'] == '210.00'
            assert body['card_sales'] == '0.00'
            assert [point['label'] for point in body['hourly_sales']] == ['01 Aug', '02 Aug']
            assert [point['label'] for point in body['date_sales']] == ['01 Aug', '02 Aug']
            assert [point['label'] for point in body['hour_sales']] == ['10:00', '11:00']
            assert [point['value'] for point in body['hour_sales']] == ['105.00', '210.00']
            assert body['top_products'][0]['quantity_sold'] == 2

            assert client.get('/api/dashboard?from_date=2026-08-02&to_date=2026-08-01').status_code == 422
            assert client.get('/api/dashboard?from_date=2027-01-01&to_date=2027-01-01').status_code == 422
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
