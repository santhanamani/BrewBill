import json
import secrets
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from .deps import require_role
from ..database import get_session, settings
from ..inventory_service import adjust_stock
from ..models import MarketplaceOrder, MarketplaceOrderItem, Outlet, OutletProductMapping, Product, Tenant, TenantSetting, User
from ..schemas import MarketplaceMockOrderCreate, MarketplaceOrderIngest, MarketplaceOrderRead, MarketplaceStatusUpdate, MarketplaceSummaryRead
from ..subscriptions import require_plan_feature, subscription_lifecycle

router = APIRouter(prefix='/api/marketplace', tags=['marketplace'])
INDIA = ZoneInfo('Asia/Kolkata')
ACTIVE = {'RECEIVED','ACCEPTED','PREPARING','READY'}
ALLOWED = {'RECEIVED': {'ACCEPTED','REJECTED','CANCELLED'}, 'ACCEPTED': {'PREPARING','READY','CANCELLED'}, 'PREPARING': {'READY','CANCELLED'}, 'READY': {'COMPLETED','CANCELLED'}}


def scope(user: User):
    return MarketplaceOrder.tenant_id == user.tenant_id, MarketplaceOrder.outlet_id == user.outlet_id


def ensure_feature(user: User, session: Session) -> None:
    require_plan_feature(user, session, 'marketplace_integrations')


def ensure_channel_enabled(user: User, session: Session, provider: str) -> None:
    key = f'{provider.lower()}_enabled'
    setting = session.get(TenantSetting, (user.tenant_id, key))
    if not setting or setting.setting_value.strip().lower() not in {'true', '1', 'yes', 'on'}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Enable {provider.title()} in Settings before receiving orders.',
        )


