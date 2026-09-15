from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    tenant_name: str | None = Field(default=None, min_length=2, max_length=160)
    tenant_code: str | None = Field(default=None, min_length=2, max_length=32)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    outlet_id: str | None
    username: str
    display_name: str
    role_code: str


class LoginResponse(TokenPair):
    user: UserRead


class MfaChallengeResponse(BaseModel):
    status: str = 'MFA_REQUIRED'
    challenge_token: str
    setup_required: bool
    setup_secret: str | None = None
    otpauth_uri: str | None = None


class MfaVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(min_length=6, max_length=6, pattern=r'^\d{6}$')


class DeviceActivationRequest(BaseModel):
    installation_id: str = Field(min_length=16, max_length=160)
    terminal_code: str = Field(min_length=2, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')
    terminal_name: str = Field(min_length=2, max_length=120)
    outlet_id: str | None = Field(default=None, min_length=36, max_length=36)


class LicenseEnvelope(BaseModel):
    payload: dict[str, Any]
    signature: str
    public_key: str


class CurrencyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str
    name: str
    symbol: str
    locale: str
    decimal_places: int


class TenantCurrencyUpdate(BaseModel):
    currency_code: str = Field(min_length=3, max_length=3, pattern=r'^[A-Za-z]{3}$')


class PlatformContextRead(BaseModel):
    tenant_id: str
    tenant_code: str | None
    tenant_name: str
    outlet_id: str | None
    outlet_code: str | None
    outlet_name: str | None
    role_code: str
    branding: dict[str, str | None]
    subscription_status: str
    subscription_end: datetime
    subscription_state: str
    grace_ends_at: datetime | None
    subscription_message: str
    plan_code: str
    max_terminals: int
    features: dict[str, Any]
    currency: CurrencyRead


class TenantResolveRead(BaseModel):
    code: str
    name: str
    status: str
    outlet_name: str | None
    outlet_address: str | None
    logo_url: str | None
    cover_image_url: str | None
    primary_color: str
    tagline: str | None
    plan_code: str | None
    subscription_state: str
    subscription_end: datetime | None
    grace_ends_at: datetime | None
    days_remaining: int | None
    grace_days_remaining: int | None
    login_allowed: bool
    subscription_message: str
    currency: CurrencyRead


class GlobalProductCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    category_name: str = Field(min_length=2, max_length=160)
    base_unit: str = Field(default='pcs', min_length=1, max_length=24)
    default_gst: Decimal = Field(default=Decimal('5.00'), ge=0, le=100, max_digits=5, decimal_places=2)
    image_path: str | None = Field(default=None, max_length=512)
    status: str = Field(default='ACTIVE', pattern=r'^(ACTIVE|INACTIVE)$')


class GlobalProductRead(GlobalProductCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str


class GlobalProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    description: str | None = Field(default=None, max_length=4000)
    category_name: str | None = Field(default=None, min_length=2, max_length=160)
    base_unit: str | None = Field(default=None, min_length=1, max_length=24)
    default_gst: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    image_path: str | None = Field(default=None, max_length=512)
    status: str | None = Field(default=None, pattern=r'^(ACTIVE|INACTIVE)$')


class OutletProductMappingCreate(BaseModel):
    selling_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    opening_stock: Decimal = Field(default=Decimal('0.000'), ge=0, max_digits=18, decimal_places=3)
    low_stock_limit: Decimal = Field(default=Decimal('0.000'), ge=0, max_digits=18, decimal_places=3)
    favourite: bool = False
    kot_required: bool = True
    is_available: bool = True
    is_active: bool = True
    display_order: int = Field(default=0, ge=0, le=100000)
    outlet_specific_name: str | None = Field(default=None, max_length=180)
    tax_override: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class ProductFavouriteUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    is_favourite: bool


class OutletProductMappingUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    stock_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    expected_stock_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    selling_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    low_stock_limit: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    favourite: bool | None = None
    kot_required: bool | None = None
    is_available: bool | None = None
    is_active: bool | None = None
    display_order: int | None = Field(default=None, ge=0, le=100000)
    outlet_specific_name: str | None = Field(default=None, max_length=180)
    tax_override: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)


class ProductVariantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    price_adjustment: Decimal
    display_order: int
    is_active: bool


class ProductVariantCreate(BaseModel):
    model_config = {'extra': 'forbid'}
    name: str = Field(min_length=1, max_length=120)
    price_adjustment: Decimal = Field(default=Decimal('0.00'), ge=Decimal('-1000000'), max_digits=18, decimal_places=2)
    display_order: int = Field(default=0, ge=0, le=10000)


class ProductVariantConfigurationItem(BaseModel):
    model_config = {'extra': 'forbid'}
    id: str | None = Field(default=None, max_length=36)
    name: str = Field(min_length=1, max_length=120)
    price_adjustment: Decimal = Field(ge=Decimal('-1000000'), max_digits=18, decimal_places=2)
    display_order: int = Field(default=0, ge=0, le=10000)


class ProductVariantConfigurationUpdate(BaseModel):
    model_config = {'extra': 'forbid'}
    variants: list[ProductVariantConfigurationItem] = Field(default_factory=list, max_length=20)


class OutletProductMappingRead(BaseModel):
    tax_override: Decimal | None = None
    id: str
    global_product_id: str | None
    legacy_product_id: str
    code: str
    name: str
    category_name: str
    image_path: str | None
    base_unit: str
    default_gst: Decimal
    selling_price: Decimal
    stock_quantity: Decimal
    low_stock_limit: Decimal
    favourite: bool
    kot_required: bool
    is_available: bool
    is_active: bool
    display_order: int
    source: str = 'GLOBAL'
    variants: list[ProductVariantRead] = Field(default_factory=list)


class TenantBrandingUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    logo_url: str | None = Field(default=None, max_length=512)
    cover_image_url: str | None = Field(default=None, max_length=512)
    primary_color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    secondary_color: str | None = Field(default=None, pattern=r'^#[0-9A-Fa-f]{6}$')
    tagline: str | None = Field(default=None, max_length=240)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)


