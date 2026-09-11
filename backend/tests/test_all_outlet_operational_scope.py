from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models import Outlet, Product, Role, Subscription, SubscriptionPlan, Tenant, User
from app.security import create_token


def test_all_outlet_admin_header_scopes_operations_without_assigning_the_user() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool,
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with sessions() as session:
        tenant = Tenant(id=str(uuid4()), code='SCOPE', name='Scope Cafe', status='ACTIVE')
        other_tenant = Tenant(id=str(uuid4()), code='OTHER', name='Other Cafe', status='ACTIVE')
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        plan = SubscriptionPlan(id=str(uuid4()), code='PRO', name='Professional', max_terminals=2, feature_json='{}')
        subscription = Subscription(
            id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30),
        )
        first = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='AAAA', name='First Outlet')
        second = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='BBBB', name='Second Outlet')
        foreign = Outlet(id=str(uuid4()), tenant_id=other_tenant.id, code='CCCC', name='Foreign Outlet')
        user = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=None, role_id=role.id,
            username='all-outlets', display_name='All Outlets', password_hash='unused', is_active=True,
        )
        product = Product(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=second.id, code='TEA', name='Tea',
            selling_price=Decimal('20.00'), purchase_price=Decimal('10.00'),
            gst_percent=Decimal('5.00'), stock_quantity=Decimal('10.000'),
            low_stock_limit=Decimal('2.000'), unit='pcs', is_available=True, is_active=True,
        )
        session.add_all([
            tenant, other_tenant, role, plan, subscription, first, second, foreign, user, product,
        ])
        session.commit()
        user_id, tenant_id, second_id, foreign_id = user.id, tenant.id, second.id, foreign.id

    token = create_token(user_id, tenant_id, 'access', timedelta(minutes=5))[0]

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            headers = {'Authorization': f'Bearer {token}', 'X-BrewBill-Outlet': second_id}
            outlets = client.get('/api/platform/outlets', headers=headers)
            assert outlets.status_code == 200, outlets.text
            assert {row['id'] for row in outlets.json()} == {first.id, second_id}

            products = client.get('/api/products', headers=headers)
            assert products.status_code == 200, products.text
            assert [row['name'] for row in products.json()] == ['Tea']

            rejected = client.get(
                '/api/products',
                headers={'Authorization': f'Bearer {token}', 'X-BrewBill-Outlet': foreign_id},
            )
            assert rejected.status_code == 422

        with sessions() as session:
            assert session.scalar(select(User).where(User.id == user_id)).outlet_id is None
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
