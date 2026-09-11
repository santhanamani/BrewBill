from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Order, Outlet, Role, Tenant, User


def test_order_report_uses_india_date_boundaries_and_returns_multiple_rows() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        tenant = Tenant(id=str(uuid4()), code='REPORT', name='Report Tenant', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MAIN', name='Main')
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        user = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id, username='admin', display_name='Admin', password_hash='x', is_active=True)
        user.role = role
        session.add_all([tenant, outlet, role, user])
        session.flush()
        for index, created_at in enumerate((
            datetime(2026, 9, 5, 1, 0, tzinfo=UTC),
            datetime(2026, 9, 5, 18, 0, tzinfo=UTC),
            datetime(2026, 9, 6, 19, 0, tzinfo=UTC),
        )):
            session.add(Order(
                id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id,
                terminal_id=str(uuid4()), cashier_id=user.id,
                invoice_number=f'REPORT-{index}', subtotal=Decimal('100'), tax=Decimal('5'),
                grand_total=Decimal('105'), status='COMPLETED', created_at=created_at,
            ))
        session.commit()

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            response = client.get('/api/orders?from_date=2026-09-05&to_date=2026-09-05')
            assert response.status_code == 200, response.text
            assert {row['invoice_number'] for row in response.json()} == {'REPORT-0', 'REPORT-1'}
            assert client.get('/api/orders?from_date=2026-09-06&to_date=2026-09-05').status_code == 422
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
