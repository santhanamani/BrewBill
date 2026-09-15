from io import BytesIO

import pytest
from PIL import Image
from sqlalchemy import select

from app.database import settings
from app.models import Product
from app.product_media import MAX_PRODUCT_IMAGE_BYTES
from test_tenant_catalogue_products import tenant_catalogue


def transparent_png():
    image = Image.new('RGBA', (128, 128), (180, 80, 30, 255))
    image.putpixel((0, 0), (0, 0, 0, 0))
    stream = BytesIO()
    image.save(stream, format='PNG')
    return stream.getvalue()


def test_upload_publish_and_mapped_outlet_propagation(tenant_catalogue, tmp_path, monkeypatch):
    client, active, users, _, _, master, _, sessions = tenant_catalogue
    root = tmp_path / 'external-data'
    monkeypatch.setattr(settings, 'brewbill_data_path', str(root))
    mappings = []
    for key, price in [('admin', '99.00'), ('other_admin', '149.00')]:
        active['user'] = users[key]
        mapped = client.post(f'/api/products/catalogue/{master.id}', json={
            'selling_price': price, 'opening_stock': '8.000', 'favourite': True,
        })
        assert mapped.status_code == 201, mapped.text
        mappings.append(mapped.json())
    active['user'] = users['super']
    upload = client.post('/api/products/master/image', files={'file': ('../../fake.jpg', transparent_png(), 'image/jpeg')})
    assert upload.status_code == 201, upload.text
    result = upload.json()
    assert result['path'].startswith('products/global-uploads/product-')
    assert (root / result['path']).is_file()
    served = client.get(result['url'])
    assert served.status_code == 200
    with Image.open(BytesIO(served.content)) as image:
        assert image.format == 'WEBP'
        assert image.getchannel('A').getextrema() == (0, 255)
    # Upload alone is not publishing.
    before = next(p for p in client.get('/api/products/master').json() if p['id'] == master.id)
    assert before['image_path'] is None
    saved = client.patch(f'/api/products/master/{master.id}', json={'image_path': result['path']})
    assert saved.status_code == 200, saved.text
    for index, key in enumerate(['admin', 'other_admin']):
        active['user'] = users[key]
        mapped = client.get('/api/products/catalogue').json()[0]
        assert mapped['image_path'] == result['path']
        for field in ['selling_price', 'stock_quantity', 'favourite', 'tax_override', 'kot_required']:
            assert mapped[field] == mappings[index][field]
        assert client.get('/api/products').json()[0]['image_path'] == result['path']
    with sessions() as db:
        assert all(p.image_path == result['path'] for p in db.scalars(select(Product)))
    # Source is the configured backend directory, not a frontend fallback.
    monkeypatch.setattr(settings, 'brewbill_data_path', str(tmp_path / 'different-root'))
    assert client.get(result['url']).status_code == 404
    active['user'] = users['super']
    second = client.post('/api/products/master/image', files={'file': ('image.png', transparent_png(), 'image/png')})
    assert second.status_code == 201
    assert (tmp_path / 'different-root' / second.json()['path']).is_file()
    assert second.json()['path'] != result['path']
    created = client.post('/api/products/master', json={
        'code': 'NEW_IMAGE', 'name': 'New image product', 'category_name': 'Coffee',
        'image_path': second.json()['path'],
    })
    assert created.status_code == 201, created.text


@pytest.mark.parametrize('role', ['admin', 'cashier', 'other_admin'])
def test_upload_is_superadmin_only(tenant_catalogue, role):
    client, active, users, *_ = tenant_catalogue
    active['user'] = users[role]
    assert client.post('/api/products/master/image', files={'file': ('image.png', transparent_png(), 'image/png')}).status_code == 403


@pytest.mark.parametrize('content,expected', [(b'not an image', 422), (b'', 413), (b'x' * (MAX_PRODUCT_IMAGE_BYTES + 1), 413)], ids=['invalid', 'empty', 'oversized'])
def test_invalid_upload_does_not_write(tenant_catalogue, tmp_path, monkeypatch, content, expected):
    client, active, users, *_ = tenant_catalogue
    active['user'] = users['super']
    root = tmp_path / 'rejected-uploads'
    monkeypatch.setattr(settings, 'brewbill_data_path', str(root))
    response = client.post('/api/products/master/image', files={'file': ('fake.png', content, 'image/png')})
    assert response.status_code == expected
    assert not root.exists()


@pytest.mark.parametrize('path', ['https://example.com/image.png', '../private.png', 'products/../private.png', 'products/global-uploads/missing.webp', 'products/tenant-uploads/other.webp'])
def test_global_image_requires_existing_server_file(tenant_catalogue, path):
    client, active, users, _, _, master, *_ = tenant_catalogue
    active['user'] = users['super']
    assert client.patch(f'/api/products/master/{master.id}', json={'image_path': path}).status_code == 422
