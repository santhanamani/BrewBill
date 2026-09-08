from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import current_user
from app.database import Base, get_session
from app.main import app
from app.models import Role, Subscription, SubscriptionPlan, Tenant, User
from app.security import hash_password
from app.subscriptions import require_subscription_access, subscription_lifecycle


def database():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    return engine, sessions


def seed(sessions):
    now = datetime.now(UTC)
    with sessions() as session:
        tenant = Tenant(id=str(uuid4()), code='SUB-TEST', name='Subscription Test', status='ACTIVE')
        platform = Tenant(id=str(uuid4()), code='PLATFORM', name='Platform', status='ACTIVE')
        admin_role = Role(id=str(uuid4()), code='TENANT_ADMIN', name='Tenant Admin')
        super_role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Super Admin')
        plan = SubscriptionPlan(id=str(uuid4()), code='PROFESSIONAL', name='Professional', max_terminals=3)
        session.add_all([tenant, platform, admin_role, super_role, plan]); session.flush()
        user = User(id=str(uuid4()), tenant_id=tenant.id, role_id=admin_role.id, username='admin', display_name='Admin', password_hash='x')
        super_user = User(id=str(uuid4()), tenant_id=platform.id, role_id=super_role.id, username='owner', display_name='Owner', password_hash='x')
        subscription = Subscription(
            id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
            starts_at=now-timedelta(days=20), ends_at=now+timedelta(days=30),
            grace_ends_at=now+timedelta(days=37),
        )
        session.add_all([user, super_user, subscription]); session.commit()
        user.role = admin_role; super_user.role = super_role
        return tenant, user, super_user, subscription


def test_subscription_active_warning_grace_and_expired_states() -> None:
    engine, sessions = database()
    tenant, user, _, subscription = seed(sessions)
    now = datetime.now(UTC)
    try:
        with sessions() as session:
            assert subscription_lifecycle(tenant.id, session, now).state == 'ACTIVE'
            saved = session.get(Subscription, subscription.id)
            saved.ends_at = now + timedelta(days=3)
            saved.grace_ends_at = now + timedelta(days=10)
            session.commit()
            lifecycle = subscription_lifecycle(tenant.id, session, now)
            assert lifecycle.state == 'EXPIRING_SOON'
            assert lifecycle.login_allowed is True

            saved.ends_at = now - timedelta(days=1)
            saved.grace_ends_at = now + timedelta(days=4)
            session.commit()
            lifecycle = subscription_lifecycle(tenant.id, session, now)
            assert lifecycle.state == 'GRACE'
            assert lifecycle.login_allowed is True

            saved.grace_ends_at = now - timedelta(seconds=1)
            session.commit()
            lifecycle = subscription_lifecycle(tenant.id, session, now)
            assert lifecycle.state == 'EXPIRED'
            assert lifecycle.login_allowed is False
            stored_user = session.get(User, user.id)
            stored_user.role = session.get(Role, user.role_id)
            with pytest.raises(HTTPException) as error:
                require_subscription_access(stored_user, session)
            assert error.value.status_code == 402
            assert error.value.detail['code'] == 'SUBSCRIPTION_RENEWAL_REQUIRED'
    finally:
        Base.metadata.drop_all(engine)


def test_only_super_admin_can_update_subscription_dates() -> None:
    engine, sessions = database()
    tenant, tenant_admin, super_user, _ = seed(sessions)

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        expiry = datetime.now(UTC) + timedelta(days=90)
        grace = expiry + timedelta(days=7)
        with TestClient(app) as client:
            platform_preview = client.get('/api/platform/tenants/resolve?code=PLATFORM')
            assert platform_preview.status_code == 200
            assert platform_preview.json()['login_allowed'] is True
            app.dependency_overrides[current_user] = lambda: tenant_admin
            denied = client.put(f'/api/platform/admin/tenants/{tenant.id}/subscription', json={
                'ends_at': expiry.isoformat(), 'grace_ends_at': grace.isoformat(),
            })
            assert denied.status_code == 403

            app.dependency_overrides[current_user] = lambda: super_user
            updated = client.put(f'/api/platform/admin/tenants/{tenant.id}/subscription', json={
                'ends_at': expiry.isoformat(), 'grace_ends_at': grace.isoformat(),
            })
            assert updated.status_code == 200, updated.text
            body = updated.json()
            assert body['lifecycle_state'] == 'ACTIVE'
            assert body['login_allowed'] is True

            invalid = client.put(f'/api/platform/admin/tenants/{tenant.id}/subscription', json={
                'ends_at': expiry.isoformat(), 'grace_ends_at': (expiry-timedelta(days=1)).isoformat(),
            })
            assert invalid.status_code == 422
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)


def test_login_allows_grace_and_blocks_after_grace() -> None:
    engine, sessions = database()
    tenant, user, _, subscription = seed(sessions)
    now = datetime.now(UTC)
    with sessions() as session:
        session.get(User, user.id).password_hash = hash_password('Tenant@123')
        saved = session.get(Subscription, subscription.id)
        saved.ends_at = now - timedelta(days=1)
        saved.grace_ends_at = now + timedelta(days=2)
        session.commit()

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            preview = client.get('/api/platform/tenants/resolve?code=SUB-TEST')
            assert preview.status_code == 200
            assert preview.json()['subscription_state'] == 'GRACE'
            assert preview.json()['login_allowed'] is True

            allowed = client.post('/api/auth/login', json={
                'tenant_code': 'SUB-TEST', 'username': 'admin', 'password': 'Tenant@123',
            })
            assert allowed.status_code == 200, allowed.text

            with sessions() as session:
                saved = session.get(Subscription, subscription.id)
                saved.grace_ends_at = now - timedelta(seconds=1)
                session.commit()

            blocked = client.post('/api/auth/login', json={
                'tenant_code': 'SUB-TEST', 'username': 'admin', 'password': 'Tenant@123',
            })
            assert blocked.status_code == 402
            assert blocked.json()['detail']['code'] == 'SUBSCRIPTION_RENEWAL_REQUIRED'
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)