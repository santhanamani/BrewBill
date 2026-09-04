import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, firstValueFrom, timeout } from 'rxjs';
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
  Purchase,
  PurchaseCreate,
  Supplier,
  TenantAdmin,
  AdminOutlet,
  AdminRole,
  AdminUser,
  TenantPreview,
  TenantSetting,
  MfaChallenge,
} from './models/api.models';
import { RuntimeConfigService } from './runtime-config.service';

@Injectable({ providedIn: 'root' })
export class BrewBillApiService {
  private readonly http = inject(HttpClient);
  private readonly runtime = inject(RuntimeConfigService);

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

  listGlobalProducts(accessToken: string): Promise<GlobalProduct[]> {
    return this.get<GlobalProduct[]>(accessToken, '/products/master');
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

  updateOutletProduct(
    accessToken: string,
    mappingId: string,
    body: Partial<OutletProductMapping>,
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
      code: string; name: string; outlet_code: string; outlet_name: string;
      outlet_address: string | null; admin_username: string; admin_password: string;
      admin_display_name: string; plan_code: string;
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

  createAdminOutlet(accessToken: string, body: {tenant_id:string;code:string;name:string;address:string|null}): Promise<AdminOutlet> {
    return this.post<AdminOutlet>(accessToken, '/platform/admin/outlets', body);
  }

  updateAdminOutlet(accessToken:string, outletId:string, body:Partial<Pick<AdminOutlet,'name'|'address'>>):Promise<AdminOutlet>{
    return this.request(this.http.patch<AdminOutlet>(this.runtime.apiUrl(`/platform/admin/outlets/${outletId}`),body,{headers:this.authHeaders(accessToken)}),5000);
  }

  listAdminUsers(accessToken:string, tenantId?:string):Promise<AdminUser[]>{
    return this.get<AdminUser[]>(accessToken,`/platform/admin/users${tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''}`);
  }

  createAdminUser(accessToken:string, body:{tenant_id:string;outlet_id:string|null;role_code:AdminUser['role_code'];username:string;display_name:string;email:string|null;phone:string|null;password:string}):Promise<AdminUser>{
    return this.post<AdminUser>(accessToken,'/platform/admin/users',body);
  }

  updateAdminUser(accessToken:string,userId:string,body:Partial<{outlet_id:string|null;role_code:AdminUser['role_code'];display_name:string;email:string|null;phone:string|null;password:string;is_active:boolean}>):Promise<AdminUser>{
    return this.request(this.http.patch<AdminUser>(this.runtime.apiUrl(`/platform/admin/users/${userId}`),body,{headers:this.authHeaders(accessToken)}),5000);
  }

  listAdminRoles(accessToken:string):Promise<AdminRole[]>{ return this.get<AdminRole[]>(accessToken,'/platform/admin/roles'); }

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

  listProducts(accessToken: string): Promise<Product[]> {
    return this.request(
      this.http.get<Product[]>(this.runtime.apiUrl('/products'), {
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

  activateDevice(
    accessToken: string,
    body: { installation_id: string; terminal_code: string; terminal_name: string },
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

  listOrders(accessToken: string): Promise<OrderListItem[]> {
    return this.request(
      this.http.get<OrderListItem[]>(this.runtime.apiUrl('/orders'), {
        headers: this.authHeaders(accessToken),
      }),
      2500,
    );
  }

  voidOrder(accessToken: string, orderId: string, reason: string): Promise<OrderResult> {
    return this.post<OrderResult>(accessToken, `/orders/${orderId}/void`, { reason });
  }

  listKots(accessToken: string): Promise<KotTicket[]> {
    return this.request(
      this.http.get<KotTicket[]>(this.runtime.apiUrl('/kot'), {
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

  getDashboard(accessToken: string): Promise<DashboardMetric> {
    return this.request(
      this.http.get<DashboardMetric>(this.runtime.apiUrl('/dashboard'), {
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

  createCategory(
    accessToken: string,
    body: { code: string; name: string; image_path: string | null; display_order: number },
  ): Promise<Category> {
    return this.post<Category>(accessToken, '/categories', body);
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
    return new HttpHeaders({ Authorization: `Bearer ${accessToken}` });
  }

  private request<T>(request: Observable<T>, timeoutMs: number): Promise<T> {
    return firstValueFrom(request.pipe(timeout({ first: timeoutMs })));
  }
}
