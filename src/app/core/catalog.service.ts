import { Injectable, inject } from '@angular/core';
import { BrewBillApiService } from './brew-bill-api.service';
import { Category, Product } from './models/api.models';

export interface CatalogResult {
  source: 'cloud';
  categories: Category[];
  products: Product[];
}

@Injectable({ providedIn: 'root' })
export class CatalogService {
  private readonly api = inject(BrewBillApiService);

  async load(accessToken: string, outletId?: string): Promise<CatalogResult> {
    if (!accessToken) throw new Error('Sign in to load the PostgreSQL catalogue.');
    const [categories, products] = await Promise.all([
      this.api.listCategories(accessToken),
      this.api.listProducts(accessToken, outletId),
    ]);
    return {
      source: 'cloud',
      categories,
      products: products.map((product) => ({ ...product, source: 'cloud' })),
    };
  }
}
