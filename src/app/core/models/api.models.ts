export interface RuntimeConfig {
  apiBaseUrl: string;
  assetsBaseUrl: string;
  terminalCode: string;
  tenantName: string;
  tenantCode?: string;
  environment: 'development' | 'staging' | 'production';
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: 'bearer';
}

export interface LoginResponse extends TokenPair {
  user: CurrentUser;
}

export interface MfaChallenge {
  status: 'MFA_REQUIRED';
  challenge_token: string;
  setup_required: boolean;
  setup_secret: string | null;
  otpauth_uri: string | null;
}

export interface CurrentUser {
  id: string;
  tenant_id: string;
  outlet_id: string | null;
  username: string;
  display_name: string;
  role_code: 'SUPER_ADMIN' | 'TENANT_ADMIN' | 'ADMIN' | 'CASHIER';
}

export interface CurrencyDefinition {
  code: string;
  name: string;
  symbol: string;
  locale: string;
  decimal_places: number;
}

export type SubscriptionState = 'ACTIVE' | 'EXPIRING_SOON' | 'GRACE' | 'EXPIRED' | 'NOT_STARTED';

export interface TenantPreview {
  code: string;
  name: string;
  status: string;
  outlet_name: string | null;
  outlet_address: string | null;
  logo_url: string | null;
  cover_image_url: string | null;
  primary_color: string;
  tagline: string | null;
  plan_code: string | null;
  subscription_state: SubscriptionState;
  subscription_end: string | null;
  grace_ends_at: string | null;
  days_remaining: number | null;
  grace_days_remaining: number | null;
  login_allowed: boolean;
  subscription_message: string;
  currency: CurrencyDefinition;
}

export interface PlatformContext {
  tenant_id: string;
  tenant_code: string | null;
  tenant_name: string;
  outlet_id: string | null;
  outlet_code: string | null;
  outlet_name: string | null;
  role_code: CurrentUser['role_code'];
  branding: {
    display_name: string | null;
    logo_url: string | null;
    cover_image_url: string | null;
    primary_color: string | null;
    secondary_color: string | null;
    tagline: string | null;
  };
  subscription_status: string;
  subscription_end: string;
  subscription_state: SubscriptionState;
  grace_ends_at: string | null;
  subscription_message: string;
  plan_code: string;
  max_terminals: number;
  features: Record<string, unknown>;
  currency: CurrencyDefinition;
}

export interface GlobalProduct {
  id: string;
  code: string;
  name: string;
  description: string | null;
  category_name: string;
  base_unit: string;
  default_gst: string;
  image_path: string | null;
  status: 'ACTIVE' | 'INACTIVE';
}

export interface ProductVariant {
  id: string;
  name: string;
  price_adjustment: string;
  display_order: number;
  is_active: boolean;
}

export interface OutletProductMapping {
  tax_override?: string | null;
  id: string;
  global_product_id: string | null;
  legacy_product_id: string;
  code: string;
  name: string;
  category_name: string;
  image_path: string | null;
  base_unit: string;
  default_gst: string;
  selling_price: string;
  stock_quantity: string;
  low_stock_limit: string;
  favourite: boolean;
  kot_required: boolean;
  is_available: boolean;
  is_active: boolean;
  display_order: number;
  source: 'GLOBAL' | 'TENANT';
  variants: ProductVariant[];
}

export interface TenantAdmin {
  id: string;
  code: string | null;
  name: string;
  status: string;
  outlet_count: number;
  admin_count: number;
  logo_url: string | null;
  cover_image_url: string | null;
  primary_color: string;
  secondary_color: string;
  tagline: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  plan_code: string | null;
  plan_name: string | null;
  subscription_state: SubscriptionState;
  subscription_end: string | null;
  grace_ends_at: string | null;
  login_allowed: boolean;
  currency_code: string;
}

export interface TenantSubscription {
  tenant_id: string;
  subscription_id: string | null;
  plan_code: string | null;
  plan_name: string | null;
  status: string;
  starts_at: string | null;
  ends_at: string | null;
  grace_ends_at: string | null;
  lifecycle_state: SubscriptionState;
  days_remaining: number | null;
  grace_days_remaining: number | null;
  login_allowed: boolean;
  message: string;
}

export interface AdminOutlet {
  id: string;
  tenant_id: string;
  code: string;
  name: string;
  address: string | null;
}

