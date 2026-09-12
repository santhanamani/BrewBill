from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.database import settings
from app.main import app
from app.media_storage import media_file_path, normalise_media_path


def test_central_media_route_serves_relative_table_path(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, 'brewbill_data_path', str(tmp_path))
    image = tmp_path / 'products' / 'photos' / 'coffee.jpg'
    image.parent.mkdir(parents=True)
    image.write_bytes(b'test-image')

    with TestClient(app) as client:
        response = client.get('/api/media/products/photos/coffee.jpg')

    assert response.status_code == 200
    assert response.content == b'test-image'
    assert response.headers['content-type'].startswith('image/jpeg')
    assert response.headers['x-content-type-options'] == 'nosniff'


@pytest.mark.parametrize('value', [
    '../secret.jpg',
    '/absolute/image.jpg',
    'products/../../secret.jpg',
    'products/photo.exe',
    'products/bad name.jpg',
])
def test_central_media_path_rejects_unsafe_values(tmp_path, monkeypatch, value) -> None:
    monkeypatch.setattr(settings, 'brewbill_data_path', str(tmp_path))
    with pytest.raises(HTTPException) as error:
        media_file_path(value)
    assert error.value.status_code == 404


def test_media_path_normalises_windows_separators() -> None:
    assert normalise_media_path(r'products\photos\coffee.jpg') == 'products/photos/coffee.jpg'
