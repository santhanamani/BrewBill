import { Component, computed, inject, signal } from '@angular/core';
import { EChartsCoreOption } from 'echarts/core';
import { NgxEchartsDirective } from 'ngx-echarts';
import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { CatalogService } from '../../core/catalog.service';
import { DashboardMetric, Product } from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';

@Component({
  selector: 'app-dashboard',
  imports: [NgxEchartsDirective],
  templateUrl: './dashboard.component.html',
})
export class DashboardComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly catalog = inject(CatalogService);
  readonly session = inject(SessionService);

  readonly products = signal<Product[]>([]);
  readonly metrics = signal<DashboardMetric | null>(null);
  readonly loading = signal(true);
  readonly error = signal('');
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
      data: (this.metrics()?.hourly_sales ?? []).map((point) => point.label),
      axisLine: { lineStyle: { color: '#d9cdc4' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { formatter: (value: number) => `₹${Math.round(value / 1000)}K` },
      splitLine: { lineStyle: { color: '#eee8e3', type: 'dashed' } },
    },
    series: [
      {
        type: 'line',
        smooth: true,
        symbolSize: 8,
        data: (this.metrics()?.hourly_sales ?? []).map((point) => Number(point.value)),
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
        this.api.getDashboard(token),
      ]);
      this.products.set(catalog.products);
      this.metrics.set(metrics);
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to load dashboard data.');
    } finally {
      this.loading.set(false);
    }
  }

  money(value: string | number): string {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency: 'INR',
      maximumFractionDigits: 2,
    }).format(Number(value));
  }
}
