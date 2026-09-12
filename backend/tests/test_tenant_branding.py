from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import branding_media
from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Role, Tenant, User


@pytest.fixture
def branding_client(tmp_path, monkeypatch):
    monkeypatch.setattr(branding_media, 'MEDIA_ROOT', tmp_path / 'branding')
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        first = Tenant(id=str(uuid4()), code='CAFE-A', name='Cafe A', status='ACTIVE')
        second = Tenant(id=str(uuid4()), code='CAFE-B', name='Cafe B', status='ACTIVE')
        inactive = Tenant(id=str(uuid4()), code='CLOSED', name='Closed Cafe', status='INACTIVE')
        role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Super Administrator')
        admin = User(id=str(uuid4()), tenant_id=first.id, role_id=role.id, username='owner', display_name='Owner', password_hash='x', is_active=True)
        session.add_all([first, second, inactive, role, admin])
        session.commit()
        admin.role = role
    def test_session():
        with sessions() as session:
            yield session
    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: admin
    try:
        with TestClient(app) as client:
            yield client, first.id, second.id, admin
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def picture(size=(128, 128), format='PNG'):
    output = BytesIO()
    Image.new('RGB', size, '#9a7850').save(output, format=format)
    return output.getvalue()


def upload(client, tenant_id, content=None, kind='logo'):
    return client.post(f'/api/platform/admin/tenants/{tenant_id}/branding/{kind}/upload',
                       files={'file': ('../../unsafe.svg', picture() if content is None else content, 'image/png')})


def test_upload_save_resolve_isolated_and_public(branding_client):
    client, first, second, _ = branding_client
    for kind, field in [('logo', 'logo_url'), ('cover', 'cover_image_url')]:
        response = upload(client, first, kind=kind)
        assert response.status_code == 200, response.text
        media = response.json()
        path = media['path']
        url = media['url']
        assert path.startswith(f'tenant-branding/{first}/{kind}-')
        # Upload is a draft until the explicit save; no tenant name/images modified.
        assert client.get('/api/platform/tenants/resolve?code=CAFE-A').json()[field] is None
        saved = client.patch(f'/api/platform/admin/tenants/{first}/branding',
                             json={field: path, 'name': 'Cafe A New Name'})
        assert saved.status_code == 200, saved.text
        resolved = client.get('/api/platform/tenants/resolve?code=%20cafe-a%20').json()
        assert resolved[field] == path
        assert resolved['name'] == 'Cafe A New Name'
        assert client.get('/api/platform/tenants/resolve?code=CAFE-B').json()[field] is None
        image = client.get(url)
        assert image.status_code == 200
        assert image.headers['content-type'] == 'image/webp'
        assert image.headers['x-content-type-options'] == 'nosniff'
        with Image.open(BytesIO(image.content)) as decoded:
            assert decoded.size == (128, 128)
            assert not decoded.getexif()
        wrong = client.patch(f'/api/platform/admin/tenants/{second}/branding', json={field: path})
        assert wrong.status_code == 422
        assert client.get(url.replace(first, second)).status_code == 404


@pytest.mark.parametrize('content', [b'', b'not an image', b'<svg xmlns="http://www.w3.org/2000/svg"/>', picture((20, 20)), b'x' * (2 * 1024 * 1024 + 1)], ids=['empty', 'garbage', 'svg', 'too-small', 'too-large'])
def test_reject_invalid_uploads(branding_client, content):
    client, first, _, _ = branding_client
    assert upload(client, first, content).status_code in (413, 422)
    assert client.get('/api/platform/tenants/resolve?code=CAFE-A').json()['logo_url'] is None


def test_authorization_missing_tenant_and_code_errors(branding_client):
    client, first, _, admin = branding_client
    assert upload(client, str(uuid4())).status_code == 404
    assert client.get('/api/platform/tenants/resolve?code=NOT-REAL').status_code == 404
    assert client.get('/api/platform/tenants/resolve?code=X').status_code == 422
    assert client.get('/api/platform/tenants/resolve?code=CLOSED').json()['status'] == 'INACTIVE'
    admin.role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Admin')
    assert upload(client, first).status_code == 403
    assert client.patch(f'/api/platform/admin/tenants/{first}/branding', json={'name': 'Bad'}).status_code == 403
    app.dependency_overrides.pop(current_user)
    assert upload(client, first).status_code in (401, 422)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'data:image/svg+xml,bad', '//example.com/x', '/api/platform/tenants/other/media/bad.webp'])
def test_reject_unsafe_branding_urls(branding_client, url):
    client, first, _, _ = branding_client
    assert client.patch(f'/api/platform/admin/tenants/{first}/branding', json={'logo_url': url}).status_code == 422


def test_new_upload_preserves_previous_file(branding_client):
    client, first, _, _ = branding_client
    first_url = upload(client, first).json()['url']
    second_url = upload(client, first).json()['url']
    assert first_url != second_url
    assert client.get(first_url).status_code == 200
    assert client.get(second_url).status_code == 200
