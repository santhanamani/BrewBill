import { Component, HostListener, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationCancel, NavigationEnd, NavigationError, NavigationStart, Router, RouterLink, RouterOutlet } from '@angular/router';
import { SessionService } from '../../core/session.service';
import { ClockService } from '../../core/clock.service';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { BrewBillApiService } from '../../core/brew-bill-api.service';

@Component({
  selector: 'app-shell',
  imports: [RouterLink, RouterOutlet],
  templateUrl: './shell.component.html',
})
export class ShellComponent {
  readonly session = inject(SessionService);
  readonly clock = inject(ClockService);
  private readonly runtime = inject(RuntimeConfigService);
  private readonly router = inject(Router);
  private readonly api = inject(BrewBillApiService);
  readonly navigationError = signal('');
  readonly navigating = signal(false);
  readonly marketplaceUnread = signal(0);
  private failedPath = '';

  constructor() {
    this.router.events.pipe(takeUntilDestroyed()).subscribe((event) => {
      if (event instanceof NavigationStart) {
        this.navigating.set(true);
        this.navigationError.set('');
      } else if (event instanceof NavigationError) {
        this.navigating.set(false);
        this.failedPath = event.url;
        this.navigationError.set('Unable to open this page. Retry, or reload the app to load the latest version.');
      } else if (event instanceof NavigationEnd || event instanceof NavigationCancel) {
        this.navigating.set(false);
      }
    });
    if (this.marketplaceEnabled()) {
      void this.pollMarketplace();
      window.setInterval(() => void this.pollMarketplace(), 15000);
    }
  }

  marketplaceEnabled(): boolean { return !this.session.isSuperAdmin() && this.session.context()?.plan_code === 'ULTRA_PROFESSIONAL'; }

  private async pollMarketplace(): Promise<void> {
    const token=this.session.accessToken();const userId=this.session.user()?.id;
    if(!token||!userId||!this.marketplaceEnabled())return;
    try{
      const orders=await this.api.listMarketplaceOrders(token);const received=orders.filter(order=>order.status==='RECEIVED');this.marketplaceUnread.set(received.length);
      const key=`brewbill.marketplace.seen.${userId}`;let seen:string[]=[];try{seen=JSON.parse(localStorage.getItem(key)??'[]');}catch{}
      const known=new Set(seen);const fresh=received.filter(order=>!known.has(order.id));
      for(const order of fresh.slice(0,3)){if('Notification'in window&&Notification.permission==='granted')new Notification(`New ${order.provider} order`,{body:`${order.external_order_id} · ${order.items.length} items`});known.add(order.id);}
      try{localStorage.setItem(key,JSON.stringify([...known].slice(-250)));}catch{}
    }catch{/* Notification polling must never interrupt billing. */}
  }

  async logout(): Promise<void> {
    this.session.clear();
    await this.router.navigateByUrl('/login');
  }

  async openPage(path: string): Promise<void> {
    try {
      await this.router.navigateByUrl(path, { onSameUrlNavigation: 'reload' });
    } catch {
      this.failedPath = path;
      this.navigating.set(false);
      this.navigationError.set('Unable to open this page. Retry, or reload the app to load the latest version.');
    }
  }

  retryPage(): Promise<void> {
    return this.openPage(this.failedPath || this.router.url);
  }

  reloadApp(): void {
    window.location.reload();
  }

  isActive(path: string): boolean {
    return this.router.url === path;
  }

  roleLabel(): string {
    const role = this.session.user()?.role_code;
    if (role === 'SUPER_ADMIN') return 'Super Administrator';
    if (role === 'ADMIN' || role === 'TENANT_ADMIN') return 'Administrator';
    return 'Cashier';
  }

  brandLabel(): string {
    const context = this.session.context();
    return context?.branding?.display_name?.trim()
      || context?.tenant_name?.trim()
      || context?.outlet_name?.trim()
      || 'BrewBill';
  }

  asset(path: string): string {
    return this.runtime.assetUrl(path);
  }

  logoAsset(): string {
    return this.asset(this.session.context()?.branding.logo_url ?? 'brand/logo.svg');
  }

  @HostListener('document:keydown', ['$event'])
  onFunctionKey(event: KeyboardEvent): void {
    if (this.session.isSuperAdmin() || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    const routes: Record<string, string> = {
      F1: '/dashboard',
      F2: '/pos',
      F3: '/operations/holds',
      F4: '/management/purchases',
      F5: '/products',
      F6: '/operations/inventory',
      F7: '/management/expenses',
      F8: '/operations/reports',
      F9: '/management/settings',
    };
    const route = routes[event.key];
    if (!route || (!this.session.isAdmin() && ['F4', 'F5', 'F6', 'F7', 'F9'].includes(event.key))) return;
    event.preventDefault();
    void this.openPage(route);
  }
}