def connector_authorized(token: str | None) -> None:
    configured = settings.marketplace_connector_token.strip()
    if not configured or not token or not secrets.compare_digest(configured, token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid marketplace connector token.')


@router.post('/provider-orders', response_model=MarketplaceOrderRead, status_code=status.HTTP_201_CREATED)
def ingest_provider_order(
    body: MarketplaceOrderIngest,
    connector_token: str | None = Header(default=None, alias='X-Marketplace-Connector-Token'),
    session: Session = Depends(get_session),
):
    """Receive a provider-neutral order from an approved Swiggy/Zomato adapter."""
    connector_authorized(connector_token)
    merchant_key = f'{body.provider.lower()}_merchant_id'
    merchant_settings = list(session.scalars(select(TenantSetting).where(
        TenantSetting.setting_key == merchant_key,
        TenantSetting.setting_value == body.merchant_id,
    )))
    if not merchant_settings:
        raise HTTPException(status_code=404, detail='No tenant is mapped to this marketplace merchant.')
    if len(merchant_settings) > 1:
        raise HTTPException(status_code=409, detail='Marketplace merchant mapping is ambiguous.')
    tenant_id = merchant_settings[0].tenant_id
    enabled = session.get(TenantSetting, (tenant_id, f'{body.provider.lower()}_enabled'))
    if not enabled or enabled.setting_value.strip().lower() not in {'true', '1', 'yes', 'on'}:
        raise HTTPException(status_code=409, detail=f'{body.provider.title()} is disabled for this tenant.')
    lifecycle = subscription_lifecycle(tenant_id, session)
    try:
        feature_enabled = bool(json.loads(lifecycle.plan.feature_json or '{}').get('marketplace_integrations', False)) if lifecycle.plan else False
    except (TypeError, ValueError, json.JSONDecodeError):
        feature_enabled = False
    if not lifecycle.login_allowed or not feature_enabled:
        raise HTTPException(status_code=403, detail='Marketplace integration is unavailable for this tenant.')
    outlet_query = select(Outlet).where(Outlet.tenant_id == tenant_id)
    if body.outlet_code:
        outlet_query = outlet_query.where(Outlet.code == body.outlet_code)
    outlet = session.scalar(outlet_query.order_by(Outlet.created_at).limit(1))
    if not outlet:
        raise HTTPException(status_code=404, detail='No matching tenant outlet was found.')
    existing = session.scalar(select(MarketplaceOrder).where(
        MarketplaceOrder.tenant_id == tenant_id,
        MarketplaceOrder.provider == body.provider,
        MarketplaceOrder.external_order_id == body.external_order_id,
    ).options(selectinload(MarketplaceOrder.items)))
    if existing:
        return existing
    mappings = list(session.scalars(select(OutletProductMapping).where(
        OutletProductMapping.tenant_id == tenant_id,
        OutletProductMapping.outlet_id == outlet.id,
        OutletProductMapping.is_active.is_(True),
    ).options(selectinload(OutletProductMapping.legacy_product))))
    catalogue = {
        mapping.legacy_product.code.upper(): mapping.legacy_product
        for mapping in mappings
        if mapping.legacy_product
    }
    tenant = session.get(Tenant, tenant_id)
    placed_at = body.placed_at.replace(tzinfo=UTC) if body.placed_at.tzinfo is None else body.placed_at.astimezone(UTC)
    order = MarketplaceOrder(
        id=str(uuid4()), tenant_id=tenant_id, outlet_id=outlet.id, provider=body.provider,
        external_order_id=body.external_order_id, merchant_id=body.merchant_id, status='RECEIVED',
        currency_code=tenant.currency_code if tenant else 'INR',
        tax=body.tax, packaging_charge=body.packaging_charge, discount=body.discount,
        commission=body.commission, customer_name=body.customer_name,
        customer_phone_masked=body.customer_phone_masked, instructions=body.instructions,
        placed_at=placed_at,
    )
    subtotal = Decimal('0.00')
    food_cost = Decimal('0.00')
    for incoming in body.items:
        product = catalogue.get(incoming.external_item_id.upper())
        line_total = (incoming.unit_price * incoming.quantity).quantize(Decimal('0.01'))
        unit_cost = product.purchase_price if product else Decimal('0.00')
        subtotal += line_total
        food_cost += unit_cost * incoming.quantity
        order.items.append(MarketplaceOrderItem(
            id=str(uuid4()), product_id=product.id if product else None, variant_id=None,
            external_item_id=incoming.external_item_id, product_name=incoming.product_name,
            variant_name=incoming.variant_name, quantity=incoming.quantity,
            unit_price=incoming.unit_price, line_total=line_total, unit_cost=unit_cost,
        ))
    order.subtotal = subtotal
    order.grand_total = subtotal + body.tax + body.packaging_charge - body.discount
    order.net_settlement = order.grand_total - body.commission
    order.food_cost = food_cost
    order.estimated_profit = order.net_settlement - food_cost
    session.add(order)
    session.commit()
    return session.scalar(select(MarketplaceOrder).where(
        MarketplaceOrder.id == order.id,
    ).options(selectinload(MarketplaceOrder.items)))


@router.get('/orders', response_model=list[MarketplaceOrderRead])
def list_orders(provider: str | None = Query(None), order_status: str | None = Query(None), user: User = Depends(require_role('ADMIN','CASHIER')), session: Session = Depends(get_session)):
    ensure_feature(user, session)
    query = select(MarketplaceOrder).where(*scope(user)).options(selectinload(MarketplaceOrder.items)).order_by(MarketplaceOrder.placed_at.desc()).limit(250)
    if provider: query = query.where(MarketplaceOrder.provider == provider.upper())
    if order_status: query = query.where(MarketplaceOrder.status == order_status.upper())
    return list(session.scalars(query).unique())


@router.get('/summary', response_model=MarketplaceSummaryRead)
def summary(from_date: date | None = None, to_date: date | None = None, user: User = Depends(require_role('ADMIN','CASHIER')), session: Session = Depends(get_session)):
    ensure_feature(user, session)
    filters = list(scope(user))
    if from_date:
        filters.append(MarketplaceOrder.placed_at >= datetime.combine(from_date,time.min,tzinfo=INDIA).astimezone(UTC))
    if to_date:
        filters.append(MarketplaceOrder.placed_at < datetime.combine(to_date+timedelta(days=1),time.min,tzinfo=INDIA).astimezone(UTC))
    rows = session.execute(select(MarketplaceOrder.provider, MarketplaceOrder.status, func.count(MarketplaceOrder.id), func.coalesce(func.sum(MarketplaceOrder.grand_total),0), func.coalesce(func.sum(MarketplaceOrder.net_settlement),0), func.coalesce(func.sum(MarketplaceOrder.estimated_profit),0)).where(*filters).group_by(MarketplaceOrder.provider, MarketplaceOrder.status)).all()
    result = dict(total_orders=0,active_orders=0,completed_orders=0,cancelled_orders=0,gross_sales=Decimal('0'),net_settlement=Decimal('0'),estimated_profit=Decimal('0'),swiggy_orders=0,zomato_orders=0,mock_enabled=settings.marketplace_mock_enabled)
    for provider_name,state,count,gross,net,profit in rows:
        result['total_orders'] += count
        result['swiggy_orders' if provider_name=='SWIGGY' else 'zomato_orders'] += count
        if state in ACTIVE: result['active_orders'] += count
        if state == 'COMPLETED':
            result['completed_orders'] += count; result['gross_sales'] += gross; result['net_settlement'] += net; result['estimated_profit'] += profit
        if state in ('CANCELLED','REJECTED'): result['cancelled_orders'] += count
    return result


@router.post('/mock-orders', response_model=MarketplaceOrderRead, status_code=status.HTTP_201_CREATED)
def create_mock_order(body: MarketplaceMockOrderCreate, user: User = Depends(require_role('ADMIN')), session: Session = Depends(get_session)):
    ensure_feature(user, session)
    ensure_channel_enabled(user, session, body.provider)
    if not settings.marketplace_mock_enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Marketplace mock mode is disabled.')
    mappings = list(session.scalars(select(OutletProductMapping).where(OutletProductMapping.tenant_id==user.tenant_id, OutletProductMapping.outlet_id==user.outlet_id, OutletProductMapping.is_active.is_(True), OutletProductMapping.is_available.is_(True)).options(selectinload(OutletProductMapping.legacy_product)).limit(2)))
    catalogue = [(mapping.legacy_product, mapping.selling_price) for mapping in mappings if mapping.legacy_product]
    if not catalogue:
        catalogue = [(product, product.selling_price) for product in session.scalars(select(Product).where(Product.tenant_id==user.tenant_id, Product.outlet_id==user.outlet_id, Product.is_active.is_(True), Product.is_available.is_(True)).limit(2))]
    if not catalogue: raise HTTPException(status_code=409, detail='Add an available outlet product before creating a test order.')
    tenant = session.get(Tenant,user.tenant_id)
    merchant = session.get(TenantSetting,(user.tenant_id,f'{body.provider.lower()}_merchant_id'))
    external_id = f'TEST-{body.provider[:3]}-{datetime.now(UTC):%Y%m%d%H%M%S%f}'
    order = MarketplaceOrder(id=str(uuid4()),tenant_id=user.tenant_id,outlet_id=user.outlet_id,provider=body.provider,external_order_id=external_id,merchant_id=merchant.setting_value if merchant else f'TEST-{body.provider}',status='RECEIVED',currency_code=tenant.currency_code if tenant else 'INR',customer_name='Test Customer',customer_phone_masked='******0000',instructions='Test order generated inside BrewBill.',placed_at=datetime.now(UTC))
    subtotal=Decimal('0'); food_cost=Decimal('0')
    for product, price in catalogue:
        cost=product.purchase_price; subtotal += price; food_cost += cost
        order.items.append(MarketplaceOrderItem(id=str(uuid4()),product_id=product.id,variant_id=None,external_item_id=product.code,product_name=product.name,variant_name='Regular',quantity=1,unit_price=price,line_total=price,unit_cost=cost))
    order.subtotal=subtotal; order.tax=(subtotal*Decimal('.05')).quantize(Decimal('.01')); order.packaging_charge=Decimal('10'); order.grand_total=order.subtotal+order.tax+order.packaging_charge; order.commission=(order.grand_total*Decimal('.20')).quantize(Decimal('.01')); order.net_settlement=order.grand_total-order.commission; order.food_cost=food_cost; order.estimated_profit=order.net_settlement-food_cost
    session.add(order); session.commit(); session.refresh(order)
    return session.scalar(select(MarketplaceOrder).where(MarketplaceOrder.id==order.id).options(selectinload(MarketplaceOrder.items)))


@router.put('/orders/{order_id}/status', response_model=MarketplaceOrderRead)
def update_status(order_id: str, body: MarketplaceStatusUpdate, user: User = Depends(require_role('ADMIN','CASHIER')), session: Session = Depends(get_session)):
    ensure_feature(user, session)
    order = session.scalar(select(MarketplaceOrder).where(MarketplaceOrder.id==order_id,*scope(user)).options(selectinload(MarketplaceOrder.items)).with_for_update())
    if not order: raise HTTPException(status_code=404, detail='Marketplace order not found.')
    if body.status not in ALLOWED.get(order.status,set()): raise HTTPException(status_code=409, detail=f'{order.status} cannot change to {body.status}.')
    products = {p.id:p for p in session.scalars(select(Product).where(Product.id.in_([i.product_id for i in order.items if i.product_id])).with_for_update())}
    if body.status == 'ACCEPTED' and not order.stock_committed:
        for item in order.items:
            if not item.product_id or item.product_id not in products: raise HTTPException(status_code=409, detail=f'{item.product_name} is not mapped to an outlet product.')
            try: adjust_stock(session,user=user,outlet_id=order.outlet_id,product=products[item.product_id],quantity_delta=Decimal(-item.quantity),transaction_type='SALE',reference_type='MARKETPLACE_ORDER',reference_id=order.id)
            except ValueError as error: raise HTTPException(status_code=409, detail=str(error)) from error
        order.stock_committed=True; order.accepted_at=datetime.now(UTC)
    if body.status in ('CANCELLED','REJECTED') and order.stock_committed:
        for item in order.items:
            if item.product_id in products: adjust_stock(session,user=user,outlet_id=order.outlet_id,product=products[item.product_id],quantity_delta=Decimal(item.quantity),transaction_type='VOID_REVERSAL',reference_type='MARKETPLACE_ORDER',reference_id=order.id,notes=f'{order.provider} order cancelled')
        order.stock_committed=False
    order.status=body.status; now=datetime.now(UTC)
    if body.status=='READY': order.ready_at=now
    if body.status=='COMPLETED': order.completed_at=now
    if body.status in ('CANCELLED','REJECTED'): order.cancelled_at=now
    session.commit(); session.refresh(order); return order
