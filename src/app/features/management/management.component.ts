import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute } from '@angular/router';
import { RouterLink } from '@angular/router';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import {
  Category,
  Customer,
  DailyClosing,
  Expense,
  Product,
  Purchase,
  Supplier,
  TenantSetting,
} from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';

const pageDetails: Record<string, { title: string; detail: string; icon: string }> = {
  purchases: {
    title: 'Purchase Management',
    detail: 'Manage purchases, suppliers and stock procurement',
    icon: 'shopping_bag',
  },
  expenses: {
    title: 'Expense Management',
    detail: 'Record and review outlet expenses from PostgreSQL',
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
  imports: [FormsModule, RouterLink],
  templateUrl: './management.component.html',
})
export class ManagementComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(BrewBillApiService);
  private readonly session = inject(SessionService);

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
  readonly closings = signal<DailyClosing[]>([]);
  readonly settings = signal<TenantSetting[]>([]);
  readonly categories = signal<Category[]>([]);
  readonly search = signal('');
  readonly visibleLimit = signal(10);
  readonly visiblePurchases = computed(() => this.filtered(this.purchases()));
  readonly visibleExpenses = computed(() => this.filtered(this.expenses()));
  readonly visibleCustomers = computed(() => this.filtered(this.customers()));
  readonly visibleClosings = computed(() => this.filtered(this.closings()));
  readonly visibleSettings = computed(() => this.filtered(this.settings()));
  readonly visibleCategories = computed(() => this.filtered(this.categories()));

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

  constructor() {
    this.route.paramMap.subscribe((params) => {
      this.key.set(params.get('module') ?? 'purchases');
      this.search.set('');
      this.visibleLimit.set(10);
      void this.load();
    });
  }

  setSearch(value: string): void {
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
        case 'customers':
          this.customers.set(await this.api.listCustomers(token));
          break;
        case 'closing':
          this.closings.set(await this.api.listClosings(token));
          break;
        case 'settings':
          this.settings.set(await this.api.listSettings(token));
          await this.loadPaymentTerminalSettings();
          break;
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

  async loadPaymentTerminalSettings(): Promise<void> {
    if (!window.brewBill) return;
    this.terminalProvider = (await window.brewBill.settings.get('payment.terminal.provider')) ?? '';
    this.terminalEndpoint = (await window.brewBill.settings.get('payment.terminal.endpoint')) ?? '';
    const status = await window.brewBill.payment.status();
    this.terminalMessage.set(status.message);
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
      this.terminalMessage.set(status.message);
    } catch (error) {
      this.terminalMessage.set(
        error instanceof Error ? error.message : 'Unable to save terminal settings.',
      );
    }
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
        notes: null,
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
    if (!this.categoryCode.trim() || !this.categoryName.trim()) return;
    await this.save('Category added.', async (token) => {
      await this.api.createCategory(token, {
        code: this.categoryCode.trim().toUpperCase(),
        name: this.categoryName.trim(),
        image_path: this.categoryImage.trim() || null,
        display_order: this.categories().length + 1,
      });
      this.categoryCode = this.categoryName = this.categoryImage = '';
      this.categories.set(await this.api.listCategories(token));
    });
  }

  money(value: string | number): string {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(
      Number(value),
    );
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
