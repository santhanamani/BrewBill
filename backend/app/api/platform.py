import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import FileResponse
from typing import Literal
from ..branding_media import LIMITS, save_image, media_path, validate_branding_url
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .deps import current_user, require_role
from ..database import get_session, settings
from ..licensing import public_key_pem, sign_payload
from ..models import LicenseEvent, Outlet, PosTerminal, Role, Subscription, SubscriptionPlan, Tenant, TenantSetting, User
from ..schemas import (
    AdminOutletCreate, AdminOutletRead, AdminOutletUpdate, AdminRoleRead,
    AdminUserCreate, AdminUserRead, AdminUserUpdate, DeviceActivationRequest,
    LicenseEnvelope, PlatformContextRead, TenantAdminRead, TenantBrandingUpdate,
    TenantCreate, TenantResolveRead, TenantUpdate,
    TenantPaymentPolicyRead, TenantPaymentPolicyUpdate,
    TenantSubscriptionRead, TenantSubscriptionUpdate,
)
from ..security import hash_password
from ..subscriptions import (
    active_subscription, grace_end, subscription_lifecycle, utc,
)

router = APIRouter(prefix='/api/platform', tags=['platform'])
PAYMENT_POLICY_KEY = 'payment_processing_mode'


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
    lifecycle = subscription_lifecycle(tenant.id, session)
    subscription = lifecycle.subscription
    is_platform_admin_tenant = session.scalar(
        select(User.id).where(User.tenant_id == tenant.id, User.role.has(code='SUPER_ADMIN'))
    ) is not None
    return TenantResolveRead(
        code=tenant.code or code.upper(), name=tenant.name, status=tenant.status,
        outlet_name=outlet.name if outlet else None,
        outlet_address=outlet.address if outlet else None,
        logo_url=tenant.logo_url, cover_image_url=tenant.cover_image_url,
        primary_color=tenant.primary_color, tagline=tenant.tagline,
        plan_code=lifecycle.plan.code if lifecycle.plan else None,
        subscription_state=lifecycle.state,
        subscription_end=subscription.ends_at if subscription else None,
        grace_ends_at=lifecycle.grace_ends_at,
        days_remaining=lifecycle.days_remaining,
        grace_days_remaining=lifecycle.grace_days_remaining,
        login_allowed=(lifecycle.login_allowed or is_platform_admin_tenant) and tenant.status == 'ACTIVE',
        subscription_message=lifecycle.message,
    )


def features(plan: SubscriptionPlan) -> dict:
    try:
        value = json.loads(plan.feature_json)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


@router.get('/context', response_model=PlatformContextRead)
def context(user: User = Depends(current_user), session: Session = Depends(get_session)) -> PlatformContextRead:
    subscription, plan = active_subscription(user, session)
    lifecycle = subscription_lifecycle(user.tenant_id, session)
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
        subscription_state=lifecycle.state,
        grace_ends_at=lifecycle.grace_ends_at,
        subscription_message=lifecycle.message,
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
    return [tenant_read(tenant, session) for tenant in tenants]


