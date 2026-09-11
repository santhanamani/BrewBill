from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .deps import current_user
from ..database import get_session
from ..models import Category, Inventory, Order, OrderItem, Payment, Product, User
from ..owner_access import resolve_read_scope
from ..schemas import DashboardRead, DashboardSeriesPoint, DashboardTopProduct

router = APIRouter(prefix='/api/dashboard', tags=['dashboard'])
BUSINESS_TIMEZONE = ZoneInfo('Asia/Kolkata')


def business_today(now: datetime | None = None) -> date:
    """Return the cafe's current calendar date, independent of server timezone."""
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(BUSINESS_TIMEZONE).date()


def business_date_bounds(range_start: date, range_end: date) -> tuple[datetime, datetime]:
    """Convert inclusive cafe-local dates to a half-open UTC timestamp range."""
    starts_at = datetime.combine(range_start, time.min, tzinfo=BUSINESS_TIMEZONE).astimezone(UTC)
    ends_before = datetime.combine(
        range_end + timedelta(days=1), time.min, tzinfo=BUSINESS_TIMEZONE
    ).astimezone(UTC)
    return starts_at, ends_before


def business_local_datetime(value: datetime) -> datetime:
    """Normalise DB datetimes before rendering local date/hour dashboard labels."""
    instant = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return instant.astimezone(BUSINESS_TIMEZONE)


@router.get('', response_model=DashboardRead)
def dashboard(
    from_date: date | None = Query(default=None),
    to_date: date | None = Query(default=None),
    tenant_id: str | None = Query(default=None, max_length=36),
    outlet_id: str | None = Query(default=None, max_length=36),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> DashboardRead:
    """Return only metrics scoped to the signed-in tenant and outlet."""
    today = business_today()
    range_start = from_date or today
    range_end = to_date or range_start
    if range_end < range_start:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='To date must be on or after from date.')
    if range_end > today:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Dashboard dates cannot be in the future.')
    if (range_end - range_start).days > 366:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Dashboard date range cannot exceed 367 days.')
    starts_at, ends_before = business_date_bounds(range_start, range_end)
    scoped_tenant_id, scoped_outlet_id = resolve_read_scope(session, user, tenant_id, outlet_id)
    completed = [
        Order.tenant_id == scoped_tenant_id,
        Order.status == 'COMPLETED',
        Order.created_at >= starts_at,
        Order.created_at < ends_before,
    ]
    if scoped_outlet_id:
        completed.append(Order.outlet_id == scoped_outlet_id)
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
            Inventory.tenant_id == scoped_tenant_id,
            Product.is_active.is_(True),
            Inventory.available_quantity <= Inventory.low_stock_limit,
            *([Inventory.outlet_id == scoped_outlet_id] if scoped_outlet_id else []),
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
    order_rows = session.execute(
        select(Order.created_at, Order.grand_total)
        .where(*completed)
        .order_by(Order.created_at)
    ).all()
    date_totals: dict[date, Decimal] = {}
    hour_totals: dict[int, Decimal] = {}
    for created_at, value in order_rows:
        local_created_at = business_local_datetime(created_at)
        date_totals[local_created_at.date()] = (
            date_totals.get(local_created_at.date(), Decimal('0.00')) + value
        )
        hour_totals[local_created_at.hour] = (
            hour_totals.get(local_created_at.hour, Decimal('0.00')) + value
        )
    date_points = [
        DashboardSeriesPoint(label=period.strftime('%d %b'), value=value)
        for period, value in sorted(date_totals.items())
    ]
    hour_points = [
        DashboardSeriesPoint(label=f'{period:02d}:00', value=value)
        for period, value in sorted(hour_totals.items())
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