export interface AdminUser {
  id: string;
  tenant_id: string;
  tenant_name: string;
  outlet_id: string | null;
  outlet_name: string | null;
  username: string;
  display_name: string;
  email: string | null;
  phone: string | null;
  role_code: 'TENANT_ADMIN' | 'ADMIN' | 'CASHIER';
  is_active: boolean;
  last_active: string;
}

export interface AdminRole { id: string; code: AdminUser['role_code']; name: string; }

export interface Category {
  id: string;
  code: string;
  name: string;
  image_path: string | null;
  display_order: number;
}

export interface Product {
  id: string;
  code: string;
  name: string;
  outlet_id: string | null;
  category_id: string | null;
  category_name: string | null;
  description: string | null;
  image_path: string | null;
  selling_price: string;
  purchase_price: string;
  gst_percent: string;
  stock_quantity: string;
  low_stock_limit: string;
  unit: string;
  is_favourite: boolean;
  kot_required: boolean;
  is_available: boolean;
  is_active: boolean;
  shared_across_outlets: boolean;
  variants: ProductVariant[];
  source?: 'cloud' | 'local';
}

export interface ProductCreate {
  code: string;
  name: string;
  selling_price: string;
  purchase_price: string;
  gst_percent: string;
  category_id: string | null;
  description: string | null;
  image_path: string | null;
  unit: string;
  stock_quantity: string;
  low_stock_limit: string;
  is_favourite: boolean;
  kot_required: boolean;
  is_available: boolean;
  is_active: boolean;
  shared_across_outlets: boolean;
}

export interface CartLine extends Product {
  quantity: number;
  cart_key: string;
  selected_variant_id: string | null;
  selected_variant_name: string;
}

export interface OrderCreate {
  order_id: string;
  terminal_code: string;
  items: Array<{ product_id: string; variant_id?: string | null; quantity: number }>;
  payments: Array<{
    mode: 'CASH' | 'UPI' | 'CARD';
    amount: string;
    reference?: string;
    capture_source?: 'MANUAL' | 'PAYMENT_TERMINAL';
    provider?: string;
  }>;
  credit_customer_id?: string;
  credit_due_days?: number;
  held_order_id?: string;
  discount_percent?: string;
  round_to_rupee?: boolean;
  order_type?: 'DIRECT' | 'KOT' | 'TAKEAWAY';
  service_reference?: string | null;
}

export interface OfflineOrderSync {
  order_id: string;
  terminal_code: string;
  items: Array<{ product_code: string; variant_name?: string | null; quantity: number }>;
  payments: Array<{ mode: 'CASH' | 'UPI' | 'CARD'; amount: string; reference?: string }>;
}

export interface OrderResult {
  id: string;
  invoice_number: string;
  grand_total: string;
  status: string;
  payment_status: 'PAID' | 'CREDIT' | 'SETTLED' | 'VOID';
  customer_id: string | null;
  order_type: 'DIRECT' | 'KOT' | 'TAKEAWAY';
  service_reference: string | null;
}

export interface OrderListItem extends OrderResult {
  subtotal: string;
  discount: string;
  tax: string;
  round_off: string;
  created_at: string;
  cashier_name: string;
  item_count: number;
  payment_modes: string[];
  items: Array<{
    product_name: string;
    variant_name: string | null;
    quantity: number;
    line_total: string;
  }>;
}

export interface KotTicket {
  id: string;
  kot_number: string;
  invoice_number: string;
  cashier_name: string;
  station: string;
  status: 'NEW' | 'PREPARING' | 'READY' | 'SERVED' | 'DELAYED';
  created_at: string;
  items: Array<{ product_name: string; variant_name: string | null; quantity: number }>;
}

export interface HeldBill {
  id: string;
  hold_number: string;
  invoice_number: string;
  held_at: string;
  cashier_name: string;
  subtotal: string;
  tax: string;
  grand_total: string;
  items: Array<{
    product_id: string;
    variant_id: string | null;
    product_name: string;
    variant_name: string | null;
    quantity: number;
    rate: string;
    tax: string;
    line_total: string;
  }>;
}

export interface IngredientInventoryItem {
  id: string;
  code: string;
  name: string;
  category: string;
  unit: string;
  image_path: string | null;
  opening_quantity: string;
  stock_added: string;
  stock_used: string;
  available_quantity: string;
  low_stock_limit: string;
  is_active: boolean;
  status: 'IN_STOCK' | 'LOW_STOCK' | 'OUT_OF_STOCK';
}

