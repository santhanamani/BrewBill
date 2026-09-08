import base64
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session, settings
from app.main import app
from app.models import Outlet, PosTerminal, Role, Subscription, SubscriptionPlan, Tenant, User


def test_same_desktop_can_activate_a_separate_terminal_for_each_tenant() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)

    with sessions() as session:
        role = Role(id=str(uuid4()), code='ADMIN', name='Administrator')
        plan = SubscriptionPlan(
            id=str(uuid4()), code='POS_TEST', name='POS Test', max_terminals=1, feature_json='{}'
        )
        session.add_all([role, plan])
        session.flush()
        users: list[User] = []
        for number in (1, 2):
            tenant = Tenant(
                id=str(uuid4()), code=f'CAFE-{number}', name=f'Cafe {number}', status='ACTIVE'
            )
            session.add(tenant)
            session.flush()
            outlet = Outlet(
                id=str(uuid4()), tenant_id=tenant.id, code='MAIN', name=f'Cafe {number} Main'
            )
            session.add(outlet)
            session.flush()
            user = User(
                id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id,
                role_id=role.id, username=f'admin-{number}', display_name=f'Admin {number}',
                password_hash='not-used', is_active=True,
            )
            subscription = Subscription(
                id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
                starts_at=now - timedelta(days=1), ends_at=now + timedelta(days=30),
            )
            user.role = role
            users.append(user)
            session.add_all([user, subscription])
            session.flush()
        session.commit()

    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    previous_private, previous_public = settings.license_private_key, settings.license_public_key
    settings.license_private_key = base64.b64encode(private_pem).decode('ascii')
    settings.license_public_key = base64.b64encode(public_pem).decode('ascii')
    active_user = {'value': users[0]}

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[current_user] = lambda: active_user['value']
    request = {
        'installation_id': 'shared-desktop-installation',
        'terminal_code': 'POS01',
        'terminal_name': 'Front Counter',
    }
    try:
        with TestClient(app) as client:
            first = client.post('/api/platform/device/activate', json=request)
            assert first.status_code == 200, first.text
            active_user['value'] = users[1]
            second = client.post('/api/platform/device/activate', json=request)
            assert second.status_code == 200, second.text
            assert first.json()['payload']['tenant_id'] != second.json()['payload']['tenant_id']

        with sessions() as session:
            terminals = list(session.scalars(select(PosTerminal).order_by(PosTerminal.tenant_id)))
            assert len(terminals) == 2
            assert {terminal.tenant_id for terminal in terminals} == {user.tenant_id for user in users}
            assert len({terminal.device_key_hash for terminal in terminals}) == 2
            assert all(terminal.terminal_code == 'POS01' for terminal in terminals)
    finally:
        settings.license_private_key = previous_private
        settings.license_public_key = previous_public
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
