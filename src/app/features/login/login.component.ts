import { Component, OnDestroy, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { SessionService } from '../../core/session.service';
import { ClockService } from '../../core/clock.service';
import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { TenantPreview } from '../../core/models/api.models';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent implements OnDestroy {
  private readonly api = inject(BrewBillApiService);
  private readonly route = inject(ActivatedRoute);
  readonly runtime = inject(RuntimeConfigService);
  readonly tenantCode = signal(this.route.snapshot.queryParamMap.get('tenant') ?? this.runtime.config().tenantCode ?? '');
  readonly tenant = signal<TenantPreview | null>(null);
  readonly resolving = signal(false);
  readonly tenantError = signal('');
  readonly logoFailed = signal(false);
  readonly coverFailed = signal(false);
  private lookupVersion = 0;
  private lookupTimer: ReturnType<typeof setTimeout> | undefined;
  private destroyed = false;

  ngOnDestroy():void { this.destroyed=true;this.lookupVersion++;clearTimeout(this.lookupTimer); }

  changeTenantCode(value:string):void {
    if(this.loading())return;
    clearTimeout(this.lookupTimer);this.lookupVersion++;
    this.tenantCode.set(value);this.tenant.set(null);this.resolving.set(false);
    this.logoFailed.set(false);this.coverFailed.set(false);
    this.tenantError.set('');this.error.set('');this.password.set('');
    this.mfaChallenge.set(null);this.verificationCode.set('');
    if(value.trim().length>=2)this.lookupTimer=setTimeout(()=>void this.resolveTenant(),400);
  }

  verifiedTenant():boolean {
    const cafe=this.tenant();
    return !!cafe && cafe.code.trim().toUpperCase()===this.tenantCode().trim().toUpperCase() && cafe.status==='ACTIVE';
  }

  canTenantLogin():boolean { return this.verifiedTenant() && !!this.tenant()?.login_allowed; }
  subscriptionNeedsAttention():boolean { return ['EXPIRING_SOON','GRACE','EXPIRED','NOT_STARTED'].includes(this.tenant()?.subscription_state ?? ''); }
  subscriptionTone():string { return (this.tenant()?.subscription_state ?? 'ACTIVE').toLowerCase().replace('_','-'); }
  formatDate(value:string|null|undefined):string {
    if(!value)return 'not available';
    return new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
  }
  openSubscription():void { void this.router.navigate(['/subscribe'],{queryParams:{tenant:this.tenantCode().trim().toUpperCase()}}); }

  logoUrl():string {
    return this.runtime.assetUrl(!this.logoFailed() && this.verifiedTenant() ? this.tenant()?.logo_url || 'brand/logo.svg' : 'brand/logo.svg');
  }

  coverUrl():string {
    return this.runtime.assetUrl(!this.coverFailed() && this.verifiedTenant() ? this.tenant()?.cover_image_url || 'brand/login-hero.png' : 'brand/login-hero.png');
  }
  readonly username = signal('');
  readonly password = signal('');
  readonly error = signal('');
  readonly loading = signal(false);
  readonly mfaChallenge = signal<{token:string;setup:boolean;secret:string|null;uri:string|null}|null>(null);
  readonly verificationCode = signal('');
  readonly clock = inject(ClockService);

  constructor(
    readonly session: SessionService,
    private readonly router: Router,
  ) { void this.resolveTenant(); }

  async resolveTenant(): Promise<void> {
    if(this.loading())return;
    clearTimeout(this.lookupTimer);
    const code=this.tenantCode().trim().toUpperCase(),version=++this.lookupVersion;
    this.tenant.set(null);this.logoFailed.set(false);this.coverFailed.set(false);
    this.tenantError.set('');
    if(code.length<2||code.length>32){
      this.resolving.set(false);
      this.tenantError.set('Enter the café code supplied by your administrator (2-32 characters).');return;
    }
    this.resolving.set(true);
    try {
      const cafe=await this.api.resolveTenant(code);
      if(this.destroyed||version!==this.lookupVersion||code!==this.tenantCode().trim().toUpperCase())return;
      if(cafe.status!=='ACTIVE'){
        this.tenantError.set('This café account is inactive. Please contact your administrator.');return;
      }
      this.tenant.set(cafe);
    }catch(error){
      if(version!==this.lookupVersion||this.destroyed)return;
      const status=(error as {status?:number})?.status;
      this.tenantError.set(status===404 ? 'Café code not found. Check the code or ask your café administrator.' :
        status===422 ? 'Enter a valid café code (2-32 characters).' :
        'Unable to verify your café. Check the connection and retry.');
    }finally{if(version===this.lookupVersion&&!this.destroyed)this.resolving.set(false);}
  }
  async retrySession():Promise<void> {
    if(this.loading())return;
    this.loading.set(true);
    try {
      await this.session.restore();
      if(this.session.isAuthenticated())await this.router.navigateByUrl(this.session.isSuperAdmin()?'/administration':this.session.user()?.role_code==='CASHIER'?'/pos':'/dashboard');
    } finally {this.loading.set(false);}
  }
  async login(): Promise<void> {
    if (this.loading() || this.resolving()) return;
    if (!this.verifiedTenant()) {
      this.tenantError.set('Verify an active café code before signing in.');
      return;
    }
    if (!this.canTenantLogin()) { this.openSubscription(); return; }
    this.error.set('');
    this.loading.set(true);
    try {
      const challenge = await this.session.login(this.username().trim(), this.password(), this.tenantCode().trim());
      if (challenge) {
        this.mfaChallenge.set({token:challenge.challenge_token, setup:challenge.setup_required, secret:challenge.setup_secret, uri:challenge.otpauth_uri});
        return;
      }
      const role = this.session.user()?.role_code;
      await this.router.navigateByUrl(
        role === 'SUPER_ADMIN' ? '/administration' : role === 'CASHIER' ? '/pos' : '/dashboard',
      );
    } catch (error) {
      const status=(error as {status?:number})?.status;
      if(status===402){this.openSubscription();return;}
      const detail=(error as {error?:{detail?:string|{message?:string}}})?.error?.detail;
      this.error.set(typeof detail==='string'?detail:detail?.message || (error instanceof Error ? error.message : 'Unable to sign in.'));
    } finally {
      this.loading.set(false);
    }
  }

  async verifySecondStep(): Promise<void> {
    const challenge = this.mfaChallenge();
    if (!challenge || this.loading()) return;
    this.loading.set(true); this.error.set('');
    try {
      await this.session.verifyMfa(challenge.token, this.verificationCode().trim());
      await this.router.navigateByUrl('/administration');
    } catch (error) {
      this.error.set(error instanceof Error ? error.message : 'Unable to verify this code.');
    } finally { this.loading.set(false); }
  }
}
