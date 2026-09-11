from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import GlobalProduct, Inventory, InventoryTransaction, Outlet, Role, Tenant, User


@pytest.fixture
def catalogue(tmp_path):
    # File-backed database: dispose/reconnect tests persistence beyond one connection.
    engine = create_engine(f'sqlite+pysqlite:///{tmp_path / "catalogue.db"}', connect_args={'check_same_thread': False})
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as db:
        role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Admin')
        tenant = Tenant(id=str(uuid4()), code='FIRST', name='First Cafe', status='ACTIVE')
        other = Tenant(id=str(uuid4()), code='OTHER', name='Other Cafe', status='ACTIVE')
        master = GlobalProduct(id=str(uuid4()), code='CAP', name='Cappuccino', category_name='Coffee', base_unit='pcs', default_gst=Decimal('5.00'), status='ACTIVE')
        users = []
        for cafe, code in [(tenant, 'RAAA'), (tenant, 'GAAA'), (other, 'MAAA')]:
            outlet = Outlet(id=str(uuid4()), tenant_id=cafe.id, code=code, name=code)
            user = User(id=str(uuid4()), tenant_id=cafe.id, outlet_id=outlet.id, role_id=role.id, username=code, display_name=code, password_hash='x', is_active=True)
            user.role = role
            db.add_all([outlet, user]); users.append(user)
        db.add_all([role, tenant, other, master]); db.commit()
    active = {'user': users[0]}
    def session():
        with sessions() as db:
            yield db
    app.dependency_overrides[get_session] = session
    app.dependency_overrides[current_user] = lambda: active['user']
    try:
        with TestClient(app) as client:
            mappings = []
            for user, stock in zip(users, ['40.000', '25.000', '12.000']):
                active['user'] = user
                response = client.post(f'/api/products/catalogue/{master.id}', json={'selling_price':'80.00','opening_stock':stock})
                assert response.status_code == 201, response.text
                mappings.append(response.json())
            active['user'] = users[0]
            yield client, active, users, mappings, engine, sessions
    finally:
        app.dependency_overrides.clear(); engine.dispose()


def test_stock_persists_in_ledger_and_pos_after_reconnect_and_is_isolated(catalogue):
    client, active, users, mappings, engine, sessions = catalogue
    first = mappings[0]
    response = client.patch(f'/api/products/catalogue/{first["id"]}', json={
        'stock_quantity':'35.000', 'expected_stock_quantity':'40.000',
        'selling_price':'90.00', 'favourite':True, 'kot_required':False, 'is_available':False,
    })
    assert response.status_code == 200, response.text
    engine.dispose()
    saved = client.get('/api/products/catalogue').json()[0]
    assert saved['stock_quantity'] == '35.000'
    assert saved['selling_price'] == '90.00' and saved['favourite'] and not saved['kot_required'] and not saved['is_available']
    pos = client.get('/api/products').json()[0]
    assert pos['stock_quantity'] == '35.000'
    assert pos['selling_price'] == '90.00' and pos['is_favourite'] and not pos['is_available']
    with sessions() as db:
        inventory = db.scalar(select(Inventory).where(Inventory.outlet_id == users[0].outlet_id))
        assert inventory.available_quantity == Decimal('35.000')
        movement = db.scalar(select(InventoryTransaction))
        assert movement.quantity_delta == Decimal('-5.000')
        assert movement.transaction_type == 'CORRECTION'
        assert movement.tenant_id == users[0].tenant_id and movement.outlet_id == users[0].outlet_id
    for user, expected in zip(users[1:], ['25.000','12.000']):
        active['user'] = user
        assert client.get('/api/products/catalogue').json()[0]['stock_quantity'] == expected
        assert client.get('/api/products').json()[0]['stock_quantity'] == expected
        assert client.patch(f'/api/products/catalogue/{first["id"]}', json={'stock_quantity':'1','expected_stock_quantity':'35'}).status_code == 404


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', '1.2345', None, '1000000000000000'])
def test_invalid_stock_never_changes_database(catalogue, value):
    client, _, _, mappings, _, _ = catalogue
    response = client.patch(f'/api/products/catalogue/{mappings[0]["id"]}', json={'stock_quantity':value,'expected_stock_quantity':'40'})
    assert response.status_code == 422, response.text
    assert client.get('/api/products/catalogue').json()[0]['stock_quantity'] == '40.000'


def test_stale_stock_conflict_rolls_back_other_mapping_changes(catalogue):
    client, _, _, mappings, _, _ = catalogue
    url = f'/api/products/catalogue/{mappings[0]["id"]}'
    assert client.patch(url, json={'stock_quantity':'35.125','expected_stock_quantity':'40'}).status_code == 200
    stale = client.patch(url, json={'stock_quantity':'34','expected_stock_quantity':'40','selling_price':'1'})
    assert stale.status_code == 409
    row = client.get('/api/products/catalogue').json()[0]
    assert row['stock_quantity'] == '35.125' and row['selling_price'] == '80.00'
    assert client.patch(url, json={'stock_quantity':'0','expected_stock_quantity':'35.125'}).status_code == 200
    assert client.get('/api/products').json()[0]['stock_quantity'] == '0.000'


def test_auth_and_untrusted_context_and_missing_expected_stock(catalogue):
    client, active, users, mappings, _, _ = catalogue
    url = f'/api/products/catalogue/{mappings[0]["id"]}'
    assert client.patch(url, json={'stock_quantity':'35'}).status_code == 422
    assert client.patch(url, json={'stock_quantity':'35','expected_stock_quantity':'40','outlet_id':users[1].outlet_id}).status_code == 422
    active['user'].role = Role(id=str(uuid4()),code='CASHIER',name='Cashier')
    assert client.patch(url, json={'stock_quantity':'35','expected_stock_quantity':'40'}).status_code == 403
    assert client.get('/api/products/catalogue').json()[0]['stock_quantity'] == '40.000'


def test_all_outlet_admin_can_select_only_an_outlet_in_own_tenant(catalogue):
    client, active, users, mappings, _, _ = catalogue
    all_outlet_admin = users[0]
    first_outlet_id = all_outlet_admin.outlet_id
    all_outlet_admin.outlet_id = None
    active['user'] = all_outlet_admin

    outlets = client.get('/api/platform/outlets')
    assert outlets.status_code == 200, outlets.text
    own_outlet_ids = {row['id'] for row in outlets.json()}
    assert own_outlet_ids == {first_outlet_id, users[1].outlet_id}

    selected_outlet_id = users[1].outlet_id
    products = client.get('/api/products', params={'outlet_id': selected_outlet_id})
    assert products.status_code == 200, products.text
    assert products.json()[0]['stock_quantity'] == '25.000'

    favourite = client.patch(
        f'/api/products/{mappings[1]["legacy_product_id"]}/favourite',
        params={'outlet_id': selected_outlet_id},
        json={'is_favourite': True},
    )
    assert favourite.status_code == 200, favourite.text
    assert favourite.json()['is_favourite'] is True

    cross_tenant = client.get('/api/products', params={'outlet_id': users[2].outlet_id})
    assert cross_tenant.status_code == 422