class TenantAdminRead(BaseModel):
    id: str
    code: str | None
    name: str
    status: str
    outlet_count: int
    admin_count: int
    logo_url: str | None
    cover_image_url: str | None = None
    primary_color: str
    secondary_color: str = '#C8874A'
    tagline: str | None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    plan_code: str | None = None
    plan_name: str | None = None
    subscription_state: str = 'EXPIRED'
    subscription_end: datetime | None = None
    grace_ends_at: datetime | None = None
    login_allowed: bool = False
    currency_code: str = 'INR'


class TenantSubscriptionRead(BaseModel):
    tenant_id: str
    subscription_id: str | None
    plan_code: str | None
    plan_name: str | None
    status: str
    starts_at: datetime | None
    ends_at: datetime | None
    grace_ends_at: datetime | None
    lifecycle_state: str
    days_remaining: int | None
    grace_days_remaining: int | None
    login_allowed: bool
    message: str


class TenantSubscriptionUpdate(BaseModel):
    ends_at: datetime
    grace_ends_at: datetime
    plan_code: str | None = Field(default=None, pattern=r'^(PROFESSIONAL|ULTRA_PROFESSIONAL)$')


class TenantCreate(BaseModel):
    code: str = Field(min_length=2, max_length=32, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=2, max_length=160)
    outlet_name: str = Field(min_length=2, max_length=160)
    outlet_address: str | None = Field(default=None, max_length=2000)
    admin_username: str = Field(min_length=3, max_length=80)
    admin_password: str = Field(min_length=8, max_length=128)
    admin_display_name: str = Field(min_length=2, max_length=120)
    plan_code: str = Field(default='PROFESSIONAL', min_length=2, max_length=48)
    currency_code: str = Field(default='INR', min_length=3, max_length=3, pattern=r'^[A-Za-z]{3}$')


class TenantUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    status: str | None = Field(default=None, pattern=r'^(ACTIVE|INACTIVE)$')
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    website: str | None = Field(default=None, max_length=255)


class AdminOutletCreate(BaseModel):
    tenant_id: str
    name: str = Field(min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=2000)


class AdminOutletUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    address: str | None = Field(default=None, max_length=2000)


class AdminOutletRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    tenant_id: str
    code: str
    name: str
    address: str | None


