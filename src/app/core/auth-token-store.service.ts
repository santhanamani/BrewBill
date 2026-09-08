import { Injectable, inject, signal } from '@angular/core';
import { RuntimeConfigService } from './runtime-config.service';

interface TokenPair { access_token:string; refresh_token:string; }

@Injectable({ providedIn: 'root' })
export class AuthTokenStoreService {
  private readonly runtime = inject(RuntimeConfigService);
  readonly accessToken = signal<string | null>(null);
  readonly refreshToken = signal<string | null>(null);
  private refreshInFlight: Promise<string> | null = null;
  private generation = 0;
  private readonly storageKey = 'brewbill.session.v1';

  // Tab/window scoped: survives reload, not a permanent remembered login.
  // User/roles and tenant data are never trusted from browser storage.
  restore():boolean {
    try {
      const saved=JSON.parse(sessionStorage.getItem(this.storageKey) ?? 'null');
      if(!saved)return false;
      if(saved.api!==this.runtime.config().apiBaseUrl || !this.validPair(saved)) {this.clear();return false;}
      this.set(saved);return true;
    } catch {this.clear();return false;}
  }
  private validPair(value:unknown):value is TokenPair {
    const pair=value as TokenPair | null;
    return !!pair && typeof pair.access_token==='string' && !!pair.access_token &&
      typeof pair.refresh_token==='string' && !!pair.refresh_token;
  }
  set(tokens:TokenPair):void {
    if(!this.validPair(tokens))throw new Error('Invalid session response. Sign in again.');
    this.generation++;
    this.accessToken.set(tokens.access_token);this.refreshToken.set(tokens.refresh_token);
    try {sessionStorage.setItem(this.storageKey,JSON.stringify({...tokens,api:this.runtime.config().apiBaseUrl}));} catch { /* Memory-only when storage is disabled. */ }
  }
  clear():void {
    this.generation++;this.refreshInFlight=null;
    this.accessToken.set(null);this.refreshToken.set(null);
    try {sessionStorage.removeItem(this.storageKey);} catch { /* Storage may be unavailable. */ }
  }
  refresh():Promise<string> {
    if(this.refreshInFlight)return this.refreshInFlight;
    const refreshToken=this.refreshToken(),generation=this.generation;
    if(!refreshToken)return Promise.reject(new Error('Your session has expired. Sign in again.'));
    const operation=fetch(this.runtime.apiUrl('/auth/refresh'),{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({refresh_token:refreshToken}),signal:AbortSignal.timeout(5000),
    }).then(async response=>{
      if(!response.ok) {
        const detail=await response.json().catch(()=>({}));
        throw Object.assign(new Error(detail.detail ?? 'Unable to renew your session.'),{status:response.status});
      }
      const tokens:unknown=await response.json();
      if(generation!==this.generation)throw new Error('Session changed while renewing.');
      if(!this.validPair(tokens))throw Object.assign(new Error('Invalid session response.'),{status:401});
      this.set(tokens);return tokens.access_token;
    }).catch(error=>{
      if(generation===this.generation && [401,403].includes(error?.status))this.clear();
      throw error;
    }).finally(()=>{if(this.refreshInFlight===operation)this.refreshInFlight=null;});
    this.refreshInFlight=operation;return operation;
  }
}