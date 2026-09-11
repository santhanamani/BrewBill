import { Injectable, computed, signal } from '@angular/core';
import { AdminOutlet, CurrentUser } from './models/api.models';
import type { BrewBillApiService } from './brew-bill-api.service';

@Injectable({ providedIn: 'root' })
export class OutletContextService {
  readonly outlets = signal<AdminOutlet[]>([]);
  readonly selectedOutletId = signal('');
  readonly loading = signal(false);
  readonly error = signal('');
  readonly selectedOutlet = computed(() =>
    this.outlets().find(outlet => outlet.id === this.selectedOutletId()) ?? null,
  );
  readonly canSelect = signal(false);
  private initializedUserId = '';

  async ensure(api: BrewBillApiService, accessToken: string, user: CurrentUser): Promise<void> {
    if (this.initializedUserId === user.id) return;
    this.initializedUserId = user.id;
    this.error.set('');
    this.canSelect.set(!user.outlet_id && ['ADMIN', 'TENANT_ADMIN'].includes(user.role_code));
    if (user.outlet_id) {
      this.selectedOutletId.set(user.outlet_id);
      return;
    }
    if (!this.canSelect()) {
      this.selectedOutletId.set('');
      return;
    }
    this.loading.set(true);
    try {
      const outlets = await api.listTenantOutlets(accessToken);
      this.outlets.set(outlets);
      const key = this.storageKey(user);
      let remembered = '';
      try { remembered = window.localStorage.getItem(key) ?? ''; } catch { /* storage is optional */ }
      const selected = outlets.some(outlet => outlet.id === remembered)
        ? remembered
        : (outlets[0]?.id ?? '');
      this.selectedOutletId.set(selected);
      if (selected) {
        try { window.localStorage.setItem(key, selected); } catch { /* storage is optional */ }
      }
    } catch (error) {
      this.outlets.set([]);
      this.selectedOutletId.set('');
      this.error.set(error instanceof Error ? error.message : 'Unable to load tenant outlets.');
    } finally {
      this.loading.set(false);
    }
  }

  select(outletId: string, user: CurrentUser | null): boolean {
    if (!user || !this.canSelect() || !this.outlets().some(outlet => outlet.id === outletId)) return false;
    if (outletId === this.selectedOutletId()) return false;
    this.selectedOutletId.set(outletId);
    try { window.localStorage.setItem(this.storageKey(user), outletId); } catch { /* storage is optional */ }
    return true;
  }

  clear(): void {
    this.initializedUserId = '';
    this.outlets.set([]);
    this.selectedOutletId.set('');
    this.canSelect.set(false);
    this.loading.set(false);
    this.error.set('');
  }

  private storageKey(user: CurrentUser): string {
    return `brewbill.operational-outlet.${user.tenant_id}.${user.id}`;
  }
}