class AdminUserCreate(BaseModel):
    tenant_id: str
    outlet_id: str | None = None
    role_code: str = Field(pattern=r'^(TENANT_ADMIN|ADMIN|CASHIER|OWNER)$')
    owner_tenant_ids: list[str] = Field(default_factory=list, max_length=200)
    username: str = Field(min_length=3, max_length=80)
    display_name: str = Field(min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class AdminUserUpdate(BaseModel):
    outlet_id: str | None = None
    role_code: str | None = Field(default=None, pattern=r'^(TENANT_ADMIN|ADMIN|CASHIER|OWNER)$')
    owner_tenant_ids: list[str] | None = Field(default=None, max_length=200)
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None


class AdminUserRead(BaseModel):
    id: str
    tenant_id: str
    tenant_name: str
    outlet_id: str | None
    outlet_name: str | None
    username: str
    display_name: str
    email: str | None
    phone: str | None
    role_code: str
    owner_tenant_ids: list[str] = Field(default_factory=list)
    owner_tenant_names: list[str] = Field(default_factory=list)
    is_active: bool
    last_active: datetime


class AdminRoleRead(BaseModel):
    id: str
    code: str
    name: str


class OwnerTenantRead(BaseModel):
    tenant_id: str
    tenant_code: str
    tenant_name: str
    currency: CurrencyRead
    outlets: list[AdminOutletRead]


class ProductCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=2, max_length=180)
    selling_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    purchase_price: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=18, decimal_places=2)
    gst_percent: Decimal = Field(default=Decimal('5.00'), ge=0, le=100, max_digits=5, decimal_places=2)
    outlet_id: str | None = Field(default=None, max_length=36)
    category_id: str | None = Field(default=None, max_length=36)
    description: str | None = Field(default=None, max_length=4000)
    image_path: str | None = Field(default=None, max_length=512)
    unit: str = Field(default='pcs', min_length=1, max_length=24)
    stock_quantity: Decimal = Field(default=Decimal('0.000'), ge=0, max_digits=18, decimal_places=3)
    low_stock_limit: Decimal = Field(default=Decimal('0.000'), ge=0, max_digits=18, decimal_places=3)
    is_favourite: bool = False
    kot_required: bool = True
    is_available: bool = True
    is_active: bool = True
    shared_across_outlets: bool = True


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    selling_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    purchase_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    gst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    outlet_id: str | None = Field(default=None, max_length=36)
    category_id: str | None = Field(default=None, max_length=36)
    description: str | None = Field(default=None, max_length=4000)
    image_path: str | None = Field(default=None, max_length=512)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    stock_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    low_stock_limit: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    is_favourite: bool | None = None
    kot_required: bool | None = None
    is_available: bool | None = None
    is_active: bool | None = None
    shared_across_outlets: bool | None = None


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    selling_price: Decimal
    purchase_price: Decimal
    gst_percent: Decimal
    outlet_id: str | None
    category_id: str | None
    category_name: str | None
    description: str | None
    image_path: str | None
    unit: str
    stock_quantity: Decimal
    low_stock_limit: Decimal
    is_favourite: bool
    kot_required: bool
    is_available: bool
    is_active: bool
    shared_across_outlets: bool
    variants: list[ProductVariantRead] = Field(default_factory=list)


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    code: str
    name: str
    image_path: str | None
    display_order: int


class OrderLineCreate(BaseModel):
    product_id: str = Field(min_length=36, max_length=36)
    variant_id: str | None = Field(default=None, min_length=36, max_length=36)
    quantity: int = Field(gt=0, le=999)


class PaymentCreate(BaseModel):
    mode: str = Field(pattern=r'^(CASH|UPI|CARD)$')
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reference: str | None = Field(default=None, max_length=128)
    capture_source: str = Field(default='MANUAL', pattern=r'^(MANUAL|PAYMENT_TERMINAL)$')
    provider: str | None = Field(default=None, max_length=80)


class OrderCreate(BaseModel):
    order_id: str = Field(min_length=36, max_length=36)
    terminal_code: str = Field(min_length=2, max_length=64)
    outlet_id: str | None = Field(default=None, min_length=36, max_length=36)
    items: list[OrderLineCreate] = Field(min_length=1, max_length=100)
    payments: list[PaymentCreate] = Field(default_factory=list, max_length=3)
    credit_customer_id: str | None = Field(default=None, min_length=36, max_length=36)
    credit_due_days: int = Field(default=10, ge=1, le=365)
    held_order_id: str | None = Field(default=None, min_length=36, max_length=36)
    discount_percent: Decimal = Field(default=Decimal('0.00'), ge=0, le=50, max_digits=5, decimal_places=2)
    round_to_rupee: bool = True
    order_type: str = Field(default='KOT', pattern=r'^(DIRECT|KOT|TAKEAWAY)$')
    service_reference: str | None = Field(default=None, max_length=80)

    @model_validator(mode='after')
    def validate_payment_choice(self) -> 'OrderCreate':
        if not self.credit_customer_id and not self.payments:
            raise ValueError('Provide a payment or select a credit customer.')
        return self


class OrderVoidRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)


class SyncOrderLine(BaseModel):
    product_code: str = Field(min_length=2, max_length=80)
    variant_name: str | None = Field(default=None, max_length=120)
    quantity: int = Field(gt=0, le=999)


class SyncOrderCreate(BaseModel):
    order_id: str = Field(min_length=36, max_length=36)
    terminal_code: str = Field(min_length=2, max_length=64)
    items: list[SyncOrderLine] = Field(min_length=1, max_length=100)
    payments: list[PaymentCreate] = Field(min_length=1, max_length=3)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    invoice_number: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    round_off: Decimal
    grand_total: Decimal
    status: str
    payment_status: str
    customer_id: str | None
    order_type: str
    service_reference: str | None


class OrderReceiptItemRead(BaseModel):
    product_id: str
    product_name: str
    variant_name: str | None
    category_name: str | None = None
    image_path: str | None = None
    is_available: bool | None = None
    quantity: int
    rate: Decimal
    tax: Decimal
    line_total: Decimal


class OrderReportPaymentRead(BaseModel):
    payment_mode: str
    amount: Decimal


class OrderListItemRead(OrderRead):
    created_at: datetime
    cashier_name: str
    outlet_name: str
    outlet_code: str
    item_count: int
    payment_modes: list[str]
    items: list[OrderReceiptItemRead]
    payments: list[OrderReportPaymentRead]


class KotItemRead(BaseModel):
    product_name: str
    variant_name: str | None
    quantity: int


class KotRead(BaseModel):
    id: str
    kot_number: str
    invoice_number: str
    cashier_name: str
    station: str
    status: str
    created_at: datetime
    items: list[KotItemRead]


class KotStatusUpdate(BaseModel):
    status: str = Field(pattern=r'^(NEW|PREPARING|READY|SERVED|DELAYED)$')


class HoldCreate(BaseModel):
    terminal_code: str = Field(min_length=2, max_length=64)
    outlet_id: str | None = Field(default=None, min_length=36, max_length=36)
    items: list[OrderLineCreate] = Field(min_length=1, max_length=100)


class HeldItemRead(BaseModel):
    product_id: str
    variant_id: str | None
    product_name: str
    variant_name: str | None
    quantity: int
    rate: Decimal
    tax: Decimal
    line_total: Decimal


class HeldOrderRead(BaseModel):
    id: str
    hold_number: str
    invoice_number: str
    held_at: datetime
    cashier_name: str
    subtotal: Decimal
    tax: Decimal
    grand_total: Decimal
    items: list[HeldItemRead]


class IngredientCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=2, max_length=180)
    category: str = Field(min_length=2, max_length=120)
    unit: str = Field(min_length=1, max_length=24)
    image_path: str | None = Field(default=None, max_length=512)
    opening_quantity: Decimal = Field(default=Decimal('0.000'), ge=0, max_digits=18, decimal_places=3)
    low_stock_limit: Decimal = Field(default=Decimal('0.000'), ge=0, max_digits=18, decimal_places=3)


class IngredientUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=180)
    category: str | None = Field(default=None, min_length=2, max_length=120)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    image_path: str | None = Field(default=None, max_length=512)
    low_stock_limit: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=3)
    is_active: bool | None = None


class IngredientAdjustment(BaseModel):
    transaction_type: str = Field(pattern=r'^(STOCK_IN|STOCK_OUT|DAMAGE|WASTAGE|MANUAL_CORRECTION)$')
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    direction: str | None = Field(default=None, pattern=r'^(ADD|REMOVE)$')
    reference: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class IngredientRead(BaseModel):
    id: str
    code: str
    name: str
    category: str
    unit: str
    image_path: str | None
    opening_quantity: Decimal
    stock_added: Decimal
    stock_used: Decimal
    available_quantity: Decimal
    low_stock_limit: Decimal
    is_active: bool
    status: str


