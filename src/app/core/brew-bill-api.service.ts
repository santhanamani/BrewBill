import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, firstValueFrom, throwError, timeout } from 'rxjs';
import {
  Category,
  CurrentUser,
  DashboardMetric,
  DailyClosing,
  Expense,
  ExpenseCreate,
  HeldBill,
  GlobalProduct,
  IngredientInventoryItem,
  IngredientMovement,
  Customer,
  CustomerCreditAccount,
  KotTicket,
  LicenseEnvelope,
  LoginResponse,
  OfflineOrderSync,
  OrderCreate,
  OrderListItem,
  OrderResult,
  OutletProductMapping,
  PlatformContext,
  Product,
  ProductCreate,
  ProductVariant,
  Purchase,
  PurchaseCreate,
  Supplier,
  TenantAdmin,
  AdminOutlet,
  AdminRole,
  AdminUser,
  TenantPreview,
  TenantSetting,
  TenantPaymentPolicy,
  TenantSubscription,
  MfaChallenge,
  CurrencyDefinition,
  MarketplaceOrder,
  MarketplaceOrderStatus,
  MarketplaceProvider,
  MarketplaceSummary,
  TenantMessage,
  TenantMessageUser,
  OwnerTenantScope,
} from './models/api.models';
import { RuntimeConfigService } from './runtime-config.service';
import { OutletContextService } from './outlet-context.service';

@Injectable({ providedIn: 'root' })
export class BrewBillApiService {
  private readonly http = inject(HttpClient);
  private readonly runtime = inject(RuntimeConfigService);
  private readonly outletContext = inject(OutletContextService);

  login(username: string, password: string, tenantCode?: string): Promise<LoginResponse | MfaChallenge> {
    return this.request(
      this.http.post<LoginResponse | MfaChallenge>(this.runtime.apiUrl('/auth/login'), {
        username,
        password,
        tenant_code: tenantCode || undefined,
        tenant_name: tenantCode ? undefined : this.runtime.config().tenantName,
      }),
      5000,
    );
  }

  verifyMfa(challengeToken: string, code: string): Promise<LoginResponse> {
    return this.request(
      this.http.post<LoginResponse>(this.runtime.apiUrl('/auth/mfa/verify'), {
        challenge_token: challengeToken, code,
      }), 5000,
    );
  }

  uploadTenantBranding(accessToken: string, tenantId: string, kind: 'logo' | 'cover', file: File): Promise<{path:string;url:string;width:number;height:number}> {
    const body = new FormData();
    body.append('file', file);
    return this.request(this.http.post<{path:string;url:string;width:number;height:number}>(
      this.runtime.apiUrl('/platform/admin/tenants/' + encodeURIComponent(tenantId) + '/branding/' + kind + '/upload'),
      body, {headers:this.authHeaders(accessToken)},
    ), 30000);
  }

  uploadTenantProductImage(accessToken: string, file: File): Promise<{path:string;url:string;width:number;height:number}> {
    const body = new FormData();
    body.append('file', file);
    return this.request(this.http.post<{path:string;url:string;width:number;height:number}>(
      this.runtime.apiUrl('/products/catalogue/local/image'), body,
      {headers:this.authHeaders(accessToken)},
    ), 30000);
  }
  uploadGlobalProductImage(accessToken: string, file: File): Promise<{path:string;url:string;width:number;height:number}> {
    const body = new FormData();
    body.append('file', file);
    return this.request(this.http.post<{path:string;url:string;width:number;height:number}>(
      this.runtime.apiUrl('/products/master/image'), body,
      {headers:this.authHeaders(accessToken)},
    ), 30000);
  }
  resolveTenant(code: string): Promise<TenantPreview> {
    return this.request(
      this.http.get<TenantPreview>(
        this.runtime.apiUrl(`/platform/tenants/resolve?code=${encodeURIComponent(code)}`),
      ),
      5000,
    );
  }

  getPlatformContext(accessToken: string): Promise<PlatformContext> {
    return this.get<PlatformContext>(accessToken, '/platform/context');
  }

