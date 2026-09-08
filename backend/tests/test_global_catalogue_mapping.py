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
        cashier_role = Role(id=str(uuid4()), code='CASHIER', name='Cashier')
        cashier = User(
            id=str(uuid4()), tenant_id=users[0].tenant_id, outlet_id=users[0].outlet_id,
            role_id=cashier_role.id, username='cashier', display_name='Cashier',
            password_hash='x', is_active=True,
        )
        cashier.role = cashier_role
        session.add_all([role, master, cashier_role, cashier])
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
            edited = client.patch(f'/api/products/catalogue/{mapping_a_id}', json={
                'selling_price': '125.00', 'low_stock_limit': '4.000', 'kot_required': False,
            })
            assert edited.status_code == 200, edited.text
            assert edited.json()['selling_price'] == '125.00'
            assert edited.json()['low_stock_limit'] == '4.000'
            assert edited.json()['stock_quantity'] == '10.000'
            assert edited.json()['kot_required'] is False
            assert client.get('/api/products/catalogue').json()[0]['low_stock_limit'] == '4.000'
            invalid = client.patch(f'/api/products/catalogue/{mapping_a_id}', json={'low_stock_limit': '-1'})
            assert invalid.status_code == 422
            disabled = client.patch(f'/api/products/catalogue/{mapping_a_id}', json={'is_active': False})
            assert disabled.status_code == 200

            active_user['value'] = users[1]
            cafe_b = client.get('/api/products/catalogue').json()[0]
            assert cafe_b['is_active'] is True
            assert cafe_b['stock_quantity'] == '7.000'
            assert cafe_b['low_stock_limit'] == '1.000'
            assert client.patch(f'/api/products/catalogue/{mapping_a_id}', json={'selling_price':'1.00'}).status_code == 404
            # A cashier can change only favourites in their own outlet.
            active_user['value'] = cashier
            product_id = mapped_a.json()['legacy_product_id']
            favourite_url = f'/api/products/{product_id}/favourite'
            removed = client.patch(favourite_url, json={'is_favourite': False})
            assert removed.status_code == 200, removed.text
            assert removed.json()['is_favourite'] is False
            saved = client.patch(favourite_url, json={'is_favourite': True})
            assert saved.status_code == 200, saved.text
            assert client.get('/api/products').json()[0]['is_favourite'] is True
            assert client.get('/api/products/catalogue').json()[0]['favourite'] is True
            assert client.patch(favourite_url, json={'is_favourite': False, 'selling_price': '1.00'}).status_code == 422
            assert client.patch(f'/api/products/{product_id}', json={'selling_price': '1.00'}).status_code == 403
            active_user['value'] = users[1]
            assert client.patch(favourite_url, json={'is_favourite': False}).status_code == 404
            assert client.get('/api/products/catalogue').json()[0]['favourite'] is False
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_tenant_admin_can_configure_catalogue_variants_without_cross_tenant_access() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Administrator')
        master = GlobalProduct(
            id=str(uuid4()), code='SHAKE', name='Milkshake',
            category_name='Milkshakes', base_unit='cup', default_gst=Decimal('5.00'), status='ACTIVE',
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
            mapped = client.post(f'/api/products/catalogue/{master.id}', json={'selling_price': '100.00'})
            assert mapped.status_code == 201, mapped.text
            product_id = mapped.json()['legacy_product_id']
            configured = client.put(f'/api/products/{product_id}/variants', json={'variants': [
                {'name': 'Medium', 'price_adjustment': '10.00', 'display_order': 0},
                {'name': 'Large', 'price_adjustment': '30.00', 'display_order': 1},
            ]})
            assert configured.status_code == 200, configured.text
            assert [row['name'] for row in configured.json()] == ['Medium', 'Large']
            catalogue = client.get('/api/products/catalogue').json()[0]
            assert [row['name'] for row in catalogue['variants'] if row['is_active']] == ['Medium', 'Large']
            operational = client.get('/api/products').json()[0]
            assert [row['price_adjustment'] for row in operational['variants']] == ['10.00', '30.00']

            active_user['value'] = users[1]
            assert client.put(f'/api/products/{product_id}/variants', json={'variants': []}).status_code == 404
            assert client.get('/api/products/catalogue').json() == []

            active_user['value'] = users[0]
            disabled = client.put(f'/api/products/{product_id}/variants', json={'variants': []})
            assert disabled.status_code == 200, disabled.text
            assert disabled.json() == []
            catalogue = client.get('/api/products/catalogue').json()[0]
            assert len(catalogue['variants']) == 2
            assert all(not row['is_active'] for row in catalogue['variants'])
            operational_variants = client.get('/api/products').json()[0]['variants']
            assert len(operational_variants) == 2
            assert all(not row['is_active'] for row in operational_variants)
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_master_actions_persist_and_are_restricted_to_super_admin() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        tenant = Tenant(id=str(uuid4()), code='BHV-TEST', name='Test Cafe', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='MAIN', name='Main')
        owner_role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Platform Owner')
        admin_role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Admin')
        owner = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=owner_role.id,
                     username='owner', display_name='Owner', password_hash='x', is_active=True)
        admin = User(id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=admin_role.id,
                     username='admin', display_name='Admin', password_hash='x', is_active=True)
        owner.role = owner_role
        admin.role = admin_role
        session.add_all([tenant, outlet, owner_role, admin_role, owner, admin])
        session.commit()

    active_user = {'value': owner}

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: active_user['value']
    try:
        with TestClient(app) as client:
            created = client.post('/api/products/master', json={
                'code':'COF-TEST', 'name':'Coffee', 'category_name':'Coffee',
                'base_unit':'Cup', 'default_gst':'5.00', 'status':'ACTIVE',
            })
            assert created.status_code == 201, created.text
            product_id = created.json()['id']
            active_user['value'] = admin
            assert client.patch(f'/api/products/master/{product_id}', json={'name':'Forbidden'}).status_code == 403
            mapped = client.post(f'/api/products/catalogue/{product_id}', json={'selling_price':'120.00'})
            assert mapped.status_code == 201, mapped.text
            active_user['value'] = owner
            edited = client.patch(f'/api/products/master/{product_id}', json={
                'name':'Premium Coffee', 'default_gst':'12.00', 'image_path':'products/coffee.jpg',
            })
            assert edited.status_code == 200, edited.text
            active_user['value'] = admin
            operational = client.get('/api/products').json()[0]
            assert operational['name'] == 'Premium Coffee'
            assert operational['gst_percent'] == '12.00'
            assert operational['image_path'] == 'products/coffee.jpg'
            assert operational['selling_price'] == '120.00'
            active_user['value'] = owner
            assert client.patch(f'/api/products/master/{product_id}', json={'status':'INACTIVE'}).status_code == 200
            assert client.get('/api/products/master').json() == []
            assert client.get('/api/products/master?include_inactive=true').json()[0]['status'] == 'INACTIVE'
            active_user['value'] = admin
            assert client.get('/api/products').json()[0]['is_active'] is False
            active_user['value'] = owner
            assert client.patch(f'/api/products/master/{product_id}', json={'status':'ACTIVE'}).status_code == 200
            assert client.get('/api/products/master').json()[0]['name'] == 'Premium Coffee'
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
