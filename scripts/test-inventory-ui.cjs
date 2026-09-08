const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const signal=value=>Object.assign(()=>value,{set:v=>value=v,update:fn=>value=fn(value)});
test('Inventory adjustments call existing API and reload authoritative balances',async()=>{
 let balance='10.000', calls=0;
 const item=()=>({id:'beans',name:'Beans',available_quantity:balance,status:'IN_STOCK'});
 const services={ActivatedRoute:{paramMap:{subscribe(){}}},BrewBillApiService:{listInventoryItems:async()=>[item()],listInventoryMovements:async()=>[],adjustInventoryItem:async(token,id,payload)=>{assert.equal(token,'test');assert.equal(id,'beans');assert.equal(payload.quantity,'2.000');assert.equal(payload.notes,'Count check');calls++;balance='12.000';}},SessionService:{accessToken:()=> 'test'},RuntimeConfigService:{},HeldCartService:{},Router:{},ReceiptPrinterService:{}};
 const exports={};
 const source=ts.transpileModule(fs.readFileSync('src/app/features/operations/operations.component.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
 vm.runInNewContext(source,{exports,Intl,Date,console,require:path=>path==='@angular/core'?{signal,computed:fn=>fn,Component:()=>target=>target,inject:key=>services[key]}:new Proxy({},{get:(_,key)=>key})});
 const c=new exports.OperationsComponent();await c.load();c.adjustmentQuantity.set('2');c.adjustmentNotes.set('Count check');await c.saveAdjustment();assert.equal(calls,1);assert.equal(c.selectedInventory().available_quantity,'12.000');await c.load();assert.equal(c.selectedInventory().available_quantity,'12.000');c.adjustmentQuantity.set('0');await c.saveAdjustment();assert.equal(calls,1);
});
test('Inventory styling is scoped away from other screens',()=>{
 const css=fs.readFileSync('src/app/features/operations/inventory.component.css','utf8');
 for(const part of css.matchAll(/([^{}]+)\{/g)){
  const selector=part[1].replace(/\/\*[\s\S]*?\*\//g,'').trim();if(selector.startsWith('@media'))continue;
  for(const branch of selector.split(',')) assert.ok(branch.includes(":host([data-view='inventory'])"),branch);
 }
 assert.doesNotMatch(css,/\.bottom-nav|\.light-topbar|\.app-shell/);
});
