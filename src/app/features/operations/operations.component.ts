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
    detail: 'Detailed view of sales transactions, payments and tax reports.',
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
  readonly reportCashier = signal('');
  readonly reportProductSearch = signal('');
  readonly reportProductCategory = signal('');
  readonly reportProductAvailability = signal('');
  readonly reportPeriod = signal<'DAY'|'WEEK'|'MONTH'|'OVERALL'|'CUSTOM'>('DAY');
  readonly reportTab = signal<'SALES'|'PAYMENTS'|'PRODUCTS'|'CATEGORIES'|'MARKETPLACE'|'TAX'>('SALES');
  readonly reportFromDate = signal(this.localDateValue(new Date()));
  readonly reportToDate = signal(this.localDateValue(new Date()));
  readonly reportPage = signal(0);
  readonly reportPageSize = signal(10);
  readonly filteredOrders = computed(() => {
    const query=this.reportSearch().trim().toLowerCase();
    return this.orders().filter(order =>
      (!query || [order.invoice_number,order.cashier_name,order.status,...order.payment_modes].some(value=>value.toLowerCase().includes(query))) &&
      (!this.reportStatus() || order.status===this.reportStatus()) &&
      (!this.reportPayment() || order.payment_modes.includes(this.reportPayment())) &&
      (!this.reportCashier() || order.cashier_name===this.reportCashier()));
  });
  readonly reportCashiers = computed(()=>[...new Set(this.orders().map(order=>order.cashier_name))].sort());
  readonly reportPages = computed(()=>Math.max(1,Math.ceil(this.filteredOrders().length/this.reportPageSize())));
  readonly currentReportPage = computed(()=>Math.min(this.reportPage(),this.reportPages()-1));
  readonly visibleOrders = computed(()=>this.filteredOrders().slice(this.currentReportPage()*this.reportPageSize(),(this.currentReportPage()+1)*this.reportPageSize()));
  readonly reportPeriodLabel = computed(() => {
    const period=this.reportPeriod();
    if(period==='OVERALL')return 'Overall sales';
    if(period==='DAY')return `Day · ${this.shortReportDate(this.reportFromDate())}`;
    if(period==='WEEK')return `Week · ${this.shortReportDate(this.reportFromDate())} – ${this.shortReportDate(this.reportToDate())}`;
    if(period==='MONTH')return new Intl.DateTimeFormat('en-IN',{month:'long',year:'numeric',timeZone:'Asia/Kolkata'}).format(new Date(`${this.reportFromDate()}T12:00:00+05:30`));
    return `Custom · ${this.shortReportDate(this.reportFromDate())} – ${this.shortReportDate(this.reportToDate())}`;
  });
  readonly reportDiscount = computed(()=>this.completedOrders().reduce((sum,row)=>sum+Number(row.discount),0));
  readonly reportTax = computed(()=>this.completedOrders().reduce((sum,row)=>sum+Number(row.tax),0));
  readonly reportSubtotal = computed(()=>this.completedOrders().reduce((sum,row)=>sum+Number(row.subtotal),0));
  readonly reportTaxableSales = computed(()=>this.completedOrders().reduce((sum,order)=>sum+order.items.reduce((itemSum,item)=>itemSum+(Number(item.tax??0)>0?Number(item.line_total):0),0),0));
  readonly reportNonTaxableSales = computed(()=>Math.max(0,this.reportSubtotal()-this.reportTaxableSales()));
  readonly voidValue = computed(()=>this.orders().filter(row=>row.status==='VOID').reduce((sum,row)=>sum+Number(row.grand_total),0));
  readonly paymentReport = computed(()=>{
    const totals=new Map<string,{mode:string;transactions:number;amount:number}>();
    for(const order of this.completedOrders()){const payments=order.payments?.length?order.payments:[{payment_mode:order.payment_modes.length===1?order.payment_modes[0]:'SPLIT',amount:order.grand_total}];for(const payment of payments){const key=payment.payment_mode;const row=totals.get(key)??{mode:key,transactions:0,amount:0};row.transactions++;row.amount+=Number(payment.amount);totals.set(key,row);}}
    if(this.completedOrders().some(order=>order.payment_status==='CREDIT'))totals.set('CREDIT',{mode:'CREDIT',transactions:this.completedOrders().filter(order=>order.payment_status==='CREDIT').length,amount:this.completedOrders().filter(order=>order.payment_status==='CREDIT').reduce((sum,order)=>sum+Number(order.grand_total)-(order.payments??[]).reduce((paid,p)=>paid+Number(p.amount),0),0)});
    return [...totals.values()].sort((a,b)=>b.amount-a.amount);
  });
  readonly productReport = computed(()=>{
    const totals=new Map<string,{name:string;category:string;image:string|null;available:boolean;quantity:number;orders:Set<string>;gross:number;discount:number;tax:number}>();
    for(const order of this.completedOrders())for(const item of order.items){const key=item.product_id??item.product_name;const itemGross=Number(item.line_total);const allocatedDiscount=Number(order.subtotal)?Number(order.discount)*itemGross/Number(order.subtotal):0;const row=totals.get(key)??{name:item.product_name,category:item.category_name??'Uncategorised',image:item.image_path??null,available:item.is_available!==false,quantity:0,orders:new Set<string>(),gross:0,discount:0,tax:0};row.quantity+=item.quantity;row.orders.add(order.id);row.gross+=itemGross;row.discount+=allocatedDiscount;row.tax+=item.tax!==undefined?Number(item.tax):(Number(order.subtotal)?Number(order.tax)*itemGross/Number(order.subtotal):0);totals.set(key,row);}
    return [...totals.values()].sort((a,b)=>b.gross-a.gross);
  });
  readonly categoryReport = computed(()=>{
    const totals=new Map<string,{name:string;quantity:number;gross:number;tax:number}>();
    for(const product of this.productReport()){const row=totals.get(product.category)??{name:product.category,quantity:0,gross:0,tax:0};row.quantity+=product.quantity;row.gross+=product.gross;row.tax+=product.tax;totals.set(product.category,row);}
    return [...totals.values()].sort((a,b)=>b.gross-a.gross);
  });
  readonly taxReport = computed(()=>{
    const totals=new Map<string,{rate:number;taxable:number;tax:number;invoices:Set<string>}>();
    for(const order of this.completedOrders())for(const item of order.items){const itemTax=item.tax!==undefined?Number(item.tax):(Number(order.subtotal)?Number(order.tax)*Number(item.line_total)/Number(order.subtotal):0);const rate=Number(item.line_total)>0?Math.round(itemTax/Number(item.line_total)*10000)/100:0;const key=rate.toFixed(2);const row=totals.get(key)??{rate,taxable:0,tax:0,invoices:new Set<string>()};row.taxable+=Number(item.line_total);row.tax+=itemTax;row.invoices.add(order.id);totals.set(key,row);}
    return [...totals.values()].sort((a,b)=>a.rate-b.rate);
  });
  readonly paymentTotal = computed(()=>this.paymentReport().reduce((sum,row)=>sum+row.amount,0));
  readonly paymentHourlyReport = computed(()=>{
    const hours=Array.from({length:24},(_,hour)=>({hour,label:new Intl.DateTimeFormat('en-IN',{hour:'numeric',hour12:true,timeZone:'Asia/Kolkata'}).format(new Date(Date.UTC(2026,0,1,hour))),total:0,modes:new Map<string,number>()}));
    for(const order of this.completedOrders()){
      const hour=Number(new Intl.DateTimeFormat('en-IN',{hour:'2-digit',hourCycle:'h23',timeZone:'Asia/Kolkata'}).format(new Date(order.created_at)));
      const payments=order.payments?.length?order.payments:[{payment_mode:order.payment_modes[0]??'CASH',amount:order.grand_total}];
      for(const payment of payments){const value=Number(payment.amount);hours[hour].total+=value;hours[hour].modes.set(payment.payment_mode,(hours[hour].modes.get(payment.payment_mode)??0)+value);}
    }
    return hours;
  });
  readonly paymentHourlyMax = computed(()=>Math.max(1,...this.paymentHourlyReport().map(row=>row.total)));
  readonly paymentTrendHours = computed(()=>this.paymentHourlyReport().filter(row=>row.hour>=6&&row.hour<=21&&row.hour%3===0));
  readonly reportProductCategories = computed(()=>[...new Set(this.productReport().map(row=>row.category))].sort());
  readonly filteredProductReport = computed(()=>{
    const query=this.reportProductSearch().trim().toLowerCase();
    return this.productReport().filter(row=>(!query||[row.name,row.category].some(value=>value.toLowerCase().includes(query)))&&(!this.reportProductCategory()||row.category===this.reportProductCategory())&&(!this.reportProductAvailability()||(this.reportProductAvailability()==='AVAILABLE'?row.available:!row.available)));
  });
  readonly marketplaceChannels = computed(()=>['SWIGGY','ZOMATO'].map(provider=>{
    const orders=this.marketplaceOrders().filter(order=>order.provider===provider);
    const completed=orders.filter(order=>order.status==='COMPLETED');
    const gross=completed.reduce((sum,order)=>sum+Number(order.grand_total),0);
    const commission=completed.reduce((sum,order)=>sum+Number(order.commission),0);
    const net=completed.reduce((sum,order)=>sum+Number(order.net_settlement),0);
    const profit=completed.reduce((sum,order)=>sum+Number(order.estimated_profit),0);
    return {provider,orders:orders.length,gross,commission,net,profit,average:completed.length?gross/completed.length:0,share:this.marketplaceOrders().length?orders.length/this.marketplaceOrders().length*100:0};
  }));
  readonly marketplaceDonut = computed(()=>this.donutGradient(this.marketplaceChannels().map(row=>row.orders)));
  readonly paymentDonut = computed(()=>this.donutGradient(this.paymentReport().map(row=>row.amount)));
  readonly categoryDonut = computed(()=>this.donutGradient(this.categoryReport().map(row=>row.gross)));
  readonly taxDonut = computed(()=>this.donutGradient(this.taxReport().map(row=>row.tax)));
  paymentShare(amount:number):number {const total=this.paymentReport().reduce((sum,row)=>sum+row.amount,0);return total?amount/total*100:0;}
  productShare(amount:number):number {const max=Math.max(0,...this.productReport().map(row=>row.gross));return max?amount/max*100:0;}
  categoryShare(amount:number):number {const total=this.categoryReport().reduce((sum,row)=>sum+row.gross,0);return total?amount/total*100:0;}
  orderTaxSlabs(order:OrderListItem):string {return [...new Set(order.items.map(item=>{const taxable=Number(item.line_total);const tax=Number(item.tax??0);return taxable>0?`${Math.round(tax/taxable*10000)/100}%`:'0%';}))].join(', ');}
  private donutGradient(values:number[]):string {
    const palette=['#653407','#9a622e','#c0915d','#dec29d','#7d9a78','#b95f62'];const total=values.reduce((sum,value)=>sum+value,0);
    if(!total)return 'conic-gradient(#eee5d9 0 100%)';let cursor=0;const stops=values.map((value,index)=>{const start=cursor;cursor+=value/total*100;return `${palette[index%palette.length]} ${start}% ${cursor}%`;});return `conic-gradient(${stops.join(',')})`;
  }
  filterReports(field:'status'|'payment',value:string):void {
    (field==='status'?this.reportStatus:this.reportPayment).set(value);this.reportPage.set(0);
  }
  pageReports(delta:number):void { this.reportPage.set(Math.max(0,Math.min(this.currentReportPage()+delta,this.reportPages()-1))); }
  sizeReports(value:string):void { const size=Number(value);if([10,25,50].includes(size)){this.reportPageSize.set(size);this.reportPage.set(0);} }
  openMarketplace():void { void this.router.navigateByUrl('/marketplace'); }

  setReportPeriod(period:'DAY'|'WEEK'|'MONTH'|'OVERALL'):void {
    const today=new Date();
    if(period==='OVERALL') {
      this.reportFromDate.set('');this.reportToDate.set('');
    } else if(period==='DAY') {
      const value=this.localDateValue(today);this.reportFromDate.set(value);this.reportToDate.set(value);
    } else if(period==='WEEK') {
      const start=new Date(today);const day=(start.getDay()+6)%7;start.setDate(start.getDate()-day);
      const end=new Date(start);end.setDate(start.getDate()+6);
      this.reportFromDate.set(this.localDateValue(start));this.reportToDate.set(this.localDateValue(end));
    } else {
      const start=new Date(today.getFullYear(),today.getMonth(),1);
      const end=new Date(today.getFullYear(),today.getMonth()+1,0);
      this.reportFromDate.set(this.localDateValue(start));this.reportToDate.set(this.localDateValue(end));
    }
    this.reportPeriod.set(period);this.reportPage.set(0);void this.load();
  }

  setCustomReportPeriod():void {
    this.reportPeriod.set('CUSTOM');
  }

  exportSalesReport():void {
    const rows:(string|number|null)[][]=[
      ['Invoice','Date & Time','Cashier','Item Count','Products','Payment','Payment Status','Order Type','Service Reference','Subtotal','Discount','GST','Round Off','Grand Total','Status'],
      ...this.filteredOrders().map(order=>[order.invoice_number,this.date(order.created_at),order.cashier_name,order.item_count,order.items.map(item=>`${item.product_name}${item.variant_name&&item.variant_name!=='Regular'?' ('+item.variant_name+')':''} x ${item.quantity}`).join(' | '),order.payment_modes.join(' + '),order.payment_status,order.order_type,order.service_reference,order.subtotal,order.discount,order.tax,order.round_off,order.grand_total,order.status]),
    ];
    const csv=rows.map(row=>row.map(value=>{let cell=String(value??'');if(/^[\s]*[=+@-]/.test(cell))cell="'"+cell;return '"'+cell.replaceAll('"','""')+'"';}).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob(['\uFEFF',csv],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=`brew-haven-sales-${this.reportPeriod().toLowerCase()}-${this.localDateValue(new Date())}.csv`;
    document.body.appendChild(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000);
    this.notice.set(`${this.filteredOrders().length} sales records exported.`);
  }
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
      if(params.has('from') || params.has('to'))this.reportPeriod.set('CUSTOM');
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
          this.marketplaceEnabled() ? this.api.listMarketplaceOrders(token, this.reportFromDate() || undefined, this.reportToDate() || undefined) : Promise.resolve([]),
          this.marketplaceEnabled() ? this.api.getMarketplaceSummary(token, this.reportFromDate() || undefined, this.reportToDate() || undefined) : Promise.resolve(null),
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
    if(this.reportPeriod()==='OVERALL'){this.reportPage.set(0);void this.load();return;}
    if (!this.reportFromDate() || !this.reportToDate() || this.reportFromDate() > this.reportToDate()) {
      this.error.set('Choose a valid From and To date range.');
      return;
    }
    this.reportPeriod.set('CUSTOM');
    this.reportPage.set(0);
    void this.load();
  }

  clearReportFilters(): void {
    const today = this.localDateValue(new Date());
    this.reportStatus.set('');
    this.reportPayment.set('');
    this.reportCashier.set('');
    this.reportProductSearch.set('');
    this.reportProductCategory.set('');
    this.reportProductAvailability.set('');
    this.reportFromDate.set(today);
    this.reportToDate.set(today);
    this.reportPeriod.set('DAY');
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

  private shortReportDate(value:string):string {
    if(!value)return '';
    return new Intl.DateTimeFormat('en-IN',{day:'2-digit',month:'short',year:'numeric',timeZone:'Asia/Kolkata'}).format(new Date(`${value}T12:00:00+05:30`));
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
