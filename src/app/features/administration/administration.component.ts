import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { RuntimeConfigService } from '../../core/runtime-config.service';
import { Component, computed, inject, signal } from '@angular/core';

import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { AdminOutlet, AdminUser, CurrencyDefinition, GlobalProduct, TenantAdmin, TenantPaymentPolicy, TenantSubscription } from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';

type AdminTab = 'tenants' | 'outlets' | 'products' | 'users' | 'branding';
type ModalType = 'tenant' | 'tenant-edit' | 'outlet' | 'outlet-edit' | 'user' | 'product' | null;

@Component({ selector: 'app-administration', imports: [NgTemplateOutlet], templateUrl: './administration.component.html' })
export class AdministrationComponent {
  private readonly api = inject(BrewBillApiService);
  private readonly session = inject(SessionService);
  readonly runtime = inject(RuntimeConfigService);
  readonly saving = signal(false);
  readonly uploadingBrand = signal<'logo' | 'cover' | null>(null);
  readonly savingBrand = signal(false);
  readonly brandFeedback = signal('');
  private brandSelectionVersion = 0;
  readonly formError = signal('');
  readonly editingProductId = signal<string | null>(null);
  readonly detailTab = signal<'overview' | 'branding' | 'payments' | 'subscription'>('branding');
  readonly currencies = signal<CurrencyDefinition[]>([]);
  readonly tenantCurrencyCode = signal('INR');
  readonly currencySaving = signal(false);
  readonly currencyFeedback = signal('');
  readonly tenantPaymentMode = signal<TenantPaymentPolicy['payment_processing_mode']>('MANUAL_ALLOWED');
  readonly paymentPolicyLoading = signal(false);
  readonly paymentPolicySaving = signal(false);
  readonly paymentPolicyFeedback = signal('');
  readonly tenantSubscription = signal<TenantSubscription | null>(null);
  readonly subscriptionLoading = signal(false);
  readonly subscriptionSaving = signal(false);
  readonly subscriptionFeedback = signal('');
  readonly subscriptionExpiryDraft = signal('');
  readonly subscriptionGraceDraft = signal('');
  readonly productMenu = signal<string | null>(null);
  readonly tenants = signal<TenantAdmin[]>([]);
  readonly outlets = signal<AdminOutlet[]>([]);
  readonly users = signal<AdminUser[]>([]);
  readonly products = signal<GlobalProduct[]>([]);
  readonly selected = signal<TenantAdmin | null>(null);
  readonly tab = signal<AdminTab>('tenants');
  readonly search = signal('');
  readonly filtersOpen = signal(false);
  readonly statusFilter = signal('ALL');
  readonly categoryFilter = signal('ALL');
  readonly pageIndex = signal(0);
  readonly pageSize = signal(10);
  readonly loading = signal(true);
  readonly notice = signal('');
  readonly modal = signal<ModalType>(null);
  readonly form = signal<Record<string, string | boolean>>({});
  readonly draft = signal({ name:'', tagline:'', primary_color:'#5A2D18', secondary_color:'#C8874A', logo_url:'', cover_image_url:'', phone:'', email:'', website:'' });

