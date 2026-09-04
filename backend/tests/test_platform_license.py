import base64
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session, settings
from app.main import app
from app.models import LicenseEvent, Outlet, PosTerminal, Role, Subscription, SubscriptionPlan, Tenant, User


def test_device_activation_issues_verifiable_tenant_license() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    with testing_session() as session:
        tenant = Tenant(id=str(uuid4()), name='License Tenant', status='ACTIVE')
        outlet = Outlet(id=str(uuid4()), tenant_id=tenant.id, code='LIC01', name='License Outlet')
        role = Role(id=str(uuid4()), code='LICENSE_ADMIN', name='License Admin')
        user = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id,
            username='license-admin', display_name='License Admin', password_hash='not-used', is_active=True,
        )
        user.role = role
        plan = SubscriptionPlan(
            id=str(uuid4()), code='PRO', name='Professional', max_terminals=1,
            feature_json='{"inventory":true,"reports":true}',
        )
        subscription = Subscription(
            id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
            starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30),
        )
        terminal = PosTerminal(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, terminal_code='POS01',
            terminal_name='Unclaimed POS', device_key_hash='development-only-test', status='ACTIVE',
        )
        session.add_all([tenant, outlet, role, user, plan, subscription, terminal])
        session.commit()

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    previous_private, previous_public = settings.license_private_key, settings.license_public_key
    settings.license_private_key = base64.b64encode(private_pem).decode('ascii')
    settings.license_public_key = base64.b64encode(public_pem).decode('ascii')

    def test_session():
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: user
    try:
        with TestClient(app) as client:
            context = client.get('/api/platform/context')
            assert context.status_code == 200, context.text
            assert context.json()['features']['inventory'] is True

            response = client.post('/api/platform/device/activate', json={
                'installation_id': str(uuid4()),
                'terminal_code': 'POS01',
                'terminal_name': 'Front Counter',
            })
            assert response.status_code == 200, response.text
            envelope = response.json()
            serialized = json.dumps(
                envelope['payload'], separators=(',', ':'), ensure_ascii=True, sort_keys=True
            ).encode('utf-8')
            private_key.public_key().verify(base64.b64decode(envelope['signature']), serialized)
            assert envelope['payload']['terminal_code'] == 'POS01'
            assert envelope['payload']['plan_code'] == 'PRO'

        with testing_session() as session:
            assert session.scalar(select(LicenseEvent).where(LicenseEvent.tenant_id == tenant.id))
    finally:
        settings.license_private_key = previous_private
        settings.license_public_key = previous_public
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
