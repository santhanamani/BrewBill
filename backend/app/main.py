from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session
from .database import get_session, settings
from .models import RefreshToken, Tenant, User
from .schemas import LoginRequest, LoginResponse, MfaChallengeResponse, MfaVerifyRequest, RefreshRequest, TokenPair, UserRead
from .security import (
    create_token, decode_token, decrypt_mfa_secret, encrypt_mfa_secret,
    generate_totp_secret, verify_password, verify_totp,
)
from .api.deps import current_user
from .subscriptions import require_subscription_access
from .api.products import router as product_router
from .api.categories import router as category_router
from .api.orders import router as order_router
from .api.dashboard import router as dashboard_router
from .api.kot import router as kot_router
from .api.operations import router as operations_router
from .api.holds import router as holds_router
from .api.platform import router as platform_router
from .api.inventory import router as inventory_router
from .api.marketplace import router as marketplace_router
from .api.messages import router as message_router
from .api.media import router as media_router

app = FastAPI(
    title="BrewBill Cloud API",
    description="Tenant-scoped APIs for BrewBill POS and administration.",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.include_router(product_router)
app.include_router(category_router)
app.include_router(order_router)
app.include_router(dashboard_router)
app.include_router(kot_router)
app.include_router(operations_router)
app.include_router(holds_router)
app.include_router(platform_router)
app.include_router(inventory_router)
app.include_router(marketplace_router)
app.include_router(message_router)
app.include_router(media_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(',') if origin.strip()],
    allow_credentials=False,
    allow_methods=['*'],
    allow_headers=['*'],
)


def issue_pair(user: User, session: Session) -> TokenPair:
    access, _ = create_token(user.id, user.tenant_id, "access", timedelta(minutes=settings.jwt_access_expire_minutes))
    refresh, token_id = create_token(user.id, user.tenant_id, "refresh", timedelta(days=settings.jwt_refresh_expire_days))
    session.add(RefreshToken(id=__import__('uuid').uuid4().hex, token_id=token_id, user_id=user.id, expires_at=datetime.now(UTC) + timedelta(days=settings.jwt_refresh_expire_days)))
    session.commit()
    return TokenPair(access_token=access, refresh_token=refresh)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/login", response_model=LoginResponse | MfaChallengeResponse)
def login(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse | MfaChallengeResponse:
    if not body.tenant_code:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Cafe / tenant code is required.')
    query = session.query(User).filter(User.username == body.username)
    if body.tenant_code:
        query = query.join(Tenant, Tenant.id == User.tenant_id).filter(
            func.upper(Tenant.code) == body.tenant_code.strip().upper()
        )
    elif body.tenant_name:
        query = query.join(Tenant, Tenant.id == User.tenant_id).filter(Tenant.name == body.tenant_name)
    matches = query.limit(2).all()
    if len(matches) > 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Tenant name is required for this username.')
    user = matches[0] if matches else None
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    tenant = session.get(Tenant, user.tenant_id)
    if tenant is None or tenant.status != 'ACTIVE':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='This cafe account is not active.')
    require_subscription_access(user, session)
    if user.role_code == 'SUPER_ADMIN':
        setup_required = not user.mfa_enabled or not user.mfa_secret_encrypted
        if not user.mfa_secret_encrypted:
            secret = generate_totp_secret()
            user.mfa_secret_encrypted = encrypt_mfa_secret(secret)
            session.commit()
        else:
            secret = decrypt_mfa_secret(user.mfa_secret_encrypted)
        challenge, _ = create_token(user.id, user.tenant_id, 'mfa', timedelta(minutes=5))
        label = quote(f'Brew Haven:{user.username}')
        uri = f'otpauth://totp/{label}?secret={secret}&issuer={quote("Brew Haven")}' if setup_required else None
        return MfaChallengeResponse(
            challenge_token=challenge, setup_required=setup_required,
            setup_secret=secret if setup_required else None, otpauth_uri=uri,
        )
    pair = issue_pair(user, session)
    return LoginResponse(**pair.model_dump(), user=UserRead.model_validate(user))


@app.post('/api/auth/mfa/verify', response_model=LoginResponse)
def verify_mfa(body: MfaVerifyRequest, session: Session = Depends(get_session)) -> LoginResponse:
    payload = decode_token(body.challenge_token, 'mfa')
    user = session.get(User, payload['sub'])
    if user is None or not user.is_active or user.tenant_id != payload.get('tenant_id') or user.role_code != 'SUPER_ADMIN':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='MFA challenge is no longer valid.')
    if not user.mfa_secret_encrypted or not verify_totp(decrypt_mfa_secret(user.mfa_secret_encrypted), body.code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='The verification code is invalid or expired.')
    user.mfa_enabled = True
    session.flush()
    pair = issue_pair(user, session)
    return LoginResponse(**pair.model_dump(), user=UserRead.model_validate(user))


@app.post("/api/auth/refresh", response_model=TokenPair)
def refresh(body: RefreshRequest, session: Session = Depends(get_session)) -> TokenPair:
    payload = decode_token(body.refresh_token, "refresh")
    record = session.query(RefreshToken).filter(RefreshToken.token_id == payload["jti"], RefreshToken.revoked.is_(False)).one_or_none()
    if record is None or record.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is no longer valid")
    require_subscription_access(record.user, session)
    record.revoked = True
    session.flush()
    return issue_pair(record.user, session)


@app.post('/api/auth/logout', status_code=status.HTTP_204_NO_CONTENT)
def logout(body: RefreshRequest, session: Session = Depends(get_session)) -> None:
    payload = decode_token(body.refresh_token, 'refresh')
    record = session.query(RefreshToken).filter(RefreshToken.token_id == payload['jti'], RefreshToken.revoked.is_(False)).one_or_none()
    if record is not None:
        record.revoked = True
        session.commit()


@app.get("/api/me", response_model=UserRead)
def me(user: User = Depends(current_user)) -> User:
    return user
