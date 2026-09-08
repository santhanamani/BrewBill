const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const signal=value=>Object.assign(()=>value,{set:v=>value=v,update:fn=>value=fn(value)});
const first={id:'hold-a',hold_number:'HLD-000001',invoice_number:'INV-A',cashier_name:'Admin',held_at:new Date().toISOString(),subtotal:'240.00',tax:'12.00',grand_total:'252.00',items:[{product_id:'product-a',variant_id:null,product_name:'Butterscotch Milkshake',variant_name:'Regular',quantity:2,line_total:'240.00'}]};
const second={...first,id:'hold-b',hold_number:'HLD-000002',grand_total:'57.75',items:[{...first.items[0],product_id:'product-b',product_name:'Boost'}]};
function setup(overrides={}) {
  const api={listHolds:async()=>[first,second],listProducts:async()=>[{id:'product-a',image_path:'milkshake.png'}],...overrides};
  const state={opened:null,navigated:null,confirm:true};
  const services={ActivatedRoute:{paramMap:{subscribe(){}}},BrewBillApiService:api,SessionService:{accessToken:()=> 'scoped-test-token'},RuntimeConfigService:{assetUrl:p=>p??'placeholder.svg'},HeldCartService:{open:hold=>state.opened=hold},Router:{navigateByUrl:async path=>state.navigated=path},ReceiptPrinterService:{}};
  const exports={};
  const source=ts.transpileModule(fs.readFileSync('src/app/features/operations/operations.component.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
  vm.runInNewContext(source,{exports,Intl,Date,console,window:{confirm:()=>state.confirm},require:path=>path==='@angular/core'?{signal,computed:fn=>fn,Component:()=>target=>target,inject:key=>services[key]}:new Proxy({},{get:(_,key)=>key})});
  const component=new exports.OperationsComponent();component.key.set('holds');return {component,state};
}
test('held list search, selection, totals and refresh retain existing behavior',async()=>{
  const {component:c}=setup();await c.load();
  assert.equal(c.holds().length,2);assert.equal(c.selectedHold().id,first.id);assert.equal(c.heldValue(),309.75);
  c.selectHold(second);await c.load();assert.equal(c.selectedHold().id,second.id);
  for(const query of ['boost','HLD-000002']){c.setSearch(query);assert.equal(c.visibleHolds().length,1);assert.equal(c.visibleHolds()[0].id,second.id);}
  c.setSearch('unknown');assert.equal(c.visibleHolds().length,0);
  c.setSearch('');assert.equal(c.visibleHolds().length,2);
  assert.equal(c.holdImage('product-a'),'milkshake.png');assert.equal(c.holdImage('missing'),'placeholder.svg');
});
test('optional image failure never blocks held bills or totals',async()=>{
  const {component:c}=setup({listProducts:async()=>{throw Error('image lookup unavailable');}});
  await c.load();assert.equal(c.error(),'');assert.equal(c.loading(),false);assert.equal(c.holds().length,2);assert.equal(c.selectedHold().grand_total,'252.00');
});
test('reopen uses existing API and transfers server bill to POS',async()=>{
  let called;const {component:c,state}=setup({reopenHold:async(token,id)=>{called={token,id};return first;}});
  await c.reopen(first);assert.equal(called.id,first.id);assert.equal(called.token,'scoped-test-token');assert.equal(state.opened,first);assert.equal(state.navigated,'/pos');
});
test('discard requires confirmation and refreshes without altering bill totals locally',async()=>{
  let calls=0;const {component:c,state}=setup({deleteHold:async(token,id)=>{assert.equal(id,first.id);calls++;}});
  state.confirm=false;await c.deleteHold(first);assert.equal(calls,0);
  state.confirm=true;await c.deleteHold(first);assert.equal(calls,1);assert.equal(c.holds().length,2);assert.equal(first.tax,'12.00');
});
test('new stylesheet cannot style other Operations screens or shell navigation',()=>{
  const css=fs.readFileSync('src/app/features/operations/held-orders.component.css','utf8');
  for(const part of css.matchAll(/([^{}]+)\{/g)){
    const selector=part[1].replace(/\/\*[\s\S]*?\*\//g,'').trim();
    if(selector.startsWith('@media'))continue;
    for(const branch of selector.split(','))assert.ok(branch.includes(":host([data-view='holds'])"),branch);
  }
  assert.doesNotMatch(css,/\.bottom-nav|\.light-topbar|\.app-shell/);
});
