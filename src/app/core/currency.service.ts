import { Injectable, computed, signal } from '@angular/core';
import { CurrencyDefinition } from './models/api.models';

const INR: CurrencyDefinition = {
  code: 'INR',
  name: 'Indian Rupee',
  symbol: '₹',
  locale: 'en-IN',
  decimal_places: 2,
};

@Injectable({ providedIn: 'root' })
export class CurrencyService {
  readonly current = signal<CurrencyDefinition>(INR);
  readonly code = computed(() => this.current().code);
  readonly symbol = computed(() => this.current().symbol);
  readonly label = computed(() => `${this.current().code} (${this.current().symbol})`);

  configure(currency: CurrencyDefinition | null | undefined): void {
    this.current.set(currency ?? INR);
  }

  reset(): void {
    this.current.set(INR);
  }

  format(value: string | number): string {
    const currency = this.current();
    const amount = Number(value);
    return new Intl.NumberFormat(currency.locale || 'en-US', {
      style: 'currency',
      currency: currency.code,
      minimumFractionDigits: currency.decimal_places,
      maximumFractionDigits: currency.decimal_places,
    }).format(Number.isFinite(amount) ? amount : 0);
  }

  compact(value: string | number): string {
    const currency = this.current();
    const amount = Number(value);
    return new Intl.NumberFormat(currency.locale || 'en-US', {
      style: 'currency',
      currency: currency.code,
      notation: 'compact',
      maximumFractionDigits: 1,
    }).format(Number.isFinite(amount) ? amount : 0);
  }
}
