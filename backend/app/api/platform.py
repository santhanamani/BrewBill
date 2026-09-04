import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .deps import current_user, require_role
from ..database import get_session, settings
from ..licensing import public_key_pem, sign_payload
from ..models import LicenseEvent, Outlet, PosTerminal, Role, Subscription, SubscriptionPlan, Tenant, User
from ..schemas import (
    AdminOutletCreate, AdminOutletRead, AdminOutletUpdate, AdminRoleRead,
    AdminUserCreate, AdminUserRead, AdminUserUpdate, DeviceActivationRequest,
    LicenseEnvelope, PlatformContextRead, TenantAdminRead, TenantBrandingUpdate,
    TenantCreate, TenantResolveRead, TenantUpdate,
)
from ..security import hash_password

router = APIRouter(prefix='/api/platform', tags=['platform'])


def branding(tenant: Tenant) -> dict[str, str | None]:
    return {
        'display_name': tenant.name,
        'logo_url': tenant.logo_url,
        'cover_image_url': tenant.cover_image_url,
        'primary_color': tenant.primary_color,
        'secondary_color': tenant.secondary_color,
        'tagline': tenant.tagline,
    }


@router.get('/tenants/resolve', response_model=TenantResolveRead)
def resolve_tenant(
    code: str = Query(min_length=2, max_length=32),
    session: Session = Depends(get_session),
) -> TenantResolveRead:
    tenant = session.scalar(select(Tenant).where(func.upper(Tenant.code) == code.strip().upper()))
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Cafe code was not found.')
    outlet = session.scalar(select(Outlet).where(Outlet.tenant_id == tenant.id).order_by(Outlet.created_at))
    return TenantResolveRead(
        code=tenant.code or code.upper(), name=tenant.name, status=tenant.status,
        outlet_name=outlet.name if outlet else None,
        outlet_address=outlet.address if outlet else None,
        logo_url=tenant.logo_url, cover_image_url=tenant.cover_image_url,
        primary_color=tenant.primary_color, tagline=tenant.tagline,
    )


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def active_subscription(user: User, session: Session) -> tuple[Subscription, SubscriptionPlan]:
    now = datetime.now(UTC)
    subscription = session.scalar(
        select(Subscription)
        .where(Subscription.tenant_id == user.tenant_id, Subscription.status == 'ACTIVE')
        .order_by(Subscription.ends_at.desc())
    )
    if subscription is None or utc(subscription.starts_at) > now or utc(subscription.ends_at) <= now:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail='Subscription is not active.')
    plan = session.get(SubscriptionPlan, subscription.plan_id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Subscription plan is unavailable.')
    return subscription, plan


def features(plan: SubscriptionPlan) -> dict:
    try:
        value = json.loads(plan.feature_json)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


@router.get('/context', response_model=PlatformContextRead)
def context(user: User = Depends(current_user), session: Session = Depends(get_session)) -> PlatformContextRead:
    subscription, plan = active_subscription(user, session)
    tenant = session.get(Tenant, user.tenant_id)
    outlet = session.get(Outlet, user.outlet_id) if user.outlet_id else None
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Tenant context is unavailable.')
    return PlatformContextRead(
        tenant_id=user.tenant_id,
        tenant_code=tenant.code,
        tenant_name=tenant.name,
        outlet_id=user.outlet_id,
        outlet_code=outlet.code if outlet else None,
        outlet_name=outlet.name if outlet else None,
        role_code=user.role_code,
        branding=branding(tenant),
        subscription_status=subscription.status,
        subscription_end=subscription.ends_at,
        plan_code=plan.code,
        max_terminals=plan.max_terminals,
        features=features(plan),
    )


@router.get('/admin/tenants', response_model=list[TenantAdminRead])
def list_tenants(
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> list[TenantAdminRead]:
    tenants = session.scalars(select(Tenant).order_by(Tenant.name)).all()
    return [TenantAdminRead(
        id=tenant.id, code=tenant.code, name=tenant.name, status=tenant.status,
        outlet_count=session.scalar(select(func.count(Outlet.id)).where(Outlet.tenant_id == tenant.id)) or 0,
        admin_count=session.scalar(
            select(func.count(User.id)).join(User.role).where(
                User.tenant_id == tenant.id,
                User.role.has(code='ADMIN') | User.role.has(code='TENANT_ADMIN'),
            )
        ) or 0,
        logo_url=tenant.logo_url, primary_color=tenant.primary_color, tagline=tenant.tagline,
    ) for tenant in tenants]


@router.post('/admin/tenants', response_model=TenantAdminRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantAdminRead:
    plan = session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == body.plan_code))
    role = session.scalar(select(Role).where(Role.code == 'TENANT_ADMIN'))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Subscription plan was not found.')
    if role is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Tenant administrator role is unavailable.')
    tenant = Tenant(
        id=str(uuid4()), code=body.code.upper(), name=body.name, status='ACTIVE',
        primary_color='#5A2D18', secondary_color='#C8874A',
    )
    outlet = Outlet(
        id=str(uuid4()), tenant_id=tenant.id, code=body.outlet_code.upper(),
        name=body.outlet_name, address=body.outlet_address,
    )
    admin = User(
        id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id,
        username=body.admin_username, display_name=body.admin_display_name,
        password_hash=hash_password(body.admin_password), is_active=True,
    )
    subscription = Subscription(
        id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
        starts_at=datetime.now(UTC), ends_at=datetime.now(UTC) + timedelta(days=365),
    )
    session.add_all([tenant, outlet, admin, subscription])
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Tenant code, name, or admin username already exists.') from error
    return TenantAdminRead(
        id=tenant.id, code=tenant.code, name=tenant.name, status=tenant.status,
        outlet_count=1, admin_count=1, logo_url=tenant.logo_url,
        primary_color=tenant.primary_color, tagline=tenant.tagline,
    )


def tenant_read(tenant: Tenant, session: Session) -> TenantAdminRead:
    return TenantAdminRead(
        id=tenant.id, code=tenant.code, name=tenant.name, status=tenant.status,
        outlet_count=session.scalar(select(func.count(Outlet.id)).where(Outlet.tenant_id == tenant.id)) or 0,
        admin_count=session.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == tenant.id,
                User.role.has(code='ADMIN') | User.role.has(code='TENANT_ADMIN'),
            )
        ) or 0,
        logo_url=tenant.logo_url, primary_color=tenant.primary_color, tagline=tenant.tagline,
    )


