from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_swagger_ui_is_available_under_api_scope() -> None:
    response = client.get('/api/docs')

    assert response.status_code == 200
    assert '/api/openapi.json' in response.text


def test_openapi_schema_is_available_under_api_scope() -> None:
    response = client.get('/api/openapi.json')

    assert response.status_code == 200
    schema = response.json()
    assert schema['info']['title'] == 'BrewBill Cloud API'
    assert '/api/health' in schema['paths']


def test_redoc_is_available_under_api_scope() -> None:
    response = client.get('/api/redoc')

    assert response.status_code == 200
    assert '/api/openapi.json' in response.text
