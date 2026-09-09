from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Currency(Base):
    __tablename__ = 'currencies'
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    symbol: Mapped[str] = mapped_column(String(12))
    locale: Mapped[str] = mapped_column(String(24), default='en-US')
    decimal_places: Mapped[int] = mapped_column(Integer, default=2)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class Tenant(Base, Timestamped):
    __tablename__ = 'tenants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    status: Mapped[str] = mapped_column(String(24), default='ACTIVE')
    logo_url: Mapped[str | None] = mapped_column(String(512))
    cover_image_url: Mapped[str | None] = mapped_column(String(512))
    primary_color: Mapped[str] = mapped_column(String(16), default='#5A2D18')
    secondary_color: Mapped[str] = mapped_column(String(16), default='#C8874A')
    tagline: Mapped[str | None] = mapped_column(String(240))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    # The database migration enforces this reference. Keeping ORM metadata
    # independent lets isolated test databases create tenants before seed data.
    currency_code: Mapped[str] = mapped_column(String(3), default='INR', index=True)


class SubscriptionPlan(Base, Timestamped):
    __tablename__ = 'subscription_plans'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    max_terminals: Mapped[int] = mapped_column(Integer, default=1)
    feature_json: Mapped[str] = mapped_column(Text, default='{}')


class Subscription(Base, Timestamped):
    __tablename__ = 'subscriptions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey('subscription_plans.id'))
    status: Mapped[str] = mapped_column(String(24), default='ACTIVE')
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    grace_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class Outlet(Base, Timestamped):
    __tablename__ = 'outlets'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint('tenant_id', 'code', name='uq_outlet_tenant_code'),)


class Category(Base, Timestamped):
    __tablename__ = 'categories'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(160))
    image_path: Mapped[str | None] = mapped_column(String(512))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('tenant_id', 'code', name='uq_category_tenant_code'),)


class Role(Base):
    __tablename__ = 'roles'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))


class Permission(Base):
    __tablename__ = 'permissions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(160))


class RolePermission(Base):
    __tablename__ = 'role_permissions'
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'), primary_key=True)
    permission_id: Mapped[str] = mapped_column(ForeignKey('permissions.id'), primary_key=True)


class User(Base, Timestamped):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str | None] = mapped_column(ForeignKey('outlets.id'))
    role_id: Mapped[str] = mapped_column(ForeignKey('roles.id'))
    username: Mapped[str] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[Role] = relationship()
    __table_args__ = (UniqueConstraint('tenant_id', 'username', name='uq_user_tenant_username'),)

    @property
    def role_code(self) -> str:
        return self.role.code


class RefreshToken(Base):
    __tablename__ = 'refresh_tokens'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    token_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    user: Mapped[User] = relationship()


class PosTerminal(Base, Timestamped):
    __tablename__ = 'pos_terminals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'))
    terminal_code: Mapped[str] = mapped_column(String(64))
    terminal_name: Mapped[str] = mapped_column(String(120))
    device_key_hash: Mapped[str] = mapped_column(String(255), unique=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(24), default='PENDING')
    __table_args__ = (UniqueConstraint('tenant_id', 'terminal_code', name='uq_terminal_tenant_code'),)


class LicenseEvent(Base):
    __tablename__ = 'license_events'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    terminal_id: Mapped[str] = mapped_column(ForeignKey('pos_terminals.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base, Timestamped):
    __tablename__ = 'products'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str | None] = mapped_column(ForeignKey('outlets.id'))
    category_id: Mapped[str | None] = mapped_column(ForeignKey('categories.id'), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    gst_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('5.00'))
    description: Mapped[str | None] = mapped_column(Text)
    image_path: Mapped[str | None] = mapped_column(String(512))
    unit: Mapped[str] = mapped_column(String(24), default='pcs')
    stock_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    low_stock_limit: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    is_favourite: Mapped[bool] = mapped_column(Boolean, default=False)
    kot_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[Category | None] = relationship()
    variants: Mapped[list['ProductVariant']] = relationship(back_populates='product', cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('tenant_id', 'code', name='uq_product_tenant_code'),)

    @property
    def category_name(self) -> str | None:
        return self.category.name if self.category else None

    @property
    def shared_across_outlets(self) -> bool:
        return self.outlet_id is None


class GlobalProduct(Base, Timestamped):
    """Platform product definition shared by every tenant.

    Operational orders still point to ``Product`` so existing invoices remain
    immutable. ``OutletProductMapping.legacy_product_id`` is the compatibility
    bridge used while existing installations adopt the global catalogue.
    """

    __tablename__ = 'global_products'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    category_name: Mapped[str] = mapped_column(String(160), index=True)
    base_unit: Mapped[str] = mapped_column(String(24), default='pcs')
    default_gst: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('5.00'))
    image_path: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(24), default='ACTIVE', index=True)