  readonly filteredTenants = computed(() => this.filter(this.tenants(), row => `${row.name} ${row.code} ${row.status}`).filter(row => this.matchesStatus(row.status)));
  readonly filteredOutlets = computed(() => this.filter(this.outlets(), row => `${row.name} ${row.code} ${this.tenantName(row.tenant_id)} ${row.address ?? ''}`));
  readonly filteredUsers = computed(() => this.filter(this.users(), row => `${row.display_name} ${row.username} ${row.email ?? ''} ${row.phone ?? ''} ${row.tenant_name} ${row.outlet_name} ${row.role_code}`).filter(row => this.matchesStatus(row.is_active ? 'ACTIVE' : 'INACTIVE')));
  readonly filteredProducts = computed(() => this.filter(this.products(), row => `${row.name} ${row.code} ${row.category_name} ${row.status}`).filter(row => this.matchesStatus(row.status) && (this.categoryFilter() === 'ALL' || row.category_name === this.categoryFilter())));
  readonly productCategories = computed(() => [...new Set(this.products().map(row => row.category_name))].sort());
  readonly resultCount = computed(() => this.tab() === 'products' ? this.filteredProducts().length : this.tab() === 'users' ? this.filteredUsers().length : this.tab() === 'outlets' ? this.filteredOutlets().length : this.filteredTenants().length);
  readonly pageCount = computed(() => Math.max(1, Math.ceil(this.resultCount() / this.pageSize())));
  readonly currentPage = computed(() => Math.min(this.pageIndex(), this.pageCount() - 1));
  readonly pageStart = computed(() => this.currentPage() * this.pageSize());
  readonly pageEnd = computed(() => Math.min(this.pageStart() + this.pageSize(), this.resultCount()));
  readonly tenantRows = computed(() => this.page(this.filteredTenants()));
  readonly outletRows = computed(() => this.page(this.filteredOutlets()));
  readonly userRows = computed(() => this.page(this.filteredUsers()));
  readonly productRows = computed(() => this.page(this.filteredProducts()));
  readonly activeTenants = computed(() => this.tenants().filter(row => row.status === 'ACTIVE').length);
  readonly adminUsers = computed(() => this.users().filter(row => ['ADMIN','TENANT_ADMIN'].includes(row.role_code) && row.is_active).length);
  readonly activeUsers = computed(() => this.users().filter(row => row.is_active).length);
  readonly activeProducts = computed(() => this.products().filter(row => row.status === 'ACTIVE').length);
  readonly inactiveProducts = computed(() => this.products().filter(row => row.status !== 'ACTIVE').length);

  constructor() { void this.load(); }

  private filter<T>(rows:T[], text:(row:T)=>string):T[]{ const q=this.search().trim().toLowerCase(); return rows.filter(row=>!q || text(row).toLowerCase().includes(q)); }
  private page<T>(rows:T[]):T[]{ return rows.slice(this.pageStart(), this.pageEnd()); }
  private matchesStatus(status:string):boolean { return this.statusFilter() === 'ALL' || this.statusFilter() === status; }
  setSearch(value:string):void { this.search.set(value); this.pageIndex.set(0); this.productMenu.set(null); }
  resetFilters():void { this.setSearch(''); this.statusFilter.set('ALL'); this.categoryFilter.set('ALL'); }
  changePage(delta:number):void { this.pageIndex.set(Math.max(0,Math.min(this.currentPage()+delta,this.pageCount()-1))); this.productMenu.set(null); }
  setPageSize(value:string):void { const size=Number(value); if([5,10,25,50].includes(size)){this.pageSize.set(size);this.pageIndex.set(0);} }
  exportRows():void {
    let rows: (string | number | null)[][];
    if(this.tab()==='products') rows=[['Code','Product','Category','Base Unit','GST (%)','Status'],...this.filteredProducts().map(row=>[row.code,row.name,row.category_name,row.base_unit,row.default_gst,row.status])];
    else if(this.tab()==='users') rows=[['Name','Username','Role','Tenant','Outlet','Status'],...this.filteredUsers().map(row=>[row.display_name,row.username,row.role_code,row.tenant_name,row.outlet_name,row.is_active?'ACTIVE':'INACTIVE'])];
    else if(this.tab()==='outlets') rows=[['Code','Outlet','Tenant','Address'],...this.filteredOutlets().map(row=>[row.code,row.name,this.tenantName(row.tenant_id),row.address])];
    else rows=[['Tenant Code','Cafe','Outlets','Admin Users','Status'],...this.filteredTenants().map(row=>[row.code,row.name,row.outlet_count,row.admin_count,row.status])];
    const csv=rows.map(row=>row.map(value=>{let cell=String(value??'');if(/^[\s]*[=+@-]/.test(cell))cell="'"+cell;return '"'+cell.replaceAll('"','""')+'"';}).join(',')).join('\r\n');
    const url=URL.createObjectURL(new Blob(['\uFEFF',csv],{type:'text/csv;charset=utf-8'}));
    const link=document.createElement('a');link.href=url;link.download=`brew-haven-${this.tab()}.csv`;document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
    this.notice.set(`${rows.length-1} matching records exported.`);
  }
  private token():string|null { return this.session.accessToken(); }
  tenantName(id:string):string { return this.tenants().find(row=>row.id===id)?.name ?? '—'; }
  shortDate(value:string):string { return value ? value.slice(0,10) : '—'; }

