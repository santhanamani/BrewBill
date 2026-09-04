import { Injectable, signal } from '@angular/core';
import { HeldBill } from './models/api.models';

@Injectable({ providedIn: 'root' })
export class HeldCartService {
  readonly pending = signal<HeldBill | null>(null);

  open(held: HeldBill): void {
    this.pending.set(held);
  }

  take(): HeldBill | null {
    const value = this.pending();
    this.pending.set(null);
    return value;
  }
}
