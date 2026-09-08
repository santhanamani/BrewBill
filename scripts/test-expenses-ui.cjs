const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const signal=v=>Object.assign(()=>v,{set:n=>v=n,update:fn=>v=fn(v)});
function setup(overrides={}) {
 const api={listExpenses:async()=>[],...overrides};
 const services={ActivatedRoute:{paramMap:{subscribe(){}}},BrewBillApiService:api,SessionService:{accessToken:()=> 'test-token'}};
 const exports={};
 const source=ts.transpileModule(fs.readFileSync('src/app/features/management/management.component.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
 vm.runInNewContext(source,{exports,Intl,Date,console,require:path=>path==='@angular/core'?{signal,computed:fn=>fn,Component:()=>t=>t,inject:key=>services[key]}:new Proxy({},{get:(_,key)=>key})});
 const c=new exports.ManagementComponent();c.key.set('expenses');return c;
}
test('expense search, category/date filters and pagination use loaded rows',()=>{
 const c=setup();c.expenses.set(Array.from({length:19},(_,i)=>({id:String(i),category:i<10?'Supplies':'Utilities',expense_date:i<10?c.localDate()+'T12:00:00':'2000-01-01T12:00:00',description:'Expense '+i,amount:'10',payment_mode:'CASH'})));
 assert.equal(c.visibleExpenses().length,8);c.pageExpenses(1);assert.equal(c.visibleExpenses()[0].id,'8');c.pageExpenses(1);assert.equal(c.visibleExpenses().length,3);
 c.filterExpenses('category','Utilities');assert.equal(c.currentExpensePage(),0);assert.equal(c.filteredExpenses().length,9);
 c.filterExpenses('date','today');assert.equal(c.visibleExpenses().length,0);assert.equal(c.expensePages(),1);
 c.filterExpenses('category','');assert.equal(c.filteredExpenses().length,10);
 c.setSearch('Expense 2');assert.equal(c.visibleExpenses().length,1);
 assert.equal(c.expenseTotal(),190);assert.equal(c.cashExpense(),190);
});
test('expense submit keeps payment, remarks and existing API reload behavior',async()=>{
 let body,token;const saved={id:'saved',amount:'250',payment_mode:'UPI'};
 const c=setup({createExpense:async(t,p)=>{token=t;body=p;},listExpenses:async()=>[saved]});
 c.expenseDate='2026-09-06';c.expenseCategory='Utilities';c.expenseDescription=' Electricity ';c.expenseAmount='250';c.expenseMode='UPI';c.expenseRemarks=' September ';
 await c.addExpense();assert.equal(token,'test-token');assert.equal(body.payment_mode,'UPI');assert.equal(body.remarks,'September');assert.equal(body.description,'Electricity');assert.equal(c.expenses()[0],saved);assert.equal(c.saving(),false);
});
test('expense stylesheet never targets other screens',()=>{
 const css=fs.readFileSync('src/app/features/management/expenses.component.css','utf8');
 for(const part of css.matchAll(/([^{}]+)\{/g)){
 const s=part[1].replace(/\/\*[\s\S]*?\*\//g,'').trim();if(s.startsWith('@media'))continue;
 for(const branch of s.split(','))assert.ok(branch.includes(":host([data-view='expenses'])"),branch);
 }
 assert.doesNotMatch(css,/\.bottom-nav|\.light-topbar/);
});
