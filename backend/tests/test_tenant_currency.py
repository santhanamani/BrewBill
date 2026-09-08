from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Currency, Outlet, Role, Subscription, SubscriptionPlan, Tenant, User


def test_currency_is_tenant_scoped_and_returned_in_context() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        currencies = [
            Currency(code='INR', name='Indian Rupee', symbol='₹', locale='en-IN', decimal_places=2),
            Currency(code='USD', name='US Dollar', symbol='$', locale='en-US', decimal_places=2),
            Currency(code='EUR', name='Euro', symbol='€', locale='en-IE', decimal_places=2),
        ]
        platform = Tenant(id=str(uuid4()), code='PLATFORM', name='Platform', status='ACTIVE')
        first = Tenant(id=str(uuid4()), code='FIRST', name='First Cafe', status='ACTIVE')
        second = Tenant(id=str(uuid4()), code='SECOND', name='Second Cafe', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=first.id, code='MAIN', name='Main')
        plan = SubscriptionPlan(
            id=str(uuid4()), code='PRO', name='Pro', max_terminals=2, feature_json='{}'
        )
        now = datetime.now(UTC)
        subscriptions = [
            Subscription(id=str(uuid4()), tenant_id=first.id, plan_id=plan.id, status='ACTIVE', starts_at=now, ends_at=now + timedelta(days=30)),
            Subscription(id=str(uuid4()), tenant_id=second.id, plan_id=plan.id, status='ACTIVE', starts_at=now, ends_at=now + timedelta(days=30)),
        ]
        admin_role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Admin')
        cashier_role = Role(id=str(uuid4()), code='CASHIER', name='Cashier')
        super_role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Super Admin')
        admin = User(id=str(uuid4()), tenant_id=first.id, outlet_id=outlet.id, role_id=admin_role.id, username='admin', display_name='Admin', password_hash='x')
        cashier = User(id=str(uuid4()), tenant_id=first.id, outlet_id=outlet.id, role_id=cashier_role.id, username='cashier', display_name='Cashier', password_hash='x')
        super_admin = User(id=str(uuid4()), tenant_id=platform.id, role_id=super_role.id, username='owner', display_name='Owner', password_hash='x')
        session.add_all(currencies + [platform, first, second, outlet, plan, *subscriptions, admin_role, cashier_role, super_role, admin, cashier, super_admin])
        session.commit()
        admin.role, cashier.role, super_admin.role = admin_role, cashier_role, super_role

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        app.dependency_overrides[current_user] = lambda: admin
        with TestClient(app) as client:
            response = client.put('/api/currency', json={'currency_code': 'usd'})
            assert response.status_code == 200, response.text
            assert response.json()['code'] == 'USD'
            context = client.get('/api/platform/context')
            assert context.status_code == 200, context.text
            assert context.json()['currency']['symbol'] == '$'

        with sessions() as session:
            assert session.get(Tenant, first.id).currency_code == 'USD'
            assert session.get(Tenant, second.id).currency_code == 'INR'

        app.dependency_overrides[current_user] = lambda: super_admin
        with TestClient(app) as client:
            response = client.put(
                f'/api/platform/admin/tenants/{second.id}/currency',
                json={'currency_code': 'EUR'},
            )
            assert response.status_code == 200, response.text

        app.dependency_overrides[current_user] = lambda: cashier
        with TestClient(app) as client:
            assert client.put('/api/currency', json={'currency_code': 'INR'}).status_code == 403
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
