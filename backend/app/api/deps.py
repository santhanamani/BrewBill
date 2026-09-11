from typing import Annotated
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm.attributes import set_committed_value
from sqlalchemy.orm import Session
from ..database import get_session
from ..models import User
from ..outlet_scope import resolve_operational_outlet
from ..security import decode_token
from ..subscriptions import require_subscription_access


OPERATIONAL_PATHS = (
    '/api/dashboard', '/api/orders', '/api/holds', '/api/kot', '/api/products',
    '/api/inventory', '/api/suppliers', '/api/purchases', '/api/expenses',
    '/api/customers', '/api/closings', '/api/marketplace',
)


def current_user(
    request: Request,
    authorization: Annotated[str, Header()],
    x_brewbill_outlet: Annotated[str | None, Header(alias='X-BrewBill-Outlet')] = None,
    session: Session = Depends(get_session),
) -> User:
    payload = decode_token(authorization.removeprefix('Bearer '), 'access')
    user = session.get(User, payload['sub'])
    if user is None or not user.is_active or user.tenant_id != payload.get('tenant_id'):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Session is no longer valid')
    require_subscription_access(user, session)
    if x_brewbill_outlet and request.url.path.startswith(OPERATIONAL_PATHS):
        selected_outlet_id = resolve_operational_outlet(session, user, x_brewbill_outlet)
        # Request-local effective scope. Marking it committed prevents a later
        # transaction commit from permanently assigning this multi-outlet admin.
        set_committed_value(user, 'outlet_id', selected_outlet_id)
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
