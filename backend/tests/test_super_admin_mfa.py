import base64
import hashlib
import hmac
import struct
import time
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models import Role, Tenant, User
from app.security import hash_password


def current_totp(secret: str) -> str:
    padded = secret + '=' * ((8 - len(secret) % 8) % 8)
    digest = hmac.new(
        base64.b32decode(padded), struct.pack('>Q', int(time.time()) // 30), hashlib.sha1
    ).digest()
    offset = digest[-1] & 15
    value = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff) % 1_000_000
    return f'{value:06d}'


def test_super_admin_requires_totp_before_tokens_are_issued() -> None:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with sessions() as session:
        tenant = Tenant(id=str(uuid4()), code='BHV-RSP', name='Brew Haven RS Puram', status='ACTIVE')
        role = Role(id=str(uuid4()), code='SUPER_ADMIN', name='Super Administrator')
        user = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=None, role_id=role.id,
            username='platform-owner', display_name='Platform Owner',
            password_hash=hash_password('StrongPassword@123'), is_active=True,
        )
        session.add_all([tenant, role, user]); session.commit()

    def test_session():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            first = client.post('/api/auth/login', json={
                'tenant_code': 'BHV-RSP', 'username': 'platform-owner', 'password': 'StrongPassword@123'
            })
            assert first.status_code == 200, first.text
            challenge = first.json()
            assert challenge['status'] == 'MFA_REQUIRED'
            assert challenge['setup_required'] is True
            assert 'access_token' not in challenge
            verified = client.post('/api/auth/mfa/verify', json={
                'challenge_token': challenge['challenge_token'],
                'code': current_totp(challenge['setup_secret']),
            })
            assert verified.status_code == 200, verified.text
            assert verified.json()['user']['role_code'] == 'SUPER_ADMIN'
            assert verified.json()['access_token']

            again = client.post('/api/auth/login', json={
                'tenant_code': 'BHV-RSP', 'username': 'platform-owner', 'password': 'StrongPassword@123'
            }).json()
            assert again['setup_required'] is False
            assert again['setup_secret'] is None

        with sessions() as session:
            assert session.scalar(select(User)).mfa_enabled is True
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
