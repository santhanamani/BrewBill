import json

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Outlet, Tenant, TenantSetting, User

OWNER_SETTING_PREFIX = '__platform_owner_tenants__:'


def owner_setting_key(user_id: str) -> str:
    return f'{OWNER_SETTING_PREFIX}{user_id}'


def owner_tenant_ids(session: Session, user: User) -> set[str]:
    setting = session.get(TenantSetting, (user.tenant_id, owner_setting_key(user.id)))
    if setting is None:
        return set()
    try:
        values = json.loads(setting.setting_value)
    except (TypeError, ValueError):
        return set()
    return {str(value) for value in values if isinstance(value, str)} if isinstance(values, list) else set()


def resolve_read_scope(
    session: Session,
    user: User,
    requested_tenant_id: str | None = None,
    requested_outlet_id: str | None = None,
) -> tuple[str, str | None]:
    """Resolve a dashboard/report scope without allowing cross-tenant access."""
    role_code = getattr(user, 'role_code', '')
    if role_code == 'OWNER':
        allowed = owner_tenant_ids(session, user)
        tenant_id = requested_tenant_id or (user.tenant_id if user.tenant_id in allowed else None)
        if tenant_id is None and allowed:
            tenant_id = sorted(allowed)[0]
        if tenant_id is None or tenant_id not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='This tenant is not assigned to the owner.')
    else:
        tenant_id = user.tenant_id
        if requested_tenant_id and requested_tenant_id != tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Cross-tenant access is not allowed.')

    tenant = session.get(Tenant, tenant_id)
    if tenant is None or tenant.status != 'ACTIVE':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='The selected tenant is not active.')

    if role_code == 'OWNER':
        outlet_id = requested_outlet_id
    else:
        outlet_id = user.outlet_id
        if requested_outlet_id and requested_outlet_id != outlet_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Cross-outlet access is not allowed.')
    if outlet_id:
        outlet = session.scalar(select(Outlet).where(Outlet.id == outlet_id, Outlet.tenant_id == tenant_id))
        if outlet is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Outlet does not belong to the selected tenant.')
    return tenant_id, outlet_id
