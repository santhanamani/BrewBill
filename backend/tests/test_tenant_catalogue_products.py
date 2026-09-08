from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from PIL import Image

from app import product_media
from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import (
    AuditLog,
    Category,
    GlobalProduct,
    Inventory,
    Outlet,
    OutletProductMapping,
    Product,
    Role,
    Tenant,
    User,
)


@pytest.fixture
def tenant_catalogue(tmp_path, monkeypatch):
    monkeypatch.setattr(product_media, 'MEDIA_ROOT', tmp_path / 'tenant-products')
    engine = create_engine(
        f'sqlite+pysqlite:///{tmp_path / "tenant-catalogue.db"}',
        connect_args={'check_same_thread': False},
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as db:
        admin_role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Admin')
        cashier_role = Role(id=str(uuid4()), code='CASHIER', name='Cashier')
        super_role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Platform Admin')
        first_tenant = Tenant(id=str(uuid4()), code='FIRST', name='First Cafe', status='ACTIVE')
        other_tenant = Tenant(id=str(uuid4()), code='OTHER', name='Other Cafe', status='ACTIVE')
        first_outlet = Outlet(id=str(uuid4()), tenant_id=first_tenant.id, code='MAIN', name='First Main')
        other_outlet = Outlet(id=str(uuid4()), tenant_id=other_tenant.id, code='MAIN', name='Other Main')
        first_category = Category(
            id=str(uuid4()), tenant_id=first_tenant.id, code='SPECIALS', name='Specials',
            display_order=1, is_active=True,
        )
        other_category = Category(
            id=str(uuid4()), tenant_id=other_tenant.id, code='SPECIALS', name='Specials',
            display_order=1, is_active=True,
        )
        master = GlobalProduct(
            id=str(uuid4()), code='CAP', name='Cappuccino', category_name='Coffee',
            base_unit='pcs', default_gst=Decimal('5.00'), status='ACTIVE',
        )
        users = {
            'admin': User(
                id=str(uuid4()), tenant_id=first_tenant.id, outlet_id=first_outlet.id,
                role_id=admin_role.id, username='admin', display_name='Admin',
                password_hash='x', is_active=True,
            ),
            'cashier': User(
                id=str(uuid4()), tenant_id=first_tenant.id, outlet_id=first_outlet.id,
                role_id=cashier_role.id, username='cashier', display_name='Cashier',
                password_hash='x', is_active=True,
            ),
            'super': User(
                id=str(uuid4()), tenant_id=first_tenant.id, outlet_id=first_outlet.id,
                role_id=super_role.id, username='platform', display_name='Platform',
                password_hash='x', is_active=True,
            ),
            'other_admin': User(
                id=str(uuid4()), tenant_id=other_tenant.id, outlet_id=other_outlet.id,
                role_id=admin_role.id, username='admin', display_name='Other Admin',
                password_hash='x', is_active=True,
            ),
        }
        users['admin'].role = admin_role
        users['cashier'].role = cashier_role
        users['super'].role = super_role
        users['other_admin'].role = admin_role
        db.add_all([
            admin_role, cashier_role, super_role, first_tenant, other_tenant,
            first_outlet, other_outlet, first_category, other_category, master,
            *users.values(),
        ])
        db.commit()

    active = {'user': users['admin']}

    def session_override():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_session] = session_override
    app.dependency_overrides[current_user] = lambda: active['user']
    try:
        with TestClient(app) as client:
            yield client, active, users, first_category, other_category, master, engine, sessions
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def local_product_payload(category_id: str) -> dict:
    return {
        'category_id': category_id,
        'code': 'HOUSE_SPECIAL',
        'name': 'House Special',
        'selling_price': '125.00',
        'purchase_price': '60.00',
        'gst_percent': '12.00',
        'unit': 'pcs',
        'stock_quantity': '7.500',
        'low_stock_limit': '2.000',
        'image_path': 'products/house-special.png',
        'is_favourite': True,
        'kot_required': False,
        'is_available': True,
        'is_active': True,
        'shared_across_outlets': True,
    }


