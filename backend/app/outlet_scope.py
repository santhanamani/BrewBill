from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Outlet, User


def resolve_operational_outlet(
    session: Session,
    user: User,
    requested_outlet_id: str | None = None,
) -> str:
    """Resolve an operational outlet while enforcing tenant and user boundaries."""
    if requested_outlet_id and user.outlet_id and requested_outlet_id != user.outlet_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='The selected outlet is not assigned to this user.',
        )
    if requested_outlet_id and not user.outlet_id and user.role_code not in ('ADMIN', 'TENANT_ADMIN'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='This user cannot select another outlet.',
        )
    outlet_id = requested_outlet_id or user.outlet_id
    if not outlet_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='Select an outlet before continuing.',
        )
    outlet = session.scalar(
        select(Outlet).where(Outlet.id == outlet_id, Outlet.tenant_id == user.tenant_id)
    )
    if outlet is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail='The selected outlet is not available for this tenant.',
        )
    return outlet.id
