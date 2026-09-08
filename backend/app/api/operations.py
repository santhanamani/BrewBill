from datetime import UTC, datetime, time
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from .deps import require_role
from ..database import get_session
from ..inventory_service import adjust_stock
from ..models import (
    AuditLog,
    Customer,
    DailyClosing,
    Expense,
    Order,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    Supplier,
    TenantSetting,
    User,
)
from ..schemas import (
    CustomerCreate,
    CustomerRead,
    DailyClosingCreate,
    DailyClosingRead,
    ExpenseCreate,
    ExpenseRead,
    PurchaseCreate,
    PurchaseRead,
    SupplierCreate,
    SupplierRead,
    TenantSettingRead,
    TenantSettingUpdate,
    TenantPaymentPolicyRead,
    TenantPaymentPolicyUpdate,
)

router = APIRouter(prefix='/api', tags=['operations'])
MONEY = Decimal('0.01')
INDIA = ZoneInfo('Asia/Kolkata')
PAYMENT_POLICY_KEY = 'payment_processing_mode'


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def outlet_id_for(user: User) -> str:
    if not user.outlet_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Select an outlet before continuing.')
    return user.outlet_id


def audit(session: Session, user: User, action: str, entity_type: str, entity_id: str) -> None:
    session.add(AuditLog(
        id=str(uuid4()),
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload='{}',
    ))


