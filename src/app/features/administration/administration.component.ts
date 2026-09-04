import { Component, computed, inject, signal } from '@angular/core';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { TenantAdmin } from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';

@Component({
  selector: 'app-administration',
  templateUrl: './administration.component.html',
  styles: [`
    .admin-summary { margin-bottom:14px; }
    .admin-layout { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(340px,.9fr); gap:14px; }
    .tenant-name { display:flex; align-items:center; gap:10px; }
    .tenant-logo { width:42px; height:42px; border-radius:50%; background:#f6ede5; display:grid; place-items:center; color:var(--brand-primary); font-weight:800; }
    tr.selected { background:#fff5e9; }
    .tenant-form { display:grid; gap:12px; }
    .tenant-form label { display:grid; gap:5px; color:#5f5048; font-size:12px; font-weight:700; }
    .tenant-form input { min-height:42px; border:1px solid #e4dcd5; border-radius:8px; padding:0 11px; }
    .tenant-form .color-row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    @media(max-width:980px){ .admin-layout{grid-template-columns:1fr} }
  `],
})
export class AdministrationComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly session = inject(SessionService);
  readonly tenants = signal<TenantAdmin[]>([]);
  readonly selected = signal<TenantAdmin | null>(null);
  readonly search = signal('');
  readonly loading = signal(true);
  readonly notice = signal('');
  readonly draft = signal({ name:'', tagline:'', primary_color:'#5A2D18', secondary_color:'#C8874A', logo_url:'', cover_image_url:'' });
  readonly filtered = computed(() => {
    const q = this.search().toLowerCase().trim();
    return this.tenants().filter((item) => !q || `${item.name} ${item.code}`.toLowerCase().includes(q));
  });
  readonly outlets = computed(() => this.tenants().reduce((sum, row) => sum + row.outlet_count, 0));
  readonly admins = computed(() => this.tenants().reduce((sum, row) => sum + row.admin_count, 0));

  constructor() { void this.load(); }
  async load(): Promise<void> {
    const token = this.session.accessToken(); if (!token) return;
    this.loading.set(true);
    try { this.tenants.set(await this.api.listTenants(token)); if (!this.selected() && this.tenants()[0]) this.select(this.tenants()[0]); }
    catch (error) { this.notice.set(error instanceof Error ? error.message : 'Unable to load tenants.'); }
    finally { this.loading.set(false); }
  }
  select(tenant: TenantAdmin): void {
    this.selected.set(tenant);
    this.draft.set({ name:tenant.name, tagline:tenant.tagline ?? '', primary_color:tenant.primary_color, secondary_color:'#C8874A', logo_url:tenant.logo_url ?? '', cover_image_url:'' });
  }
  patch(field: keyof ReturnType<typeof this.draft>, value:string): void { this.draft.update((draft) => ({...draft,[field]:value})); }
  async save(): Promise<void> {
    const tenant=this.selected(); const token=this.session.accessToken(); if(!tenant || !token) return;
    try { const draft=this.draft(); await this.api.updateTenantBranding(token,tenant.id,{...draft,tagline:draft.tagline||null,logo_url:draft.logo_url||null,cover_image_url:draft.cover_image_url||null}); this.notice.set('Tenant branding saved.'); await this.load(); }
    catch(error){ this.notice.set(error instanceof Error ? error.message : 'Unable to save branding.'); }
  }
  async createTenant(): Promise<void> {
    const code=window.prompt('New tenant code (for login)')?.trim().toUpperCase(); if(!code) return;
    const name=window.prompt('Café / tenant name')?.trim(); if(!name) return;
    const outletName=window.prompt('First outlet name',`${name} Main`)?.trim(); if(!outletName) return;
    const username=window.prompt('Tenant admin username','admin')?.trim(); if(!username) return;
    const password=window.prompt('Temporary admin password (minimum 8 characters)'); if(!password || password.length<8) return;
    const token=this.session.accessToken(); if(!token) return;
    try {
      const tenant=await this.api.createTenant(token,{code,name,outlet_code:'MAIN',outlet_name:outletName,outlet_address:null,admin_username:username,admin_password:password,admin_display_name:`${name} Admin`,plan_code:'PROFESSIONAL'});
      this.notice.set(`${tenant.name} created with isolated tenant and outlet records.`); await this.load(); this.select(tenant);
    } catch(error){ this.notice.set(error instanceof Error ? error.message : 'Unable to create tenant.'); }
  }
}
