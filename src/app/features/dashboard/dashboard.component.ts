import { Component, computed, ElementRef, HostListener, inject, signal } from '@angular/core';
import { EChartsCoreOption } from 'echarts/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { CatalogService } from '../../core/catalog.service';
import { DashboardMetric, Product } from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';
import { CurrencyService } from '../../core/currency.service';
import { Router } from '@angular/router';

interface CalendarDay {
  value: string;
  day: number;
  outside: boolean;
  disabled: boolean;
  inRange: boolean;
  isStart: boolean;
  isEnd: boolean;
  isToday: boolean;
}

@Component({
  selector: 'app-dashboard',
  imports: [NgxEchartsDirective],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly catalog = inject(CatalogService);
  private readonly host = inject(ElementRef<HTMLElement>);
  private readonly router = inject(Router);
  readonly session = inject(SessionService);
  readonly currency = inject(CurrencyService);

  readonly products = signal<Product[]>([]);
  readonly metrics = signal<DashboardMetric | null>(null);
  readonly loading = signal(true);
  readonly error = signal('');
  readonly rangeError = signal('');
  readonly today = this.dateValue(new Date());
  readonly fromDate = signal(this.today);
  readonly toDate = signal(this.today);
  readonly appliedFromDate = signal(this.today);
  readonly appliedToDate = signal(this.today);
  readonly trendMode = signal<'date' | 'hour'>('date');
  readonly pickerOpen = signal(false);
  readonly selectingBoundary = signal<'from' | 'to'>('from');
  readonly calendarCursor = signal(this.monthStart(this.parseDate(this.today)));
  readonly weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  readonly calendarMonthLabel = computed(() => new Intl.DateTimeFormat('en-IN', {
    month: 'long', year: 'numeric',
  }).format(this.calendarCursor()));
  readonly canMoveNextMonth = computed(() => {
    const cursor = this.calendarCursor();
    const current = this.monthStart(this.parseDate(this.today));
    return cursor.getTime() < current.getTime();
  });
  readonly calendarDays = computed<CalendarDay[]>(() => {
    const cursor = this.calendarCursor();
    const gridStart = new Date(cursor.getFullYear(), cursor.getMonth(), 1 - cursor.getDay());
    const daysInMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0).getDate();
    const cellCount = Math.ceil((cursor.getDay() + daysInMonth) / 7) * 7;
    const from = this.fromDate();
    const to = this.toDate();
    return Array.from({ length: cellCount }, (_, index) => {
      const date = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + index);
      const value = this.dateValue(date);
      return {
        value,
        day: date.getDate(),
        outside: date.getMonth() !== cursor.getMonth(),
        disabled: value > this.today,
        inRange: value > from && value < to,
        isStart: value === from,
        isEnd: value === to,
        isToday: value === this.today,
      };
    });
  });
  readonly isSingleDay = computed(() => this.appliedFromDate() === this.appliedToDate());
  readonly trendSeries = computed(() => {
    const metrics = this.metrics();
    if (!metrics) return [];
    return this.trendMode() === 'date' ? metrics.date_sales : metrics.hour_sales;
  });
  readonly periodLabel = computed(() => {
    const from = this.appliedFromDate();
    const to = this.appliedToDate();
    if (from === this.today && to === this.today) return 'Today';
    if (from === to) return this.displayDate(from);
    return `${this.displayDate(from)} – ${this.displayDate(to)}`;
  });
  readonly metricPrefix = computed(() => this.periodLabel() === 'Today' ? "Today's" : 'Period');
  readonly totalProducts = computed(() => this.products().length);
  readonly availableProducts = computed(
    () =>
      this.products().filter(
        (item) => item.is_active && item.is_available && Number(item.stock_quantity) > 0,
      ).length,
  );
  readonly lowStockProducts = computed(
    () =>
      this.metrics()?.low_stock_products ??
      this.products().filter((item) => Number(item.stock_quantity) <= Number(item.low_stock_limit))
        .length,
  );
  readonly topProducts = computed(
    () =>
      this.metrics()?.top_products ??
      this.products()
        .filter((item) => item.is_favourite)
        .slice(0, 5)
        .map((item) => ({
          product_name: item.name,
          quantity_sold: 0,
          revenue: item.selling_price,
        })),
  );
  readonly maxTopProductQuantity = computed(() =>
    Math.max(0, ...this.topProducts().map((product) => Number(product.quantity_sold) || 0)),
  );
  readonly averageBill = computed(() =>
    this.metrics()?.orders_today
      ? Number(this.metrics()!.sales_today) / this.metrics()!.orders_today
      : 0,
  );
  readonly salesChart = computed<EChartsCoreOption>(() => ({
    color: ['#9b4516'],
    grid: { top: 24, right: 18, bottom: 30, left: 54 },
    tooltip: { trigger: 'axis', valueFormatter: (value: unknown) => this.money(Number(value)) },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: this.trendSeries().map((point) => point.label),
      axisLine: { lineStyle: { color: '#d9cdc4' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value: number) => this.currency.compact(value) },
      splitLine: { lineStyle: { color: '#eee8e3', type: 'dashed' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbolSize: 8,
        data: this.trendSeries().map((point) => Number(point.value)),
        areaStyle: { color: 'rgba(176,91,35,.13)' },
        lineStyle: { width: 3 },
      },
    ],
  }));
  readonly categoryChart = computed<EChartsCoreOption>(() => ({
    color: ['#2fa947', '#7542b5', '#2366bd', '#ef9200', '#20a6c7'],
    tooltip: { trigger: 'item', valueFormatter: (value: unknown) => this.money(Number(value)) },
    legend: { orient: 'vertical', right: 4, top: 'center' },
    series: [
      {
        type: 'pie',
        radius: ['48%', '72%'],
        center: ['32%', '50%'],
        avoidLabelOverlap: true,
        label: { show: false },
        data: (this.metrics()?.category_sales ?? []).map((point) => ({
          name: point.label,
          value: Number(point.value),
        })),
      },
    ],
  }));

  constructor() {
    void this.load();
  }

  async load(): Promise<void> {
    const token = this.session.accessToken();
    if (!token) return;
    this.loading.set(true);
    this.error.set('');
    try {
      const [catalog, metrics] = await Promise.all([
        this.catalog.load(token),
        this.api.getDashboard(token, this.appliedFromDate(), this.appliedToDate()),
      ]);
      this.products.set(catalog.products);
      this.metrics.set(metrics);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to load dashboard data.');
    } finally {
      this.loading.set(false);
    }
  }

  async applyDateRange(): Promise<void> {
    const from = this.fromDate();
    const to = this.toDate();
    this.rangeError.set('');
    if (!from || !to) {
      this.rangeError.set('Select both From and To dates.');
      return;
    }
    if (to < from) {
      this.rangeError.set('To date must be on or after From date.');
      return;
    }
    if (to > this.today) {
      this.rangeError.set('Future dates cannot be selected.');
      return;
    }
    const days = Math.round((this.parseDate(to).getTime() - this.parseDate(from).getTime()) / 86_400_000);
    if (days > 366) {
      this.rangeError.set('Select a range of 367 days or less.');
      return;
    }
    this.appliedFromDate.set(from);
    this.appliedToDate.set(to);
    await this.loadMetrics();
  }

  toggleDatePicker(): void {
    if (this.pickerOpen()) {
      this.cancelDatePicker();
      return;
    }
    this.rangeError.set('');
    this.fromDate.set(this.appliedFromDate());
    this.toDate.set(this.appliedToDate());
    this.selectingBoundary.set('from');
    this.calendarCursor.set(this.monthStart(this.parseDate(this.appliedFromDate())));
    this.pickerOpen.set(true);
  }

  editBoundary(boundary: 'from' | 'to'): void {
    this.selectingBoundary.set(boundary);
    this.calendarCursor.set(this.monthStart(this.parseDate(boundary === 'from' ? this.fromDate() : this.toDate())));
  }

  selectCalendarDay(day: CalendarDay): void {
    if (day.disabled) return;
    this.rangeError.set('');
    if (this.selectingBoundary() === 'from') {
      this.fromDate.set(day.value);
      if (day.value > this.toDate()) this.toDate.set(day.value);
      this.selectingBoundary.set('to');
      return;
    }
    if (day.value < this.fromDate()) {
      this.fromDate.set(day.value);
      this.toDate.set(day.value);
    } else {
      this.toDate.set(day.value);
    }
  }

  moveCalendar(months: number): void {
    if (months > 0 && !this.canMoveNextMonth()) return;
    const cursor = this.calendarCursor();
    this.calendarCursor.set(new Date(cursor.getFullYear(), cursor.getMonth() + months, 1));
  }

  chooseQuickRange(days: number): void {
    const end = this.parseDate(this.today);
    const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - days + 1);
    this.fromDate.set(this.dateValue(start));
    this.toDate.set(this.today);
    this.calendarCursor.set(this.monthStart(start));
    this.selectingBoundary.set('to');
    this.rangeError.set('');
  }

  chooseThisMonth(): void {
    const today = this.parseDate(this.today);
    this.fromDate.set(this.dateValue(this.monthStart(today)));
    this.toDate.set(this.today);
    this.calendarCursor.set(this.monthStart(today));
    this.selectingBoundary.set('to');
    this.rangeError.set('');
  }

  cancelDatePicker(): void {
    this.fromDate.set(this.appliedFromDate());
    this.toDate.set(this.appliedToDate());
    this.rangeError.set('');
    this.pickerOpen.set(false);
  }

  @HostListener('document:click', ['$event'])
  closePickerOutside(event: MouseEvent): void {
    if (!this.pickerOpen() || !(event.target instanceof Node)) return;
    const control = this.host.nativeElement.querySelector('.dashboard-date-control');
    if (control && !control.contains(event.target)) this.cancelDatePicker();
  }

  @HostListener('document:keydown.escape')
  closePickerWithEscape(): void {
    if (this.pickerOpen()) this.cancelDatePicker();
  }

  async confirmDateRange(): Promise<void> {
    await this.applyDateRange();
    if (!this.rangeError()) this.pickerOpen.set(false);
  }

  async showToday(): Promise<void> {
    this.fromDate.set(this.today);
    this.toDate.set(this.today);
    await this.applyDateRange();
    if (!this.rangeError()) this.pickerOpen.set(false);
  }

  private async loadMetrics(): Promise<void> {
    const token = this.session.accessToken();
    if (!token) return;
    this.loading.set(true);
    this.error.set('');
    try {
      this.metrics.set(await this.api.getDashboard(token, this.appliedFromDate(), this.appliedToDate()));
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to load dashboard data.');
    } finally {
      this.loading.set(false);
    }
  }

  private dateValue(value: Date): string {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private parseDate(value: string): Date {
    const [year, month, day] = value.split('-').map(Number);
    return new Date(year, month - 1, day);
  }

  private monthStart(value: Date): Date {
    return new Date(value.getFullYear(), value.getMonth(), 1);
  }

  displayDate(value: string): string {
    return new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
      .format(this.parseDate(value));
  }

  money(value: string | number): string {
    return this.currency.format(value);
  }

  topProductPercent(quantity: number): number {
    const maximum = this.maxTopProductQuantity();
    if (maximum <= 0) return 0;
    return Math.max(8, Math.round(((Number(quantity) || 0) / maximum) * 100));
  }

  viewAllSales(): void {
    void this.router.navigate(['/operations/reports']);
  }
}
