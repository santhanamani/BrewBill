import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { TenantPreview } from '../../core/models/api.models';
import { RuntimeConfigService } from '../../core/runtime-config.service';

@Component({
  selector: 'app-subscription',
  templateUrl: './subscription.component.html',
  styleUrl: './subscription.component.css',
})
export class SubscriptionComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly runtime = inject(RuntimeConfigService);
  readonly tenantCode = signal((this.route.snapshot.queryParamMap.get('tenant') ?? '').trim().toUpperCase());
  readonly tenant = signal<TenantPreview | null>(null);
  readonly loading = signal(false);
  readonly message = signal('');

  constructor() { void this.checkStatus(); }

  async checkStatus(): Promise<void> {
    const code = this.tenantCode();
    if (!code) { this.message.set('Enter your tenant code on the login screen to check subscription status.'); return; }
    this.loading.set(true); this.message.set('');
    try {
      const tenant = await this.api.resolveTenant(code);
      this.tenant.set(tenant);
      if (tenant.login_allowed) {
        await this.router.navigate(['/login'], { queryParams: { tenant: tenant.code } });
      }
    } catch {
      this.message.set('Unable to check the subscription. Verify the connection or tenant code and retry.');
    } finally { this.loading.set(false); }
  }

  backToLogin(): void {
    void this.router.navigate(['/login'], { queryParams: this.tenantCode() ? { tenant: this.tenantCode() } : {} });
  }

  formatDate(value: string | null): string {
    if (!value) return 'Not available';
    return new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
  }

  logoUrl(): string { return this.runtime.assetUrl(this.tenant()?.logo_url || 'brand/logo.svg'); }
}
