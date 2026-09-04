import { Injectable, computed, inject, signal } from '@angular/core';
import { BrewBillApiService } from './brew-bill-api.service';
import { CurrentUser, MfaChallenge, PlatformContext } from './models/api.models';
import { AuthTokenStoreService } from './auth-token-store.service';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly tokenStore = inject(AuthTokenStoreService);
  readonly accessToken = this.tokenStore.accessToken;
  readonly refreshToken = this.tokenStore.refreshToken;
  readonly user = signal<CurrentUser | null>(null);
  readonly context = signal<PlatformContext | null>(null);
  readonly licenseMessage = signal('');
  readonly isAuthenticated = computed(() => this.accessToken() !== null && this.user() !== null);
  readonly isAdmin = computed(() =>
    ['ADMIN', 'TENANT_ADMIN', 'SUPER_ADMIN'].includes(this.user()?.role_code ?? ''),
  );
  readonly isSuperAdmin = computed(() => this.user()?.role_code === 'SUPER_ADMIN');
  private licenseRefreshTimer: number | undefined;

  constructor(private readonly api: BrewBillApiService) {}

  async login(
    username: string,
    password: string,
    tenantCode?: string,
  ): Promise<MfaChallenge | null> {
    return this.loginCloud(username, password, tenantCode);
  }

  private async cloudResult(username: string, password: string, tenantCode?: string) {
    const tokens = await this.api.login(username, password, tenantCode);
    return tokens;
  }

  private async loginCloud(
    username: string,
    password: string,
    tenantCode?: string,
  ): Promise<MfaChallenge | null> {
    const result = await this.cloudResult(username, password, tenantCode);
    if ('status' in result) return result;
    await this.applyCloudSession(result, result.user);
    return null;
  }

  async verifyMfa(challengeToken:string, code:string):Promise<void>{
    const result=await this.api.verifyMfa(challengeToken,code);
    await this.applyCloudSession(result,result.user);
  }

  private async applyCloudSession(
    tokens: { access_token: string; refresh_token: string },
    user: CurrentUser,
  ): Promise<void> {
    const context = await this.api.getPlatformContext(tokens.access_token);
    this.tokenStore.set(tokens);
    this.user.set(user);
    this.context.set(context);
    const root = document.documentElement;
    root.style.setProperty('--brand-primary', context.branding.primary_color ?? '#5A2D18');
    root.style.setProperty('--brand-secondary', context.branding.secondary_color ?? '#C8874A');
    this.licenseMessage.set('');
    void this.refreshDesktopLicense(tokens.access_token);
    if (this.licenseRefreshTimer) window.clearInterval(this.licenseRefreshTimer);
    this.licenseRefreshTimer = window.setInterval(
      () => void this.refreshDesktopLicense(this.accessToken()),
      6 * 60 * 60 * 1000,
    );
  }

  clear(): void {
    if (this.licenseRefreshTimer) window.clearInterval(this.licenseRefreshTimer);
    this.licenseRefreshTimer = undefined;
    this.tokenStore.clear();
    this.user.set(null);
    this.context.set(null);
    this.licenseMessage.set('');
  }

  private async refreshDesktopLicense(accessToken: string | null): Promise<void> {
    if (!window.brewBill || !accessToken) return;
    try {
      const identity = await window.brewBill.license.identity();
      const envelope = await this.api.activateDevice(accessToken, {
        installation_id: identity.installationId,
        terminal_code: identity.terminalCode,
        terminal_name: `BrewBill ${identity.terminalCode}`,
      });
      const license = await window.brewBill.license.install(envelope);
      this.licenseMessage.set(license.message);
    } catch (error) {
      this.licenseMessage.set(
        error instanceof Error ? error.message : 'Device license verification failed.',
      );
    }
  }
}
