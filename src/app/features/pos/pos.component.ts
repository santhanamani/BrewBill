import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { CatalogService } from '../../core/catalog.service';
import { HeldCartService } from '../../core/held-cart.service';
import { CartLine, Category, Customer, Product, ProductVariant, TenantPaymentPolicy } from '../../core/models/api.models';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { SessionService } from '../../core/session.service';
import { ReceiptPayload, ReceiptPrinterService } from '../../core/receipt-printer.service';
import { CurrencyService } from '../../core/currency.service';

@Component({
  selector: 'app-pos',
  imports: [CommonModule],
  templateUrl: './pos.component.html',
  styleUrl: './pos.component.css',
})
export class PosComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly catalog = inject(CatalogService);
  private readonly runtime = inject(RuntimeConfigService);
  private readonly session = inject(SessionService);
  private readonly heldCart = inject(HeldCartService);
  private readonly receiptPrinter = inject(ReceiptPrinterService);
  readonly currency = inject(CurrencyService);

  readonly products = signal<Product[]>([]);
  readonly categories = signal<Category[]>([]);
  readonly activeCategoryId = signal<string | null>(null);
  readonly search = signal('');
  readonly favouritesOnly = signal(false);
  readonly savingFavourites = signal<ReadonlySet<string>>(new Set());
  readonly cart = signal<CartLine[]>([]);
  readonly loading = signal(true);
  readonly submitting = signal(false);
  readonly error = signal('');
  readonly notice = signal('');
  readonly billExpanded = signal(false);
  readonly resumedHoldId = signal<string | null>(null);
  readonly selectedProduct = signal<Product | null>(null);
  readonly discountPercent = signal(0);
  readonly orderType = signal<'DIRECT' | 'KOT' | 'TAKEAWAY'>('DIRECT');
  readonly serviceReference = signal('');
  readonly paymentTerminal = signal<{
    connected: boolean;
    provider: string;
    message: string;
  } | null>(null);
  readonly paymentProcessingMode = signal<TenantPaymentPolicy['payment_processing_mode'] | null>(null);
  readonly terminalRequired = computed(() => this.paymentProcessingMode() === 'TERMINAL_REQUIRED');
  readonly showSplit = signal(false);
  readonly showCredit = signal(false);
  readonly customers = signal<Customer[]>([]);
  readonly selectedCreditCustomerId = signal('');
  readonly creditDueDays = signal(10);
  readonly newCreditCustomerName = signal('');
  readonly newCreditCustomerMobile = signal('');
  readonly selectedCreditCustomer = computed(() => this.customers().find(customer => customer.id === this.selectedCreditCustomerId()) ?? null);
  readonly splitCash = signal('0.00');
  readonly splitUpi = signal('0.00');
  readonly splitCard = signal('0.00');
  readonly lastReceipt = signal<ReceiptPayload | null>(null);
  readonly filteredProducts = computed(() =>
    this.products().filter(
      (product) =>
        product.is_active &&
        (!this.favouritesOnly() || product.is_favourite) &&
        product.name.toLowerCase().includes(this.search().trim().toLowerCase()) &&
        (!this.activeCategoryId() || product.category_id === this.activeCategoryId()),
    ),
  );
  readonly subtotal = computed(() =>
    this.cart().reduce((total, line) => total + this.price(line.selling_price) * line.quantity, 0),
  );
  readonly tax = computed(() =>
    this.cart().reduce(
      (total, line) =>
        total +
        (this.price(line.selling_price) * line.quantity * this.price(line.gst_percent)) / 100,
      0,
    ),
  );
  readonly discount = computed(() => (this.subtotal() * this.discountPercent()) / 100);
  readonly beforeRounding = computed(() => this.subtotal() - this.discount() + this.tax());
  readonly grandTotal = computed(() => Math.round(this.beforeRounding()));
  readonly roundOff = computed(() => this.grandTotal() - this.beforeRounding());
  readonly splitTotal = computed(
    () => this.price(this.splitCash()) + this.price(this.splitUpi()) + this.price(this.splitCard()),
  );

  constructor() {
    void this.loadCatalog();
    void this.loadPaymentTerminal();
  }

  @HostListener('document:keydown.escape')
  closeExpandedBill(): void {
    this.billExpanded.set(false);
  }

  async loadPaymentTerminal(): Promise<void> {
    const token = this.session.accessToken();
    if (token) {
      try {
        const policy = await this.api.getPaymentPolicy(token);
        this.paymentProcessingMode.set(policy.payment_processing_mode);
      } catch (error) {
        this.paymentProcessingMode.set(null);
        this.notify(this.errorMessage(error, 'Unable to load the tenant payment setting. Payments are temporarily blocked.'));
      }
    }
    if (window.brewBill?.payment) {
      try {
        this.paymentTerminal.set(await window.brewBill.payment.status());
      } catch {
        this.paymentTerminal.set({ connected:false, provider:'UNAVAILABLE', message:'Payment terminal is unavailable.' });
      }
    }
  }

  async loadCatalog(): Promise<void> {
    const token = this.session.accessToken();
    if (!token) return;
    this.loading.set(true);
    this.error.set('');
    try {
      const catalog = await this.catalog.load(token);
      this.categories.set(catalog.categories);
      this.products.set(catalog.products);
      const held = this.heldCart.take();
      if (held) {
        const productById = new Map(catalog.products.map((product) => [product.id, product]));
        this.cart.set(
          held.items.flatMap((item) => {
            const product = productById.get(item.product_id);
            return product
              ? [
                  {
                    ...product,
                    selling_price: item.rate,
                    quantity: item.quantity,
                    cart_key: `${product.id}:${item.variant_id ?? 'regular'}`,
                    selected_variant_id: item.variant_id,
                    selected_variant_name: item.variant_name ?? 'Regular',
                  },
                ]
              : [];
          }),
        );
        this.resumedHoldId.set(held.id);
        this.notify(`Held bill ${held.hold_number} reopened.`);
      }
    } catch (error) {
      this.error.set(
        error instanceof Error ? error.message : 'Unable to load the product catalogue.',
      );
    } finally {
      this.loading.set(false);
    }
  }

  async toggleFavourite(product: Product): Promise<void> {
    const token = this.session.accessToken();
    if (!token || this.savingFavourites().has(product.id)) return;
    this.savingFavourites.update(ids => new Set([...ids, product.id]));
    try {
      const saved = await this.api.setProductFavourite(token, product.id, !product.is_favourite);
      this.products.update(products => products.map(row => row.id === product.id ? { ...row, is_favourite: saved.is_favourite } : row));
      this.notify(`${product.name} ${saved.is_favourite ? 'added to' : 'removed from'} favourites.`);
    } catch (error) {
      this.notify(error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
        ? error.error.detail : 'Unable to save favourite. Please try again.');
    } finally {
      this.savingFavourites.update(ids => { const next = new Set(ids); next.delete(product.id); return next; });
    }
  }

  add(product: Product): void {
    if (!product.is_available || Number(product.stock_quantity) <= 0) {
      this.notify(`${product.name} is currently unavailable.`);
      return;
    }
    const variants = product.variants.filter((variant) => variant.is_active);
    if (variants.length > 1) {
      this.selectedProduct.set(product);
      return;
    }
    this.addVariant(product, variants[0] ?? null);
  }

  addVariant(product: Product, variant: ProductVariant | null): void {
    const cartKey = `${product.id}:${variant?.id ?? 'regular'}`;
    const price = this.price(product.selling_price) + this.price(variant?.price_adjustment ?? '0');
    this.cart.update((lines) => {
      const line = lines.find((item) => item.cart_key === cartKey);
      return line
        ? lines.map((item) =>
            item.cart_key === cartKey ? { ...item, quantity: item.quantity + 1 } : item,
          )
        : [
            ...lines,
            {
              ...product,
              selling_price: price.toFixed(2),
              quantity: 1,
              cart_key: cartKey,
              selected_variant_id: variant?.id ?? null,
              selected_variant_name: variant?.name ?? 'Regular',
            },
          ];
    });
    this.selectedProduct.set(null);
  }

  changeQuantity(cartKey: string, amount: number): void {
    this.cart.update((lines) =>
      lines.flatMap((line) =>
        line.cart_key !== cartKey
          ? [line]
          : line.quantity + amount > 0
            ? [{ ...line, quantity: line.quantity + amount }]
            : [],
      ),
    );
  }

  async pay(mode: 'CASH' | 'UPI' | 'CARD'): Promise<void> {
    if (!this.paymentProcessingMode()) {
      this.notify('Payment settings are still loading. Please try again.');
      return;
    }
    if (mode === 'CASH' && this.terminalRequired()) {
      this.notify('Cash is disabled for this tenant. Use terminal-approved UPI or Card payment.');
      return;
    }
    await this.checkout([{ mode, amount: this.grandTotal() }], mode);
  }

  openSplit(): void {
    if (!this.cart().length) return;
    if (!this.paymentProcessingMode()) {
      this.notify('Payment settings are still loading. Please try again.');
      return;
    }
    this.splitCash.set(this.terminalRequired() ? '0.00' : this.grandTotal().toFixed(2));
    this.splitUpi.set(this.terminalRequired() ? this.grandTotal().toFixed(2) : '0.00');
    this.splitCard.set('0.00');
    this.showSplit.set(true);
  }

  async paySplit(): Promise<void> {
    if (this.terminalRequired() && this.price(this.splitCash()) > 0) {
      this.notify('Cash is not allowed when POS terminal payment is required.');
      return;
    }
    if (Math.abs(this.splitTotal() - this.grandTotal()) > 0.005) {
      this.notify('Split payment total must exactly match the grand total.');
      return;
    }
    const payments = [
      { mode: 'CASH' as const, amount: this.price(this.splitCash()) },
      { mode: 'UPI' as const, amount: this.price(this.splitUpi()) },
      { mode: 'CARD' as const, amount: this.price(this.splitCard()) },
    ].filter((payment) => payment.amount > 0);
    if (payments.length < 2) {
      this.notify('Enter at least two payment modes for a split payment.');
      return;
    }
    this.showSplit.set(false);
    await this.checkout(payments, 'SPLIT');
  }

  async openCredit(): Promise<void> {
    if (!this.cart().length || this.submitting()) return;
    const token = this.session.accessToken();
    if (!token) return;
    try {
      this.customers.set(await this.api.listCustomers(token));
      this.selectedCreditCustomerId.set(this.customers()[0]?.id ?? '');
      this.creditDueDays.set(10);
      this.showCredit.set(true);
    } catch (error) {
      this.notify(this.errorMessage(error, 'Unable to load customers.'));
    }
  }

  async addCreditCustomer(): Promise<void> {
    const token = this.session.accessToken();
    const name = this.newCreditCustomerName().trim();
    const mobile = this.newCreditCustomerMobile().trim();
    if (!token || !name || mobile.length < 7) {
      this.notify('Enter the customer name and a valid mobile number.');
      return;
    }
    try {
      const customer = await this.api.createCustomer(token, { name, mobile, email: null });
      this.customers.update(rows => [...rows, customer].sort((a, b) => a.name.localeCompare(b.name)));
      this.selectedCreditCustomerId.set(customer.id);
      this.newCreditCustomerName.set('');
      this.newCreditCustomerMobile.set('');
      this.notify(`${customer.name} added and selected.`);
    } catch (error) {
      this.notify(this.errorMessage(error, 'Unable to add customer.'));
    }
  }

  async confirmCredit(): Promise<void> {
    if (!this.selectedCreditCustomerId()) {
      this.notify('Select a customer before saving this credit bill.');
      return;
    }
    this.showCredit.set(false);
    await this.checkout([], 'CREDIT', this.selectedCreditCustomerId(), this.creditDueDays());
  }

  private async checkout(
    payments: Array<{ mode: 'CASH' | 'UPI' | 'CARD'; amount: number }>,
    receiptMode: 'CASH' | 'UPI' | 'CARD' | 'SPLIT' | 'CREDIT',
    creditCustomerId?: string,
    creditDueDays = 10,
  ): Promise<void> {
    if (!this.cart().length || this.submitting()) return;
    if (!(await this.canCreateBills())) return;
    const token = this.session.accessToken();
    if (!token) return;
    this.submitting.set(true);
    try {
      const orderId = crypto.randomUUID();
      const capturedPayments = creditCustomerId ? [] : await Promise.all(
        payments.map((payment) => this.capturePayment(payment, orderId)),
      );
      const saleLines = this.cart();
      const saleSubtotal = this.subtotal();
      const saleTax = this.tax();
      const saleGrandTotal = this.grandTotal();
      const saleDiscount = this.discount();
      const saleRoundOff = this.roundOff();
      const result = await this.api.createOrder(token, {
        order_id: orderId,
        terminal_code: this.runtime.config().terminalCode,
        items: saleLines.map((line) => ({
          product_id: line.id,
          variant_id: line.selected_variant_id,
          quantity: line.quantity,
        })),
        payments: capturedPayments,
        ...(creditCustomerId ? { credit_customer_id: creditCustomerId, credit_due_days: creditDueDays } : {}),
        order_type: this.orderType(),
        service_reference: this.serviceReference().trim() || null,
        discount_percent: this.discountPercent().toFixed(2),
        round_to_rupee: true,
        ...(this.resumedHoldId() ? { held_order_id: this.resumedHoldId()! } : {}),
      });
      const invoiceNumber = result.invoice_number;
      const user = this.session.user();
      this.lastReceipt.set({
        cafeName: 'Brew Haven',
        address: 'BrewBill POS',
        invoiceNumber,
        cashier: user?.display_name ?? 'Cashier',
        paymentMode: receiptMode,
        items: saleLines.map((line) => ({
          name:
            line.selected_variant_name && line.selected_variant_name !== 'Regular'
              ? `${line.name} (${line.selected_variant_name})`
              : line.name,
          quantity: line.quantity,
          amountMinor: Math.round(this.price(line.selling_price) * line.quantity * 100),
        })),
        subtotalMinor: Math.round(saleSubtotal * 100),
        discountMinor: Math.round(saleDiscount * 100),
        taxMinor: Math.round(saleTax * 100),
        roundOffMinor: Math.round(saleRoundOff * 100),
        grandTotalMinor: Math.round(saleGrandTotal * 100),
        orderType: this.orderType(),
        serviceReference: this.serviceReference().trim() || null,
        currency: this.currency.current(),
      });
      this.cart.set([]);
      this.resumedHoldId.set(null);
      this.discountPercent.set(0);
      this.serviceReference.set('');
      this.notify(creditCustomerId
        ? `Credit invoice ${invoiceNumber} added to ${this.selectedCreditCustomer()?.name ?? 'the customer'}'s outstanding balance.`
        : `Payment received. Invoice ${invoiceNumber} was saved. You can now print the bill.`);
      await this.loadCatalog();
    } catch (error) {
      this.notify(this.errorMessage(error, 'Unable to complete payment.'));
    } finally {
      this.submitting.set(false);
    }
  }

  private async capturePayment(
    payment: { mode: 'CASH' | 'UPI' | 'CARD'; amount: number },
    invoiceHint: string,
  ): Promise<{
    mode: 'CASH' | 'UPI' | 'CARD';
    amount: string;
    reference?: string;
    capture_source: 'MANUAL' | 'PAYMENT_TERMINAL';
    provider?: string;
  }> {
    const manual = {
      mode: payment.mode,
      amount: payment.amount.toFixed(2),
      capture_source: 'MANUAL' as const,
    };
    const terminalRequired = this.terminalRequired();
    if (payment.mode === 'CASH') {
      if (terminalRequired) throw new Error('Cash is disabled for this tenant. Use terminal-approved UPI or Card payment.');
      return manual;
    }
    if (!window.brewBill?.payment) {
      if (terminalRequired) throw new Error('POS terminal payment is required, but the desktop terminal bridge is unavailable.');
      return manual;
    }
    const result = await window.brewBill.payment.collect({
      mode: payment.mode,
      amountMinor: Math.round(payment.amount * 100),
      invoiceHint,
    });
    if (result.status === 'DECLINED') throw new Error(result.message);
    if (result.status === 'UNAVAILABLE') {
      if (terminalRequired) throw new Error('POS terminal is required and currently unavailable. The bill was not saved.');
      this.notify(result.message);
      return { ...manual, provider: result.provider };
    }
    return {
      mode: payment.mode,
      amount: payment.amount.toFixed(2),
      capture_source: 'PAYMENT_TERMINAL',
      provider: result.provider,
      ...(result.reference ? { reference: result.reference } : {}),
    };
  }

  async holdBill(): Promise<void> {
    if (!this.cart().length) return;
    if (!(await this.canCreateBills())) return;
    const token = this.session.accessToken();
    if (!token) return;
    this.submitting.set(true);
    try {
      const result = await this.api.createHold(token, {
        terminal_code: this.runtime.config().terminalCode,
        items: this.cart().map((line) => ({
          product_id: line.id,
          variant_id: line.selected_variant_id,
          quantity: line.quantity,
        })),
      });
      const holdNumber = result.hold_number;
      this.cart.set([]);
      this.resumedHoldId.set(null);
      this.notify(`Held bill ${holdNumber} was saved.`);
    } catch (error) {
      this.notify(error instanceof Error ? error.message : 'Unable to hold the bill.');
    } finally {
      this.submitting.set(false);
    }
  }

  private async canCreateBills(): Promise<boolean> {
    if (!window.brewBill) return true;
    if (!(await this.session.ensureDesktopLicense())) {
      this.notify(this.session.licenseMessage() || 'Unable to activate this POS terminal.');
      return false;
    }
    const license = await window.brewBill.license.status();
    if (license.canCreateBills) return true;
    this.notify(license.message);
    return false;
  }

  async printReceipt(): Promise<void> {
    const receipt = this.lastReceipt();
    if (!receipt) {
      this.notify('Complete a payment before printing a receipt.');
      return;
    }
    this.submitting.set(true);
    try {
      const printed = await this.receiptPrinter.print(receipt);
      if (printed) this.notify(`Print request sent for invoice ${receipt.invoiceNumber}.`);
      else this.notify('Print cancelled. No bill was printed.');
    } catch (error) {
      this.notify(this.errorMessage(error, 'Unable to print the receipt.'));
    } finally {
      this.submitting.set(false);
    }
  }

  asset(path: string | null): string {
    return this.runtime.assetUrl(path);
  }
  price(value: string): number {
    return Number.parseFloat(value) || 0;
  }
  money(value: number): string {
    return this.currency.format(value);
  }

  private notify(message: string): void {
    this.notice.set(message);
    window.setTimeout(() => this.notice.set(''), 3500);
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (error instanceof Error && error.message) return error.message;
    if (error && typeof error === 'object') {
      const response = error as { error?: { detail?: string } | string; message?: string };
      if (typeof response.error === 'object' && response.error?.detail)
        return response.error.detail;
      if (typeof response.error === 'string' && response.error) return response.error;
      if (response.message) return response.message;
    }
    return fallback;
  }
}