  async load():Promise<void>{
    const token=this.token(); if(!token)return; this.loading.set(true);
    try{
      const [tenants,outlets,users,products,currencies]=await Promise.all([this.api.listTenants(token),this.api.listAdminOutlets(token),this.api.listAdminUsers(token),this.api.listGlobalProducts(token, true),this.api.listCurrencies(token)]);
      this.tenants.set(tenants); this.outlets.set(outlets); this.users.set(users); this.products.set(products); this.currencies.set(currencies);
      const current=this.selected(); const selected=tenants.find(row=>row.id===current?.id) ?? tenants[0] ?? null; if(selected)this.select(selected);
    }catch(error){this.notice.set(error instanceof Error?error.message:'Unable to load platform administration.');}
    finally{this.loading.set(false);}
  }

  select(tenant:TenantAdmin):void{
    const version=++this.brandSelectionVersion;
    this.brandFeedback.set('');
    this.paymentPolicyFeedback.set('');
    this.subscriptionFeedback.set('');
    this.currencyFeedback.set('');
    this.tenantSubscription.set(null);
    this.selected.set(tenant);
    this.tenantCurrencyCode.set(tenant.currency_code || 'INR');
    this.draft.set({name:tenant.name,tagline:tenant.tagline??'',primary_color:tenant.primary_color,secondary_color:tenant.secondary_color,logo_url:tenant.logo_url??'',cover_image_url:tenant.cover_image_url??'',phone:tenant.phone??'',email:tenant.email??'',website:tenant.website??''});
    void this.loadTenantPaymentPolicy(tenant.id,version);
    void this.loadTenantSubscription(tenant.id,version);
  }

  async loadTenantPaymentPolicy(tenantId:string,version=this.brandSelectionVersion):Promise<void>{
    const token=this.token();if(!token)return;
    this.paymentPolicyLoading.set(true);
    try{
      const policy=await this.api.getTenantPaymentPolicy(token,tenantId);
      if(this.selected()?.id===tenantId&&version===this.brandSelectionVersion)this.tenantPaymentMode.set(policy.payment_processing_mode);
    }catch(error){
      if(this.selected()?.id===tenantId&&version===this.brandSelectionVersion)this.paymentPolicyFeedback.set(this.errorMessage(error));
    }finally{
      if(this.selected()?.id===tenantId&&version===this.brandSelectionVersion)this.paymentPolicyLoading.set(false);
    }
  }

