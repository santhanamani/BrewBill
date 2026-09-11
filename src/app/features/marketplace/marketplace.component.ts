import { Component, computed, inject, signal } from '@angular/core';
import { BrewBillApiService } from '../../core/brew-bill-api.service';
import { CurrencyService } from '../../core/currency.service';
import { MarketplaceOrder, MarketplaceOrderStatus, MarketplaceProvider, MarketplaceSummary } from '../../core/models/api.models';
import { SessionService } from '../../core/session.service';
import { timedSignal } from '../../core/timed-signal';

@Component({ selector:'app-marketplace', templateUrl:'./marketplace.component.html', styleUrl:'./marketplace.component.css' })
export class MarketplaceComponent {
  private readonly api=inject(BrewBillApiService);
  readonly session=inject(SessionService);
  readonly currency=inject(CurrencyService);
  readonly orders=signal<MarketplaceOrder[]>([]);
  readonly summary=signal<MarketplaceSummary|null>(null);
  readonly loading=signal(true);
  readonly working=signal('');
  readonly error=signal('');
  readonly notice=timedSignal();
  readonly notificationPermission=signal<NotificationPermission>(
    'Notification' in window ? Notification.permission : 'denied',
  );
  readonly provider=signal<'ALL'|MarketplaceProvider>('ALL');
  readonly status=signal<'ALL'|MarketplaceOrderStatus>('ALL');
  readonly selectedId=signal('');
  readonly visibleOrders=computed(()=>this.orders().filter(order=>(this.provider()==='ALL'||order.provider===this.provider())&&(this.status()==='ALL'||order.status===this.status())));
  readonly selected=computed(()=>this.orders().find(order=>order.id===this.selectedId())??this.visibleOrders()[0]??null);
  constructor(){void this.load();}
  private token():string { const token=this.session.accessToken();if(!token)throw new Error('Sign in again to load marketplace orders.');return token; }
  money(value:string|number):string{return this.currency.format(value);}
  date(value:string):string{return new Intl.DateTimeFormat('en-IN',{dateStyle:'medium',timeStyle:'short'}).format(new Date(value));}
  async load():Promise<void>{this.loading.set(true);this.error.set('');try{const token=this.token();const [orders,summary]=await Promise.all([this.api.listMarketplaceOrders(token),this.api.getMarketplaceSummary(token)]);this.orders.set(orders);this.summary.set(summary);if(!orders.some(o=>o.id===this.selectedId()))this.selectedId.set(orders[0]?.id??'');}catch(error){this.error.set(error instanceof Error?error.message:'Unable to load marketplace orders.');}finally{this.loading.set(false);}}
  nextActions(order:MarketplaceOrder):MarketplaceOrderStatus[]{return ({RECEIVED:['ACCEPTED','REJECTED'],ACCEPTED:['PREPARING','READY','CANCELLED'],PREPARING:['READY','CANCELLED'],READY:['COMPLETED','CANCELLED']} as Partial<Record<MarketplaceOrderStatus,MarketplaceOrderStatus[]>>)[order.status]??[];}
  actionLabel(value:MarketplaceOrderStatus):string{return ({ACCEPTED:'Accept',REJECTED:'Reject',PREPARING:'Start preparing',READY:'Mark ready',COMPLETED:'Complete',CANCELLED:'Cancel'} as Partial<Record<MarketplaceOrderStatus,string>>)[value]??value;}
  async transition(order:MarketplaceOrder,next:MarketplaceOrderStatus):Promise<void>{if(this.working())return;this.working.set(order.id);this.error.set('');try{await this.api.updateMarketplaceOrderStatus(this.token(),order.id,next);this.notice.set(`${order.external_order_id} marked ${next.toLowerCase()}.`);await this.load();}catch(error){this.error.set(error instanceof Error?error.message:'Unable to update order.');}finally{this.working.set('');}}
  async createTest(provider:MarketplaceProvider):Promise<void>{if(this.working())return;this.working.set(provider);this.error.set('');try{const order=await this.api.createMarketplaceMockOrder(this.token(),provider);this.notice.set(`Test ${provider} order received.`);await this.load();this.selectedId.set(order.id);}catch(error){this.error.set(error instanceof Error?error.message:'Unable to create test order.');}finally{this.working.set('');}}
  async enableNotifications():Promise<void>{
    if(!('Notification' in window)){this.error.set('Desktop notifications are not supported on this device.');return;}
    const permission=await Notification.requestPermission();
    this.notificationPermission.set(permission);
    this.notice.set(permission==='granted'?'New marketplace order notifications are enabled.':'Notification permission was not enabled.');
  }
}