class IngredientMovementRead(BaseModel):
    id: str
    ingredient_id: str
    ingredient_name: str
    unit: str
    transaction_type: str
    quantity_delta: Decimal
    balance_after: Decimal
    reference: str | None
    notes: str | None
    created_at: datetime


class DashboardTopProduct(BaseModel):
    product_name: str
    quantity_sold: int
    revenue: Decimal


class DashboardSeriesPoint(BaseModel):
    label: str
    value: Decimal


class DashboardRead(BaseModel):
    sales_today: Decimal
    orders_today: int
    cash_sales: Decimal
    upi_sales: Decimal
    card_sales: Decimal
    low_stock_products: int
    top_products: list[DashboardTopProduct]
    hourly_sales: list[DashboardSeriesPoint]
    date_sales: list[DashboardSeriesPoint]
    hour_sales: list[DashboardSeriesPoint]
    category_sales: list[DashboardSeriesPoint]


class MarketplaceOrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    product_id: str | None
    product_name: str
    variant_name: str | None
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class MarketplaceOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    external_order_id: str
    merchant_id: str
    status: str
    subtotal: Decimal
    tax: Decimal
    packaging_charge: Decimal
    discount: Decimal
    commission: Decimal
    grand_total: Decimal
    net_settlement: Decimal
    food_cost: Decimal
    estimated_profit: Decimal
    customer_name: str | None
    customer_phone_masked: str | None
    instructions: str | None
    placed_at: datetime
    items: list[MarketplaceOrderItemRead]


class MarketplaceSummaryRead(BaseModel):
    total_orders: int
    active_orders: int
    completed_orders: int
    cancelled_orders: int
    gross_sales: Decimal
    net_settlement: Decimal
    estimated_profit: Decimal
    swiggy_orders: int
    zomato_orders: int
    mock_enabled: bool


class MarketplaceStatusUpdate(BaseModel):
    status: Literal['ACCEPTED', 'REJECTED', 'PREPARING', 'READY', 'COMPLETED', 'CANCELLED']


class MarketplaceMockOrderCreate(BaseModel):
    provider: Literal['SWIGGY', 'ZOMATO']


class MarketplaceIngestItem(BaseModel):
    external_item_id: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=180)
    variant_name: str | None = Field(default=None, max_length=120)
    quantity: int = Field(gt=0, le=999)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class MarketplaceOrderIngest(BaseModel):
    provider: Literal['SWIGGY', 'ZOMATO']
    merchant_id: str = Field(min_length=1, max_length=120)
    outlet_code: str | None = Field(default=None, max_length=32)
    external_order_id: str = Field(min_length=1, max_length=100)
    customer_name: str | None = Field(default=None, max_length=120)
    customer_phone_masked: str | None = Field(default=None, max_length=32)
    instructions: str | None = Field(default=None, max_length=2000)
    tax: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=18, decimal_places=2)
    packaging_charge: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=18, decimal_places=2)
    discount: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=18, decimal_places=2)
    commission: Decimal = Field(default=Decimal('0.00'), ge=0, max_digits=18, decimal_places=2)
    placed_at: datetime
    items: list[MarketplaceIngestItem] = Field(min_length=1, max_length=200)


class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    contact_person: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)
    tax_number: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=2000)


class SupplierRead(SupplierCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    status: str
    created_at: datetime


class PurchaseLineCreate(BaseModel):
    product_id: str | None = Field(default=None, min_length=36, max_length=36)
    ingredient_id: str | None = Field(default=None, min_length=36, max_length=36)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=3)
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    tax_percent: Decimal = Field(default=Decimal('5.00'), ge=0, le=100, max_digits=5, decimal_places=2)

    @model_validator(mode='after')
    def validate_item_reference(self) -> 'PurchaseLineCreate':
        if bool(self.product_id) == bool(self.ingredient_id):
            raise ValueError('Select exactly one product or ingredient.')
        return self


class PurchaseCreate(BaseModel):
    supplier_id: str = Field(min_length=36, max_length=36)
    invoice_number: str = Field(min_length=2, max_length=100)
    purchase_date: datetime
    payment_status: str = Field(pattern=r'^(PAID|PENDING|PARTIAL)$')
    notes: str | None = Field(default=None, max_length=4000)
    items: list[PurchaseLineCreate] = Field(min_length=1, max_length=100)


