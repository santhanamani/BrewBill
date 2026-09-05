import { HttpErrorResponse } from '@angular/common/http';
import { Component, computed, inject, signal } from '@angular/core';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { CatalogService } from '../../core/catalog.service';
import {
  Category, GlobalProduct, OutletProductMapping, Product, ProductCreate,
} from '../../core/models/api.models';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { SessionService } from '../../core/session.service';

type ProductDraft = {
  categoryId: string;
  code: string;
  name: string;
  sellingPrice: string;
  purchasePrice: string;
  gstPercent: string;
  stockQuantity: string;
  lowStockLimit: string;
  unit: string;
  imagePath: string;
  favourite: boolean;
  kotRequired: boolean;
  available: boolean;
  active: boolean;
  sharedAcrossOutlets: boolean;
};

const emptyDraft = (): ProductDraft => ({
  categoryId: '',
  code: '',
  name: '',
  sellingPrice: '',
  purchasePrice: '0',
  gstPercent: '5',
  stockQuantity: '0',
  lowStockLimit: '5',
  unit: 'pcs',
  imagePath: 'products/placeholder.svg',
  favourite: false,
  kotRequired: true,
  available: true,
  active: true,
  sharedAcrossOutlets: true,
});

@Component({
  selector: 'app-products',
  templateUrl: './products.component.html',
  styles: [
    `
      .product-tools {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        justify-content: flex-end;
      }
      .catalogue-tabs { display:flex; gap:8px; margin-bottom:12px; }
      .catalogue-tabs button { min-height:44px; border:1px solid #eadfd6; background:#fff; border-radius:10px; padding:0 18px; font-weight:750; }
      .catalogue-tabs button.active { color:#fff; background:var(--brand-primary,#5a2d18); border-color:transparent; }
      .split-catalogue { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.12fr); gap:14px; }
      .catalogue-card { min-width:0; }
      .catalogue-card .panel-title { align-items:flex-start; gap:12px; }
      .catalogue-card .panel-title p { margin:3px 0 0; color:#80736b; font-size:12px; }
      .shared-badge { display:inline-flex; border-radius:20px; padding:4px 9px; color:#176938; background:#e5f6ea; font-size:11px; font-weight:750; }
      .mapping-actions { display:flex; gap:6px; }
      .mapping-actions button { min-width:34px; min-height:32px; }
      .catalogue-search { width:min(320px,100%); min-height:40px; border:1px solid #e4dcd5; border-radius:9px; padding:0 12px; }
      .product-tools input,
      .product-tools select {
        min-height: 44px;
        border: 1px solid #e5dcd6;
        border-radius: 9px;
        padding: 0 12px;
        background: #fff;
      }
      .product-metrics {
        margin-bottom: 16px;
      }
      .product-thumb {
        width: 46px;
        height: 46px;
        border-radius: 7px;
        object-fit: cover;
      }
      .product-cell {
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 210px;
      }
      .product-cell span {
        display: grid;
        gap: 3px;
      }
      .product-cell small {
        color: #776b63;
      }
      .scope-pill {
        font-size: 11px;
        color: #6a3e20;
        background: #fff0d9;
        border-radius: 20px;
        padding: 3px 7px;
      }
      .toggle-button {
        width: 40px;
        height: 23px;
        padding: 2px;
        border: 0;
        border-radius: 20px;
        background: #d6d6d6;
      }
      .toggle-button::after {
        content: '';
        display: block;
        width: 19px;
        height: 19px;
        border-radius: 50%;
        background: #fff;
        transition: 0.15s;
      }
      .toggle-button.on {
        background: #27a64b;
      }
      .toggle-button.on::after {
        transform: translateX(17px);
      }
      .product-dialog {
        width: min(720px, calc(100vw - 36px));
        border: 0;
        border-radius: 14px;
        padding: 0;
        box-shadow: 0 18px 60px #2f160f45;
      }
      .product-dialog::backdrop {
        background: #2f160f66;
      }
      .product-form {
        display: grid;
        gap: 14px;
        padding: 20px;
      }
      .product-form .form-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
      }
      .product-form label {
        display: grid;
        gap: 6px;
        font-size: 12px;
        font-weight: 700;
        color: #4b3a2f;
      }
      .product-form input,
      .product-form select {
        border: 1px solid #e4dcd5;
        border-radius: 8px;
        padding: 11px;
        font: 14px inherit;
      }
      .product-form .checks {
        display: flex;
        flex-wrap: wrap;
        gap: 18px;
      }
      .dialog-actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
      }
      @media (max-width: 760px) {
        .split-catalogue { grid-template-columns:1fr; }
        .product-form .form-grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class ProductsComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly catalog = inject(CatalogService);
  readonly session = inject(SessionService);
  private readonly runtime = inject(RuntimeConfigService);
  readonly products = signal<Product[]>([]);
  readonly globalProducts = signal<GlobalProduct[]>([]);
  readonly outletMappings = signal<OutletProductMapping[]>([]);
  readonly masterSearch = signal('');
  readonly mappingSearch = signal('');
  readonly categories = signal<Category[]>([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly notice = signal('');
  readonly search = signal('');
  readonly visibleLimit = signal(10);
  readonly categoryFilter = signal('ALL');
  readonly statusFilter = signal('ALL');
  readonly editingId = signal<string | null>(null);
  readonly draft = signal<ProductDraft>(emptyDraft());
  readonly visibleProducts = computed(() => {
    const query = this.search().trim().toLowerCase();
    return this.products()
      .filter(
        (product) =>
          (!query ||
            product.name.toLowerCase().includes(query) ||
            product.code.toLowerCase().includes(query)) &&
          (this.categoryFilter() === 'ALL' || product.category_id === this.categoryFilter()) &&
          (this.statusFilter() === 'ALL' ||
            (this.statusFilter() === 'ACTIVE' ? product.is_active : !product.is_active)),
      )
      .slice(0, this.visibleLimit());
  });
  readonly visibleMasters = computed(() => {
    const query = this.masterSearch().trim().toLowerCase();
    return this.globalProducts().filter((product) =>
      !query || `${product.code} ${product.name} ${product.category_name}`.toLowerCase().includes(query),
    );
  });
  readonly visibleMappings = computed(() => {
    const query = this.mappingSearch().trim().toLowerCase();
    return this.outletMappings().filter((product) =>
      !query || `${product.code} ${product.name} ${product.category_name}`.toLowerCase().includes(query),
    );
  });
  readonly mappedIds = computed(() => new Set(this.outletMappings().map((item) => item.global_product_id)));

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
  readonly favourites = computed(() => this.products().filter((item) => item.is_favourite).length);
  readonly outOfStock = computed(
    () => this.products().filter((item) => Number(item.stock_quantity) <= 0).length,
  );
  readonly lowStock = computed(
    () =>
      this.products().filter(
        (item) =>
          Number(item.stock_quantity) > 0 &&
          Number(item.stock_quantity) <= Number(item.low_stock_limit),
      ).length,
  );

  constructor() {
    void this.load();
  }

  async load(): Promise<void> {
    const token = this.requireToken();
    this.loading.set(true);
    try {
      const [result, globalProducts, outletMappings] = await Promise.all([
        this.catalog.load(token),
        this.api.listGlobalProducts(token, true),
        this.api.listOutletCatalogue(token),
      ]);
      this.categories.set(result.categories);
      this.products.set(result.products);
      this.globalProducts.set(globalProducts);
      this.outletMappings.set(outletMappings);
      if (!this.draft().categoryId && result.categories[0])
        this.patch('categoryId', result.categories[0].id);
    } catch (error) {
      this.notice.set(error instanceof Error ? error.message : 'Unable to load products.');
    } finally {
      this.loading.set(false);
    }
  }

  readonly mappingTarget = signal<{ productId: string; mappingId: string | null } | null>(null);
  readonly mappingError = signal('');

  async addGlobalProduct(): Promise<void> {
    const name = window.prompt('Global product name')?.trim(); if (!name) return;
    const code = window.prompt('Global product code', name.toUpperCase().replace(/[^A-Z0-9]+/g, '_'))?.trim(); if (!code) return;
    const category = window.prompt('Category', 'Beverages')?.trim(); if (!category) return;
    const unit = window.prompt('Base unit', 'pcs')?.trim(); if (!unit) return;
    try {
      await this.api.createGlobalProduct(this.requireToken(), {
        code: code.toUpperCase(), name, description: null, category_name: category,
        base_unit: unit, default_gst: '5.00', image_path: 'products/placeholder.svg', status: 'ACTIVE',
      });
      this.notice.set(`${name} added to the global product master.`); await this.load();
    } catch (error) { this.notice.set(error instanceof Error ? error.message : 'Unable to add global product.'); }
  }

  async toggleMapping(
    mapping: OutletProductMapping,
    field: 'favourite' | 'kot_required' | 'is_available' | 'is_active',
  ): Promise<void> {
    try {
      await this.api.updateOutletProduct(this.requireToken(), mapping.id, { [field]: !mapping[field] });
      await this.load();
    } catch (error) {
      this.notice.set(error instanceof Error ? error.message : 'Unable to update outlet product.');
    }
  }

  mapProduct(product: GlobalProduct, dialog: HTMLDialogElement): void {
    const mapping = this.outletMappings().find(row => row.global_product_id === product.id);
    if (!mapping && product.status !== 'ACTIVE') {
      this.notice.set('Activate this global product before mapping it to an outlet.');
      return;
    }
    this.mappingTarget.set({ productId: product.id, mappingId: mapping?.id ?? null });
    this.mappingError.set('');
    this.draft.set({ ...emptyDraft(), code: product.code, name: product.name, unit: product.base_unit,
      sellingPrice: mapping?.selling_price ?? '0', stockQuantity: mapping?.stock_quantity ?? '0',
      lowStockLimit: mapping?.low_stock_limit ?? '5', favourite: mapping?.favourite ?? false,
      kotRequired: mapping?.kot_required ?? true, available: mapping?.is_available ?? true, active: mapping?.is_active ?? true });
    dialog.showModal();
  }

  editMapping(mapping: OutletProductMapping, dialog: HTMLDialogElement): void {
    const master = this.globalProducts().find(row => row.id === mapping.global_product_id);
    if (!master) { this.notice.set('Product details could not be loaded. Refresh the catalogue and try again.'); return; }
    this.mapProduct(master, dialog);
  }

  async saveMapping(dialog: HTMLDialogElement): Promise<void> {
    const target = this.mappingTarget(), draft = this.draft();
    if (!target || this.saving()) return;
    if ([draft.sellingPrice, draft.stockQuantity, draft.lowStockLimit].some(value => !value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0)) {
      this.mappingError.set('Enter valid, non-negative price and stock values.'); return;
    }
    this.saving.set(true); this.mappingError.set('');
    const body = { selling_price: Number(draft.sellingPrice).toFixed(2), low_stock_limit: Number(draft.lowStockLimit).toFixed(3),
      favourite: draft.favourite, kot_required: draft.kotRequired, is_available: draft.available, is_active: draft.active };
    try {
      if (target.mappingId) await this.api.updateOutletProduct(this.requireToken(), target.mappingId, body);
      else await this.api.mapOutletProduct(this.requireToken(), target.productId, { ...body,
        opening_stock: Number(draft.stockQuantity).toFixed(3), display_order: this.outletMappings().length });
      dialog.close(); await this.load(); this.notice.set(draft.name + ' outlet mapping saved.');
    } catch (error) {
      this.mappingError.set(error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
        ? error.error.detail : 'Unable to save outlet mapping. Please try again.');
    } finally { this.saving.set(false); }
  }

  async unmap(mapping: OutletProductMapping): Promise<void> {
    if (this.saving()) return;
    if (!window.confirm(`Remove ${mapping.name} from this outlet catalogue? Existing invoices are preserved.`)) return;
    this.saving.set(true);
    try {
      await this.api.unmapOutletProduct(this.requireToken(), mapping.id);
      this.notice.set(`${mapping.name} removed from this outlet catalogue.`);
      await this.load();
    } catch (error) {
      this.notice.set(error instanceof HttpErrorResponse && typeof error.error?.detail === 'string'
        ? error.error.detail : 'Unable to remove this outlet mapping. Please try again.');
    } finally { this.saving.set(false); }
  }

  openAdd(dialog: HTMLDialogElement): void {
    this.editingId.set(null);
    this.draft.set({ ...emptyDraft(), categoryId: this.categories()[0]?.id ?? '' });
    dialog.showModal();
  }

  openEdit(product: Product, dialog: HTMLDialogElement): void {
    this.editingId.set(product.id);
    this.draft.set({
      categoryId: product.category_id ?? '',
      code: product.code,
      name: product.name,
      sellingPrice: product.selling_price,
      purchasePrice: product.purchase_price,
      gstPercent: product.gst_percent,
      stockQuantity: product.stock_quantity,
      lowStockLimit: product.low_stock_limit,
      unit: product.unit,
      imagePath: product.image_path ?? '',
      favourite: product.is_favourite,
      kotRequired: product.kot_required,
      available: product.is_available,
      active: product.is_active,
      sharedAcrossOutlets: product.shared_across_outlets,
    });
    dialog.showModal();
  }

  patch(key: keyof ProductDraft, value: string | boolean): void {
    this.draft.update((draft) => ({ ...draft, [key]: value }));
  }

  async save(dialog: HTMLDialogElement): Promise<void> {
    const draft = this.draft();
    if (
      !draft.categoryId ||
      !draft.code.trim() ||
      !draft.name.trim() ||
      Number(draft.sellingPrice) < 0
    ) {
      this.notice.set('Category, code, product name and a valid price are required.');
      return;
    }
    const body: ProductCreate = {
      code: draft.code
        .trim()
        .toUpperCase()
        .replace(/[^A-Z0-9_-]+/g, '_'),
      name: draft.name.trim(),
      selling_price: Number(draft.sellingPrice).toFixed(2),
      purchase_price: Number(draft.purchasePrice || 0).toFixed(2),
      gst_percent: Number(draft.gstPercent || 0).toFixed(2),
      category_id: draft.categoryId,
      description: null,
      image_path: draft.imagePath.trim() || null,
      unit: draft.unit,
      stock_quantity: Number(draft.stockQuantity || 0).toFixed(3),
      low_stock_limit: Number(draft.lowStockLimit || 0).toFixed(3),
      is_favourite: draft.favourite,
      kot_required: draft.kotRequired,
      is_available: draft.available,
      is_active: draft.active,
      shared_across_outlets: draft.sharedAcrossOutlets,
    };
    this.saving.set(true);
    this.notice.set('');
    try {
      if (this.editingId())
        await this.api.updateProduct(this.requireToken(), this.editingId()!, body);
      else await this.api.createProduct(this.requireToken(), body);
      this.notice.set(`${draft.name} was ${this.editingId() ? 'updated' : 'added'} in PostgreSQL.`);
      dialog.close();
      await this.load();
    } catch (error) {
      this.notice.set(error instanceof Error ? error.message : 'Unable to save product.');
    } finally {
      this.saving.set(false);
    }
  }

  async toggle(
    product: Product,
    field: 'is_favourite' | 'kot_required' | 'is_active',
  ): Promise<void> {
    try {
      await this.api.updateProduct(this.requireToken(), product.id, { [field]: !product[field] });
      await this.load();
    } catch (error) {
      this.notice.set(error instanceof Error ? error.message : 'Unable to update product.');
    }
  }

  async addVariant(product: Product): Promise<void> {
    const name = window.prompt(`Variant name for ${product.name}`)?.trim();
    if (!name) return;
    const adjustment = window.prompt('Price adjustment', '0')?.trim();
    if (adjustment === undefined) return;
    try {
      await this.api.createProductVariant(this.requireToken(), product.id, {
        name,
        price_adjustment: Number(adjustment).toFixed(2),
        display_order: product.variants.length,
      });
      await this.load();
    } catch (error) {
      this.notice.set(error instanceof Error ? error.message : 'Unable to add variant.');
    }
  }

  money(value: string): string {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR' }).format(
      Number(value),
    );
  }
  asset(path: string | null): string {
    return this.runtime.assetUrl(path);
  }
  private requireToken(): string {
    const token = this.session.accessToken();
    if (!token) throw new Error('Sign in to manage PostgreSQL products.');
    return token;
  }
}