class OutletProductMapping(Base, Timestamped):
    __tablename__ = 'outlet_product_mappings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    global_product_id: Mapped[str | None] = mapped_column(ForeignKey('global_products.id'), index=True)
    legacy_product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    selling_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    favourite: Mapped[bool] = mapped_column(Boolean, default=False)
    kot_required: Mapped[bool] = mapped_column(Boolean, default=True)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    outlet_specific_name: Mapped[str | None] = mapped_column(String(180))
    tax_override: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    global_product: Mapped[GlobalProduct | None] = relationship()
    legacy_product: Mapped[Product] = relationship()
    __table_args__ = (
        UniqueConstraint('outlet_id', 'global_product_id', name='uq_outlet_global_product'),
        UniqueConstraint('outlet_id', 'legacy_product_id', name='uq_outlet_legacy_product'),
    )


class ProductVariant(Base):
    __tablename__ = 'product_variants'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    name: Mapped[str] = mapped_column(String(120))
    price_adjustment: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    product: Mapped[Product] = relationship(back_populates='variants')
    __table_args__ = (UniqueConstraint('product_id', 'name', name='uq_variant_product_name'),)


class Order(Base, Timestamped):
    __tablename__ = 'orders'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    terminal_id: Mapped[str] = mapped_column(ForeignKey('pos_terminals.id'))
    # Nullable only for orders created before the cashier migration. Every new
    # API order always stores the authenticated user below.
    cashier_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'), index=True)
    customer_id: Mapped[str | None] = mapped_column(ForeignKey('customers.id'), index=True)
    invoice_number: Mapped[str] = mapped_column(String(80), unique=True)
    order_type: Mapped[str] = mapped_column(String(24), default='KOT', index=True)
    service_reference: Mapped[str | None] = mapped_column(String(80))
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    round_off: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(24), default='COMPLETED')
    payment_status: Mapped[str] = mapped_column(String(24), default='PAID', index=True)
    cancellation_reason: Mapped[str | None] = mapped_column(Text)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    voided_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    items: Mapped[list['OrderItem']] = relationship(back_populates='order', cascade='all, delete-orphan')
    payments: Mapped[list['Payment']] = relationship(back_populates='order', cascade='all, delete-orphan')


class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'))
    variant_id: Mapped[str | None] = mapped_column(ForeignKey('product_variants.id'))
    product_name: Mapped[str] = mapped_column(String(180))
    variant_name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    order: Mapped[Order] = relationship(back_populates='items')


class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), index=True)
    payment_mode: Mapped[str] = mapped_column(String(24))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    reference: Mapped[str | None] = mapped_column(String(128))
    capture_source: Mapped[str] = mapped_column(String(24), default='MANUAL')
    provider: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    order: Mapped[Order] = relationship(back_populates='payments')


class MarketplaceOrder(Base, Timestamped):
    __tablename__ = 'marketplace_orders'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    provider: Mapped[str] = mapped_column(String(24), index=True)
    external_order_id: Mapped[str] = mapped_column(String(100))
    merchant_id: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default='RECEIVED', index=True)
    currency_code: Mapped[str] = mapped_column(String(3), default='INR')
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    packaging_charge: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    commission: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    net_settlement: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    food_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    estimated_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    customer_name: Mapped[str | None] = mapped_column(String(120))
    customer_phone_masked: Mapped[str | None] = mapped_column(String(32))
    instructions: Mapped[str | None] = mapped_column(Text)
    stock_committed: Mapped[bool] = mapped_column(Boolean, default=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items: Mapped[list['MarketplaceOrderItem']] = relationship(back_populates='order', cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('tenant_id', 'provider', 'external_order_id', name='uq_marketplace_external_order'),)


class MarketplaceOrderItem(Base):
    __tablename__ = 'marketplace_order_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('marketplace_orders.id'), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey('products.id'), index=True)
    variant_id: Mapped[str | None] = mapped_column(ForeignKey('product_variants.id'))
    external_item_id: Mapped[str] = mapped_column(String(120))
    product_name: Mapped[str] = mapped_column(String(180))
    variant_name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    order: Mapped[MarketplaceOrder] = relationship(back_populates='items')


class KotHeader(Base):
    __tablename__ = 'kot_headers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), unique=True, index=True)
    kot_number: Mapped[str] = mapped_column(String(80), unique=True)
    station: Mapped[str] = mapped_column(String(80), default='Hot Kitchen')
    status: Mapped[str] = mapped_column(String(24), default='NEW', index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    items: Mapped[list['KotItem']] = relationship(back_populates='kot', cascade='all, delete-orphan')


class KotItem(Base):
    __tablename__ = 'kot_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kot_id: Mapped[str] = mapped_column(ForeignKey('kot_headers.id'), index=True)
    order_item_id: Mapped[str] = mapped_column(ForeignKey('order_items.id'))
    product_name: Mapped[str] = mapped_column(String(180))
    variant_name: Mapped[str | None] = mapped_column(String(120))
    quantity: Mapped[int] = mapped_column(Integer)
    kot: Mapped[KotHeader] = relationship(back_populates='items')


class HeldOrder(Base):
    __tablename__ = 'held_orders'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    order_id: Mapped[str] = mapped_column(ForeignKey('orders.id'), unique=True, index=True)
    cashier_id: Mapped[str] = mapped_column(ForeignKey('users.id'))
    hold_number: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default='HELD', index=True)
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reopened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    order: Mapped[Order] = relationship()
    cashier: Mapped[User] = relationship()


class Supplier(Base, Timestamped):
    __tablename__ = 'suppliers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    name: Mapped[str] = mapped_column(String(180))
    contact_person: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    tax_number: Mapped[str | None] = mapped_column(String(64))
    address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default='ACTIVE')
    __table_args__ = (UniqueConstraint('tenant_id', 'name', name='uq_supplier_tenant_name'),)