  async saveTenantPaymentPolicy():Promise<void>{
    const token=this.token(),tenant=this.selected(),version=this.brandSelectionVersion;
    if(!token||!tenant||this.paymentPolicySaving())return;
    this.paymentPolicySaving.set(true);this.paymentPolicyFeedback.set('');
    try{
      const saved=await this.api.updateTenantPaymentPolicy(token,tenant.id,this.tenantPaymentMode());
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion){
        this.tenantPaymentMode.set(saved.payment_processing_mode);
        this.paymentPolicyFeedback.set(`Payment mode saved for ${tenant.code} only.`);
      }
    }catch(error){
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.paymentPolicyFeedback.set(this.errorMessage(error));
    }finally{
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.paymentPolicySaving.set(false);
    }
  }
  async saveTenantCurrency():Promise<void>{
    const token=this.token(),tenant=this.selected(),version=this.brandSelectionVersion;
    if(!token||!tenant||this.currencySaving())return;
    const selectedCurrency=this.currencies().find(row=>row.code===this.tenantCurrencyCode());
    if(!selectedCurrency){this.currencyFeedback.set('Choose a valid currency from the master list.');return;}
    this.currencySaving.set(true);this.currencyFeedback.set('');
    try{
      const saved=await this.api.updateTenantCurrency(token,tenant.id,selectedCurrency.code);
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion){
        const changed={...tenant,currency_code:saved.code};
        this.selected.set(changed);this.tenants.update(rows=>rows.map(row=>row.id===tenant.id?changed:row));
        this.tenantCurrencyCode.set(saved.code);
        this.currencyFeedback.set(`${saved.name} (${saved.code}) saved for ${tenant.code} only.`);
      }
    }catch(error){
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.currencyFeedback.set(this.errorMessage(error));
    }finally{
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.currencySaving.set(false);
    }
  }
  private toDateTimeInput(value:string|null):string {
    if(!value)return '';
    const date=new Date(value);if(Number.isNaN(date.getTime()))return '';
    return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16);
  }
  formatSubscriptionDate(value:string|null):string {
    if(!value)return 'Not configured';
    return new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
  }
  subscriptionTone(state:string|null|undefined):string { return (state||'EXPIRED').toLowerCase().replace('_','-'); }

  async loadTenantSubscription(tenantId:string,version=this.brandSelectionVersion):Promise<void>{
    const token=this.token();if(!token)return;
    this.subscriptionLoading.set(true);
    try{
      const subscription=await this.api.getTenantSubscription(token,tenantId);
      if(this.selected()?.id===tenantId&&version===this.brandSelectionVersion){
        this.tenantSubscription.set(subscription);
        this.subscriptionExpiryDraft.set(this.toDateTimeInput(subscription.ends_at));
        this.subscriptionGraceDraft.set(this.toDateTimeInput(subscription.grace_ends_at));
      }
    }catch(error){
      if(this.selected()?.id===tenantId&&version===this.brandSelectionVersion)this.subscriptionFeedback.set(this.errorMessage(error));
    }finally{
      if(this.selected()?.id===tenantId&&version===this.brandSelectionVersion)this.subscriptionLoading.set(false);
    }
  }

  setRenewalMonths(months:number):void {
    const current=this.tenantSubscription()?.ends_at?new Date(this.tenantSubscription()!.ends_at!):new Date();
    const expiry=current>new Date()?current:new Date();
    expiry.setMonth(expiry.getMonth()+months);
    const grace=new Date(expiry.getTime()+7*24*60*60*1000);
    this.subscriptionExpiryDraft.set(this.toDateTimeInput(expiry.toISOString()));
    this.subscriptionGraceDraft.set(this.toDateTimeInput(grace.toISOString()));
    this.subscriptionFeedback.set(`Prepared a ${months}-month renewal with 7 days grace. Save to publish.`);
  }

  async saveTenantSubscription():Promise<void>{
    const token=this.token(),tenant=this.selected(),version=this.brandSelectionVersion;
    if(!token||!tenant||this.subscriptionSaving())return;
    const expiry=new Date(this.subscriptionExpiryDraft()),grace=new Date(this.subscriptionGraceDraft());
    if(Number.isNaN(expiry.getTime())||Number.isNaN(grace.getTime())){this.subscriptionFeedback.set('Choose both expiry and grace date/time.');return;}
    if(grace<=expiry){this.subscriptionFeedback.set('Grace end must be later than the subscription expiry.');return;}
    this.subscriptionSaving.set(true);this.subscriptionFeedback.set('');
    try{
      const saved=await this.api.updateTenantSubscription(token,tenant.id,expiry.toISOString(),grace.toISOString());
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion){
        this.tenantSubscription.set(saved);
        this.subscriptionExpiryDraft.set(this.toDateTimeInput(saved.ends_at));
        this.subscriptionGraceDraft.set(this.toDateTimeInput(saved.grace_ends_at));
        const changed={...tenant,plan_code:saved.plan_code,plan_name:saved.plan_name,subscription_state:saved.lifecycle_state,subscription_end:saved.ends_at,grace_ends_at:saved.grace_ends_at,login_allowed:saved.login_allowed};
        this.selected.set(changed);this.tenants.update(rows=>rows.map(row=>row.id===tenant.id?changed:row));
        this.subscriptionFeedback.set(`Subscription dates saved for ${tenant.code} only.`);
      }
    }catch(error){
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.subscriptionFeedback.set(this.errorMessage(error));
    }finally{
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.subscriptionSaving.set(false);
    }
  }
  setTab(tab:AdminTab):void{this.tab.set(tab);this.resetFilters();this.filtersOpen.set(false);}
  patchDraft(field:keyof ReturnType<typeof this.draft>,value:string):void{this.draft.update(row=>({...row,[field]:value}));}
  patchForm(field:string,value:string|boolean):void{this.formError.set('');this.form.update(row=>({...row,[field]:value,...(field==='tenant_id'?{outlet_id:''}:{})}));}
  editOutlet(row:AdminOutlet):void { this.open('outlet-edit');this.form.set({id:row.id,tenant_id:row.tenant_id,code:row.code,name:row.name,address:row.address??''}); }

  open(type:Exclude<ModalType,null>, item?:TenantAdmin):void{
    this.editingProductId.set(null); this.formError.set('');
    this.modal.set(type);
    if(type==='tenant')this.form.set({code:'',name:'',outlet_code:'MAIN',outlet_name:'',outlet_address:'',admin_username:'admin',admin_password:'',admin_display_name:'',plan_code:'PROFESSIONAL',currency_code:'INR'});
    if(type==='tenant-edit' && item)this.form.set({id:item.id,name:item.name,status:item.status});
    if(type==='outlet')this.form.set({tenant_id:this.selected()?.id??'',code:'',name:'',address:''});
    if(type==='user')this.form.set({tenant_id:this.selected()?.id??'',outlet_id:'',role_code:'CASHIER',username:'',display_name:'',email:'',phone:'',password:''});
    if(type==='product')this.form.set({code:'',name:'',category_name:'Coffee',base_unit:'Cup',default_gst:'5.00',image_path:'',description:'',status:'ACTIVE'});
  }
  editProduct(row:GlobalProduct):void {
    this.open('product'); this.editingProductId.set(row.id); this.productMenu.set(null);
    this.form.set({...row,description:row.description??'',image_path:row.image_path??''});
  }
  errorMessage(error:unknown):string {
    if(error instanceof HttpErrorResponse) { const detail=error.error?.detail; return typeof detail==='string'?detail:Array.isArray(detail)?detail.map((x:{msg:string})=>x.msg).join('; '):'Unable to save. Please try again.'; }
    return error instanceof Error?error.message:'Unable to save.';
  }
  async toggleProduct(row:GlobalProduct):Promise<void>{
    const token=this.token();if(!token||this.saving())return;
    this.saving.set(true);this.productMenu.set(null);
    try{await this.api.updateGlobalProduct(token,row.id,{status:row.status==='ACTIVE'?'INACTIVE':'ACTIVE'});await this.load();this.notice.set(row.name+' updated.');}
    catch(error){this.notice.set(this.errorMessage(error));}finally{this.saving.set(false);}
  }
  close():void{if(this.saving())return;this.modal.set(null);this.form.set({});}

  private duplicateError(type:Exclude<ModalType,null>, f:Record<string,string|boolean>):string {
    if(type==='tenant') {
      const code=String(f['code']).trim().toUpperCase();
      const name=String(f['name']).trim().toLocaleLowerCase();
      if(this.tenants().some(row=>row.code?.trim().toUpperCase()===code)) return `Tenant code "${code}" already exists.`;
      if(this.tenants().some(row=>row.name.trim().toLocaleLowerCase()===name)) return `Café name "${String(f['name']).trim()}" already exists.`;
    }
    if(type==='outlet') {
      const tenantId=String(f['tenant_id']);
      const code=String(f['code']).trim().toUpperCase();
      if(this.outlets().some(row=>row.tenant_id===tenantId && row.code.trim().toUpperCase()===code)) return `Outlet code "${code}" already exists for this tenant.`;
    }
    if(type==='user') {
      const tenantId=String(f['tenant_id']);
      const username=String(f['username']).trim().toLocaleLowerCase();
      if(this.users().some(row=>row.tenant_id===tenantId && row.username.trim().toLocaleLowerCase()===username)) return `Username "${String(f['username']).trim()}" already exists for this tenant.`;
    }
    return '';
  }
  async submit():Promise<void>{
    const token=this.token(), type=this.modal(), f=this.form(); if(!token||!type||this.saving())return;
    const duplicateError=this.duplicateError(type,f);
    if(duplicateError){this.formError.set(duplicateError);return;}
    this.saving.set(true); this.formError.set('');
    try{
      if(type==='tenant')await this.api.createTenant(token,{code:String(f['code']).trim().toUpperCase(),name:String(f['name']).trim(),outlet_code:String(f['outlet_code']).trim().toUpperCase(),outlet_name:String(f['outlet_name']).trim(),outlet_address:String(f['outlet_address']).trim()||null,admin_username:String(f['admin_username']).trim(),admin_password:String(f['admin_password']),admin_display_name:String(f['admin_display_name']).trim(),plan_code:String(f['plan_code']).trim().toUpperCase(),currency_code:String(f['currency_code']||'INR').toUpperCase()});
      if(type==='tenant-edit')await this.api.updateTenant(token,String(f['id']),{name:String(f['name']),status:String(f['status']) as 'ACTIVE'|'INACTIVE'});
      if(type==='outlet')await this.api.createAdminOutlet(token,{tenant_id:String(f['tenant_id']),code:String(f['code']).toUpperCase(),name:String(f['name']),address:String(f['address'])||null});
      if(type==='outlet-edit')await this.api.updateAdminOutlet(token,String(f['id']),{name:String(f['name']).trim(),address:String(f['address']).trim()||null});
      if(type==='user')await this.api.createAdminUser(token,{tenant_id:String(f['tenant_id']),outlet_id:String(f['outlet_id'])||null,role_code:String(f['role_code']) as AdminUser['role_code'],username:String(f['username']),display_name:String(f['display_name']),email:String(f['email'])||null,phone:String(f['phone'])||null,password:String(f['password'])});
      if(type==='product') {
        const body={code:String(f['code']).trim().toUpperCase(),name:String(f['name']).trim(),category_name:String(f['category_name']).trim(),base_unit:String(f['base_unit']).trim(),default_gst:Number(f['default_gst']).toFixed(2),image_path:String(f['image_path'])||null,description:String(f['description'])||null,status:String(f['status']) as 'ACTIVE'|'INACTIVE'};
        if(this.editingProductId()) { const {code,...changes}=body; await this.api.updateGlobalProduct(token,this.editingProductId()!,changes); }
        else await this.api.createGlobalProduct(token,body);
      }
      this.notice.set('Changes saved successfully.'); this.modal.set(null); this.form.set({}); await this.load();
    }catch(error){this.formError.set(this.errorMessage(error));}
    finally{this.saving.set(false);}
  }

  async toggleUser(row:AdminUser):Promise<void>{const token=this.token();if(!token)return;try{await this.api.updateAdminUser(token,row.id,{is_active:!row.is_active});await this.load();}catch(error){this.notice.set(error instanceof Error?error.message:'Unable to update user.');}}
  async uploadBrandImage(kind:'logo'|'cover', event:Event):Promise<void> {
    const input=event.target as HTMLInputElement;
    const file=input.files?.[0]; input.value='';
    const tenant=this.selected(),token=this.token(),version=this.brandSelectionVersion;
    if(!file||!tenant||!token||this.uploadingBrand()||this.savingBrand())return;
    const maxMb=kind==='logo'?2:5;
    if(!['image/png','image/jpeg','image/webp'].includes(file.type)){
      this.brandFeedback.set('Choose a PNG, JPG or WebP image. SVG and animated images are not supported.');return;
    }
    if(!file.size||file.size>maxMb*1024*1024){this.brandFeedback.set('This image must be smaller than '+maxMb+' MB.');return;}
    this.uploadingBrand.set(kind);this.brandFeedback.set('');
    try {
      const result=await this.api.uploadTenantBranding(token,tenant.id,kind,file);
      if(this.selected()?.id!==tenant.id||version!==this.brandSelectionVersion)return;
      this.patchDraft(kind==='logo'?'logo_url':'cover_image_url',result.url);
      this.brandFeedback.set('Uploaded '+result.width+' × '+result.height+' px. Click Save Changes to publish for '+tenant.code+' only.');
    }catch(error){
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.brandFeedback.set(this.errorMessage(error));
    }finally{this.uploadingBrand.set(null);}
  }

  async saveBranding():Promise<void>{
    const token=this.token(),tenant=this.selected(),version=this.brandSelectionVersion;
    if(!token||!tenant||this.uploadingBrand()||this.savingBrand())return;
    const d={...this.draft()};
    if(d.name.trim().length<2){this.brandFeedback.set('Enter a café name with at least two characters.');return;}
    this.savingBrand.set(true);this.brandFeedback.set('');
    try {
      const updated=await this.api.updateTenantBranding(token,tenant.id,{
        name:d.name.trim(),tagline:d.tagline||null,primary_color:d.primary_color,secondary_color:d.secondary_color,
        logo_url:d.logo_url||null,cover_image_url:d.cover_image_url||null,phone:d.phone||null,email:d.email||null,website:d.website||null,
      });
      this.tenants.update(rows=>rows.map(row=>row.id===tenant.id?updated:row));
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion){
        this.select(updated);this.brandFeedback.set('Branding saved for '+updated.code+' only. Login now shows these images.');
      }
    }catch(error){
      if(this.selected()?.id===tenant.id&&version===this.brandSelectionVersion)this.brandFeedback.set(this.errorMessage(error));
    }finally{this.savingBrand.set(false);}
  }
}
