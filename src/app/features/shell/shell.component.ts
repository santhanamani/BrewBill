import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { SessionService } from '../../core/session.service';
import { ClockService } from '../../core/clock.service';
import { RuntimeConfigService } from '../../core/runtime-config.service';

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

  async logout(): Promise<void> {
    this.session.clear();
    await this.router.navigateByUrl('/login');
  }

  async openPage(path: string): Promise<void> {
    if (this.router.url === path) return;
    await this.router.navigateByUrl(path);
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

  asset(path: string): string {
    return this.runtime.assetUrl(path);
  }

  logoAsset(): string {
    return this.asset(this.session.context()?.branding.logo_url ?? 'brand/logo.svg');
  }
}
