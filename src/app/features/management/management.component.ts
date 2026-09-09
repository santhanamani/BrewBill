import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { RouterLink } from '@angular/router';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import {
  Category,
  AdminUser,
  Customer,
  CustomerCreditAccount,
  DailyClosing,
  Expense,
  Product,
  Purchase,
  Supplier,
  TenantSetting,
  TenantPaymentPolicy,
  CurrencyDefinition,
} from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';
import { CurrencyService } from '../../core/currency.service';

const pageDetails: Record<string, { title: string; detail: string; icon: string }> = {
  purchases: {
    title: 'Purchase Management',
    detail: 'Manage purchases, suppliers and stock procurement',
    icon: 'shopping_bag',
  },
  expenses: {
    title: 'Expenses',
    detail: 'Manage and track all outlet expenses',
    icon: 'account_balance_wallet',
  },
  customers: {
    title: 'Customer Management',
    detail: 'Live tenant customer and loyalty directory',
    icon: 'groups',
  },
  closing: {
    title: 'Daily Closing',
    detail: 'Reconcile sales, expenses and counted cash',
    icon: 'task_alt',
  },
  settings: {
    title: 'Outlet Settings',
    detail: 'Tenant-controlled business configuration',
    icon: 'settings',
  },
  categories: {
    title: 'Category Management',
    detail: 'Create and organize the live menu catalogue',
    icon: 'category',
  },
};