class Purchase(Base, Timestamped):
    __tablename__ = 'purchases'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey('suppliers.id'), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    invoice_number: Mapped[str] = mapped_column(String(100))
    purchase_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal('0.00'))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment_status: Mapped[str] = mapped_column(String(24), default='PENDING')
    notes: Mapped[str | None] = mapped_column(Text)
    supplier: Mapped[Supplier] = relationship()
    items: Mapped[list['PurchaseItem']] = relationship(back_populates='purchase', cascade='all, delete-orphan')
    __table_args__ = (UniqueConstraint('tenant_id', 'invoice_number', name='uq_purchase_tenant_invoice'),)


class PurchaseItem(Base):
    __tablename__ = 'purchase_items'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    purchase_id: Mapped[str] = mapped_column(ForeignKey('purchases.id'), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    product_name: Mapped[str] = mapped_column(String(180))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('5.00'))
    line_total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    purchase: Mapped[Purchase] = relationship(back_populates='items')


class Expense(Base, Timestamped):
    __tablename__ = 'expenses'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    expense_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    description: Mapped[str] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    payment_mode: Mapped[str] = mapped_column(String(24))
    remarks: Mapped[str | None] = mapped_column(Text)


class Customer(Base, Timestamped):
    __tablename__ = 'customers'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    name: Mapped[str] = mapped_column(String(160))
    mobile: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    loyalty_points: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint('tenant_id', 'mobile', name='uq_customer_tenant_mobile'),)


class CustomerCreditEntry(Base):
    """Immutable customer-credit ledger.

    PURCHASE and REVERSAL entries belong to an order. PAYMENT entries record a
    later full settlement, so repeated credit purchases naturally accumulate.
    """

    __tablename__ = 'customer_credit_entries'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey('customers.id'), index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey('orders.id'), index=True)
    entry_type: Mapped[str] = mapped_column(String(24), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    payment_mode: Mapped[str | None] = mapped_column(String(24))
    reference: Mapped[str | None] = mapped_column(String(128))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DailyClosing(Base, Timestamped):
    __tablename__ = 'daily_closings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    closed_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    business_date: Mapped[str] = mapped_column(String(10), index=True)
    order_count: Mapped[int] = mapped_column(Integer)
    gross_sales: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    cash_sales: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    upi_sales: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    card_sales: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expenses: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    expected_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    counted_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    variance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(24), default='CLOSED')
    __table_args__ = (UniqueConstraint('tenant_id', 'outlet_id', 'business_date', name='uq_closing_outlet_date'),)


class TenantSetting(Base, Timestamped):
    __tablename__ = 'tenant_settings'
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(120), primary_key=True)
    setting_value: Mapped[str] = mapped_column(Text)


class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(36))
    payload: Mapped[str] = mapped_column(Text, default='{}')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Inventory(Base, Timestamped):
    __tablename__ = 'inventory'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    opening_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    stock_added: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    stock_sold: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    low_stock_limit: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    __table_args__ = (UniqueConstraint('tenant_id', 'outlet_id', 'product_id', name='uq_inventory_outlet_product'),)


class InventoryTransaction(Base):
    __tablename__ = 'inventory_transactions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey('products.id'), index=True)
    transaction_type: Mapped[str] = mapped_column(String(48), index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reference_type: Mapped[str] = mapped_column(String(48))
    reference_id: Mapped[str] = mapped_column(String(100), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Ingredient(Base, Timestamped):
    __tablename__ = 'ingredients'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    code: Mapped[str] = mapped_column(String(80))
    name: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(120))
    unit: Mapped[str] = mapped_column(String(24))
    image_path: Mapped[str | None] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint('tenant_id', 'code', name='uq_ingredient_tenant_code'),)


class IngredientStock(Base, Timestamped):
    __tablename__ = 'ingredient_stocks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey('ingredients.id'), index=True)
    opening_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    stock_added: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    stock_used: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    available_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    low_stock_limit: Mapped[Decimal] = mapped_column(Numeric(18, 3), default=Decimal('0.000'))
    ingredient: Mapped[Ingredient] = relationship()
    __table_args__ = (
        UniqueConstraint('tenant_id', 'outlet_id', 'ingredient_id', name='uq_ingredient_stock_outlet_item'),
    )


class IngredientTransaction(Base):
    __tablename__ = 'ingredient_transactions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey('tenants.id'), index=True)
    outlet_id: Mapped[str] = mapped_column(ForeignKey('outlets.id'), index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey('ingredients.id'), index=True)
    transaction_type: Mapped[str] = mapped_column(String(48), index=True)
    quantity_delta: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 3))
    reference: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