class PurchaseLineRead(BaseModel):
    product_id: str | None
    ingredient_id: str | None
    item_name: str
    quantity: Decimal
    unit_cost: Decimal
    tax_percent: Decimal
    line_total: Decimal


class PurchaseRead(BaseModel):
    id: str
    supplier_id: str
    supplier_name: str
    invoice_number: str
    purchase_date: datetime
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    payment_status: str
    item_count: int
    notes: str | None
    items: list[PurchaseLineRead]


class ExpenseCreate(BaseModel):
    expense_date: datetime
    category: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=2, max_length=300)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_mode: str = Field(pattern=r'^(CASH|UPI|CARD|BANK_TRANSFER)$')
    remarks: str | None = Field(default=None, max_length=4000)


class ExpenseRead(ExpenseCreate):
    id: str
    created_by_name: str
    created_at: datetime


class CustomerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    mobile: str | None = Field(default=None, min_length=7, max_length=32)
    email: str | None = Field(default=None, max_length=255)


class CustomerRead(CustomerCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    loyalty_points: int
    created_at: datetime


class CustomerCreditEntryRead(BaseModel):
    id: str
    order_id: str | None
    invoice_number: str | None
    entry_type: str
    amount: Decimal
    due_date: date | None
    payment_mode: str | None
    reference: str | None
    notes: str | None
    created_at: datetime


class CustomerCreditAccountRead(BaseModel):
    customer: CustomerRead
    outstanding_balance: Decimal
    overdue_amount: Decimal
    oldest_due_date: date | None
    open_bill_count: int
    entries: list[CustomerCreditEntryRead]


class CustomerCreditSettlementCreate(BaseModel):
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    payment_mode: str = Field(pattern=r'^(CASH|UPI|CARD)$')
    reference: str | None = Field(default=None, max_length=128)
    notes: str | None = Field(default=None, max_length=1000)


class DailyClosingCreate(BaseModel):
    business_date: date
    counted_cash: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class DailyClosingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    business_date: str
    order_count: int
    gross_sales: Decimal
    cash_sales: Decimal
    upi_sales: Decimal
    card_sales: Decimal
    expenses: Decimal
    expected_cash: Decimal
    counted_cash: Decimal
    variance: Decimal
    status: str
    created_at: datetime


class TenantSettingRead(BaseModel):
    setting_key: str
    setting_value: str


class TenantSettingUpdate(BaseModel):
    setting_value: str = Field(max_length=10000)


class TenantPaymentPolicyRead(BaseModel):
    payment_processing_mode: Literal['MANUAL_ALLOWED', 'TERMINAL_REQUIRED']


class TenantPaymentPolicyUpdate(BaseModel):
    payment_processing_mode: Literal['MANUAL_ALLOWED', 'TERMINAL_REQUIRED']


class TenantMessageUserRead(BaseModel):
    id: str
    display_name: str
    username: str
    role_code: str


class TenantMessageCreate(BaseModel):
    audience: Literal['DIRECT', 'GROUP'] = 'DIRECT'
    recipient_user_id: str | None = None
    subject: str = Field(min_length=2, max_length=160)
    body: str = Field(min_length=1, max_length=5000)
    reply_to_id: str | None = Field(default=None, min_length=36, max_length=36)


class TenantMessageReactionRead(BaseModel):
    emoji: str
    count: int
    reacted_by_me: bool


class TenantMessageReactionUpdate(BaseModel):
    emoji: str = Field(min_length=1, max_length=16)


class TenantMessageRead(BaseModel):
    id: str
    group_message_id: str | None
    sender_user_id: str
    sender_name: str
    recipient_user_id: str
    recipient_name: str
    audience: Literal['DIRECT', 'GROUP']
    subject: str
    body: str
    reply_to_id: str | None
    reply_to_group_message_id: str | None
    reply_to_sender_name: str | None
    reply_to_body: str | None
    reactions: list[TenantMessageReactionRead]
    read_at: datetime | None
    created_at: datetime


class TenantMessageSendResult(BaseModel):
    delivered: int


class CategoryCreate(BaseModel):
    code: str = Field(min_length=2, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')
    name: str = Field(min_length=2, max_length=160)
    image_path: str | None = Field(default=None, max_length=512)
    display_order: int = Field(default=0, ge=0, le=10000)


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    image_path: str | None = Field(default=None, max_length=512)
    display_order: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None