@router.post('/admin/tenants', response_model=TenantAdminRead, status_code=status.HTTP_201_CREATED)
def create_tenant(
    body: TenantCreate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantAdminRead:
    code = body.code.strip().upper()
    name = body.name.strip()
    outlet_code = body.outlet_code.strip().upper()
    outlet_name = body.outlet_name.strip()
    admin_username = body.admin_username.strip()
    admin_display_name = body.admin_display_name.strip()
    if not all((code, name, outlet_code, outlet_name, admin_username, admin_display_name)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Required tenant fields cannot be blank.')

    if session.scalar(select(Tenant.id).where(func.upper(Tenant.code) == code)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Tenant code "{code}" already exists.')
    if session.scalar(select(Tenant.id).where(func.lower(Tenant.name) == name.lower())):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Café name "{name}" already exists.')

    plan = session.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == body.plan_code.strip().upper()))
    role = session.scalar(select(Role).where(Role.code == 'TENANT_ADMIN'))
    if plan is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Subscription plan was not found.')
    if role is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Tenant administrator role is unavailable.')

    tenant = Tenant(
        id=str(uuid4()), code=code, name=name, status='ACTIVE',
        primary_color='#5A2D18', secondary_color='#C8874A',
    )
    session.add(tenant)
    try:
        # Establish the tenant row before inserting its outlet, admin and subscription.
        # These models carry foreign-key IDs directly and do not declare ORM relationships
        # that SQLAlchemy can otherwise use to infer the required flush order.
        session.flush()
        outlet = Outlet(
            id=str(uuid4()), tenant_id=tenant.id, code=outlet_code,
            name=outlet_name, address=body.outlet_address.strip() if body.outlet_address else None,
        )
        admin = User(
            id=str(uuid4()), tenant_id=tenant.id, outlet_id=outlet.id, role_id=role.id,
            username=admin_username, display_name=admin_display_name,
            password_hash=hash_password(body.admin_password), is_active=True,
        )
        subscription = Subscription(
            id=str(uuid4()), tenant_id=tenant.id, plan_id=plan.id, status='ACTIVE',
            starts_at=datetime.now(UTC), ends_at=datetime.now(UTC) + timedelta(days=365),
            grace_ends_at=datetime.now(UTC) + timedelta(days=372),
        )
        session.add(outlet)
        session.flush()
        session.add_all([admin, subscription])
        session.commit()
    except IntegrityError as error:
        session.rollback()
        constraint = getattr(getattr(error.orig, 'diag', None), 'constraint_name', '') or ''
        detail = {
            'tenants_code_key': f'Tenant code "{code}" already exists.',
            'ix_tenants_code': f'Tenant code "{code}" already exists.',
            'tenants_name_key': f'Café name "{name}" already exists.',
            'uq_outlet_tenant_code': f'Outlet code "{outlet_code}" already exists for this tenant.',
            'uq_user_tenant_username': f'Admin username "{admin_username}" already exists for this tenant.',
        }.get(constraint, 'Tenant could not be created because related data is invalid.')
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail) from error
    return tenant_read(tenant, session)

def tenant_read(tenant: Tenant, session: Session) -> TenantAdminRead:
    lifecycle = subscription_lifecycle(tenant.id, session)
    subscription = lifecycle.subscription
    return TenantAdminRead(
        id=tenant.id, code=tenant.code, name=tenant.name, status=tenant.status,
        outlet_count=session.scalar(select(func.count(Outlet.id)).where(Outlet.tenant_id == tenant.id)) or 0,
        admin_count=session.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == tenant.id,
                User.role.has(code='ADMIN') | User.role.has(code='TENANT_ADMIN'),
            )
        ) or 0,
        logo_url=tenant.logo_url, cover_image_url=tenant.cover_image_url,
        primary_color=tenant.primary_color, secondary_color=tenant.secondary_color,
        tagline=tenant.tagline, phone=tenant.phone, email=tenant.email, website=tenant.website,
        plan_code=lifecycle.plan.code if lifecycle.plan else None,
        plan_name=lifecycle.plan.name if lifecycle.plan else None,
        subscription_state=lifecycle.state,
        subscription_end=subscription.ends_at if subscription else None,
        grace_ends_at=lifecycle.grace_ends_at, login_allowed=lifecycle.login_allowed,
    )


