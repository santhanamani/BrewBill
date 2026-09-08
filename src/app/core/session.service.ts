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
  readonly restoreMessage = signal('');
  private lifecycle = 0;
  readonly isAuthenticated = computed(() => this.accessToken() !== null && this.user() !== null);
  readonly isAdmin = computed(() =>
    ['ADMIN', 'TENANT_ADMIN', 'SUPER_ADMIN'].includes(this.user()?.role_code ?? ''),
  );
  readonly isSuperAdmin = computed(() => this.user()?.role_code === 'SUPER_ADMIN');
  private licenseRefreshTimer: number | undefined;
  private licenseRefreshPromise: Promise<boolean> | null = null;

  constructor(private readonly api: BrewBillApiService) {}

  async restore():Promise<void> {
    if(this.isAuthenticated())return;
    const lifecycle=this.lifecycle;
    this.restoreMessage.set('');
    if(!this.tokenStore.restore())return;
    try {
      const token=this.accessToken()!;
      const [user,context]=await Promise.all([this.api.getCurrentUser(token),this.api.getPlatformContext(token)]);
      if(lifecycle!==this.lifecycle)return;
      if(!this.accessToken() || !this.refreshToken())return;
      this.validateContext(user,context);
      this.activate({access_token:this.accessToken()!,refresh_token:this.refreshToken()!},user,context,true);
    } catch(error) {
      if(lifecycle!==this.lifecycle)return;
      const status=(error as {status?:number})?.status;
      if(status===401||status===403){this.clear();this.restoreMessage.set('Your session has expired. Please sign in again.');}
      else if(status===402){this.clear();this.restoreMessage.set('Your subscription renewal is required before you can sign in.');}
      else this.restoreMessage.set('Unable to restore your session. Check the server connection and retry.');
    }
  }
  private validateContext(user:CurrentUser,context:PlatformContext):void {
    if(user.tenant_id!==context.tenant_id || user.outlet_id!==context.outlet_id)
      throw Object.assign(new Error('Session context mismatch. Sign in again.'),{status:401});
  }

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
    const lifecycle=++this.lifecycle;
    const result = await this.cloudResult(username, password, tenantCode);
    if(lifecycle!==this.lifecycle)throw new Error('Sign-in was cancelled.');
    if ('status' in result) return result;
    await this.applyCloudSession(result, result.user, lifecycle);
    return null;
  }

  async verifyMfa(challengeToken:string, code:string):Promise<void>{
    const lifecycle=++this.lifecycle;
    const result=await this.api.verifyMfa(challengeToken,code);
    if(lifecycle!==this.lifecycle)throw new Error('Sign-in was cancelled.');
    await this.applyCloudSession(result,result.user,lifecycle);
  }

  private async applyCloudSession(
    tokens: { access_token: string; refresh_token: string },
    user: CurrentUser,
    lifecycle: number,
  ): Promise<void> {
    const context = await this.api.getPlatformContext(tokens.access_token);
    if(lifecycle!==this.lifecycle)throw new Error('Sign-in was cancelled.');
    this.validateContext(user,context);
    this.activate(tokens,user,context,true);
  }

  private activate(tokens:{access_token:string;refresh_token:string}, user:CurrentUser, context:PlatformContext, verifyLicense:boolean):void {
    this.restoreMessage.set('');
    this.tokenStore.set(tokens);
    this.user.set(user);
    this.context.set(context);
    const root = document.documentElement;
    root.style.setProperty('--brand-primary', context.branding.primary_color ?? '#5A2D18');
    root.style.setProperty('--brand-secondary', context.branding.secondary_color ?? '#C8874A');
    this.licenseMessage.set('');
    if(verifyLicense)void this.ensureDesktopLicense();
    if (this.licenseRefreshTimer) window.clearInterval(this.licenseRefreshTimer);
    this.licenseRefreshTimer = window.setInterval(
      () => void this.ensureDesktopLicense(),
      6 * 60 * 60 * 1000,
    );
  }

  clear(): void {
    this.lifecycle++;this.restoreMessage.set('');
    if (this.licenseRefreshTimer) window.clearInterval(this.licenseRefreshTimer);
    this.licenseRefreshTimer = undefined;
    this.tokenStore.clear();
    this.user.set(null);
    this.context.set(null);
    this.licenseMessage.set('');
  }

  async ensureDesktopLicense(): Promise<boolean> {
    if (!window.brewBill) return true;
    const accessToken = this.accessToken();
    if (!accessToken) {
      this.licenseMessage.set('Sign in again to activate this POS terminal.');
      return false;
    }
    if (this.licenseRefreshPromise) return this.licenseRefreshPromise;

    const lifecycle = this.lifecycle;
    const refresh = this.activateDesktopLicense(accessToken, lifecycle);
    this.licenseRefreshPromise = refresh;
    try {
      return await refresh;
    } finally {
      if (this.licenseRefreshPromise === refresh) this.licenseRefreshPromise = null;
    }
  }

  private async activateDesktopLicense(accessToken: string, lifecycle: number): Promise<boolean> {
    try {
      const identity = await window.brewBill!.license.identity();
      const envelope = await this.api.activateDevice(accessToken, {
        installation_id: identity.installationId,
        terminal_code: identity.terminalCode,
        terminal_name: `BrewBill ${identity.terminalCode}`,
      });
      if (lifecycle !== this.lifecycle || accessToken !== this.accessToken()) return false;
      const license = await window.brewBill!.license.install(envelope);
      if (lifecycle !== this.lifecycle || accessToken !== this.accessToken()) return false;
      this.licenseMessage.set(license.message);
      return license.canCreateBills;
    } catch (error) {
      if (lifecycle === this.lifecycle) {
        this.licenseMessage.set(
          error instanceof Error ? error.message : 'Device license verification failed.',
        );
      }
      return false;
    }
  }
}
