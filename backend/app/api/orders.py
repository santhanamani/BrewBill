import json
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload
from .deps import current_user, require_role
from .platform import active_subscription
from ..database import get_session
from ..inventory_service import adjust_stock
from ..models import AuditLog, HeldOrder, KotHeader, KotItem, Order, OrderItem, Outlet, OutletProductMapping, Payment, PosTerminal, Product, ProductVariant, User
from ..schemas import OrderCreate, OrderListItemRead, OrderRead, OrderVoidRequest, SyncOrderCreate

router = APIRouter(prefix='/api/orders', tags=['orders'])
MONEY = Decimal('0.01')


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


@router.get('', response_model=list[OrderListItemRead])
def list_orders(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[OrderListItemRead]:
    """Return the signed-in outlet's PostgreSQL order history."""
    orders = session.scalars(
        select(Order)
        .where(Order.tenant_id == user.tenant_id, Order.outlet_id == user.outlet_id, Order.status.in_(('COMPLETED', 'VOID')))
        .options(selectinload(Order.items), selectinload(Order.payments))
        .order_by(Order.created_at.desc())
        .limit(250)
    ).all()
    cashier_ids = {order.cashier_id for order in orders if order.cashier_id}
    cashiers = {
        cashier.id: cashier.display_name
        for cashier in session.scalars(select(User).where(User.id.in_(cashier_ids))).all()
    } if cashier_ids else {}
    return [
        OrderListItemRead(
            id=order.id,
            invoice_number=order.invoice_number,
            subtotal=order.subtotal,
            discount=order.discount,
            tax=order.tax,
            round_off=order.round_off,
            grand_total=order.grand_total,
            status=order.status,
            order_type=order.order_type,
            service_reference=order.service_reference,
            created_at=order.created_at,
            cashier_name=cashiers.get(order.cashier_id, 'Unknown'),
            item_count=sum(item.quantity for item in order.items),
            payment_modes=sorted({payment.payment_mode for payment in order.payments}),
            items=[
                {
                    'product_name': item.product_name,
                    'variant_name': item.variant_name,
                    'quantity': item.quantity,
                    'line_total': item.line_total,
                }
                for item in order.items
            ],
        )
        for order in orders
    ]


@router.post('', response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    body: OrderCreate,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Order:
    existing = session.scalar(select(Order).where(Order.id == body.order_id, Order.tenant_id == user.tenant_id))
    if existing is not None:
        return existing
    active_subscription(user, session)
    held_order = None
    if body.held_order_id:
        held_order = session.scalar(select(HeldOrder).where(
            HeldOrder.id == body.held_order_id,
            HeldOrder.tenant_id == user.tenant_id,
            HeldOrder.outlet_id == user.outlet_id,
            HeldOrder.status == 'HELD',
        ).with_for_update())
        if held_order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Held order is no longer available.')
    terminal = session.scalar(select(PosTerminal).where(
        PosTerminal.tenant_id == user.tenant_id,
        PosTerminal.terminal_code == body.terminal_code,
        PosTerminal.status == 'ACTIVE',
    ))
    if terminal is None or terminal.outlet_id != user.outlet_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='This POS terminal is not active for the signed-in outlet.')

    product_ids = [line.product_id for line in body.items]
    products = session.scalars(select(Product).where(
        Product.tenant_id == user.tenant_id,
        Product.id.in_(product_ids),
        or_(Product.outlet_id.is_(None), Product.outlet_id == user.outlet_id),
    ).with_for_update()).all()
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
    order_lines: list[OrderItem] = []
    kot_required_by_product: dict[str, bool] = {}
    for requested in body.items:
        product = product_by_id[requested.product_id]
        mapping = mapping_by_product.get(product.id)
        variant = variant_by_id.get(requested.variant_id) if requested.variant_id else None
        if variant is not None and (variant.product_id != product.id or not variant.is_active):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Invalid variant for {product.name}.')
        is_active = (mapping.is_active and mapping.global_product.status == 'ACTIVE') if mapping else product.is_active
        is_available = mapping.is_available if mapping else product.is_available
        if not is_active or not is_available:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f'{product.name} is unavailable.')
        base_price = mapping.selling_price if mapping else product.selling_price
        tax_percent = (mapping.tax_override if mapping.tax_override is not None else mapping.global_product.default_gst) if mapping else product.gst_percent
        product_name = (mapping.outlet_specific_name or mapping.global_product.name) if mapping else product.name
        kot_required_by_product[product.id] = mapping.kot_required if mapping else product.kot_required
        rate = money(base_price + (variant.price_adjustment if variant else Decimal('0.00')))
        if rate < 0:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'Invalid price for {product.name}.')
        line_total = money(rate * requested.quantity)
        line_tax = money(line_total * tax_percent / Decimal('100'))
        subtotal += line_total
        tax += line_tax
        try:
            adjust_stock(
                session,
                user=user,
                outlet_id=terminal.outlet_id,
                product=product,
                quantity_delta=Decimal(-requested.quantity),
                transaction_type='SALE',
                reference_type='ORDER',
                reference_id=body.order_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
        order_lines.append(OrderItem(id=str(uuid4()), product_id=product.id, variant_id=variant.id if variant else None, product_name=product_name, variant_name=variant.name if variant else 'Regular', quantity=requested.quantity, rate=rate, tax=line_tax, line_total=line_total))

    subtotal, tax = money(subtotal), money(tax)
    discount = money(subtotal * body.discount_percent / Decimal('100'))
    before_rounding = money(subtotal - discount + tax)
    rounded_total = before_rounding.quantize(Decimal('1'), rounding=ROUND_HALF_UP) if body.round_to_rupee else before_rounding
    round_off = money(rounded_total - before_rounding)
    grand_total = money(before_rounding + round_off)
    paid_total = money(sum((payment.amount for payment in body.payments), Decimal('0.00')))
    if paid_total != grand_total:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Payment total must exactly equal the grand total.')

    sequence = session.query(Order).filter(Order.tenant_id == user.tenant_id).count() + 1
    outlet = session.get(Outlet, terminal.outlet_id)
    if outlet is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='The terminal outlet no longer exists.')
    invoice_number = f'BH-{outlet.code}-{terminal.terminal_code}-{datetime.now(UTC).year}-{sequence:06d}'
    order = Order(
        id=body.order_id, tenant_id=user.tenant_id, outlet_id=terminal.outlet_id,
        terminal_id=terminal.id, cashier_id=user.id, invoice_number=invoice_number,
        order_type=body.order_type, service_reference=body.service_reference,
        subtotal=subtotal, discount=discount, tax=tax, round_off=round_off,
        grand_total=grand_total, status='COMPLETED',
    )
    order.items = order_lines
    order.payments = [
        Payment(
            id=str(uuid4()), payment_mode=payment.mode, amount=payment.amount,
            reference=payment.reference, capture_source=payment.capture_source,
            provider=payment.provider,
        )
        for payment in body.payments
    ]
    session.add(order)
    # KOT rows reference the order and order-item rows. Flush those parent
    # records first so PostgreSQL foreign-key validation always succeeds.
    session.flush()
    kot_lines = [
        KotItem(
            id=str(uuid4()),
            order_item_id=line.id,
            product_name=line.product_name,
            variant_name=line.variant_name,
            quantity=line.quantity,
        )
        for line in order_lines
        if kot_required_by_product[line.product_id]
    ]
    if kot_lines and body.order_type in ('KOT', 'TAKEAWAY'):
        kot_sequence = session.query(KotHeader).filter(KotHeader.tenant_id == user.tenant_id).count() + 1
        kot = KotHeader(
            id=str(uuid4()),
            tenant_id=user.tenant_id,
            outlet_id=terminal.outlet_id,
            order_id=order.id,
            kot_number=f'KOT-{kot_sequence:06d}',
            station='Takeaway Counter' if body.order_type == 'TAKEAWAY' else 'Hot Kitchen',
            status='NEW',
        )
        kot.items = kot_lines
        session.add(kot)
    if held_order is not None:
        held_order.status = 'COMPLETED'
        held_order.order.status = 'CONVERTED'
    session.commit()
    session.refresh(order)
    return order


