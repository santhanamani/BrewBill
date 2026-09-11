from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .deps import require_role
from ..database import get_session
from ..models import KotHeader, Order, User
from ..schemas import KotItemRead, KotRead, KotStatusUpdate

router = APIRouter(prefix='/api/kot', tags=['kot'])
INDIA = ZoneInfo('Asia/Kolkata')


def to_read(kot: KotHeader, order: Order | None, cashier_name: str) -> KotRead:
    return KotRead(
        id=kot.id,
        kot_number=kot.kot_number,
        invoice_number=order.invoice_number if order else 'Unknown',
        cashier_name=cashier_name,
        station=kot.station,
        status=kot.status,
        created_at=kot.created_at,
        items=[KotItemRead(product_name=item.product_name, variant_name=item.variant_name, quantity=item.quantity) for item in kot.items],
    )


@router.get('', response_model=list[KotRead])
def list_kots(
    completed_date: date | None = Query(default=None),
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[KotRead]:
    conditions = [KotHeader.tenant_id == user.tenant_id, KotHeader.outlet_id == user.outlet_id]
    if completed_date:
        start = datetime.combine(completed_date, time.min, INDIA).astimezone(UTC)
        end = datetime.combine(completed_date + timedelta(days=1), time.min, INDIA).astimezone(UTC)
        conditions.append(or_(
            KotHeader.status != 'SERVED',
            (KotHeader.created_at >= start) & (KotHeader.created_at < end),
        ))
    kots = session.scalars(
        select(KotHeader)
        .where(*conditions)
        .options(selectinload(KotHeader.items))
        .order_by(KotHeader.created_at.desc())
        .limit(1000)
    ).all()
    order_ids = {kot.order_id for kot in kots}
    orders = {
        order.id: order
        for order in session.scalars(select(Order).where(Order.id.in_(order_ids))).all()
    } if order_ids else {}
    cashier_ids = {order.cashier_id for order in orders.values() if order.cashier_id}
    cashiers = {
        cashier.id: cashier.display_name
        for cashier in session.scalars(select(User).where(User.id.in_(cashier_ids))).all()
    } if cashier_ids else {}
    return [
        to_read(kot, orders.get(kot.order_id), cashiers.get(orders[kot.order_id].cashier_id, 'Unknown') if kot.order_id in orders else 'Unknown')
        for kot in kots
    ]


@router.patch('/{kot_id}/status', response_model=KotRead)
def update_kot_status(
    kot_id: str,
    body: KotStatusUpdate,
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> KotRead:
    kot = session.scalar(
        select(KotHeader)
        .where(KotHeader.id == kot_id, KotHeader.tenant_id == user.tenant_id, KotHeader.outlet_id == user.outlet_id)
        .options(selectinload(KotHeader.items))
        .with_for_update()
    )
    if kot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Kitchen ticket not found.')
    allowed = {
        'NEW': {'PREPARING', 'DELAYED'},
        'PREPARING': {'READY', 'DELAYED'},
        'DELAYED': {'PREPARING', 'READY'},
        'READY': {'SERVED'},
        'SERVED': set(),
    }
    if body.status != kot.status and body.status not in allowed.get(kot.status, set()):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'Cannot move KOT from {kot.status} to {body.status}.')
    kot.status = body.status
    order = session.get(Order, kot.order_id)
    cashier = session.get(User, order.cashier_id) if order and order.cashier_id else None
    session.commit()
    session.refresh(kot)
    return to_read(kot, order, cashier.display_name if cashier else 'Unknown')
