from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import GlobalProduct, Outlet, Role, Tenant, User


def test_global_product_has_isolated_outlet_mapping() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Administrator')
        master = GlobalProduct(
            id=str(uuid4()), code='CAPPUCCINO', name='Cappuccino',
            category_name='Coffee', base_unit='cup', default_gst=Decimal('5.00'), status='ACTIVE',
        )
        users = []
        for code in ('CAFE1', 'CAFE2'):
            tenant = Tenant(id=str(uuid4()), code=code, name=code, status='ACTIVE')
            outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MAIN', name=f'{code} Main')
            user = User(
                id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id,
                username='admin', display_name=f'{code} Admin', password_hash='x', is_active=True,
            )
            user.role = role
            session.add_all([tenant, outlet, user])
            users.append(user)
        session.add_all([role, master])
        session.commit()

    active_user = {'value': users[0]}

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: active_user['value']
    try:
        with TestClient(app) as client:
            mapped_a = client.post(f'/api/products/catalogue/{master.id}', json={
                'selling_price': '120.00', 'opening_stock': '10.000',
                'low_stock_limit': '2.000', 'favourite': True,
            })
            assert mapped_a.status_code == 201, mapped_a.text
            mapping_a_id = mapped_a.json()['id']

            active_user['value'] = users[1]
            assert client.get('/api/products/catalogue').json() == []
            mapped_b = client.post(f'/api/products/catalogue/{master.id}', json={
                'selling_price': '135.00', 'opening_stock': '7.000',
                'low_stock_limit': '1.000', 'favourite': False,
            })
            assert mapped_b.status_code == 201, mapped_b.text
            assert mapped_b.json()['selling_price'] == '135.00'

            active_user['value'] = users[0]
            assert client.get('/api/products/catalogue').json()[0]['selling_price'] == '120.00'
            disabled = client.patch(f'/api/products/catalogue/{mapping_a_id}', json={'is_active': False})
            assert disabled.status_code == 200

            active_user['value'] = users[1]
            cafe_b = client.get('/api/products/catalogue').json()[0]
            assert cafe_b['is_active'] is True
            assert cafe_b['stock_quantity'] == '7.000'
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
