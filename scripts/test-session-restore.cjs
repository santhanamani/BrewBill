const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const ts=require('typescript');
const signal=value=>Object.assign(()=>value,{set:next=>value=next,update:fn=>value=fn(value)});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const storage=()=>{const data=new Map();return {getItem:key=>data.get(key)??null,setItem:(key,value)=>data.set(key,value),removeItem:key=>data.delete(key)};};
function load(file,name,dependencies,globals={}) {
  const exports={};
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,experimentalDecorators:true}}).outputText,{
    exports,console,AbortSignal,document:{documentElement:{style:{setProperty(){}}}},window:{setInterval:()=>1,clearInterval(){}},
    require:path=>path==='@angular/core'?{signal,computed:fn=>fn,Injectable:()=>target=>target,inject:key=>dependencies[key]}:new Proxy({},{get:(_,key)=>key}),...globals,
  });
  return exports[name];
}
const runtime={config:()=>({apiBaseUrl:'http://local/api'}),apiUrl:path=>'http://local/api'+path};
function store(saved=storage(),fetcher=()=>{throw Error('Unexpected refresh');}) {
  return new (load('src/app/core/auth-token-store.service.ts','AuthTokenStoreService',{RuntimeConfigService:runtime},{sessionStorage:saved,fetch:fetcher}))();
}
const pair={access_token:'access-one',refresh_token:'refresh-one'};
const user={id:'u1',tenant_id:'t1',outlet_id:'o1',role_code:'ADMIN'};
const context={tenant_id:'t1',outlet_id:'o1',branding:{},currency:{code:'INR',name:'Indian Rupee',symbol:'₹',locale:'en-IN',decimal_places:2}};
function session(tokens,api) {
  const currency={configure(){},reset(){}};
  return new (load('src/app/core/session.service.ts','SessionService',{AuthTokenStoreService:tokens,CurrencyService:currency}))(api);
}

test('hard reload restores tokens, then server-verified user and outlet',async()=>{
  const saved=storage(),first=store(saved);first.set(pair);
  const reloaded=store(saved);assert.equal(reloaded.accessToken(),null);
  const c=session(reloaded,{getCurrentUser:async()=>user,getPlatformContext:async()=>context});
  assert.equal(c.isAuthenticated(),false);await c.restore();assert.equal(c.isAuthenticated(),true);
  assert.equal(c.user().tenant_id,'t1');assert.equal(c.context().outlet_id,'o1');
  c.clear();assert.equal(store(saved).restore(),false);
});
test('tampered storage and different API never authenticate',async()=>{
  const saved=storage();saved.setItem('brewbill.session.v1','not json');assert.equal(store(saved).restore(),false);
  saved.setItem('brewbill.session.v1',JSON.stringify({...pair,api:'http://other/api',user:{role_code:'SUPER_ADMIN'}}));
  assert.equal(store(saved).restore(),false);
});
test('server rejects restored tokens or tenant/outlet mismatch',async()=>{
  for(const api of [{getCurrentUser:async()=>{throw {status:401};},getPlatformContext:async()=>context},
    {getCurrentUser:async()=>user,getPlatformContext:async()=>({...context,outlet_id:'wrong'})}]){
    const saved=storage();store(saved).set(pair);const tokens=store(saved),c=session(tokens,api);await c.restore();
    assert.equal(c.isAuthenticated(),false);assert.equal(tokens.accessToken(),null);assert.equal(store(saved).restore(),false);
  }
});
test('temporary restore failure preserves session for retry without trusting cached user',async()=>{
  const saved=storage();store(saved).set(pair);let online=false;
  const c=session(store(saved),{getCurrentUser:async()=>{if(!online)throw {status:0};return user;},getPlatformContext:async()=>context});
  await c.restore();assert.equal(c.isAuthenticated(),false);assert.match(c.restoreMessage(),/retry/);
  online=true;await c.restore();assert.equal(c.isAuthenticated(),true);
});
test('logout during restore prevents late session resurrection',async()=>{
  const saved=storage();store(saved).set(pair);const pending=deferred();
  const c=session(store(saved),{getCurrentUser:()=>pending.promise,getPlatformContext:async()=>context});
  const restoring=c.restore();c.clear();pending.resolve(user);await restoring;
  assert.equal(c.isAuthenticated(),false);assert.equal(store(saved).restore(),false);
});
test('concurrent token renewal is single-flight and survives the next reload',async()=>{
  const saved=storage(),pending=deferred();let calls=0;
  const tokens=store(saved,()=>{calls++;return pending.promise;});tokens.set(pair);
  const a=tokens.refresh(),b=tokens.refresh();assert.equal(a,b);assert.equal(calls,1);
  pending.resolve({ok:true,json:async()=>({access_token:'new-access',refresh_token:'new-refresh'})});await a;
  const reloaded=store(saved);reloaded.restore();assert.equal(reloaded.refreshToken(),'new-refresh');
});
test('late refresh cannot restore logout or overwrite a new login',async()=>{
  for(const newLogin of [false,true]){
    const pending=deferred(),tokens=store(storage(),()=>pending.promise);tokens.set(pair);
    const refreshing=tokens.refresh();tokens.clear();if(newLogin)tokens.set({access_token:'other',refresh_token:'other-refresh'});
    pending.resolve({ok:true,json:async()=>pair});await assert.rejects(refreshing,/Session changed/);
    assert.equal(tokens.accessToken(),newLogin?'other':null);
  }
});
test('refresh rejection clears saved credentials; temporary failure does not',async()=>{
  for(const status of [401,503]){
    const tokens=store(storage(),async()=>({ok:false,status,json:async()=>({})}));tokens.set(pair);
    await assert.rejects(tokens.refresh());assert.equal(tokens.accessToken(),status===401?null:'access-one');
  }
});
test('MFA challenge does not create a restorable session',async()=>{
  const tokens=store(),c=session(tokens,{login:async()=>({status:'MFA_REQUIRED',challenge_token:'challenge'})});
  const result=await c.login('admin','unused','CAFE');assert.equal(result.status,'MFA_REQUIRED');assert.equal(tokens.accessToken(),null);
});