def test_admin_can_create_tenant_only_catalogue_product(tenant_catalogue):
    client, active, users, category, _, _, engine, sessions = tenant_catalogue
    with sessions() as db:
        master_count = db.scalar(select(func.count()).select_from(GlobalProduct))

    response = client.post('/api/products/catalogue/local', json=local_product_payload(category.id))
    assert response.status_code == 201, response.text
    created = response.json()
    assert created['source'] == 'TENANT'
    assert created['global_product_id'] is None
    assert created['stock_quantity'] == '7.500'
    assert created['default_gst'] == '12.00'

    # Reconnect to prove that the product and inventory are persisted, not UI-only state.
    engine.dispose()
    catalogue = client.get('/api/products/catalogue').json()
    products = client.get('/api/products').json()
    assert [row['code'] for row in catalogue] == ['HOUSE_SPECIAL']
    assert [row['code'] for row in products] == ['HOUSE_SPECIAL']
    assert all(row['code'] != 'HOUSE_SPECIAL' for row in client.get('/api/products/master').json())

    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(GlobalProduct)) == master_count
        product = db.scalar(select(Product).where(Product.code == 'HOUSE_SPECIAL'))
        mapping = db.scalar(select(OutletProductMapping).where(OutletProductMapping.legacy_product_id == product.id))
        inventory = db.scalar(select(Inventory).where(Inventory.product_id == product.id))
        audit = db.scalar(select(AuditLog).where(AuditLog.entity_id == product.id))
        assert product.tenant_id == users['admin'].tenant_id
        assert product.outlet_id == users['admin'].outlet_id
        assert mapping.tenant_id == users['admin'].tenant_id and mapping.global_product_id is None
        assert inventory.tenant_id == users['admin'].tenant_id
        assert inventory.outlet_id == users['admin'].outlet_id
        assert inventory.available_quantity == Decimal('7.500')
        assert audit.entity_type == 'TENANT_CATALOGUE_PRODUCT'

    active['user'] = users['other_admin']
    assert client.get('/api/products/catalogue').json() == []
    assert client.get('/api/products').json() == []


def test_only_tenant_admin_can_map_or_create_catalogue_items(tenant_catalogue):
    client, active, users, category, other_category, master, _, _ = tenant_catalogue
    payload = local_product_payload(category.id)

    active['user'] = users['cashier']
    assert client.post('/api/products/catalogue/local', json=payload).status_code == 403
    assert client.post(
        f'/api/products/catalogue/{master.id}', json={'selling_price': '80.00'}
    ).status_code == 403

    active['user'] = users['super']
    assert client.post('/api/products/catalogue/local', json=payload).status_code == 403
    assert client.post(
        f'/api/products/catalogue/{master.id}', json={'selling_price': '80.00'}
    ).status_code == 403

    active['user'] = users['admin']
    wrong_category = local_product_payload(other_category.id)
    assert client.post('/api/products/catalogue/local', json=wrong_category).status_code == 422
    mapped = client.post(
        f'/api/products/catalogue/{master.id}', json={'selling_price': '80.00'}
    )
    assert mapped.status_code == 201, mapped.text
    assert mapped.json()['source'] == 'GLOBAL'


def test_tenant_product_code_cannot_be_duplicated(tenant_catalogue):
    client, _, _, category, _, _, _, _ = tenant_catalogue
    payload = local_product_payload(category.id)
    assert client.post('/api/products/catalogue/local', json=payload).status_code == 201
    assert client.post('/api/products/catalogue/local', json=payload).status_code == 409

def product_png() -> bytes:
    output = BytesIO()
    Image.new('RGB', (800, 600), '#c68a4b').save(output, format='PNG')
    return output.getvalue()


def test_product_image_upload_is_saved_and_scoped_to_tenant_outlet(tenant_catalogue):
    client, active, users, category, other_category, _, _, _ = tenant_catalogue
    uploaded = client.post(
        '/api/products/catalogue/local/image',
        files={'file': ('house-special.png', product_png(), 'image/png')},
    )
    assert uploaded.status_code == 200, uploaded.text
    media = uploaded.json()
    expected_prefix = (
        f'/api/products/media/{users["admin"].tenant_id}/{users["admin"].outlet_id}/'
    )
    assert media['url'].startswith(expected_prefix)
    assert media['width'] == 800 and media['height'] == 600
    assert client.get(media['url']).headers['content-type'].startswith('image/webp')

    payload = local_product_payload(category.id)
    payload['image_path'] = media['url']
    created = client.post('/api/products/catalogue/local', json=payload)
    assert created.status_code == 201, created.text
    assert created.json()['image_path'] == media['url']

    active['user'] = users['other_admin']
    other_payload = local_product_payload(other_category.id)
    other_payload['code'] = 'OTHER_SPECIAL'
    other_payload['image_path'] = media['url']
    assert client.post('/api/products/catalogue/local', json=other_payload).status_code == 422

    active['user'] = users['cashier']
    assert client.post(
        '/api/products/catalogue/local/image',
        files={'file': ('blocked.png', product_png(), 'image/png')},
    ).status_code == 403


def test_product_image_upload_rejects_invalid_file(tenant_catalogue):
    client, *_ = tenant_catalogue
    response = client.post(
        '/api/products/catalogue/local/image',
        files={'file': ('not-an-image.png', b'not an image', 'image/png')},
    )
    assert response.status_code == 422