@router.get('/suppliers', response_model=list[SupplierRead])
def list_suppliers(
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> list[Supplier]:
    return list(session.scalars(
        select(Supplier)
        .where(Supplier.tenant_id == user.tenant_id, Supplier.status == 'ACTIVE')
        .order_by(Supplier.name)
    ))


@router.post('/suppliers', response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(
    body: SupplierCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> Supplier:
    supplier = Supplier(id=str(uuid4()), tenant_id=user.tenant_id, **body.model_dump(), status='ACTIVE')
    session.add(supplier)
    audit(session, user, 'CREATE', 'SUPPLIER', supplier.id)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A supplier with this name already exists.') from error
    session.refresh(supplier)
    return supplier


@router.get('/purchases', response_model=list[PurchaseRead])
def list_purchases(
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> list[PurchaseRead]:
    purchases = session.scalars(
        select(Purchase)
        .where(Purchase.tenant_id == user.tenant_id, Purchase.outlet_id == outlet_id_for(user))
        .options(selectinload(Purchase.supplier), selectinload(Purchase.items))
        .order_by(Purchase.purchase_date.desc())
        .limit(limit)
    ).all()
    return [
        PurchaseRead(
            id=purchase.id,
            supplier_name=purchase.supplier.name,
            invoice_number=purchase.invoice_number,
            purchase_date=purchase.purchase_date,
            subtotal=purchase.subtotal,
            tax=purchase.tax,
            total=purchase.total,
            payment_status=purchase.payment_status,
            item_count=len(purchase.items),
        )
        for purchase in purchases
    ]


@router.post('/purchases', response_model=PurchaseRead, status_code=status.HTTP_201_CREATED)
def create_purchase(
    body: PurchaseCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> PurchaseRead:
    outlet_id = outlet_id_for(user)
    supplier = session.scalar(select(Supplier).where(
        Supplier.id == body.supplier_id,
        Supplier.tenant_id == user.tenant_id,
        Supplier.status == 'ACTIVE',
    ))
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Supplier not found.')

    product_ids = [line.product_id for line in body.items]
    products = session.scalars(
        select(Product)
        .where(
            Product.tenant_id == user.tenant_id,
            Product.id.in_(product_ids),
            (Product.outlet_id == outlet_id) | (Product.outlet_id.is_(None)),
        )
        .with_for_update()
    ).all()
    product_by_id = {product.id: product for product in products}
    if len(product_by_id) != len(set(product_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='One or more products are unavailable for this outlet.')

    subtotal = Decimal('0.00')
    tax = Decimal('0.00')
    purchase_items: list[PurchaseItem] = []
    for line in body.items:
        product = product_by_id[line.product_id]
        line_subtotal = money(line.quantity * line.unit_cost)
        line_tax = money(line_subtotal * line.tax_percent / Decimal('100'))
        line_total = money(line_subtotal + line_tax)
        subtotal += line_subtotal
        tax += line_tax
        product.purchase_price = line.unit_cost
        adjust_stock(
            session,
            user=user,
            outlet_id=outlet_id,
            product=product,
            quantity_delta=line.quantity,
            transaction_type='PURCHASE',
            reference_type='PURCHASE',
            reference_id=body.invoice_number.strip(),
        )
        purchase_items.append(PurchaseItem(
            id=str(uuid4()),
            product_id=product.id,
            product_name=product.name,
            quantity=line.quantity,
            unit_cost=line.unit_cost,
            tax_percent=line.tax_percent,
            line_total=line_total,
        ))

    purchase = Purchase(
        id=str(uuid4()),
        tenant_id=user.tenant_id,
        outlet_id=outlet_id,
        supplier_id=supplier.id,
        created_by=user.id,
        invoice_number=body.invoice_number.strip(),
        purchase_date=body.purchase_date,
        subtotal=money(subtotal),
        tax=money(tax),
        total=money(subtotal + tax),
        payment_status=body.payment_status,
        notes=body.notes,
        items=purchase_items,
    )
    session.add(purchase)
    audit(session, user, 'CREATE', 'PURCHASE', purchase.id)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This supplier invoice already exists.') from error
    return PurchaseRead(
        id=purchase.id,
        supplier_name=supplier.name,
        invoice_number=purchase.invoice_number,
        purchase_date=purchase.purchase_date,
        subtotal=purchase.subtotal,
        tax=purchase.tax,
        total=purchase.total,
        payment_status=purchase.payment_status,
        item_count=len(purchase.items),
    )


@router.get('/expenses', response_model=list[ExpenseRead])
def list_expenses(
    limit: int = Query(default=250, ge=1, le=500),
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> list[ExpenseRead]:
    rows = session.execute(
        select(Expense, User.display_name)
        .join(User, User.id == Expense.created_by)
        .where(Expense.tenant_id == user.tenant_id, Expense.outlet_id == outlet_id_for(user))
        .order_by(Expense.expense_date.desc())
        .limit(limit)
    ).all()
    return [ExpenseRead(
        id=expense.id,
        expense_date=expense.expense_date,
        category=expense.category,
        description=expense.description,
        amount=expense.amount,
        payment_mode=expense.payment_mode,
        remarks=expense.remarks,
        created_by_name=creator,
        created_at=expense.created_at,
    ) for expense, creator in rows]


@router.post('/expenses', response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(
    body: ExpenseCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> ExpenseRead:
    expense = Expense(
        id=str(uuid4()),
        tenant_id=user.tenant_id,
        outlet_id=outlet_id_for(user),
        created_by=user.id,
        **body.model_dump(),
    )
    session.add(expense)
    audit(session, user, 'CREATE', 'EXPENSE', expense.id)
    session.commit()
    session.refresh(expense)
    return ExpenseRead(
        id=expense.id,
        expense_date=expense.expense_date,
        category=expense.category,
        description=expense.description,
        amount=expense.amount,
        payment_mode=expense.payment_mode,
        remarks=expense.remarks,
        created_by_name=user.display_name,
        created_at=expense.created_at,
    )


@router.get('/customers', response_model=list[CustomerRead])
def list_customers(
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> list[Customer]:
    return list(session.scalars(
        select(Customer).where(Customer.tenant_id == user.tenant_id).order_by(Customer.name).limit(500)
    ))


@router.post('/customers', response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    body: CustomerCreate,
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> Customer:
    customer = Customer(id=str(uuid4()), tenant_id=user.tenant_id, loyalty_points=0, **body.model_dump())
    session.add(customer)
    audit(session, user, 'CREATE', 'CUSTOMER', customer.id)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='A customer with this mobile number already exists.') from error
    session.refresh(customer)
    return customer


@router.get('/closings', response_model=list[DailyClosingRead])
def list_closings(
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> list[DailyClosing]:
    return list(session.scalars(
        select(DailyClosing)
        .where(DailyClosing.tenant_id == user.tenant_id, DailyClosing.outlet_id == outlet_id_for(user))
        .order_by(DailyClosing.business_date.desc())
        .limit(100)
    ))


@router.post('/closings', response_model=DailyClosingRead, status_code=status.HTTP_201_CREATED)
def create_closing(
    body: DailyClosingCreate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> DailyClosing:
    outlet_id = outlet_id_for(user)
    business_date = body.business_date.isoformat()
    existing = session.scalar(select(DailyClosing).where(
        DailyClosing.tenant_id == user.tenant_id,
        DailyClosing.outlet_id == outlet_id,
        DailyClosing.business_date == business_date,
    ))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='This business day has already been closed.')

    start_local = datetime.combine(body.business_date, time.min, tzinfo=INDIA)
    end_local = datetime.combine(body.business_date, time.max, tzinfo=INDIA)
    start_utc, end_utc = start_local.astimezone(UTC), end_local.astimezone(UTC)
    order_filter = (
        Order.tenant_id == user.tenant_id,
        Order.outlet_id == outlet_id,
        Order.created_at >= start_utc,
        Order.created_at <= end_utc,
        Order.status == 'COMPLETED',
    )
    order_count, gross_sales = session.execute(
        select(func.count(Order.id), func.coalesce(func.sum(Order.grand_total), 0)).where(*order_filter)
    ).one()

    payment_rows = session.execute(
        select(Payment.payment_mode, func.coalesce(func.sum(Payment.amount), 0))
        .join(Order, Order.id == Payment.order_id)
        .where(*order_filter)
        .group_by(Payment.payment_mode)
    ).all()
    payment_totals = {mode: money(Decimal(str(total))) for mode, total in payment_rows}
    expense_total = session.scalar(
        select(func.coalesce(func.sum(Expense.amount), 0)).where(
            Expense.tenant_id == user.tenant_id,
            Expense.outlet_id == outlet_id,
            Expense.expense_date >= start_utc,
            Expense.expense_date <= end_utc,
        )
    )
    cash_sales = payment_totals.get('CASH', Decimal('0.00'))
    expenses = money(Decimal(str(expense_total or 0)))
    expected_cash = money(cash_sales - expenses)
    closing = DailyClosing(
        id=str(uuid4()),
        tenant_id=user.tenant_id,
        outlet_id=outlet_id,
        closed_by=user.id,
        business_date=business_date,
        order_count=int(order_count),
        gross_sales=money(Decimal(str(gross_sales))),
        cash_sales=cash_sales,
        upi_sales=payment_totals.get('UPI', Decimal('0.00')),
        card_sales=payment_totals.get('CARD', Decimal('0.00')),
        expenses=expenses,
        expected_cash=expected_cash,
        counted_cash=body.counted_cash,
        variance=money(body.counted_cash - expected_cash),
        status='CLOSED',
    )
    session.add(closing)
    audit(session, user, 'CREATE', 'DAILY_CLOSING', closing.id)
    session.commit()
    session.refresh(closing)
    return closing


@router.get('/settings', response_model=list[TenantSettingRead])
def list_settings(
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> list[TenantSetting]:
    return list(session.scalars(
        select(TenantSetting).where(TenantSetting.tenant_id == user.tenant_id).order_by(TenantSetting.setting_key)
    ))


@router.put('/settings/{setting_key}', response_model=TenantSettingRead)
def update_setting(
    setting_key: str,
    body: TenantSettingUpdate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> TenantSetting:
    if not setting_key.replace('_', '').replace('-', '').isalnum() or len(setting_key) > 120:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail='Invalid setting key.')
    setting = session.get(TenantSetting, (user.tenant_id, setting_key))
    if setting is None:
        setting = TenantSetting(tenant_id=user.tenant_id, setting_key=setting_key, setting_value=body.setting_value)
        session.add(setting)
    else:
        setting.setting_value = body.setting_value
    audit(session, user, 'UPDATE', 'TENANT_SETTING', setting_key)
    session.commit()
    session.refresh(setting)
    return setting

@router.get('/payment-policy', response_model=TenantPaymentPolicyRead)
def get_payment_policy(
    user: User = Depends(require_role('ADMIN', 'CASHIER')),
    session: Session = Depends(get_session),
) -> TenantPaymentPolicyRead:
    setting = session.get(TenantSetting, (user.tenant_id, PAYMENT_POLICY_KEY))
    mode = setting.setting_value if setting else 'MANUAL_ALLOWED'
    if mode not in ('MANUAL_ALLOWED', 'TERMINAL_REQUIRED'):
        mode = 'MANUAL_ALLOWED'
    return TenantPaymentPolicyRead(payment_processing_mode=mode)


@router.put('/payment-policy', response_model=TenantPaymentPolicyRead)
def update_payment_policy(
    body: TenantPaymentPolicyUpdate,
    user: User = Depends(require_role('ADMIN')),
    session: Session = Depends(get_session),
) -> TenantPaymentPolicyRead:
    setting = session.get(TenantSetting, (user.tenant_id, PAYMENT_POLICY_KEY))
    if setting is None:
        setting = TenantSetting(
            tenant_id=user.tenant_id,
            setting_key=PAYMENT_POLICY_KEY,
            setting_value=body.payment_processing_mode,
        )
        session.add(setting)
    else:
        setting.setting_value = body.payment_processing_mode
    audit(session, user, 'UPDATE', 'TENANT_PAYMENT_POLICY', user.tenant_id)
    session.commit()
    return TenantPaymentPolicyRead(payment_processing_mode=body.payment_processing_mode)