@router.patch('/admin/tenants/{tenant_id}', response_model=TenantAdminRead)
def update_tenant(
    tenant_id: str, body: TenantUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantAdminRead:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Tenant name already exists.') from error
    return tenant_read(tenant, session)


@router.get('/admin/outlets', response_model=list[AdminOutletRead])
def list_admin_outlets(
    tenant_id: str | None = None,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> list[Outlet]:
    query = select(Outlet).order_by(Outlet.name)
    if tenant_id:
        query = query.where(Outlet.tenant_id == tenant_id)
    return list(session.scalars(query).all())


@router.post('/admin/outlets', response_model=AdminOutletRead, status_code=status.HTTP_201_CREATED)
def create_admin_outlet(
    body: AdminOutletCreate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> Outlet:
    if session.get(Tenant, body.tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    outlet = Outlet(id=str(uuid4()), tenant_id=body.tenant_id, code=body.code.upper(), name=body.name, address=body.address)
    session.add(outlet)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Outlet code already exists for this tenant.') from error
    session.refresh(outlet)
    return outlet


@router.patch('/admin/outlets/{outlet_id}', response_model=AdminOutletRead)
def update_admin_outlet(
    outlet_id: str, body: AdminOutletUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> Outlet:
    outlet = session.get(Outlet, outlet_id)
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Outlet not found.')
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(outlet, field, value)
    session.commit()
    session.refresh(outlet)
    return outlet


def admin_user_read(item: User, session: Session) -> AdminUserRead:
    tenant = session.get(Tenant, item.tenant_id)
    outlet = session.get(Outlet, item.outlet_id) if item.outlet_id else None
    return AdminUserRead(
        id=item.id, tenant_id=item.tenant_id, tenant_name=tenant.name if tenant else '',
        outlet_id=item.outlet_id, outlet_name=outlet.name if outlet else None,
        username=item.username, display_name=item.display_name, email=item.email,
        phone=item.phone, role_code=item.role_code, is_active=item.is_active,
        last_active=item.updated_at,
    )


@router.get('/admin/users', response_model=list[AdminUserRead])
def list_admin_users(
    tenant_id: str | None = None,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> list[AdminUserRead]:
    query = select(User).where(User.role.has(Role.code != 'SUPER_ADMIN')).order_by(User.display_name)
    if tenant_id:
        query = query.where(User.tenant_id == tenant_id)
    return [admin_user_read(item, session) for item in session.scalars(query).all()]


@router.post('/admin/users', response_model=AdminUserRead, status_code=status.HTTP_201_CREATED)
def create_admin_user(
    body: AdminUserCreate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> AdminUserRead:
    tenant = session.get(Tenant, body.tenant_id)
    role = session.scalar(select(Role).where(Role.code == body.role_code))
    outlet = session.get(Outlet, body.outlet_id) if body.outlet_id else None
    if tenant is None or role is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Tenant or role was not found.')
    if outlet and outlet.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Outlet does not belong to the selected tenant.')
    item = User(
        id=str(uuid4()), tenant_id=tenant.id, outlet_id=body.outlet_id, role_id=role.id,
        username=body.username, display_name=body.display_name, email=body.email, phone=body.phone,
        password_hash=hash_password(body.password), is_active=True,
    )
    session.add(item)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Username already exists for this tenant.') from error
    return admin_user_read(item, session)


@router.patch('/admin/users/{user_id}', response_model=AdminUserRead)
def update_admin_user(
    user_id: str, body: AdminUserUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> AdminUserRead:
    item = session.get(User, user_id)
    if item is None or item.role_code == 'SUPER_ADMIN':
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant user not found.')
    values = body.model_dump(exclude_unset=True)
    role_code = values.pop('role_code', None)
    password = values.pop('password', None)
    if role_code:
        role = session.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Role not found.')
        item.role_id = role.id
    if password:
        item.password_hash = hash_password(password)
    for field, value in values.items():
        setattr(item, field, value)
    if item.outlet_id:
        outlet = session.get(Outlet, item.outlet_id)
        if outlet is None or outlet.tenant_id != item.tenant_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Outlet does not belong to this tenant.')
    session.commit()
    return admin_user_read(item, session)


@router.get('/admin/roles', response_model=list[AdminRoleRead])
def list_admin_roles(
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> list[Role]:
    return list(session.scalars(select(Role).where(Role.code.in_(['TENANT_ADMIN', 'ADMIN', 'CASHIER'])).order_by(Role.name)).all())


@router.patch('/admin/tenants/{tenant_id}/branding', response_model=TenantAdminRead)
def update_tenant_branding(
    tenant_id: str,
    body: TenantBrandingUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantAdminRead:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    session.commit()
    return TenantAdminRead(
        id=tenant.id, code=tenant.code, name=tenant.name, status=tenant.status,
        outlet_count=session.scalar(select(func.count(Outlet.id)).where(Outlet.tenant_id == tenant.id)) or 0,
        admin_count=session.scalar(select(func.count(User.id)).where(User.tenant_id == tenant.id)) or 0,
        logo_url=tenant.logo_url, primary_color=tenant.primary_color, tagline=tenant.tagline,
    )


@router.post('/device/activate', response_model=LicenseEnvelope)
def activate_device(
    body: DeviceActivationRequest,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> LicenseEnvelope:
    if user.outlet_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='An outlet must be assigned before activation.')
    subscription, plan = active_subscription(user, session)
    now = datetime.now(UTC)
    device_hash = hashlib.sha256(body.installation_id.encode('utf-8')).hexdigest()
    terminal = session.scalar(
        select(PosTerminal)
        .where(PosTerminal.tenant_id == user.tenant_id, PosTerminal.terminal_code == body.terminal_code)
        .with_for_update()
    )
    existing_device = session.scalar(select(PosTerminal).where(PosTerminal.device_key_hash == device_hash))
    if existing_device is not None and (terminal is None or existing_device.id != terminal.id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This device is already assigned to another terminal.')
    if terminal is None:
        active_count = session.scalar(
            select(func.count(PosTerminal.id)).where(
                PosTerminal.tenant_id == user.tenant_id,
                PosTerminal.status == 'ACTIVE',
            )
        ) or 0
        if active_count >= plan.max_terminals:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The subscription terminal limit has been reached.')
        terminal = PosTerminal(
            id=str(uuid4()),
            tenant_id=user.tenant_id,
            outlet_id=user.outlet_id,
            terminal_code=body.terminal_code,
            terminal_name=body.terminal_name,
            device_key_hash=device_hash,
            activated_at=now,
            last_seen_at=now,
            status='ACTIVE',
        )
        session.add(terminal)
    else:
        claimable = terminal.device_key_hash.startswith('development-only') or terminal.device_key_hash == device_hash
        if not claimable:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This terminal is activated on another device.')
        terminal.device_key_hash = device_hash
        terminal.terminal_name = body.terminal_name
        terminal.outlet_id = user.outlet_id
        terminal.activated_at = terminal.activated_at or now
        terminal.last_seen_at = now
        terminal.status = 'ACTIVE'

    offline_until = min(now + timedelta(hours=settings.offline_license_hours), utc(subscription.ends_at))
    payload = {
        'tenant_id': user.tenant_id,
        'outlet_id': user.outlet_id,
        'terminal_id': terminal.id,
        'terminal_code': terminal.terminal_code,
        'plan_code': plan.code,
        'subscription_plan': plan.code,
        'features': features(plan),
        'license_version': 1,
        'issued_at': now.isoformat(),
        'offline_valid_until': offline_until.isoformat(),
        'subscription_end': utc(subscription.ends_at).isoformat(),
    }
    try:
        signature = sign_payload(payload)
        public_key = public_key_pem()
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
    session.add(LicenseEvent(
        id=str(uuid4()),
        tenant_id=user.tenant_id,
        terminal_id=terminal.id,
        event_type='ACTIVATED' if terminal.activated_at == now else 'REFRESHED',
        expires_at=offline_until,
    ))
    session.commit()
    return LicenseEnvelope(payload=payload, signature=signature, public_key=public_key)