export interface IngredientMovement {
  id: string;
  ingredient_id: string;
  ingredient_name: string;
  unit: string;
  transaction_type: 'STOCK_IN' | 'STOCK_OUT' | 'DAMAGE' | 'WASTAGE' | 'MANUAL_CORRECTION';
  quantity_delta: string;
  balance_after: string;
  reference: string | null;
  notes: string | null;
  created_at: string;
}

export interface DashboardMetric {
  sales_today: string;
  orders_today: number;
  cash_sales: string;
  upi_sales: string;
  card_sales: string;
  low_stock_products: number;
  top_products: Array<{ product_name: string; quantity_sold: number; revenue: string }>;
  hourly_sales: Array<{ label: string; value: string }>;
  date_sales: Array<{ label: string; value: string }>;
  hour_sales: Array<{ label: string; value: string }>;
  category_sales: Array<{ label: string; value: string }>;
}

export interface Supplier {
  id: string;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  tax_number: string | null;
  address: string | null;
  status: string;
  created_at: string;
}

export interface Purchase {
  id: string;
  supplier_name: string;
  invoice_number: string;
  purchase_date: string;
  subtotal: string;
  tax: string;
  total: string;
  payment_status: 'PAID' | 'PENDING' | 'PARTIAL';
  item_count: number;
}

export interface PurchaseCreate {
  supplier_id: string;
  invoice_number: string;
  purchase_date: string;
  payment_status: Purchase['payment_status'];
  notes: string | null;
  items: Array<{
    product_id: string;
    quantity: string;
    unit_cost: string;
    tax_percent: string;
  }>;
}

export interface Expense {
  id: string;
  expense_date: string;
  category: string;
  description: string;
  amount: string;
  payment_mode: 'CASH' | 'UPI' | 'CARD' | 'BANK_TRANSFER';
  remarks: string | null;
  created_by_name: string;
  created_at: string;
}

export type ExpenseCreate = Omit<Expense, 'id' | 'created_by_name' | 'created_at'>;

export interface Customer {
  id: string;
  name: string;
  mobile: string | null;
  email: string | null;
  loyalty_points: number;
  created_at: string;
}

export interface CustomerCreditEntry {
  id: string;
  order_id: string | null;
  invoice_number: string | null;
  entry_type: 'PURCHASE' | 'PAYMENT' | 'REVERSAL';
  amount: string;
  due_date: string | null;
  payment_mode: 'CASH' | 'UPI' | 'CARD' | null;
  reference: string | null;
  notes: string | null;
  created_at: string;
}

export interface CustomerCreditAccount {
  customer: Customer;
  outstanding_balance: string;
  overdue_amount: string;
  oldest_due_date: string | null;
  open_bill_count: number;
  entries: CustomerCreditEntry[];
}

export interface DailyClosing {
  id: string;
  business_date: string;
  order_count: number;
  gross_sales: string;
  cash_sales: string;
  upi_sales: string;
  card_sales: string;
  expenses: string;
  expected_cash: string;
  counted_cash: string;
  variance: string;
  status: string;
  created_at: string;
}

export interface TenantSetting {
  setting_key: string;
  setting_value: string;
}

export interface TenantPaymentPolicy {
  payment_processing_mode: 'MANUAL_ALLOWED' | 'TERMINAL_REQUIRED';
}

export type MarketplaceProvider = 'SWIGGY' | 'ZOMATO';
export type MarketplaceOrderStatus = 'RECEIVED' | 'ACCEPTED' | 'PREPARING' | 'READY' | 'COMPLETED' | 'REJECTED' | 'CANCELLED';

export interface MarketplaceOrder {
  id: string;
  provider: MarketplaceProvider;
  external_order_id: string;
  merchant_id: string;
  status: MarketplaceOrderStatus;
  subtotal: string;
  tax: string;
  packaging_charge: string;
  discount: string;
  commission: string;
  grand_total: string;
  net_settlement: string;
  food_cost: string;
  estimated_profit: string;
  customer_name: string | null;
  customer_phone_masked: string | null;
  instructions: string | null;
  placed_at: string;
  items: Array<{ id:string; product_id:string|null; product_name:string; variant_name:string|null; quantity:number; unit_price:string; line_total:string }>;
}

export interface MarketplaceSummary {
  total_orders: number;
  active_orders: number;
  completed_orders: number;
  cancelled_orders: number;
  gross_sales: string;
  net_settlement: string;
  estimated_profit: string;
  swiggy_orders: number;
  zomato_orders: number;
  mock_enabled: boolean;
}

export interface LicenseEnvelope {
  payload: Record<string, unknown>;
  signature: string;
  public_key: string;
}
