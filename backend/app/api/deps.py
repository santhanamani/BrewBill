from typing import Annotated
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_session
from ..models import User
from ..security import decode_token
from ..subscriptions import require_subscription_access


def current_user(authorization: Annotated[str, Header()], session: Session = Depends(get_session)) -> User:
    payload = decode_token(authorization.removeprefix('Bearer '), 'access')
    user = session.get(User, payload['sub'])
    if user is None or not user.is_active or user.tenant_id != payload.get('tenant_id'):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session is no longer valid')
    require_subscription_access(user, session)
    return user


def require_role(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        allowed = set(roles)
        # ADMIN is retained as the backwards-compatible tenant administrator
        # code. New installations may use the explicit TENANT_ADMIN code.
        if 'ADMIN' in allowed:
            allowed.add('TENANT_ADMIN')
        if 'TENANT_ADMIN' in allowed:
            allowed.add('ADMIN')
        if user.role_code not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient permission')
        return user
    return dependency
