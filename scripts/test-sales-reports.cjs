const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const signal=v=>Object.assign(()=>v,{set:n=>v=n,update:fn=>v=fn(v)});
function setup(){
 const calls={};const services={ActivatedRoute:{paramMap:{subscribe(){}}},BrewBillApiService:{listOrders:async()=>[],voidOrder:async(t,id,reason)=>calls.void={id,reason}},SessionService:{accessToken:()=> 'test',isAdmin:()=>true},ReceiptPrinterService:{print:async p=>calls.print=p}};
 const exports={};const source=ts.transpileModule(fs.readFileSync('src/app/features/operations/operations.component.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
 vm.runInNewContext(source,{exports,Intl,Date,console,window:{prompt:()=> 'Duplicate entry'},require:p=>p==='@angular/core'?{signal,computed:fn=>fn,Component:()=>t=>t,inject:k=>services[k]}:new Proxy({},{get:(_,k)=>k})});const c=new exports.OperationsComponent();c.key.set('reports');return {c,calls};
}
test('reports search and combined filters paginate API rows without changing summary totals',()=>{
 const {c}=setup();c.orders.set(Array.from({length:24},(_,i)=>({id:String(i),invoice_number:'INV-'+i,cashier_name:'Admin',status:i<20?'COMPLETED':'VOID',payment_modes:i%2?['UPI']:['CASH'],grand_total:'100',item_count:1})));
 assert.equal(c.visibleOrders().length,10);c.pageReports(2);assert.equal(c.visibleOrders().length,4);
 c.filterReports('payment','UPI');assert.equal(c.currentReportPage(),0);assert.equal(c.filteredOrders().length,12);
 c.filterReports('status','COMPLETED');assert.equal(c.filteredOrders().length,10);assert.equal(c.reportTotal(),2000);
 c.setSearch('INV-3');assert.equal(c.visibleOrders().length,1);c.setSearch('missing');assert.equal(c.reportPages(),1);
 c.sizeReports('25');assert.equal(c.reportPageSize(),25);c.sizeReports('0');assert.equal(c.reportPageSize(),25);
});
test('existing print and void handlers retain their API payloads',async()=>{
 const {c,calls}=setup();const order={id:'order',invoice_number:'INV-1',cashier_name:'Admin',status:'COMPLETED',payment_modes:['CASH'],items:[{product_name:'Coffee',quantity:1,line_total:'100'}],subtotal:'100',discount:'0',tax:'5',round_off:'0',grand_total:'105',order_type:'DIRECT'};
 await c.printOrder(order);assert.equal(calls.print.grandTotalMinor,10500);assert.equal(calls.print.invoiceNumber,'INV-1');
 await c.voidOrder(order);assert.equal(calls.void.id,'order');assert.equal(calls.void.reason,'Duplicate entry');
});
test('sales styles remain scoped to reports only',()=>{
 const css=fs.readFileSync('src/app/features/operations/sales-reports.component.css','utf8');
 for(const part of css.matchAll(/([^{}]+)\{/g)){const s=part[1].replace(/\/\*[\s\S]*?\*\//g,'').trim();if(s.startsWith('@media'))continue;for(const branch of s.split(','))assert.ok(branch.includes(":host([data-view='reports'])"),branch);}
});
