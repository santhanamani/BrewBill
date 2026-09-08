from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import AuditLog, IngredientStock, IngredientTransaction, Outlet, Role, Tenant, User


def test_all_adjustment_types_persist_with_audit_and_outlet_isolation():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as db:
        tenant = Tenant(id=str(uuid4()), name='Inventory Test', status='ACTIVE')
        a = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='A', name='A')
        b = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='B', name='B')
        role = Role(id=str(uuid4()), code='ADMIN', name='Admin')
        user = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=a.id, role_id=role.id, username='inventory-test', display_name='Admin', password_hash='x', is_active=True)
        user.role = role
        db.add_all([tenant, a, b, role, user])
        db.commit()

    def session_override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            created = client.post('/api/inventory/items', json={'code': 'BEANS', 'name': 'Beans', 'category': 'Coffee', 'unit': 'kg', 'opening_quantity': '10.000', 'low_stock_limit': '3.000'})
            assert created.status_code == 201, created.text
            item_id = created.json()['id']
            cases = [('STOCK_IN', 'ADD', '12.000'), ('STOCK_OUT', 'REMOVE', '10.000'), ('DAMAGE', 'REMOVE', '8.000'), ('WASTAGE', 'REMOVE', '6.000'), ('MANUAL_CORRECTION', 'ADD', '8.000'), ('MANUAL_CORRECTION', 'REMOVE', '6.000')]
            for kind, direction, expected in cases:
                response = client.post(f'/api/inventory/items/{item_id}/adjustments', json={'transaction_type': kind, 'direction': direction, 'quantity': '2.000', 'notes': 'Persistence test'})
                assert response.status_code == 200, response.text
                # A separate request creates a fresh DB session, like refreshing the app.
                rows = client.get('/api/inventory/items').json()
                assert next(row for row in rows if row['id'] == item_id)['available_quantity'] == expected
            movements = client.get('/api/inventory/movements').json()
            assert len(movements) == 6
            assert all(row['notes'] == 'Persistence test' for row in movements)
            rejected = client.post(f'/api/inventory/items/{item_id}/adjustments', json={'transaction_type': 'STOCK_OUT', 'quantity': '100.000'})
            assert rejected.status_code == 409
        with sessions() as db:
            balances = {row.outlet_id: str(row.available_quantity) for row in db.scalars(select(IngredientStock)).all()}
            assert balances == {a.id: '6.000', b.id: '0.000'}
            assert len(db.scalars(select(IngredientTransaction)).all()) == 6
            assert len(db.scalars(select(AuditLog).where(AuditLog.entity_type == 'INGREDIENT_STOCK')).all()) == 6
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
