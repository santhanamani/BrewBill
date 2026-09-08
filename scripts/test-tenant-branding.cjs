// Component-state regression checks; no real API calls or tenant data changes.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const signal = value => Object.assign(() => value, { set: next => value = next, update: fn => value = fn(value) });
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return {promise,resolve,reject}; };
const cafe = code => ({ id:code, code, name:code+' Cafe', status:'ACTIVE', login_allowed:true, logo_url:code+'.webp', cover_image_url:code+'-cover.webp' });
function component(file, name, api, session) {
  const runtime = {config:()=>({tenantCode:''}),assetUrl:path=>'/assets/'+path};
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(file,'utf8'), {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,experimentalDecorators:true}}).outputText;
  vm.runInNewContext(source, {exports,setTimeout,clearTimeout,console,require:path=> {
    if(path==='@angular/core') return {signal,computed:fn=>fn,Component:()=>target=>target,inject:token=>({BrewBillApiService:api,RuntimeConfigService:runtime,SessionService:session,ClockService:{},ActivatedRoute:{snapshot:{queryParamMap:{get:()=>null}}}}[token])};
    if(path==='@angular/common/http') return {HttpErrorResponse:class extends Error{}};
    return new Proxy({}, {get:(_,key)=>key});
  }});
  return new exports[name](session,{navigateByUrl:async()=>{}});
}
function login(api, session={}) { return component('src/app/features/login/login.component.ts','LoginComponent',api,session); }
test('latest code wins; previous name and images clear immediately', async () => {
  const a=deferred(), b=deferred();
  const c=login({resolveTenant:code=>(code==='AA'?a:b).promise});
  c.changeTenantCode('AA'); const first=c.resolveTenant();
  c.changeTenantCode('BB'); const second=c.resolveTenant();
  b.resolve(cafe('BB')); await second;
  a.resolve(cafe('AA')); await first;
  assert.equal(c.tenant().code,'BB'); assert.equal(c.logoUrl(),'/assets/BB.webp');
  c.changeTenantCode('XX'); assert.equal(c.tenant(),null); assert.equal(c.verifiedTenant(),false);
  assert.equal(c.coverUrl(),'/assets/brand/login-hero.png'); c.ngOnDestroy();
});
test('invalid/inactive/offline codes block login; successful retry works', async () => {
  let response={status:404}, called=0;
  const c=login({resolveTenant:async()=>{if(response.code)return response;throw response;}},{login:async()=>{called++;}});
  c.changeTenantCode('AA'); await c.resolveTenant(); await c.login(); assert.equal(called,0); assert.match(c.tenantError(),/active|not found/);
  response={...cafe('AA'),status:'INACTIVE'}; await c.resolveTenant(); assert.equal(c.tenant(),null); assert.match(c.tenantError(),/inactive/);
  response={status:0}; await c.resolveTenant(); assert.match(c.tenantError(),/connection/);
  response=cafe('AA'); await c.resolveTenant(); assert.equal(c.verifiedTenant(),true);
  c.loading.set(true); c.changeTenantCode('BB'); assert.equal(c.tenantCode(),'AA'); c.ngOnDestroy();
});
test('late failed lookup cannot replace newer verified tenant', async () => {
  const old=deferred(); const c=login({resolveTenant:code=>code==='AA'?old.promise:Promise.resolve(cafe(code))});
  c.changeTenantCode('AA'); const first=c.resolveTenant(); c.changeTenantCode('BB'); await c.resolveTenant();
  old.reject({status:404}); await first; assert.equal(c.tenantError(),''); assert.equal(c.tenant().code,'BB'); c.ngOnDestroy();
});
test('switching tenant during upload does not modify the new draft', async () => {
  const pending=deferred(); let token=null; let requested;
  const c=component('src/app/features/administration/administration.component.ts','AdministrationComponent',{
    uploadTenantBranding:(t,id)=>{requested=id;return pending.promise;}
  },{accessToken:()=>token}); token='test';
  c.select(cafe('AA'));
  const upload=c.uploadBrandImage('logo',{target:{files:[{type:'image/png',size:10}],value:'file'}});
  c.select(cafe('BB')); pending.resolve({url:'AA-new.webp',width:512,height:512}); await upload;
  assert.equal(requested,'AA'); assert.equal(c.draft().logo_url,'BB.webp'); assert.equal(c.brandFeedback(),'');
});
test('save uses captured tenant and updates only that record after switching', async () => {
  const pending=deferred(); let token=null; let requested;
  const c=component('src/app/features/administration/administration.component.ts','AdministrationComponent',{
    updateTenantBranding:(t,id)=>{requested=id;return pending.promise;}
  },{accessToken:()=>token}); token='test';
  c.tenants.set([cafe('AA'),cafe('BB')]); c.select(cafe('AA')); const save=c.saveBranding();
  c.select(cafe('BB')); pending.resolve({...cafe('AA'),logo_url:'new.webp'}); await save;
  assert.equal(requested,'AA'); assert.equal(c.selected().id,'BB'); assert.equal(c.draft().logo_url,'BB.webp');
  assert.equal(c.tenants()[0].logo_url,'new.webp'); assert.equal(c.tenants()[1].logo_url,'BB.webp');
});
