import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { SessionService } from '../../core/session.service';
import { ClockService } from '../../core/clock.service';
import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { TenantPreview } from '../../core/models/api.models';

@Component({
  selector: 'app-login',
  imports: [FormsModule],
  templateUrl: './login.component.html',
})
export class LoginComponent {
  private readonly api = inject(BrewBillApiService);
  readonly runtime = inject(RuntimeConfigService);
  readonly tenantCode = signal(this.runtime.config().tenantCode ?? '');
  readonly tenant = signal<TenantPreview | null>(null);
  readonly resolving = signal(false);
  readonly username = signal('');
  readonly password = signal('');
  readonly error = signal('');
  readonly loading = signal(false);
  readonly mfaChallenge = signal<{token:string;setup:boolean;secret:string|null;uri:string|null}|null>(null);
  readonly verificationCode = signal('');
  readonly clock = inject(ClockService);

  constructor(
    private readonly session: SessionService,
    private readonly router: Router,
  ) { void this.resolveTenant(); }

  async resolveTenant(): Promise<void> {
    const code = this.tenantCode().trim();
    if (code.length < 2 || this.resolving()) return;
    this.resolving.set(true);
    this.error.set('');
    try { this.tenant.set(await this.api.resolveTenant(code)); }
    catch (error) { this.tenant.set(null); this.error.set(error instanceof Error ? error.message : 'Cafe code was not found.'); }
    finally { this.resolving.set(false); }
  }

  async login(): Promise<void> {
    if (this.loading()) return;
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
      this.error.set(error instanceof Error ? error.message : 'Unable to sign in.');
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
