import { Component, DestroyRef, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { HeldCartService } from '../../core/held-cart.service';
import {
  HeldBill,
  IngredientInventoryItem,
  IngredientMovement,
  KotTicket,
  MarketplaceOrder,
  MarketplaceSummary,
  OrderListItem,
  OwnerTenantScope,
} from '../../core/models/api.models';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { SessionService } from '../../core/session.service';
import { ReceiptPaymentMode, ReceiptPrinterService } from '../../core/receipt-printer.service';
import { CurrencyService } from '../../core/currency.service';
import { timedSignal } from '../../core/timed-signal';

const labels: Record<string, { title: string; detail: string; icon: string }> = {
  holds: {
    title: 'Held Orders',
    detail: 'View and manage temporarily held bills for your outlet.',
    icon: 'assignment_late',
  },
  kot: {
    title: 'Kitchen Order Tickets',
    detail: 'Live PostgreSQL kitchen queue for this outlet.',
    icon: 'skillet',
  },
  inventory: {
    title: 'Inventory',
    detail: 'Ingredient stock and audited movements for this outlet.',
    icon: 'inventory_2',
  },
  reports: {
    title: 'Sales Reports',
    detail: 'View sales transactions for the selected tenant branch and outlet.',
    icon: 'bar_chart',
  },
};

@Component({ selector: 'app-operations', host: { '[attr.data-view]': 'key()' }, templateUrl: './operations.component.html', styleUrls: ['./held-orders.component.css', './sales-reports.component.css', './inventory.component.css'] })
export class OperationsComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(BrewBillApiService);
  private readonly runtime = inject(RuntimeConfigService);
  readonly session = inject(SessionService);
  private readonly heldCart = inject(HeldCartService);
  private readonly router = inject(Router);
  private readonly receiptPrinter = inject(ReceiptPrinterService);
  private readonly destroyRef = inject(DestroyRef);
  readonly currency = inject(CurrencyService);

  readonly key = signal('inventory');
  readonly module = computed(() => labels[this.key()] ?? labels['inventory']);
  readonly holds = signal<HeldBill[]>([]);
  readonly holdImages = signal<Record<string, string>>({});
  private imageRequest = 0;

  private async loadHoldImages(token: string): Promise<void> {
    const request = ++this.imageRequest;
    this.holdImages.set({});
    try {
      const products = await this.api.listProducts(token);
      if (request !== this.imageRequest || this.key() !== 'holds') return;
      this.holdImages.set(Object.fromEntries(products.map(product => [product.id, this.asset(product.image_path)])));
    } catch { /* Optional thumbnails must never block held bills. */ }
  }

  holdImage(productId: string): string {
    return this.holdImages()[productId] ?? this.asset(null);
  }

  holdImageError(event: Event): void {
    const image = event.target as HTMLImageElement;
    const fallback = this.asset(null);
    if (image.getAttribute('src') !== fallback) image.setAttribute('src', fallback);
  }
  readonly selectedHoldId = signal<string | null>(null);
  readonly selectedHold = computed(
    () => this.holds().find((row) => row.id === this.selectedHoldId()) ?? this.holds()[0] ?? null,
  );
  readonly holdSearch = signal('');
  readonly holdLimit = signal(10);
  readonly visibleHolds = computed(() => {
    const query = this.holdSearch().trim().toLowerCase();
    const rows = !query
      ? this.holds()
      : this.holds().filter((row) =>
          [
            row.hold_number,
            row.invoice_number,
            row.cashier_name,
            ...row.items.map((item) => item.product_name),
          ].some((value) => value.toLowerCase().includes(query)),
        );
    return rows.slice(0, this.holdLimit());
  });
  readonly kots = signal<KotTicket[]>([]);
  readonly orders = signal<OrderListItem[]>([]);
  readonly marketplaceOrders = signal<MarketplaceOrder[]>([]);
  readonly marketplaceSummary = signal<MarketplaceSummary | null>(null);
  readonly marketplaceEnabled = computed(
    () => !this.session.isOwner() && this.session.context()?.plan_code === 'ULTRA_PROFESSIONAL',
  );
  readonly ownerScopes = signal<OwnerTenantScope[]>([]);
  readonly selectedTenantId = signal('');
  readonly selectedOutletId = signal('');
  readonly selectedOwnerScope = computed(() =>
    this.ownerScopes().find(scope => scope.tenant_id === this.selectedTenantId()) ?? null,
  );
  readonly inventoryItems = signal<IngredientInventoryItem[]>([]);
  readonly movements = signal<IngredientMovement[]>([]);
  readonly inventorySearch = signal('');
  readonly inventoryLimit = signal(10);
  readonly selectedInventoryId = signal<string | null>(null);
  readonly selectedInventory = computed(
    () =>
      this.inventoryItems().find((item) => item.id === this.selectedInventoryId()) ??
      this.inventoryItems()[0] ??
      null,
  );
  readonly visibleInventoryItems = computed(() => {
    const query = this.inventorySearch().trim().toLowerCase();
    const rows = !query
      ? this.inventoryItems()
      : this.inventoryItems().filter((item) =>
          [item.code, item.name, item.category, item.status].some((value) =>
            value.toLowerCase().includes(query),
          ),
        );
    return rows.slice(0, this.inventoryLimit());
  });
  readonly completedOrders = computed(() => this.orders().filter(row => row.status === 'COMPLETED'));
  readonly averageOrderValue = computed(() => this.completedOrders().length ? this.reportTotal() / this.completedOrders().length : 0);
  readonly itemsSold = computed(() => this.completedOrders().reduce((sum,row)=>sum+row.item_count,0));
  readonly todayHolds = computed(() => this.holds().filter(row => new Date(row.held_at).toDateString() === new Date().toDateString()).length);
  readonly adjusting = signal(false);
  readonly reportSearch = signal('');
  readonly reportLimit = signal(10);
  readonly reportStatus = signal('');
  readonly reportPayment = signal('');
  readonly reportFromDate = signal(this.localDateValue(new Date()));
  readonly reportToDate = signal(this.localDateValue(new Date()));
  readonly reportPage = signal(0);
  readonly reportPageSize = signal(10);
  readonly filteredOrders = computed(() => {
    const query=this.reportSearch().trim().toLowerCase();
    return this.orders().filter(order =>
      (!query || [order.invoice_number,order.cashier_name,order.status,...order.payment_modes].some(value=>value.toLowerCase().includes(query))) &&
      (!this.reportStatus() || order.status===this.reportStatus()) &&
      (!this.reportPayment() || order.payment_modes.includes(this.reportPayment())));
  });
  readonly reportPages = computed(()=>Math.max(1,Math.ceil(this.filteredOrders().length/this.reportPageSize())));
  readonly currentReportPage = computed(()=>Math.min(this.reportPage(),this.reportPages()-1));
  readonly visibleOrders = computed(()=>this.filteredOrders().slice(this.currentReportPage()*this.reportPageSize(),(this.currentReportPage()+1)*this.reportPageSize()));
  filterReports(field:'status'|'payment',value:string):void {
    (field==='status'?this.reportStatus:this.reportPayment).set(value);this.reportPage.set(0);
  }
  pageReports(delta:number):void { this.reportPage.set(Math.max(0,Math.min(this.currentReportPage()+delta,this.reportPages()-1))); }
  sizeReports(value:string):void { const size=Number(value);if([10,25,50].includes(size)){this.reportPageSize.set(size);this.reportPage.set(0);} }
  openMarketplace():void { void this.router.navigateByUrl('/marketplace'); }
  readonly inventoryDialog = signal<'ADD' | 'EDIT' | null>(null);
  readonly inventoryForm = signal({
    id: '',
    code: '',
    name: '',
    category: 'Ingredients',
    unit: 'kg',
    opening: '0',
    low: '0',
    imagePath: '',
  });
  readonly adjustmentDialog = signal(false);
  readonly adjustmentType = signal<IngredientMovement['transaction_type']>('STOCK_IN');
  readonly adjustmentQuantity = signal('1');
  readonly adjustmentDirection = signal<'ADD' | 'REMOVE'>('ADD');
  readonly adjustmentReference = signal('');
  readonly adjustmentNotes = signal('');
  readonly kotFilter = signal<'ALL' | KotTicket['status']>('ALL');
  readonly completedKotDate = signal(this.localDateValue(new Date()));
  readonly completedKots = computed(() => this.kots().filter(kot =>
    kot.status === 'SERVED' && this.localDateValue(new Date(kot.created_at)) === this.completedKotDate()));
  readonly filteredKots = computed(() => this.kotFilter() === 'ALL'
    ? this.kots().filter(kot => kot.status !== 'SERVED')
    : this.kotFilter() === 'SERVED'
      ? this.completedKots()
      : this.kots().filter(kot => kot.status === this.kotFilter()));
  readonly openKots = computed(() => this.kots().filter((kot) => kot.status !== 'SERVED').length);
  readonly readyKots = computed(() => this.kots().filter((kot) => kot.status === 'READY').length);
  readonly delayedKots = computed(
    () => this.kots().filter((kot) => kot.status === 'DELAYED').length,
  );
  readonly heldValue = computed(() =>
    this.holds().reduce((sum, hold) => sum + Number(hold.grand_total), 0),
  );
  readonly reportTotal = computed(() =>
    this.completedOrders().reduce((sum, order) => sum + Number(order.grand_total), 0),
  );
  readonly lowStockItems = computed(
    () => this.inventoryItems().filter((item) => item.status === 'LOW_STOCK').length,
  );
  readonly outOfStockItems = computed(
    () => this.inventoryItems().filter((item) => item.status === 'OUT_OF_STOCK').length,
  );
  readonly loading = signal(false);
  readonly error = signal('');
  readonly notice = timedSignal();
  readonly printingOrderId = signal<string | null>(null);

  constructor() {
    this.route.queryParamMap.subscribe((params) => {
      this.reportStatus.set(params.get('status') ?? '');
      this.reportPayment.set(params.get('payment') ?? '');
      this.reportFromDate.set(params.get('from') ?? this.reportFromDate());
      this.reportToDate.set(params.get('to') ?? this.reportToDate());
      this.selectedTenantId.set(params.get('tenant') ?? this.selectedTenantId());
      this.selectedOutletId.set(params.get('outlet') ?? this.selectedOutletId());
      this.reportPage.set(0);
    });
    this.route.paramMap.subscribe((params) => {
      this.key.set(params.get('module') ?? 'inventory');
      void this.load();
    });
    const reportRefresh = window.setInterval(() => {
      if (this.key() === 'reports' && !this.loading()) void this.load(false);
    }, 15000);
    this.destroyRef.onDestroy(() => window.clearInterval(reportRefresh));
  }

  async load(showLoading = true): Promise<void> {
    this.error.set('');
    if (showLoading) this.loading.set(true);
    try {
      const token = this.requireToken();
      if (this.key() === 'holds') {
        void this.loadHoldImages(token);
        const rows = await this.api.listHolds(token);
        this.holds.set(rows);
        if (!rows.some((row) => row.id === this.selectedHoldId()))
          this.selectedHoldId.set(rows[0]?.id ?? null);
      }
      if (this.key() === 'kot') this.kots.set(await this.api.listKots(token, this.completedKotDate()));
      if (this.key() === 'reports') {
        if (this.session.isOwner() && !this.ownerScopes().length) {
          const scopes = await this.api.listOwnerTenants(token);
          this.ownerScopes.set(scopes);
          const requested = this.selectedTenantId();
          const homeTenant = this.session.user()?.tenant_id;
          this.selectedTenantId.set(
            scopes.some(scope => scope.tenant_id === requested) ? requested
              : scopes.some(scope => scope.tenant_id === homeTenant) ? String(homeTenant)
                : (scopes[0]?.tenant_id ?? ''),
          );
          const selectedScope = scopes.find(scope => scope.tenant_id === this.selectedTenantId());
          if (!selectedScope?.outlets.some(outlet => outlet.id === this.selectedOutletId())) {
            this.selectedOutletId.set('');
          }
          this.currency.configure(selectedScope?.currency);
        }
        const [orders, marketplaceOrders, marketplaceSummary] = await Promise.all([
          this.api.listOrders(
            token,
            this.reportFromDate(),
            this.reportToDate(),
            this.session.isOwner() ? this.selectedTenantId() || undefined : undefined,
            this.session.isOwner() ? this.selectedOutletId() || undefined : undefined,
          ),
          this.marketplaceEnabled() ? this.api.listMarketplaceOrders(token) : Promise.resolve([]),
          this.marketplaceEnabled() ? this.api.getMarketplaceSummary(token) : Promise.resolve(null),
        ]);
        this.orders.set(orders);
        this.marketplaceOrders.set(marketplaceOrders);
        this.marketplaceSummary.set(marketplaceSummary);
      }
      if (this.key() === 'inventory') {
        const [items, movements] = await Promise.all([
          this.api.listInventoryItems(token),
          this.api.listInventoryMovements(token),
        ]);
        this.inventoryItems.set(items);
        this.movements.set(movements);
        if (!items.some((item) => item.id === this.selectedInventoryId())) {
          this.selectedInventoryId.set(items[0]?.id ?? null);
        }
      }
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to load PostgreSQL data.');
    } finally {
      if (showLoading) this.loading.set(false);
    }
  }

  applyReportDates(): void {
    if (!this.reportFromDate() || !this.reportToDate() || this.reportFromDate() > this.reportToDate()) {
      this.error.set('Choose a valid From and To date range.');
      return;
    }
    this.reportPage.set(0);
    void this.load();
  }

  clearReportFilters(): void {
    const today = this.localDateValue(new Date());
    this.reportStatus.set('');
    this.reportPayment.set('');
    this.reportFromDate.set(today);
    this.reportToDate.set(today);
    this.reportPage.set(0);
    void this.load();
  }

  changeOwnerTenant(tenantId: string): void {
    if (!tenantId || tenantId === this.selectedTenantId()) return;
    this.selectedTenantId.set(tenantId);
    this.selectedOutletId.set('');
    this.currency.configure(this.ownerScopes().find(scope => scope.tenant_id === tenantId)?.currency);
    this.reportPage.set(0);
    void this.load();
  }

  changeOwnerOutlet(outletId: string): void {
    this.selectedOutletId.set(outletId);
    this.reportPage.set(0);
    void this.load();
  }

  changeCompletedKotDate(value: string): void {
    if (!value) return;
    this.completedKotDate.set(value);
    void this.load();
  }

  private localDateValue(value: Date): string {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit',
    }).formatToParts(value);
    const part = (type: Intl.DateTimeFormatPartTypes) => parts.find(row => row.type === type)?.value ?? '';
    return `${part('year')}-${part('month')}-${part('day')}`;
  }


  selectHold(hold: HeldBill): void {
    this.selectedHoldId.set(hold.id);
  }

  async reopen(hold: HeldBill): Promise<void> {
    try {
      this.heldCart.open(await this.api.reopenHold(this.requireToken(), hold.id));
      await this.router.navigateByUrl('/pos');
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to reopen hold.');
    }
  }

  async deleteHold(hold: HeldBill): Promise<void> {
    if (!window.confirm(`Cancel ${hold.hold_number}? The audit history will be retained.`)) return;
    try {
      await this.api.deleteHold(this.requireToken(), hold.id);
      this.notice.set(`${hold.hold_number} was cancelled.`);
      await this.load();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to cancel hold.');
    }
  }

  addInventoryItem(): void {
    this.inventoryForm.set({
      id: '',
      code: '',
      name: '',
      category: 'Ingredients',
      unit: 'kg',
      opening: '0',
      low: '0',
      imagePath: '',
    });
    this.inventoryDialog.set('ADD');
  }

  editInventory(item: IngredientInventoryItem): void {
    this.selectedInventoryId.set(item.id);
    this.inventoryForm.set({
      id: item.id,
      code: item.code,
      name: item.name,
      category: item.category,
      unit: item.unit,
      opening: item.opening_quantity,
      low: item.low_stock_limit,
      imagePath: item.image_path ?? '',
    });
    this.inventoryDialog.set('EDIT');
  }

  updateInventoryForm(field: string, value: string): void {
    this.inventoryForm.update((form) => ({ ...form, [field]: value }));
  }

  async saveInventoryItem(): Promise<void> {
    const form = this.inventoryForm();
    if (!form.name.trim() || !form.category.trim() || !form.unit.trim()) {
      this.error.set('Name, category and unit are required.');
      return;
    }
    try {
      if (this.inventoryDialog() === 'ADD') {
        const code = (
          form.code.trim() || form.name.trim().replace(/[^A-Za-z0-9]+/g, '_')
        ).toUpperCase();
        await this.api.createInventoryItem(this.requireToken(), {
          code,
          name: form.name.trim(),
          category: form.category.trim(),
          unit: form.unit.trim(),
          image_path: form.imagePath.trim() || null,
          opening_quantity: Number(form.opening || 0).toFixed(3),
          low_stock_limit: Number(form.low || 0).toFixed(3),
        });
        this.notice.set(`${form.name} was added to PostgreSQL inventory.`);
      } else {
        await this.api.updateInventoryItem(this.requireToken(), form.id, {
          name: form.name.trim(),
          category: form.category.trim(),
          unit: form.unit.trim(),
          image_path: form.imagePath.trim() || null,
          low_stock_limit: Number(form.low || 0).toFixed(3),
        });
        this.notice.set(`${form.name} was updated.`);
      }
      this.inventoryDialog.set(null);
      await this.load();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to save inventory item.');
    }
  }

  adjustInventory(
    item: IngredientInventoryItem,
    type: IngredientMovement['transaction_type'],
  ): void {
    this.selectedInventoryId.set(item.id);
    this.adjustmentType.set(type);
    this.adjustmentQuantity.set('1');
    this.adjustmentDirection.set('ADD');
    this.adjustmentReference.set('');
    this.adjustmentNotes.set('');
    this.adjustmentDialog.set(true);
  }

  async saveAdjustment(): Promise<void> {
    if(this.adjusting()) return;
    const item = this.selectedInventory();
    const quantity = Number(this.adjustmentQuantity());
    if (!item || !Number.isFinite(quantity) || quantity <= 0) {
      this.error.set('Select an item and enter a valid quantity.');
      return;
    }
    this.adjusting.set(true);
    try {
      await this.api.adjustInventoryItem(this.requireToken(), item.id, {
        transaction_type: this.adjustmentType(),
        quantity: quantity.toFixed(3),
        direction: this.adjustmentDirection(),
        reference: this.adjustmentReference().trim() || undefined,
        notes: this.adjustmentNotes().trim() || undefined,
      });
      this.notice.set(`${item.name} stock was adjusted.`);
      this.adjustmentDialog.set(false);
      await this.load();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to adjust inventory.');
    } finally { this.adjusting.set(false); }
  }

  setSearch(value: string): void {
    if (this.key() === 'holds') {
      this.holdSearch.set(value);
      this.holdLimit.set(10);
    }
    if (this.key() === 'inventory') {
      this.inventorySearch.set(value);
      this.inventoryLimit.set(10);
    }
    if (this.key() === 'reports') {
      this.reportSearch.set(value);
      this.reportPage.set(0);
      this.reportLimit.set(10);
    }
  }

  onTableScroll(event: Event): void {
    const element = event.currentTarget as HTMLElement;
    if (element.scrollHeight - element.scrollTop - element.clientHeight > 48) return;
    if (this.key() === 'holds') this.holdLimit.update((value) => value + 10);
    if (this.key() === 'inventory') this.inventoryLimit.update((value) => value + 10);
    if (this.key() === 'reports') this.reportLimit.update((value) => value + 10);
  }

  async nextKotStatus(kot: KotTicket): Promise<void> {
    const next: Record<KotTicket['status'], KotTicket['status']> = {
      NEW: 'PREPARING',
      PREPARING: 'READY',
      DELAYED: 'PREPARING',
      READY: 'SERVED',
      SERVED: 'SERVED',
    };
    try {
      await this.api.updateKotStatus(this.requireToken(), kot.id, next[kot.status]);
      await this.load();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to update kitchen ticket.');
    }
  }

  async voidOrder(order: OrderListItem): Promise<void> {
    if (order.status !== 'COMPLETED' || !this.session.isAdmin()) return;
    const reason = window.prompt(`Reason for voiding ${order.invoice_number}:`)?.trim();
    if (!reason || reason.length < 5) return;
    try {
      await this.api.voidOrder(this.requireToken(), order.id, reason);
      await this.load();
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to void invoice.');
    }
  }

  async printOrder(order: OrderListItem): Promise<void> {
    if (this.printingOrderId()) return;
    const modes = order.payment_modes;
    const paymentMode: ReceiptPaymentMode =
      modes.length > 1 ? 'SPLIT' : ((modes[0] as ReceiptPaymentMode | undefined) ?? 'CASH');
    this.printingOrderId.set(order.id);
    this.error.set('');
    try {
      const printed = await this.receiptPrinter.print({
        cafeName: 'Brew Haven',
        address: 'BrewBill POS',
        invoiceNumber: order.invoice_number,
        cashier: order.cashier_name,
        items: order.items.map((item) => ({
          name:
            item.variant_name && item.variant_name !== 'Regular'
              ? `${item.product_name} (${item.variant_name})`
              : item.product_name,
          quantity: item.quantity,
          amountMinor: Math.round(Number(item.line_total) * 100),
        })),
        subtotalMinor: Math.round(Number(order.subtotal) * 100),
        discountMinor: Math.round(Number(order.discount) * 100),
        taxMinor: Math.round(Number(order.tax) * 100),
        roundOffMinor: Math.round(Number(order.round_off) * 100),
        grandTotalMinor: Math.round(Number(order.grand_total) * 100),
        paymentMode,
        orderType: order.order_type,
        serviceReference: order.service_reference,
        currency: this.currency.current(),
      });
      if (printed) this.notice.set(`Print request sent for ${order.invoice_number}.`);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to print this invoice.');
    } finally {
      this.printingOrderId.set(null);
    }
  }

  setKotFilter(filter: 'ALL' | KotTicket['status']): void {
    this.kotFilter.set(filter);
  }
  countStatus(status: KotTicket['status']): number {
    return this.kots().filter((kot) => kot.status === status).length;
  }
  money(value: string | number): string {
    return this.currency.format(value);
  }
  date(value: string): string {
    return new Intl.DateTimeFormat('en-IN', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'Asia/Kolkata',
    }).format(new Date(value));
  }
  asset(path: string | null): string {
    return this.runtime.assetUrl(path);
  }
  quantity(value: string, unit: string): string {
    return `${Number(value).toFixed(unit === 'pcs' ? 0 : 2)} ${unit}`;
  }
  private requireToken(): string {
    const token = this.session.accessToken();
    if (!token) throw new Error('Sign in to load PostgreSQL data.');
    return token;
  }
}
