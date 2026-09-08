from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, cast, func, Integer, select
from sqlalchemy.orm import Session
from .deps import current_user
from ..database import get_session
from ..models import Category, Inventory, Order, OrderItem, Payment, Product, User
from ..schemas import DashboardRead, DashboardSeriesPoint, DashboardTopProduct

router = APIRouter(prefix='/api/dashboard', tags=['dashboard'])


@router.get('', response_model=DashboardRead)
def dashboard(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> DashboardRead:
    """Return only metrics scoped to the signed-in tenant and outlet."""
    today = datetime.now(UTC).date()
    range_start = from_date or today
    range_end = to_date or range_start
    if range_end < range_start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='To date must be on or after from date.')
    if range_end > today:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Dashboard dates cannot be in the future.')
    if (range_end - range_start).days > 366:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Dashboard date range cannot exceed 367 days.')
    starts_at = datetime.combine(range_start, time.min, tzinfo=UTC)
    ends_before = datetime.combine(range_end + timedelta(days=1), time.min, tzinfo=UTC)
    completed = (
        Order.tenant_id == user.tenant_id,
        Order.outlet_id == user.outlet_id,
        Order.status == 'COMPLETED',
        Order.created_at >= starts_at,
        Order.created_at < ends_before,
    )
    totals = session.execute(
        select(
            func.coalesce(func.sum(Order.grand_total), Decimal('0.00')),
            func.coalesce(func.count(Order.id), 0),
        ).where(*completed)
    ).one()
    payment_rows = session.execute(
        select(Payment.payment_mode, func.coalesce(func.sum(Payment.amount), Decimal('0.00')))
        .join(Order, Order.id == Payment.order_id)
        .where(*completed)
        .group_by(Payment.payment_mode)
    ).all()
    payment_totals = {mode: value for mode, value in payment_rows}
    low_stock = session.scalar(
        select(func.count(Inventory.id))
        .join(Product, Product.id == Inventory.product_id)
        .where(
            Inventory.tenant_id == user.tenant_id,
            Inventory.outlet_id == user.outlet_id,
            Product.is_active.is_(True),
            Inventory.available_quantity <= Inventory.low_stock_limit,
        )
    ) or 0
    product_rows = session.execute(
        select(
            OrderItem.product_name,
            func.coalesce(func.sum(OrderItem.quantity), 0),
            func.coalesce(func.sum(OrderItem.line_total), Decimal('0.00')),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(*completed)
        .group_by(OrderItem.product_name)
        .order_by(func.sum(OrderItem.line_total).desc())
        .limit(5)
    ).all()
    date_key = func.date(Order.created_at).label('period')
    date_rows = session.execute(
        select(date_key, func.coalesce(func.sum(Order.grand_total), Decimal('0.00')))
        .where(*completed)
        .group_by(date_key)
        .order_by(date_key)
    ).all()
    date_points = [
        DashboardSeriesPoint(
            label=(period.strftime('%d %b') if hasattr(period, 'strftime') else date.fromisoformat(str(period)).strftime('%d %b')),
            value=value,
        )
        for period, value in date_rows
    ]
    hour_key = func.extract('hour', Order.created_at).label('period')
    hour_rows = session.execute(
        select(hour_key, func.coalesce(func.sum(Order.grand_total), Decimal('0.00')))
        .where(*completed)
        .group_by(hour_key)
        .order_by(hour_key)
    ).all()
    hour_points = [
        DashboardSeriesPoint(label=f'{int(period):02d}:00', value=value)
        for period, value in hour_rows
    ]
    # Keep the existing response field stable for older desktop builds.
    trend_points = hour_points if range_start == range_end else date_points
    category_rows = session.execute(
        select(
            Category.name,
            func.coalesce(func.sum(OrderItem.line_total), Decimal('0.00')),
        )
        .join(Product, Product.category_id == Category.id)
        .join(OrderItem, OrderItem.product_id == Product.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(*completed)
        .group_by(Category.name)
        .order_by(func.sum(OrderItem.line_total).desc())
    ).all()
    return DashboardRead(
        sales_today=totals[0],
        orders_today=totals[1],
        cash_sales=payment_totals.get('CASH', Decimal('0.00')),
        upi_sales=payment_totals.get('UPI', Decimal('0.00')),
        card_sales=payment_totals.get('CARD', Decimal('0.00')),
        low_stock_products=low_stock,
        top_products=[DashboardTopProduct(product_name=name, quantity_sold=quantity, revenue=revenue) for name, quantity, revenue in product_rows],
        hourly_sales=trend_points,
        date_sales=date_points,
        hour_sales=hour_points,
        category_sales=[DashboardSeriesPoint(label=name, value=value) for name, value in category_rows],
    )