  listCurrencies(accessToken: string): Promise<CurrencyDefinition[]> {
    return this.get<CurrencyDefinition[]>(accessToken, '/currencies');
  }

  updateCurrency(accessToken: string, currencyCode: string): Promise<CurrencyDefinition> {
    return this.request(
      this.http.put<CurrencyDefinition>(this.runtime.apiUrl('/currency'),
        { currency_code: currencyCode }, { headers: this.authHeaders(accessToken) }),
      5000,
    );
  }

  updateTenantCurrency(accessToken: string, tenantId: string, currencyCode: string): Promise<CurrencyDefinition> {
    return this.request(
      this.http.put<CurrencyDefinition>(
        this.runtime.apiUrl(`/platform/admin/tenants/${tenantId}/currency`),
        { currency_code: currencyCode },
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  listGlobalProducts(accessToken: string, includeInactive = false): Promise<GlobalProduct[]> {
    return this.get<GlobalProduct[]>(accessToken, `/products/master?include_inactive=${includeInactive}`);
  }

  createGlobalProduct(
    accessToken: string,
    body: Omit<GlobalProduct, 'id'>,
  ): Promise<GlobalProduct> {
    return this.post<GlobalProduct>(accessToken, '/products/master', body);
  }

  listOutletCatalogue(accessToken: string): Promise<OutletProductMapping[]> {
    return this.get<OutletProductMapping[]>(accessToken, '/products/catalogue');
  }

  mapOutletProduct(
    accessToken: string,
    globalProductId: string,
    body: {
      selling_price: string;
      opening_stock: string;
      low_stock_limit: string;
      favourite: boolean;
      kot_required: boolean;
      is_available: boolean;
      is_active: boolean;
      display_order: number;
    },
  ): Promise<OutletProductMapping> {
    return this.post<OutletProductMapping>(accessToken, `/products/catalogue/${globalProductId}`, body);
  }


  createTenantCatalogueProduct(
    accessToken: string,
    body: ProductCreate,
  ): Promise<OutletProductMapping> {
    return this.post<OutletProductMapping>(accessToken, '/products/catalogue/local', body);
  }
  updateOutletProduct(
    accessToken: string,
    mappingId: string,
    body: Partial<OutletProductMapping> & { expected_stock_quantity?: string },
  ): Promise<OutletProductMapping> {
    return this.request(
      this.http.patch<OutletProductMapping>(
        this.runtime.apiUrl(`/products/catalogue/${mappingId}`), body,
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  unmapOutletProduct(accessToken: string, mappingId: string): Promise<void> {
    return this.request(
      this.http.delete<void>(this.runtime.apiUrl(`/products/catalogue/${mappingId}`), {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  listTenants(accessToken: string): Promise<TenantAdmin[]> {
    return this.get<TenantAdmin[]>(accessToken, '/platform/admin/tenants');
  }

  createTenant(
    accessToken: string,
    body: {
      code: string; name: string; outlet_name: string;
      outlet_address: string | null; admin_username: string; admin_password: string;
      admin_display_name: string; plan_code: string; currency_code?: string;
    },
  ): Promise<TenantAdmin> {
    return this.post<TenantAdmin>(accessToken, '/platform/admin/tenants', body);
  }

  updateTenant(accessToken: string, tenantId: string, body: Partial<{name:string;status:'ACTIVE'|'INACTIVE';phone:string|null;email:string|null;website:string|null}>): Promise<TenantAdmin> {
    return this.request(this.http.patch<TenantAdmin>(this.runtime.apiUrl(`/platform/admin/tenants/${tenantId}`), body, {headers:this.authHeaders(accessToken)}), 5000);
  }

  listAdminOutlets(accessToken: string, tenantId?: string): Promise<AdminOutlet[]> {
    return this.get<AdminOutlet[]>(accessToken, `/platform/admin/outlets${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`);
  }

  listTenantOutlets(accessToken: string): Promise<AdminOutlet[]> {
    return this.get<AdminOutlet[]>(accessToken, '/platform/outlets');
  }

  createAdminOutlet(accessToken: string, body: {tenant_id:string;name:string;address:string|null}): Promise<AdminOutlet> {
    return this.post<AdminOutlet>(accessToken, '/platform/admin/outlets', body);
  }

  updateAdminOutlet(accessToken:string, outletId:string, body:Partial<Pick<AdminOutlet,'name'|'address'>>):Promise<AdminOutlet>{
    return this.request(this.http.patch<AdminOutlet>(this.runtime.apiUrl(`/platform/admin/outlets/${outletId}`),body,{headers:this.authHeaders(accessToken)}),5000);
  }

  listAdminUsers(accessToken:string, tenantId?:string):Promise<AdminUser[]>{
    return this.get<AdminUser[]>(accessToken,`/platform/admin/users${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`);
  }

  createAdminUser(accessToken:string, body:{tenant_id:string;outlet_id:string|null;role_code:AdminUser['role_code'];owner_tenant_ids?:string[];username:string;display_name:string;email:string|null;phone:string|null;password:string}):Promise<AdminUser>{
    return this.post<AdminUser>(accessToken,'/platform/admin/users',body);
  }

  updateAdminUser(accessToken:string,userId:string,body:Partial<{outlet_id:string|null;role_code:AdminUser['role_code'];owner_tenant_ids:string[];display_name:string;email:string|null;phone:string|null;password:string;is_active:boolean}>):Promise<AdminUser>{
    return this.request(this.http.patch<AdminUser>(this.runtime.apiUrl(`/platform/admin/users/${userId}`),body,{headers:this.authHeaders(accessToken)}),5000);
  }

  listAdminRoles(accessToken:string):Promise<AdminRole[]>{ return this.get<AdminRole[]>(accessToken,'/platform/admin/roles'); }

  listOwnerTenants(accessToken:string):Promise<OwnerTenantScope[]>{
    return this.get<OwnerTenantScope[]>(accessToken,'/platform/owner/tenants');
  }

  updateGlobalProduct(accessToken:string,productId:string,body:Partial<Omit<GlobalProduct,'id'|'code'>>):Promise<GlobalProduct>{
    return this.request(this.http.patch<GlobalProduct>(this.runtime.apiUrl(`/products/master/${productId}`),body,{headers:this.authHeaders(accessToken)}),5000);
  }

  updateTenantBranding(
    accessToken: string,
    tenantId: string,
    body: Partial<{
      name: string; logo_url: string | null; cover_image_url: string | null;
      primary_color: string; secondary_color: string; tagline: string | null;
      phone: string | null; email: string | null; website: string | null;
    }>,
  ): Promise<TenantAdmin> {
    return this.request(
      this.http.patch<TenantAdmin>(
        this.runtime.apiUrl(`/platform/admin/tenants/${tenantId}/branding`), body,
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  getCurrentUser(accessToken: string): Promise<CurrentUser> {
    return this.request(
      this.http.get<CurrentUser>(this.runtime.apiUrl('/me'), {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  listCategories(accessToken: string): Promise<Category[]> {
    return this.request(
      this.http.get<Category[]>(this.runtime.apiUrl('/categories'), {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  listProducts(accessToken: string, outletId?: string): Promise<Product[]> {
    return this.request(
      this.http.get<Product[]>(this.runtime.apiUrl(`/products${outletId ? `?outlet_id=${encodeURIComponent(outletId)}` : ''}`), {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  createProduct(accessToken: string, product: ProductCreate): Promise<Product> {
    return this.request(
      this.http.post<Product>(this.runtime.apiUrl('/products'), product, {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  setProductFavourite(accessToken: string, productId: string, favourite: boolean, outletId?: string): Promise<Product> {
    return this.request(this.http.patch<Product>(
      this.runtime.apiUrl(`/products/${productId}/favourite${outletId ? `?outlet_id=${encodeURIComponent(outletId)}` : ''}`),
      { is_favourite: favourite }, { headers: this.authHeaders(accessToken) },
    ), 5000);
  }

  updateProduct(
    accessToken: string,
    productId: string,
    product: Partial<ProductCreate>,
  ): Promise<Product> {
    return this.request(
      this.http.patch<Product>(this.runtime.apiUrl(`/products/${productId}`), product, {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  createProductVariant(
    accessToken: string,
    productId: string,
    body: { name: string; price_adjustment: string; display_order: number },
  ): Promise<unknown> {
    return this.post(accessToken, `/products/${productId}/variants`, body);
  }

  replaceProductVariants(
    accessToken: string,
    productId: string,
    variants: Array<{ id: string | null; name: string; price_adjustment: string; display_order: number }>,
  ): Promise<ProductVariant[]> {
    return this.request(
      this.http.put<ProductVariant[]>(
        this.runtime.apiUrl('/products/' + productId + '/variants'),
        { variants },
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  activateDevice(
    accessToken: string,
    body: { installation_id: string; terminal_code: string; terminal_name: string; outlet_id?: string },
  ): Promise<LicenseEnvelope> {
    return this.post<LicenseEnvelope>(accessToken, '/platform/device/activate', body);
  }

  createOrder(accessToken: string, order: OrderCreate): Promise<OrderResult> {
    return this.request(
      this.http.post<OrderResult>(this.runtime.apiUrl('/orders'), order, {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  syncOfflineOrder(accessToken: string, order: OfflineOrderSync): Promise<OrderResult> {
    return this.request(
      this.http.post<OrderResult>(this.runtime.apiUrl('/orders/sync'), order, {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  listOrders(accessToken: string, fromDate?: string, toDate?: string, tenantId?: string, outletId?: string): Promise<OrderListItem[]> {
    const params = new URLSearchParams();
    if (fromDate) params.set('from_date', fromDate);
    if (toDate) params.set('to_date', toDate);
    if (tenantId) params.set('tenant_id', tenantId);
    if (outletId) params.set('outlet_id', outletId);
    const query = params.size ? `?${params.toString()}` : '';
    return this.request(
      this.http.get<OrderListItem[]>(this.runtime.apiUrl(`/orders${query}`), {
        headers: this.authHeaders(accessToken),
      }),
      2500,
    );
  }

  listMarketplaceOrders(accessToken: string, fromDate?: string, toDate?: string): Promise<MarketplaceOrder[]> {
    const params = new URLSearchParams();
    if (fromDate) params.set('from_date', fromDate);
    if (toDate) params.set('to_date', toDate);
    return this.get<MarketplaceOrder[]>(accessToken, `/marketplace/orders${params.size ? `?${params}` : ''}`);
  }

  getMarketplaceSummary(accessToken: string, fromDate?: string, toDate?: string): Promise<MarketplaceSummary> {
    const params = new URLSearchParams();
    if (fromDate) params.set('from_date', fromDate);
    if (toDate) params.set('to_date', toDate);
    return this.get<MarketplaceSummary>(accessToken, `/marketplace/summary${params.size ? `?${params}` : ''}`);
  }

  createMarketplaceMockOrder(accessToken: string, provider: MarketplaceProvider): Promise<MarketplaceOrder> {
    return this.post<MarketplaceOrder>(accessToken, '/marketplace/mock-orders', { provider });
  }

  updateMarketplaceOrderStatus(accessToken: string, orderId: string, orderStatus: MarketplaceOrderStatus): Promise<MarketplaceOrder> {
    return this.request(this.http.put<MarketplaceOrder>(this.runtime.apiUrl(`/marketplace/orders/${orderId}/status`), { status: orderStatus }, { headers: this.authHeaders(accessToken) }), 8000);
  }

  voidOrder(accessToken: string, orderId: string, reason: string): Promise<OrderResult> {
    return this.post<OrderResult>(accessToken, `/orders/${orderId}/void`, { reason });
  }

  listKots(accessToken: string, completedDate?: string): Promise<KotTicket[]> {
    const query = completedDate ? `?completed_date=${encodeURIComponent(completedDate)}` : '';
    return this.request(
      this.http.get<KotTicket[]>(this.runtime.apiUrl(`/kot${query}`), {
        headers: this.authHeaders(accessToken),
      }),
      2500,
    );
  }

  listHolds(accessToken: string): Promise<HeldBill[]> {
    return this.get<HeldBill[]>(accessToken, '/holds');
  }

  createHold(
    accessToken: string,
    body: {
      terminal_code: string;
      outlet_id?: string;
      items: Array<{ product_id: string; variant_id?: string | null; quantity: number }>;
    },
  ): Promise<HeldBill> {
    return this.post<HeldBill>(accessToken, '/holds', body);
  }

  reopenHold(accessToken: string, holdId: string): Promise<HeldBill> {
    return this.post<HeldBill>(accessToken, `/holds/${holdId}/reopen`, {});
  }

  deleteHold(accessToken: string, holdId: string): Promise<void> {
    return this.request(
      this.http.delete<void>(this.runtime.apiUrl(`/holds/${holdId}`), {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  listInventoryItems(accessToken: string): Promise<IngredientInventoryItem[]> {
    return this.get<IngredientInventoryItem[]>(accessToken, '/inventory/items');
  }

  createInventoryItem(
    accessToken: string,
    body: {
      code: string;
      name: string;
      category: string;
      unit: string;
      image_path: string | null;
      opening_quantity: string;
      low_stock_limit: string;
    },
  ): Promise<IngredientInventoryItem> {
    return this.post<IngredientInventoryItem>(accessToken, '/inventory/items', body);
  }

  updateInventoryItem(
    accessToken: string,
    itemId: string,
    body: Partial<{
      name: string;
      category: string;
      unit: string;
      image_path: string | null;
      low_stock_limit: string;
      is_active: boolean;
    }>,
  ): Promise<IngredientInventoryItem> {
    return this.request(
      this.http.patch<IngredientInventoryItem>(
        this.runtime.apiUrl(`/inventory/items/${itemId}`),
        body,
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  adjustInventoryItem(
    accessToken: string,
    itemId: string,
    body: {
      transaction_type: IngredientMovement['transaction_type'];
      quantity: string;
      direction?: 'ADD' | 'REMOVE';
      reference?: string;
      notes?: string;
    },
  ): Promise<IngredientInventoryItem> {
    return this.post<IngredientInventoryItem>(
      accessToken,
      `/inventory/items/${itemId}/adjustments`,
      body,
    );
  }

  listInventoryMovements(accessToken: string): Promise<IngredientMovement[]> {
    return this.get<IngredientMovement[]>(accessToken, '/inventory/movements');
  }

  updateKotStatus(
    accessToken: string,
    kotId: string,
    status: KotTicket['status'],
  ): Promise<KotTicket> {
    return this.request(
      this.http.patch<KotTicket>(
        this.runtime.apiUrl(`/kot/${kotId}/status`),
        { status },
        { headers: this.authHeaders(accessToken) },
      ),
      2500,
    );
  }

  getDashboard(accessToken: string, fromDate?: string, toDate?: string, tenantId?: string, outletId?: string): Promise<DashboardMetric> {
    const params = new URLSearchParams();
    if (fromDate) params.set('from_date', fromDate);
    if (toDate) params.set('to_date', toDate);
    if (tenantId) params.set('tenant_id', tenantId);
    if (outletId) params.set('outlet_id', outletId);
    const range = params.size ? `?${params.toString()}` : '';
    return this.request(
      this.http.get<DashboardMetric>(this.runtime.apiUrl(`/dashboard${range}`), {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  listSuppliers(accessToken: string): Promise<Supplier[]> {
    return this.get<Supplier[]>(accessToken, '/suppliers');
  }

  createSupplier(accessToken: string, body: { name: string; phone?: string }): Promise<Supplier> {
    return this.post<Supplier>(accessToken, '/suppliers', body);
  }

  listPurchases(accessToken: string): Promise<Purchase[]> {
    return this.get<Purchase[]>(accessToken, '/purchases');
  }

  createPurchase(accessToken: string, body: PurchaseCreate): Promise<Purchase> {
    return this.post<Purchase>(accessToken, '/purchases', body);
  }

  updatePurchase(accessToken: string, purchaseId: string, body: PurchaseCreate): Promise<Purchase> {
    return this.request(
      this.http.patch<Purchase>(
        this.runtime.apiUrl(`/purchases/${purchaseId}`),
        body,
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  listExpenses(accessToken: string): Promise<Expense[]> {
    return this.get<Expense[]>(accessToken, '/expenses');
  }

  createExpense(accessToken: string, body: ExpenseCreate): Promise<Expense> {
    return this.post<Expense>(accessToken, '/expenses', body);
  }

  listCustomers(accessToken: string): Promise<Customer[]> {
    return this.get<Customer[]>(accessToken, '/customers');
  }

  createCustomer(
    accessToken: string,
    body: { name: string; mobile: string | null; email: string | null },
  ): Promise<Customer> {
    return this.post<Customer>(accessToken, '/customers', body);
  }

  listCustomerCreditAccounts(accessToken: string): Promise<CustomerCreditAccount[]> {
    return this.get<CustomerCreditAccount[]>(accessToken, '/customers/credit-accounts');
  }

  listTenantUsers(accessToken: string): Promise<AdminUser[]> {
    return this.get<AdminUser[]>(accessToken, '/platform/users');
  }

  createTenantUser(
    accessToken: string,
    body: { tenant_id: string; outlet_id: string | null; role_code: 'ADMIN' | 'CASHIER'; username: string; display_name: string; email: string | null; phone: string | null; password: string },
  ): Promise<AdminUser> {
    return this.post<AdminUser>(accessToken, '/platform/users', body);
  }

  settleCustomerCredit(
    accessToken: string,
    customerId: string,
    body: { amount?: string; payment_mode: 'CASH' | 'UPI' | 'CARD'; reference?: string; notes?: string },
  ): Promise<CustomerCreditAccount> {
    return this.post<CustomerCreditAccount>(accessToken, `/customers/${customerId}/credit/settle`, body);
  }

  listClosings(accessToken: string): Promise<DailyClosing[]> {
    return this.get<DailyClosing[]>(accessToken, '/closings');
  }

  createClosing(
    accessToken: string,
    businessDate: string,
    countedCash: string,
  ): Promise<DailyClosing> {
    return this.post<DailyClosing>(accessToken, '/closings', {
      business_date: businessDate,
      counted_cash: countedCash,
    });
  }

  listSettings(accessToken: string): Promise<TenantSetting[]> {
    return this.get<TenantSetting[]>(accessToken, '/settings');
  }

  updateSetting(accessToken: string, key: string, value: string): Promise<TenantSetting> {
    return this.request(
      this.http.put<TenantSetting>(
        this.runtime.apiUrl(`/settings/${encodeURIComponent(key)}`),
        { setting_value: value },
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  getPaymentPolicy(accessToken: string): Promise<TenantPaymentPolicy> {
    return this.get<TenantPaymentPolicy>(accessToken, '/payment-policy');
  }

  updatePaymentPolicy(accessToken: string, paymentProcessingMode: TenantPaymentPolicy['payment_processing_mode']): Promise<TenantPaymentPolicy> {
    return this.request(
      this.http.put<TenantPaymentPolicy>(
        this.runtime.apiUrl('/payment-policy'),
        { payment_processing_mode: paymentProcessingMode },
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  getTenantPaymentPolicy(accessToken: string, tenantId: string): Promise<TenantPaymentPolicy> {
    return this.get<TenantPaymentPolicy>(accessToken, `/platform/admin/tenants/${tenantId}/payment-policy`);
  }

  getTenantSubscription(accessToken: string, tenantId: string): Promise<TenantSubscription> {
    return this.get<TenantSubscription>(accessToken, `/platform/admin/tenants/${tenantId}/subscription`);
  }

  updateTenantSubscription(accessToken: string, tenantId: string, endsAt: string, graceEndsAt: string, planCode: 'PROFESSIONAL' | 'ULTRA_PROFESSIONAL'): Promise<TenantSubscription> {
    return this.request(
      this.http.put<TenantSubscription>(
        this.runtime.apiUrl(`/platform/admin/tenants/${tenantId}/subscription`),
        { ends_at: endsAt, grace_ends_at: graceEndsAt, plan_code: planCode },
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  updateTenantPaymentPolicy(accessToken: string, tenantId: string, paymentProcessingMode: TenantPaymentPolicy['payment_processing_mode']): Promise<TenantPaymentPolicy> {
    return this.request(
      this.http.put<TenantPaymentPolicy>(
        this.runtime.apiUrl(`/platform/admin/tenants/${tenantId}/payment-policy`),
        { payment_processing_mode: paymentProcessingMode },
        { headers: this.authHeaders(accessToken) },
      ),
      5000,
    );
  }

  createCategory(
    accessToken: string,
    body: { code: string; name: string; image_path: string | null; display_order: number },
  ): Promise<Category> {
    return this.post<Category>(accessToken, '/categories', body);
  }

  listMessageUsers(accessToken: string): Promise<TenantMessageUser[]> {
    return this.get<TenantMessageUser[]>(accessToken, '/messages/users');
  }

  listMessages(accessToken: string): Promise<TenantMessage[]> {
    return this.get<TenantMessage[]>(accessToken, '/messages');
  }

  listSentMessages(accessToken: string): Promise<TenantMessage[]> {
    return this.get<TenantMessage[]>(accessToken, '/messages/sent');
  }

  sendMessage(accessToken: string, body: { audience: 'DIRECT' | 'GROUP'; recipient_user_id: string | null; subject: string; body: string; reply_to_id?: string | null }): Promise<{ delivered: number }> {
    return this.post<{ delivered: number }>(accessToken, '/messages', body);
  }

  markMessageRead(accessToken: string, messageId: string): Promise<TenantMessage> {
    return this.post<TenantMessage>(accessToken, `/messages/${messageId}/read`, {});
  }

  reactToMessage(accessToken: string, messageId: string, emoji: string): Promise<TenantMessage> {
    return this.post<TenantMessage>(accessToken, `/messages/${messageId}/reactions`, { emoji });
  }

  private get<T>(accessToken: string, path: string): Promise<T> {
    return this.request(
      this.http.get<T>(this.runtime.apiUrl(path), { headers: this.authHeaders(accessToken) }),
      3500,
    );
  }

  private post<T>(accessToken: string, path: string, body: unknown): Promise<T> {
    return this.request(
      this.http.post<T>(this.runtime.apiUrl(path), body, {
        headers: this.authHeaders(accessToken),
      }),
      5000,
    );
  }

  private authHeaders(accessToken: string): HttpHeaders {
    const outletId = this.outletContext.selectedOutletId();
    return new HttpHeaders({
      Authorization: `Bearer ${accessToken}`,
      ...(outletId ? { 'X-BrewBill-Outlet': outletId } : {}),
    });
  }

  private request<T>(request: Observable<T>, timeoutMs: number): Promise<T> {
    return firstValueFrom(request.pipe(
      timeout({ first: timeoutMs }),
      catchError((error: unknown) => {
        if (error instanceof HttpErrorResponse) {
          const detail = typeof error.error?.detail === 'string' ? error.error.detail : null;
          if (detail) return throwError(() => new Error(detail));
          if (error.status === 0) {
            return throwError(() => new Error(
              'Unable to connect to the BrewBill backend. Confirm the backend service is running, then retry.',
            ));
          }
          return throwError(() => new Error(`Request failed (${error.status}). Please retry.`));
        }
        return throwError(() => error);
      }),
    ));
  }
}
