const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const signal=value=>Object.assign(()=>value,{set:next=>value=next,update:fn=>value=fn(value)});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const row={id:'mapping-a',global_product_id:'master-a',legacy_product_id:'product-a',code:'COFFEE',name:'Coffee',category_name:'Coffee',stock_quantity:'40.000',low_stock_limit:'5.000',selling_price:'80.00',base_unit:'pcs',favourite:false};
async function setup(overrides={}) {
  const api={listGlobalProducts:async()=>[],listOutletCatalogue:async()=>[row],...overrides};
  const catalog={load:async()=>({categories:[],products:[{...row,id:row.legacy_product_id}]})};
  const exports={};
  const source=ts.transpileModule(fs.readFileSync('src/app/features/products/products.component.ts','utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText;
  vm.runInNewContext(source,{exports,Intl,console,require:path=>{
    if(path==='@angular/core')return {signal,computed:fn=>fn,Component:()=>target=>target,inject:key=>({BrewBillApiService:api,CatalogService:catalog,SessionService:{accessToken:()=> 'test',isSuperAdmin:()=>false},RuntimeConfigService:{assetUrl:x=>x}}[key])};
    if(path==='@angular/common/http')return {HttpErrorResponse:class extends Error{}};
    return new Proxy({},{get:(_,key)=>key});
  }});
  const c=new exports.ProductsComponent();await c.load();return c;
}
test('stock updates only after save and refetch; duplicate submission prevented',async()=>{
  const pending=deferred();let calls=0,body;let persisted=row;
  const c=await setup({updateOutletProduct:async(token,id,payload)=>{calls++;body=payload;return pending.promise;},listOutletCatalogue:async()=>[persisted]});
  c.editStock(row);c.stockValue('35.125');const save=c.saveStock();await c.saveStock();
  assert.equal(c.outletMappings()[0].stock_quantity,'40.000');assert.equal(c.stockSaving(),true);assert.equal(calls,1);
  persisted={...row,stock_quantity:'35.125'};pending.resolve(persisted);await save;
  assert.equal(body.stock_quantity,'35.125');assert.equal(body.expected_stock_quantity,'40.000');
  assert.equal(c.outletMappings()[0].stock_quantity,'35.125');assert.equal(c.products()[0].stock_quantity,'35.125');
  assert.equal(c.stockEditor(),null);assert.match(c.notice(),/successfully/);
});
test('invalid stock never reaches API and failed save restores previous value',async()=>{
  let calls=0;const c=await setup({updateOutletProduct:async()=>{calls++;throw Error('Network failure');}});
  c.editStock(row);
  for(const value of ['','-1','NaN','1.0001','1e3']){c.stockValue(value);await c.saveStock();assert.equal(calls,0);}
  c.stockValue('35');await c.saveStock();assert.equal(calls,1);
  assert.equal(c.stockEditor().value,'40.000');assert.equal(c.outletMappings()[0].stock_quantity,'40.000');assert.match(c.stockError(),/Previous value restored/);
});
test('refetch failure does not report a successful save as failed',async()=>{
  let fail=false;const c=await setup({updateOutletProduct:async()=>{fail=true;return {...row,stock_quantity:'35.000'};},listOutletCatalogue:async()=>{if(fail)throw Error('offline');return [row];}});
  c.editStock(row);c.stockValue('35');await c.saveStock();
  assert.equal(c.outletMappings()[0].stock_quantity,'35.000');assert.equal(c.stockError(),'');assert.match(c.notice(),/saved successfully.*refresh/i);
});
test('search, categories and pagination are independent for both panels',async()=>{
  const c=await setup();const items=Array.from({length:10},(_,i)=>({...row,id:String(i),name:'Product '+i,category_name:i<6?'Coffee':'Tea'}));
  c.globalProducts.set(items);c.outletMappings.set(items);assert.equal(c.masterRows().length,4);
  c.changeCataloguePage('master',1);assert.equal(c.masterRows()[0].id,'4');assert.equal(c.mappingPage(),0);
  c.filterCatalogue('master','category','Tea');assert.equal(c.masterPage(),0);assert.equal(c.visibleMasters().length,4);
  c.filterCatalogue('mapping','search','Product 2');assert.equal(c.visibleMappings().length,1);assert.equal(c.visibleMasters().length,4);
});
test('mapping modal includes edited stock with previous value; toggles persist',async()=>{
  let body;const c=await setup({updateOutletProduct:async(t,id,payload)=>{body=payload;return {...row,...payload};}});
  c.globalProducts.set([{...row,id:'master-a',status:'ACTIVE'}]);
  const dialog={showModal(){},close(){}};c.editMapping(row,dialog);c.patch('stockQuantity','35');await c.saveMapping(dialog);
  assert.equal(body.stock_quantity,'35.000');assert.equal(body.expected_stock_quantity,'40.000');
  await c.toggleMapping(row,'favourite');assert.equal(body.favourite,true);assert.equal(c.outletMappings()[0].favourite,true);
});

test('outlet GST saves disabled, custom and inherited rates without changing shared master',async()=>{
  let body;const c=await setup({updateOutletProduct:async(t,id,payload)=>{body=payload;return {...row,...payload};}});
  const master={...row,id:'master-a',status:'ACTIVE',default_gst:'5.00'};
  c.globalProducts.set([master]);
  const dialog={showModal(){},close(){}};
  c.editMapping({...row,default_gst:'5.00',tax_override:null},dialog);
  c.mappingGstEnabled.set(false);await c.saveMapping(dialog);assert.equal(body.tax_override,'0.00');
  c.mappingGstEnabled.set(true);c.mappingGstDefault.set(false);c.patch('gstPercent','12.5');
  await c.saveMapping(dialog);assert.equal(body.tax_override,'12.50');
  c.mappingGstDefault.set(true);await c.saveMapping(dialog);assert.equal(body.tax_override,null);
  assert.equal(c.globalProducts()[0]?.default_gst,undefined); // load() reloads the mocked master list
  assert.equal(master.default_gst,'5.00');
});

test('invalid custom GST never submits and view-only master never calls create',async()=>{
  let calls=0;const c=await setup({updateOutletProduct:async()=>{calls++;return row;},createGlobalProduct:async()=>{calls++;}});
  c.globalProducts.set([{...row,id:'master-a',status:'ACTIVE',default_gst:'5.00'}]);
  const dialog={showModal(){},close(){}};c.editMapping(row,dialog);c.mappingGstEnabled.set(true);c.mappingGstDefault.set(false);
  for(const value of ['','-1','101','1.234','NaN','Infinity']){c.patch('gstPercent',value);await c.saveMapping(dialog);assert.equal(calls,0);}
  await c.addGlobalProduct();assert.equal(calls,0);
  c.viewMaster(c.globalProducts()[0],dialog);assert.equal(c.viewedMaster().id,'master-a');
  const html=fs.readFileSync('src/app/features/products/products.component.html','utf8');
  const masterTable=html.split('<article class="panel table-panel catalogue-card">')[1];
  assert.match(masterTable,/viewMaster\(product, masterDialog\)/);
  assert.match(html,/!mappedIds\(\)\.has\(product\.id\)/);
  assert.match(html,/map-icon-button[\s\S]*mapProduct\(product, productDialog\)/);
  assert.doesNotMatch(html,/outlet-map-tools|Select a shared product/);
});