@router.post('/{order_id}/void', response_model=OrderRead)
def void_order(
    order_id: str,
    body: OrderVoidRequest,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> Order:
    order = session.scalar(
        select(Order)
        .where(
            Order.id == order_id,
            Order.tenant_id == user.tenant_id,
            Order.outlet_id == user.outlet_id,
        )
        .options(selectinload(Order.items))
        .with_for_update()
    )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Invoice not found.')
    if order.status != 'COMPLETED':
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Only completed invoices can be voided.')
    product_ids = [item.product_id for item in order.items]
    products = session.scalars(
        select(Product)
        .where(Product.tenant_id == user.tenant_id, Product.id.in_(product_ids))
        .with_for_update()
    ).all()
    products_by_id = {product.id: product for product in products}
    if len(products_by_id) != len(set(product_ids)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='Invoice inventory can no longer be restored.')
    for item in order.items:
        adjust_stock(
            session,
            user=user,
            outlet_id=order.outlet_id,
            product=products_by_id[item.product_id],
            quantity_delta=Decimal(item.quantity),
            transaction_type='VOID_REVERSAL',
            reference_type='ORDER',
            reference_id=order.id,
            notes=body.reason.strip(),
        )
    order.status = 'VOID'
    order.cancellation_reason = body.reason.strip()
    order.voided_at = datetime.now(UTC)
    order.voided_by = user.id
    session.add(AuditLog(
        id=str(uuid4()), tenant_id=user.tenant_id, actor_user_id=user.id,
        action='VOID', entity_type='ORDER', entity_id=order.id,
        payload=json.dumps({'reason': order.cancellation_reason}),
    ))
    session.commit()
    session.refresh(order)
    return order


@router.post('/sync', response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def sync_order(
    body: SyncOrderCreate,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Order:
    """Accept a completed offline order using tenant-scoped stable product codes.

    The order UUID remains the idempotency key, so a timed-out client can retry safely.
    """
    codes = [line.product_code for line in body.items]
    products = session.scalars(
        select(Product)
        .where(
            Product.tenant_id == user.tenant_id,
            Product.code.in_(codes),
            or_(Product.outlet_id.is_(None), Product.outlet_id == user.outlet_id),
        )
        .options(selectinload(Product.variants))
    ).all()
    ids_by_code = {product.code: product.id for product in products}
    if len(ids_by_code) != len(set(codes)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='An offline product no longer matches the cloud catalogue.')
    products_by_code = {product.code: product for product in products}
    synced_items: list[dict] = []
    for line in body.items:
        variant_id = None
        if line.variant_name and line.variant_name != 'Regular':
            variant_id = next(
                (
                    variant.id
                    for variant in products_by_code[line.product_code].variants
                    if variant.name == line.variant_name and variant.is_active
                ),
                None,
            )
            if variant_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'The {line.variant_name} variant no longer matches the cloud catalogue.',
                )
        synced_items.append({
            'product_id': ids_by_code[line.product_code],
            'variant_id': variant_id,
            'quantity': line.quantity,
        })
    return create_order(
        OrderCreate(
            order_id=body.order_id,
            terminal_code=body.terminal_code,
            items=synced_items,
            payments=body.payments,
        ),
        user,
        session,
    )