@Component({
  selector: 'app-management',
  host: { '[attr.data-view]': 'key()' },
  imports: [FormsModule, RouterLink],
  templateUrl: './management.component.html',
  styleUrls: ['./expenses.component.css', './purchases.component.css', './settings.component.css'],
})
export class ManagementComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(BrewBillApiService);
  readonly session = inject(SessionService);
  readonly currency = inject(CurrencyService);

  readonly key = signal('purchases');
  readonly page = computed(() => pageDetails[this.key()] ?? pageDetails['purchases']);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly success = signal('');
  readonly suppliers = signal<Supplier[]>([]);
  readonly products = signal<Product[]>([]);
  readonly purchases = signal<Purchase[]>([]);
  readonly expenses = signal<Expense[]>([]);
  readonly customers = signal<Customer[]>([]);
  readonly creditAccounts = signal<CustomerCreditAccount[]>([]);
  readonly settlingCustomerId = signal('');
  readonly creditCollectionCustomer = signal<Customer | null>(null);
  creditCollectionAmount = '';
  creditSettlementMode: 'CASH' | 'UPI' | 'CARD' = 'CASH';
  readonly closings = signal<DailyClosing[]>([]);
  readonly settings = signal<TenantSetting[]>([]);
  readonly currencies = signal<CurrencyDefinition[]>([]);
  readonly categories = signal<Category[]>([]);
  readonly tenantUsers = signal<AdminUser[]>([]);
  readonly ultraEnabled = computed(() => this.session.context()?.plan_code === 'ULTRA_PROFESSIONAL');
  readonly search = signal('');
  readonly visibleLimit = signal(10);
  readonly purchaseFilter = signal('');
  readonly visiblePurchases = computed(() => this.filtered(this.purchases().filter(row => !this.purchaseFilter() || row.payment_status === this.purchaseFilter())));
  readonly expenseCategoryFilter = signal('');
  readonly expenseDateFilter = signal('');
  readonly expensePage = signal(0);
  readonly expensePageSize = 8;
  readonly expenseFilterCategories = computed(() => [...new Set(this.expenses().map(row => row.category))].sort());
  readonly filteredExpenses = computed(() => {
    const query=this.search().trim().toLowerCase();
    return this.expenses().filter(row =>
      (!query || JSON.stringify(row).toLowerCase().includes(query)) &&
      (!this.expenseCategoryFilter() || row.category===this.expenseCategoryFilter()) &&
      (!this.expenseDateFilter() || row.expense_date.slice(0,10)===this.localDate()));
  });
  readonly expensePages = computed(() => Math.max(1,Math.ceil(this.filteredExpenses().length/this.expensePageSize)));
  readonly currentExpensePage = computed(() => Math.min(this.expensePage(),this.expensePages()-1));
  readonly visibleExpenses = computed(() => this.filteredExpenses().slice(this.currentExpensePage()*this.expensePageSize,(this.currentExpensePage()+1)*this.expensePageSize));
  filterExpenses(field:'category'|'date',value:string):void {
    (field==='category'?this.expenseCategoryFilter:this.expenseDateFilter).set(value);
    this.expensePage.set(0);
  }
  pageExpenses(delta:number):void { this.expensePage.set(Math.max(0,Math.min(this.currentExpensePage()+delta,this.expensePages()-1))); }
  readonly visibleCustomers = computed(() => this.filtered(this.customers()));
  readonly visibleClosings = computed(() => this.filtered(this.closings()));
  readonly visibleSettings = computed(() => this.filtered(this.settings()));
  readonly visibleCategories = computed(() => this.filtered(this.categories()));
  readonly nextCategoryDisplayOrder = computed(() =>
    this.categories().reduce((highest, row) => Math.max(highest, row.display_order), -1) + 1,
  );
  readonly categoryFormError = signal('');

  readonly purchaseTotal = computed(() =>
    this.purchases().reduce((sum, row) => sum + Number(row.total), 0),
  );
  readonly pendingTotal = computed(() =>
    this.purchases()
      .filter((row) => row.payment_status !== 'PAID')
      .reduce((sum, row) => sum + Number(row.total), 0),
  );
  readonly expenseTotal = computed(() =>
    this.expenses().reduce((sum, row) => sum + Number(row.amount), 0),
  );
  readonly todayExpense = computed(() => {
    const today = this.localDate();
    return this.expenses()
      .filter((row) => row.expense_date.slice(0, 10) === today)
      .reduce((sum, row) => sum + Number(row.amount), 0);
  });
  readonly cashExpense = computed(() =>
    this.expenses()
      .filter((row) => row.payment_mode === 'CASH')
      .reduce((sum, row) => sum + Number(row.amount), 0),
  );

  clearPurchase(): void {
    this.purchaseInvoice=''; this.purchaseDate=this.localDate(); this.purchaseQuantity='1';
    this.purchaseCost='0.00'; this.purchaseTax='5.00'; this.purchaseStatus='PENDING'; this.purchaseNotes='';
  }
  resetExpense(): void {
    this.expenseDate = this.localDate();
    this.expenseCategory = 'Supplies';
    this.expenseDescription = '';
    this.expenseAmount = '';
    this.expenseMode = 'CASH';
    this.expenseRemarks = '';
  }
  purchaseNotes = '';
  purchaseSupplier = '';
  supplierName = '';
  purchaseInvoice = '';
  purchaseDate = this.localDate();
  purchaseProduct = '';
  purchaseQuantity = '1';
  purchaseCost = '0.00';
  purchaseTax = '5.00';
  purchaseStatus: Purchase['payment_status'] = 'PENDING';

  expenseDate = this.localDate();
  expenseCategory = 'Supplies';
  expenseDescription = '';
  expenseAmount = '';
  expenseMode: Expense['payment_mode'] = 'CASH';
  expenseRemarks = '';

  customerName = '';
  customerMobile = '';
  customerEmail = '';
  closingDate = this.localDate();
  countedCash = '';
  settingKey = 'receipt_footer';
  settingValue = '';
  categoryCode = '';
  categoryName = '';
  categoryImage = '';
  terminalProvider = '';
  terminalEndpoint = '';
  terminalApiKey = '';
  readonly terminalMessage = signal('');
  readonly terminalConnected = signal(false);
  readonly posDeviceReady = signal(false);
  readonly posDeviceRefreshing = signal(false);
  readonly posDeviceMessage = signal('');
  readonly licenseResetDialog = signal(false);
  readonly licenseResetError = signal('');
  licenseResetConfirmation = '';
  readonly licenseSigningKeyChanged = computed(() =>
    this.posDeviceMessage().toLowerCase().includes('license signing key changed'),
  );
  readonly posDeviceIdentity = signal<{ installationId: string; terminalCode: string } | null>(null);
  readonly posDeviceLicense = signal<{
    state: string;
    canCreateBills: boolean;
    offlineValidUntil: string | null;
    message: string;
  } | null>(null);
  readonly posDeviceIdLabel = computed(() => {
    const id = this.posDeviceIdentity()?.installationId;
    return id ? `•••• ${id.slice(-8)}` : 'Unavailable';
  });
  paymentProcessingMode: TenantPaymentPolicy['payment_processing_mode'] = 'MANUAL_ALLOWED';
  readonly paymentPolicyMessage = signal('');
  currencyCode = 'INR';
  readonly currencyMessage = signal('');
  swiggyMerchantId = '';
  zomatoMerchantId = '';
  swiggyMarketplaceEnabled = true;
  zomatoMarketplaceEnabled = true;
  dailyReportPhone = '';
  dailyReportTime = '22:00';
  newUserName = '';
  newUsername = '';
  newUserPassword = '';
  newUserRole: 'ADMIN' | 'CASHIER' = 'CASHIER';

  constructor() {
    this.route.paramMap.subscribe((params) => {
      this.key.set(params.get('module') ?? 'purchases');
      this.search.set('');
      this.visibleLimit.set(10);
      void this.load();
    });
  }

  setSearch(value: string): void {
    if(this.key()==='expenses')this.expensePage.set(0);
    this.search.set(value);
    this.visibleLimit.set(10);
  }

  onTableScroll(event: Event): void {
    const element = event.currentTarget as HTMLElement;
    if (element.scrollHeight - element.scrollTop - element.clientHeight <= 48) {
      this.visibleLimit.update((value) => value + 10);
    }
  }

  private filtered<T>(rows: T[]): T[] {
    const query = this.search().trim().toLowerCase();
    const filtered = query
      ? rows.filter((row) => JSON.stringify(row).toLowerCase().includes(query))
      : rows;
    return filtered.slice(0, this.visibleLimit());
  }

  async load(): Promise<void> {
    const token = this.requireCloudToken();
    if (!token) return;
    this.loading.set(true);
    this.error.set('');
    try {
      switch (this.key()) {
        case 'purchases': {
          const [suppliers, products, purchases] = await Promise.all([
            this.api.listSuppliers(token),
            this.api.listProducts(token),
            this.api.listPurchases(token),
          ]);
          this.suppliers.set(suppliers);
          this.products.set(products);
          this.purchases.set(purchases);
          this.purchaseSupplier ||= suppliers[0]?.id ?? '';
          this.purchaseProduct ||= products[0]?.id ?? '';
          break;
        }
        case 'expenses':
          this.expenses.set(await this.api.listExpenses(token));
          break;
        case 'customers': {
          const [customers, creditAccounts] = await Promise.all([
            this.api.listCustomers(token),
            this.api.listCustomerCreditAccounts(token),
          ]);
          this.customers.set(customers);
          this.creditAccounts.set(creditAccounts);
          break;
        }
        case 'closing':
          this.closings.set(await this.api.listClosings(token));
          break;
        case 'settings': {
          const [settings, policy, currencies] = await Promise.all([
            this.api.listSettings(token),
            this.api.getPaymentPolicy(token),
            this.api.listCurrencies(token),
          ]);
          this.settings.set(settings);
          this.swiggyMerchantId = this.setting('swiggy_merchant_id');
          this.zomatoMerchantId = this.setting('zomato_merchant_id') || this.setting('zepto_merchant_id');
          this.swiggyMarketplaceEnabled = this.setting('swiggy_enabled') !== 'false';
          this.zomatoMarketplaceEnabled = this.setting('zomato_enabled') !== 'false';
          this.dailyReportPhone = this.setting('daily_report_phone');
          this.dailyReportTime = this.setting('daily_report_time') || '22:00';
          if (this.ultraEnabled()) this.tenantUsers.set(await this.api.listTenantUsers(token));
          this.paymentProcessingMode = policy.payment_processing_mode;
          this.currencies.set(currencies);
          this.currencyCode = this.currency.code();
          await this.loadPaymentTerminalSettings();
          break;
        }
        case 'categories':
          this.categories.set(await this.api.listCategories(token));
          break;
      }
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.loading.set(false);
    }
  }

  setting(key: string): string {
    return this.settings().find(row => row.setting_key === key)?.setting_value ?? '';
  }

  async saveUltraSettings(): Promise<void> {
    if (!this.ultraEnabled()) {
      this.error.set('Marketplace integrations and scheduled reports require Ultra Professional.');
      return;
    }
    await this.save('Ultra Professional settings saved.', async token => {
      await Promise.all([
        this.api.updateSetting(token, 'swiggy_merchant_id', this.swiggyMerchantId.trim()),
        this.api.updateSetting(token, 'zomato_merchant_id', this.zomatoMerchantId.trim()),
        this.api.updateSetting(token, 'swiggy_enabled', String(this.swiggyMarketplaceEnabled)),
        this.api.updateSetting(token, 'zomato_enabled', String(this.zomatoMarketplaceEnabled)),
        this.api.updateSetting(token, 'daily_report_phone', this.dailyReportPhone.trim()),
        this.api.updateSetting(token, 'daily_report_time', this.dailyReportTime),
      ]);
      this.settings.set(await this.api.listSettings(token));
    });
  }

  async addTenantUser(): Promise<void> {
    const context = this.session.context();
    if (!context || !this.newUserName.trim() || !this.newUsername.trim() || this.newUserPassword.length < 8) {
      this.error.set('Name, username and a password of at least 8 characters are required.');
      return;
    }
    await this.save('Tenant user added.', async token => {
      await this.api.createTenantUser(token, {
        tenant_id: context.tenant_id,
        outlet_id: context.outlet_id,
        role_code: this.newUserRole,
        username: this.newUsername.trim(),
        display_name: this.newUserName.trim(),
        email: null,
        phone: null,
        password: this.newUserPassword,
      });
      this.tenantUsers.set(await this.api.listTenantUsers(token));
      this.newUserName = this.newUsername = this.newUserPassword = '';
    });
  }

  creditAccount(customerId: string): CustomerCreditAccount | undefined {
    return this.creditAccounts().find(account => account.customer.id === customerId);
  }

  creditCollectionRemaining(customerId: string): number {
    const outstanding = Number(this.creditAccount(customerId)?.outstanding_balance || 0);
    return Math.max(0, outstanding - Math.max(0, Number(this.creditCollectionAmount) || 0));
  }

  openCreditCollection(customer: Customer): void {
    const account = this.creditAccount(customer.id);
    if (!account || Number(account.outstanding_balance) <= 0) return;
    this.creditCollectionCustomer.set(customer);
    this.creditCollectionAmount = Number(account.outstanding_balance).toFixed(2);
    this.creditSettlementMode = 'CASH';
    this.error.set('');
  }

  closeCreditCollection(): void {
    if (this.settlingCustomerId()) return;
    this.creditCollectionCustomer.set(null);
    this.creditCollectionAmount = '';
  }

  async settleCredit(): Promise<void> {
    const customer = this.creditCollectionCustomer();
    const token = this.requireCloudToken();
    const account = customer ? this.creditAccount(customer.id) : undefined;
    const amount = Number(this.creditCollectionAmount);
    const outstanding = Number(account?.outstanding_balance || 0);
    if (!customer || !token || !account || this.settlingCustomerId()) return;
    if (!Number.isFinite(amount) || amount <= 0 || amount > outstanding) {
      this.error.set('Collection amount must be greater than zero and cannot exceed the outstanding credit.');
      return;
    }
    this.settlingCustomerId.set(customer.id);
    this.error.set('');
    this.success.set('');
    try {
      const saved = await this.api.settleCustomerCredit(token, customer.id, {
        amount: amount.toFixed(2),
        payment_mode: this.creditSettlementMode,
        notes: amount === outstanding
          ? 'Full outstanding collected from Customer Management'
          : 'Partial outstanding collected from Customer Management',
      });
      this.creditAccounts.update(accounts => accounts.map(row => row.customer.id === customer.id ? saved : row));
      this.success.set(
        amount === outstanding
          ? customer.name + "'s full outstanding amount was collected."
          : this.money(amount) + ' collected from ' + customer.name + '. Remaining credit: ' + this.money(Number(saved.outstanding_balance)) + '.',
      );
      this.creditCollectionCustomer.set(null);
      this.creditCollectionAmount = '';
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.settlingCustomerId.set('');
    }
  }

  async loadPaymentTerminalSettings(): Promise<void> {
    if (!window.brewBill) {
      this.posDeviceMessage.set('Device registration is available in the BrewBill desktop app.');
      this.terminalMessage.set('Payment terminal setup is available in the desktop app.');
      return;
    }
    try {
      const [provider, endpoint, identity, terminalStatus] = await Promise.all([
        window.brewBill.settings.get('payment.terminal.provider'),
        window.brewBill.settings.get('payment.terminal.endpoint'),
        window.brewBill.license.identity(),
        window.brewBill.payment.status(),
      ]);
      this.terminalProvider = provider ?? '';
      this.terminalEndpoint = endpoint ?? '';
      this.posDeviceIdentity.set(identity);
      this.terminalConnected.set(terminalStatus.connected);
      this.terminalMessage.set(terminalStatus.message);
      await this.refreshPosDevice(false);
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unable to load device settings.';
      this.posDeviceMessage.set(message);
      this.terminalMessage.set(message);
    }
  }

  async refreshPosDevice(announce = true): Promise<void> {
    if (!window.brewBill) {
      this.posDeviceReady.set(false);
      this.posDeviceMessage.set('Open Settings in the BrewBill desktop app to activate this device.');
      return;
    }
    if (!this.session.context()?.outlet_id) {
      this.posDeviceReady.set(false);
      this.posDeviceMessage.set('An outlet must be assigned before this device can be activated.');
      return;
    }
    this.posDeviceRefreshing.set(true);
    try {
      const activated = await this.session.ensureDesktopLicense();
      const [identity, license] = await Promise.all([
        window.brewBill.license.identity(),
        window.brewBill.license.status(),
      ]);
      this.posDeviceIdentity.set(identity);
      this.posDeviceLicense.set(license);
      const ready = activated && license.canCreateBills;
      this.posDeviceReady.set(ready);
      this.posDeviceMessage.set(
        ready
          ? `Registered for ${this.session.context()?.tenant_name ?? 'this tenant'} / ${this.session.context()?.outlet_name ?? 'this outlet'}.`
          : this.session.licenseMessage() || license.message,
      );
      if (announce) {
        (ready ? this.success : this.error).set(
          ready ? 'This POS device is active and ready for billing.' : this.posDeviceMessage(),
        );
      }
    } catch (error) {
      this.posDeviceReady.set(false);
      this.posDeviceMessage.set(
        error instanceof Error ? error.message : 'Unable to activate this POS device.',
      );
      if (announce) this.error.set(this.posDeviceMessage());
    } finally {
      this.posDeviceRefreshing.set(false);
    }
  }

  openLicenseSigningKeyReset(): void {
    if (!this.session.isAdmin() || !window.brewBill) return;
    this.licenseResetConfirmation = '';
    this.licenseResetError.set('');
    this.licenseResetDialog.set(true);
  }

  closeLicenseSigningKeyReset(): void {
    if (this.posDeviceRefreshing()) return;
    this.licenseResetDialog.set(false);
    this.licenseResetConfirmation = '';
    this.licenseResetError.set('');
  }

  async resetLicenseSigningKeyTrust(): Promise<void> {
    if (!this.session.isAdmin() || !window.brewBill) return;
    if (this.licenseResetConfirmation.trim() !== 'RESET LICENSE TRUST') {
      this.licenseResetError.set('Type RESET LICENSE TRUST exactly to continue.');
      return;
    }
    this.posDeviceRefreshing.set(true);
    this.error.set('');
    this.licenseResetError.set('');
    try {
      await window.brewBill.license.resetTrust('RESET LICENSE TRUST');
      this.licenseResetDialog.set(false);
      this.licenseResetConfirmation = '';
      this.posDeviceMessage.set('Old signing-key trust cleared. Reactivating this device…');
      await this.refreshPosDevice();
    } catch (error) {
      this.posDeviceMessage.set(error instanceof Error ? error.message : 'Unable to reset license trust.');
      this.licenseResetError.set(this.posDeviceMessage());
    } finally {
      this.posDeviceRefreshing.set(false);
    }
  }

  posDeviceValidityLabel(): string {
    const value = this.posDeviceLicense()?.offlineValidUntil;
    if (!value) return 'Online verification required';
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? 'Online verification required'
      : new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  async savePaymentTerminal(): Promise<void> {
    if (!window.brewBill) {
      this.terminalMessage.set('Payment terminal setup is available in the desktop app.');
      return;
    }
    try {
      await window.brewBill.settings.set('payment.terminal.provider', this.terminalProvider.trim());
      await window.brewBill.settings.set('payment.terminal.endpoint', this.terminalEndpoint.trim());
      if (this.terminalApiKey.trim()) {
        await window.brewBill.secure.store('payment.terminal.api-key', this.terminalApiKey.trim());
        this.terminalApiKey = '';
      }
      const status = await window.brewBill.payment.status();
      this.terminalConnected.set(status.connected);
      this.terminalMessage.set(status.message);
    } catch (error) {
      this.terminalMessage.set(
        error instanceof Error ? error.message : 'Unable to save terminal settings.',
      );
    }
  }

  async savePaymentPolicy(): Promise<void> {
    this.paymentPolicyMessage.set('');
    await this.save('Payment collection setting saved for this tenant.', async (token) => {
      const saved = await this.api.updatePaymentPolicy(token, this.paymentProcessingMode);
      this.paymentProcessingMode = saved.payment_processing_mode;
      this.settings.set(await this.api.listSettings(token));
      this.paymentPolicyMessage.set(
        saved.payment_processing_mode === 'TERMINAL_REQUIRED'
          ? 'Cash/manual fallback is blocked. Only terminal-approved UPI or Card payments can complete a bill.'
          : 'Cash can be recorded directly. UPI/Card may fall back to manual recording when the terminal is unavailable.',
      );
    });
  }

  async saveCurrency(): Promise<void> {
    const selected = this.currencies().find((row) => row.code === this.currencyCode);
    if (!selected) {
      this.currencyMessage.set('Choose a valid currency from the master list.');
      return;
    }
    this.currencyMessage.set('');
    await this.save(`Currency changed to ${selected.code} for this tenant.`, async (token) => {
      const saved = await this.api.updateCurrency(token, selected.code);
      this.currency.configure(saved);
      this.session.context.update((context) => context ? { ...context, currency: saved } : context);
      this.currencyCode = saved.code;
      this.currencyMessage.set(
        `${saved.name} (${saved.code}) is now used for all amount displays and receipts.`,
      );
    });
  }

  currencyPreview(): string {
    const selected = this.currencies().find((row) => row.code === this.currencyCode);
    if (!selected) return this.currency.format(1234.5);
    return new Intl.NumberFormat(selected.locale, {
      style: 'currency',
      currency: selected.code,
      minimumFractionDigits: selected.decimal_places,
      maximumFractionDigits: selected.decimal_places,
    }).format(1234.5);
  }

  async addSupplier(): Promise<void> {
    if (!this.supplierName.trim()) {
      this.error.set('Enter the supplier name.');
      return;
    }
    await this.save('Supplier added.', async (token) => {
      const created = await this.api.createSupplier(token, { name: this.supplierName.trim() });
      this.suppliers.set(await this.api.listSuppliers(token));
      this.purchaseSupplier = created.id;
      this.supplierName = '';
    });
  }

  async addPurchase(): Promise<void> {
    if (!this.purchaseSupplier || !this.purchaseProduct || !this.purchaseInvoice.trim()) {
      this.error.set('Supplier, invoice number and product are required.');
      return;
    }
    await this.save('Purchase saved and stock updated.', async (token) => {
      await this.api.createPurchase(token, {
        supplier_id: this.purchaseSupplier,
        invoice_number: this.purchaseInvoice.trim(),
        purchase_date: new Date(`${this.purchaseDate}T12:00:00+05:30`).toISOString(),
        payment_status: this.purchaseStatus,
        notes: this.purchaseNotes.trim() || null,
        items: [
          {
            product_id: this.purchaseProduct,
            quantity: this.purchaseQuantity,
            unit_cost: this.purchaseCost,
            tax_percent: this.purchaseTax,
          },
        ],
      });
      this.purchaseInvoice = '';
      this.purchases.set(await this.api.listPurchases(token));
      this.products.set(await this.api.listProducts(token));
    });
  }

  async addExpense(): Promise<void> {
    if (!this.expenseDescription.trim() || Number(this.expenseAmount) <= 0) {
      this.error.set('Description and a valid amount are required.');
      return;
    }
    await this.save('Expense saved.', async (token) => {
      await this.api.createExpense(token, {
        expense_date: new Date(`${this.expenseDate}T12:00:00+05:30`).toISOString(),
        category: this.expenseCategory,
        description: this.expenseDescription.trim(),
        amount: this.expenseAmount,
        payment_mode: this.expenseMode,
        remarks: this.expenseRemarks.trim() || null,
      });
      this.expenseDescription = '';
      this.expenseAmount = '';
      this.expenseRemarks = '';
      this.expenses.set(await this.api.listExpenses(token));
    });
  }

  async addCustomer(): Promise<void> {
    if (!this.customerName.trim()) return;
    await this.save('Customer added.', async (token) => {
      await this.api.createCustomer(token, {
        name: this.customerName.trim(),
        mobile: this.customerMobile.trim() || null,
        email: this.customerEmail.trim() || null,
      });
      this.customerName = this.customerMobile = this.customerEmail = '';
      this.customers.set(await this.api.listCustomers(token));
    });
  }

  async closeDay(): Promise<void> {
    if (Number(this.countedCash) < 0 || this.countedCash === '') return;
    await this.save('Business day closed.', async (token) => {
      await this.api.createClosing(token, this.closingDate, this.countedCash);
      this.closings.set(await this.api.listClosings(token));
    });
  }

  async saveSetting(): Promise<void> {
    if (!this.settingKey.trim()) return;
    await this.save('Setting saved.', async (token) => {
      await this.api.updateSetting(token, this.settingKey.trim(), this.settingValue);
      this.settings.set(await this.api.listSettings(token));
    });
  }

  async addCategory(): Promise<void> {
    const code = this.categoryCode.trim().toUpperCase();
    const name = this.categoryName.trim();
    this.categoryFormError.set('');
    if (!code || !name) {
      this.categoryFormError.set('Category code and name are required.');
      return;
    }
    if (!/^[A-Z0-9_-]+$/.test(code)) {
      this.categoryFormError.set('Use only letters, numbers, hyphens or underscores in the category code.');
      return;
    }
    if (this.categories().some(row => row.code.toUpperCase() === code)) {
      this.categoryFormError.set('This category code already exists. Choose a different code.');
      return;
    }
    await this.save('Category added to this tenant catalogue.', async (token) => {
      await this.api.createCategory(token, {
        code,
        name,
        image_path: this.categoryImage.trim() || null,
        display_order: this.nextCategoryDisplayOrder(),
      });
      this.categoryCode = this.categoryName = this.categoryImage = '';
      this.categories.set(await this.api.listCategories(token));
    });
  }

  money(value: string | number): string {
    return this.currency.format(value);
  }

  date(value: string): string {
    return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(value));
  }

  private async save(success: string, task: (token: string) => Promise<void>): Promise<void> {
    const token = this.requireCloudToken();
    if (!token) return;
    this.saving.set(true);
    this.error.set('');
    this.success.set('');
    try {
      await task(token);
      this.success.set(success);
    } catch (error) {
      this.error.set(this.message(error));
    } finally {
      this.saving.set(false);
    }
  }

  private requireCloudToken(): string | null {
    const token = this.session.accessToken();
    if (!token) {
      this.error.set('Connect to the BrewBill PostgreSQL server and sign in as Admin.');
      return null;
    }
    return token;
  }

  private message(error: unknown): string {
    if (error instanceof HttpErrorResponse) return error.error?.detail ?? error.message;
    return error instanceof Error ? error.message : 'Unable to complete the request.';
  }

  private localDate(): string {
    return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());
  }
}
