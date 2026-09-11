from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Outlet, Role, Tenant, TenantSetting, User
from app.owner_access import owner_setting_key, resolve_read_scope
from app.api.platform import list_owner_tenants


def test_owner_can_only_resolve_assigned_tenants_and_outlets() -> None:
    engine = create_engine(
        'sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool
    )
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)

    with sessions() as session:
        assigned_a = Tenant(id=str(uuid4()), code='BRANCH-A', name='Branch A', status='ACTIVE')
        assigned_b = Tenant(id=str(uuid4()), code='BRANCH-B', name='Branch B', status='ACTIVE')
        forbidden = Tenant(id=str(uuid4()), code='BRANCH-C', name='Branch C', status='ACTIVE')
        outlet_b = Outlet(id=str(uuid4()), tenant_id=assigned_b.id, code='AAAA', name='Outlet B')
        owner_role = Role(id=str(uuid4()), code='OWNER', name='Multi-Tenant Owner')
        owner = User(
            id=str(uuid4()), tenant_id=assigned_a.id, outlet_id=None, role_id=owner_role.id,
            username='portfolio-owner', display_name='Portfolio Owner', password_hash='not-used',
            is_active=True,
        )
        owner.role = owner_role
        session.add_all([assigned_a, assigned_b, forbidden, outlet_b, owner_role, owner])
        session.flush()
        session.add(TenantSetting(
            tenant_id=assigned_a.id,
            setting_key=owner_setting_key(owner.id),
            setting_value=f'["{assigned_a.id}","{assigned_b.id}"]',
        ))
        session.commit()

        assert resolve_read_scope(session, owner, assigned_a.id, None) == (assigned_a.id, None)
        assert resolve_read_scope(session, owner, assigned_b.id, outlet_b.id) == (assigned_b.id, outlet_b.id)
        scopes = list_owner_tenants(user=owner, session=session)
        assert {scope.tenant_id for scope in scopes} == {assigned_a.id, assigned_b.id}
        assert all(scope.currency.code == 'INR' for scope in scopes)
        with pytest.raises(HTTPException) as denied:
            resolve_read_scope(session, owner, forbidden.id, None)
        assert denied.value.status_code == 403


def test_legacy_regular_user_scope_remains_tenant_and_outlet_bound() -> None:
    tenant_id, outlet_id = str(uuid4()), str(uuid4())
    user = SimpleNamespace(tenant_id=tenant_id, outlet_id=outlet_id)
    engine = create_engine('sqlite+pysqlite://', poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with sessions() as session:
        session.add(Tenant(id=tenant_id, code='REGULAR', name='Regular', status='ACTIVE'))
        session.add(Outlet(id=outlet_id, tenant_id=tenant_id, code='AAAB', name='Main'))
        session.commit()
        assert resolve_read_scope(session, user) == (tenant_id, outlet_id)