def subscription_read(tenant_id: str, session: Session) -> TenantSubscriptionRead:
    lifecycle = subscription_lifecycle(tenant_id, session)
    subscription = lifecycle.subscription
    return TenantSubscriptionRead(
        tenant_id=tenant_id,
        subscription_id=subscription.id if subscription else None,
        plan_code=lifecycle.plan.code if lifecycle.plan else None,
        plan_name=lifecycle.plan.name if lifecycle.plan else None,
        status=subscription.status if subscription else 'MISSING',
        starts_at=subscription.starts_at if subscription else None,
        ends_at=subscription.ends_at if subscription else None,
        grace_ends_at=lifecycle.grace_ends_at,
        lifecycle_state=lifecycle.state,
        days_remaining=lifecycle.days_remaining,
        grace_days_remaining=lifecycle.grace_days_remaining,
        login_allowed=lifecycle.login_allowed,
        message=lifecycle.message,
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


@router.get('/admin/tenants/{tenant_id}/subscription', response_model=TenantSubscriptionRead)
def get_tenant_subscription(
    tenant_id: str,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantSubscriptionRead:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    return subscription_read(tenant_id, session)


@router.put('/admin/tenants/{tenant_id}/subscription', response_model=TenantSubscriptionRead)
def update_tenant_subscription(
    tenant_id: str,
    body: TenantSubscriptionUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantSubscriptionRead:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    subscription = session.scalar(
        select(Subscription).where(Subscription.tenant_id == tenant_id).order_by(Subscription.ends_at.desc())
    )
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Subscription not found for this tenant.')
    end = utc(body.ends_at)
    grace = utc(body.grace_ends_at)
    if end <= utc(subscription.starts_at):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Expiry must be after the subscription start date.')
    if grace <= end:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Grace end must be after the subscription expiry.')
    subscription.ends_at = end
    subscription.grace_ends_at = grace
    subscription.status = 'ACTIVE'
    session.commit()
    session.refresh(subscription)
    return subscription_read(tenant_id, session)

@router.get('/admin/tenants/{tenant_id}/payment-policy', response_model=TenantPaymentPolicyRead)
def get_tenant_payment_policy(
    tenant_id: str,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantPaymentPolicyRead:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    setting = session.get(TenantSetting, (tenant_id, PAYMENT_POLICY_KEY))
    mode = setting.setting_value if setting else 'MANUAL_ALLOWED'
    if mode not in ('MANUAL_ALLOWED', 'TERMINAL_REQUIRED'):
        mode = 'MANUAL_ALLOWED'
    return TenantPaymentPolicyRead(payment_processing_mode=mode)


@router.put('/admin/tenants/{tenant_id}/payment-policy', response_model=TenantPaymentPolicyRead)
def update_tenant_payment_policy(
    tenant_id: str,
    body: TenantPaymentPolicyUpdate,
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> TenantPaymentPolicyRead:
    if session.get(Tenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Tenant not found.')
    setting = session.get(TenantSetting, (tenant_id, PAYMENT_POLICY_KEY))
    if setting is None:
        setting = TenantSetting(
            tenant_id=tenant_id,
            setting_key=PAYMENT_POLICY_KEY,
            setting_value=body.payment_processing_mode,
        )
        session.add(setting)
    else:
        setting.setting_value = body.payment_processing_mode
    session.commit()
    return TenantPaymentPolicyRead(payment_processing_mode=body.payment_processing_mode)


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
    username = body.username.strip()
    if session.scalar(
        select(User.id).where(
            User.tenant_id == tenant.id,
            func.lower(User.username) == username.lower(),
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Username "{username}" already exists for this tenant.',
        )
    item = User(
        id=str(uuid4()), tenant_id=tenant.id, outlet_id=body.outlet_id, role_id=role.id,
        username=username, display_name=body.display_name.strip(), email=body.email, phone=body.phone,
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
    for image_field in ('logo_url', 'cover_image_url'):
        validate_branding_url(tenant.id, getattr(body, image_field))
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(tenant, field, value)
    session.commit()
    return tenant_read(tenant, session)



@router.post('/admin/tenants/{tenant_id}/branding/{kind}/upload')
def upload_tenant_branding(
    tenant_id: str,
    kind: Literal['logo', 'cover'],
    file: UploadFile = File(...),
    user: User = Depends(require_role('SUPER_ADMIN')),
    session: Session = Depends(get_session),
) -> dict:
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, 'Tenant not found.')
    return save_image(tenant.id, kind, file.file.read(LIMITS[kind] + 1))


@router.get('/tenants/{tenant_id}/media/{filename}')
def read_tenant_branding(tenant_id: str, filename: str, session: Session = Depends(get_session)):
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, 'Brand image not found.')
    path = media_path(tenant.id, filename)
    if not path.is_file():
        raise HTTPException(404, 'Brand image not found.')
    return FileResponse(path, media_type='image/webp', headers={
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'public, max-age=31536000, immutable',
    })

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
    # A single desktop installation may serve more than one tenant. Scope the
    # fingerprint so every tenant gets its own audited POS terminal while its
    # subscription terminal limit remains enforced independently.
    legacy_device_hash = hashlib.sha256(body.installation_id.encode('utf-8')).hexdigest()
    device_hash = hashlib.sha256(
        f'{user.tenant_id}:{body.installation_id}'.encode('utf-8')
    ).hexdigest()
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
        claimable = (
            terminal.device_key_hash.startswith('development-only')
            or terminal.device_key_hash == device_hash
            or terminal.device_key_hash == legacy_device_hash
        )
        if not claimable:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This terminal is activated on another device.')
        terminal.device_key_hash = device_hash
        terminal.terminal_name = body.terminal_name
        terminal.outlet_id = user.outlet_id
        terminal.activated_at = terminal.activated_at or now
        terminal.last_seen_at = now
        terminal.status = 'ACTIVE'

    # Persist a newly-created terminal before its LicenseEvent foreign key is inserted.
    session.flush()

    offline_until = min(now + timedelta(hours=settings.offline_license_hours), grace_end(subscription))
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
        'grace_ends_at': grace_end(subscription).isoformat(),
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
