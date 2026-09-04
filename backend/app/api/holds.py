from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from .deps import current_user
from ..database import get_session
from ..models import AuditLog, HeldOrder, Order, OrderItem, OutletProductMapping, PosTerminal, Product, ProductVariant, User
from ..schemas import HeldItemRead, HeldOrderRead, HoldCreate

router = APIRouter(prefix='/api/holds', tags=['holds'])
MONEY = Decimal('0.01')


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def view(held: HeldOrder) -> HeldOrderRead:
    return HeldOrderRead(
        id=held.id,
        hold_number=held.hold_number,
        invoice_number=held.order.invoice_number,
        held_at=held.held_at,
        cashier_name=held.cashier.display_name,
        subtotal=held.order.subtotal,
        tax=held.order.tax,
        grand_total=held.order.grand_total,
        items=[HeldItemRead(
            product_id=item.product_id, variant_id=item.variant_id,
            product_name=item.product_name, variant_name=item.variant_name,
            quantity=item.quantity, rate=item.rate, tax=item.tax, line_total=item.line_total,
        ) for item in held.order.items],
    )


@router.get('', response_model=list[HeldOrderRead])
def list_holds(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[HeldOrderRead]:
    rows = session.scalars(
        select(HeldOrder)
        .where(HeldOrder.tenant_id == user.tenant_id, HeldOrder.outlet_id == user.outlet_id, HeldOrder.status == 'HELD')
        .options(selectinload(HeldOrder.order).selectinload(Order.items), selectinload(HeldOrder.cashier))
        .order_by(HeldOrder.held_at.desc())
    ).all()
    return [view(row) for row in rows]


@router.post('', response_model=HeldOrderRead, status_code=status.HTTP_201_CREATED)
def create_hold(
    body: HoldCreate,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> HeldOrderRead:
    terminal = session.scalar(select(PosTerminal).where(
        PosTerminal.tenant_id == user.tenant_id,
        PosTerminal.outlet_id == user.outlet_id,
        PosTerminal.terminal_code == body.terminal_code,
        PosTerminal.status == 'ACTIVE',
    ))
    if terminal is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='This terminal is not active for the signed-in outlet.')
    product_ids = [line.product_id for line in body.items]
    products = session.scalars(select(Product).where(
        Product.tenant_id == user.tenant_id,
        Product.id.in_(product_ids),
        or_(Product.outlet_id.is_(None), Product.outlet_id == user.outlet_id),
    )).all()
    product_by_id = {product.id: product for product in products}
    if len(product_by_id) != len(set(product_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='One or more products no longer exist.')
    mappings = session.scalars(select(OutletProductMapping).where(
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == user.outlet_id,
        OutletProductMapping.legacy_product_id.in_(product_ids),
    )).all()
    mapping_by_product = {mapping.legacy_product_id: mapping for mapping in mappings}
    catalogue_enabled = session.scalar(select(OutletProductMapping.id).where(
        OutletProductMapping.tenant_id == user.tenant_id,
        OutletProductMapping.outlet_id == user.outlet_id,
    ).limit(1)) is not None
    if catalogue_enabled and len(mapping_by_product) != len(set(product_ids)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='One or more products are not mapped to this outlet.')
    variant_ids = [line.variant_id for line in body.items if line.variant_id]
    variants = session.scalars(select(ProductVariant).where(ProductVariant.tenant_id == user.tenant_id, ProductVariant.id.in_(variant_ids))).all() if variant_ids else []
    variant_by_id = {variant.id: variant for variant in variants}
    if len(variant_by_id) != len(set(variant_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='One or more product variants no longer exist.')

    subtotal = Decimal('0.00')
    tax = Decimal('0.00')
    lines: list[OrderItem] = []
    for requested in body.items:
        product = product_by_id[requested.product_id]
        mapping = mapping_by_product.get(product.id)
        variant = variant_by_id.get(requested.variant_id) if requested.variant_id else None
        if variant is not None and (variant.product_id != product.id or not variant.is_active):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Invalid variant for {product.name}.')
        is_active = mapping.is_active if mapping else product.is_active
        is_available = mapping.is_available if mapping else product.is_available
        if not is_active or not is_available:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'{product.name} is unavailable.')
        base_price = mapping.selling_price if mapping else product.selling_price
        tax_percent = (mapping.tax_override if mapping.tax_override is not None else product.gst_percent) if mapping else product.gst_percent
        product_name = (mapping.outlet_specific_name or product.name) if mapping else product.name
        rate = money(base_price + (variant.price_adjustment if variant else Decimal('0.00')))
        line_total = money(rate * requested.quantity)
        line_tax = money(line_total * tax_percent / Decimal('100'))
        subtotal += line_total
        tax += line_tax
        lines.append(OrderItem(id=str(uuid4()), product_id=product.id, variant_id=variant.id if variant else None, product_name=product_name, variant_name=variant.name if variant else 'Regular', quantity=requested.quantity, rate=rate, tax=line_tax, line_total=line_total))

    sequence = session.query(HeldOrder).filter(HeldOrder.tenant_id == user.tenant_id).count() + 1
    order = Order(
        id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=terminal.outlet_id, terminal_id=terminal.id,
        cashier_id=user.id, invoice_number=f'HOLD-{body.terminal_code}-{datetime.now(UTC).year}-{sequence:06d}',
        subtotal=money(subtotal), discount=Decimal('0.00'), tax=money(tax), round_off=Decimal('0.00'), grand_total=money(subtotal + tax), status='HELD',
        items=lines,
    )
    held = HeldOrder(
        id=str(uuid4()), tenant_id=user.tenant_id, outlet_id=terminal.outlet_id, order_id=order.id,
        cashier_id=user.id, hold_number=f'HLD-{sequence:06d}', status='HELD', order=order, cashier=user,
    )
    session.add(held)
    session.commit()
    session.refresh(held)
    return view(held)


@router.get('/{hold_id}', response_model=HeldOrderRead)
def get_hold(
    hold_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> HeldOrderRead:
    held = session.scalar(
        select(HeldOrder)
        .where(HeldOrder.id == hold_id, HeldOrder.tenant_id == user.tenant_id, HeldOrder.outlet_id == user.outlet_id, HeldOrder.status == 'HELD')
        .options(selectinload(HeldOrder.order).selectinload(Order.items), selectinload(HeldOrder.cashier))
    )
    if held is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Held order not found.')
    return view(held)


@router.post('/{hold_id}/reopen', response_model=HeldOrderRead)
def reopen_hold(
    hold_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> HeldOrderRead:
    held = session.scalar(
        select(HeldOrder)
        .where(
            HeldOrder.id == hold_id,
            HeldOrder.tenant_id == user.tenant_id,
            HeldOrder.outlet_id == user.outlet_id,
            HeldOrder.status == 'HELD',
        )
        .options(selectinload(HeldOrder.order).selectinload(Order.items), selectinload(HeldOrder.cashier))
        .with_for_update()
    )
    if held is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Held order not found.')
    held.reopened_at = datetime.now(UTC)
    session.commit()
    return view(held)


@router.delete('/{hold_id}', status_code=status.HTTP_204_NO_CONTENT)
def cancel_hold(
    hold_id: str,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> None:
    held = session.scalar(
        select(HeldOrder)
        .where(
            HeldOrder.id == hold_id,
            HeldOrder.tenant_id == user.tenant_id,
            HeldOrder.outlet_id == user.outlet_id,
            HeldOrder.status == 'HELD',
        )
        .options(selectinload(HeldOrder.order))
        .with_for_update()
    )
    if held is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Held order not found.')
    held.status = 'CANCELLED'
    held.order.status = 'CANCELLED'
    session.add(AuditLog(
        id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id,
        action='CANCEL', entity_type='HELD_ORDER', entity_id=held.id,
        payload='{}',
    ))
    session.commit()
