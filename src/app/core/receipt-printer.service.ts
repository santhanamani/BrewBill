import { Injectable } from '@angular/core';
import { CurrencyDefinition } from './models/api.models';

export type ReceiptPaymentMode = 'CASH' | 'UPI' | 'CARD' | 'SPLIT';

export interface ReceiptPayload {
  cafeName: string;
  address: string;
  invoiceNumber: string;
  cashier: string;
  items: Array<{ name: string; quantity: number; amountMinor: number }>;
  subtotalMinor: number;
  discountMinor: number;
  taxMinor: number;
  roundOffMinor: number;
  grandTotalMinor: number;
  paymentMode: ReceiptPaymentMode;
  orderType: 'DIRECT' | 'KOT' | 'TAKEAWAY';
  serviceReference: string | null;
  currency: CurrencyDefinition;
}

@Injectable({ providedIn: 'root' })
export class ReceiptPrinterService {
  async print(receipt: ReceiptPayload): Promise<boolean> {
    if (window.brewBill?.printer) {
      const result = await window.brewBill.printer.printReceipt(receipt);
      return result.success;
    }

    this.printInBrowser(receipt);
    return true;
  }

  private printInBrowser(receipt: ReceiptPayload): void {
    const printWindow = window.open('', '_blank', 'width=420,height=720');
    if (!printWindow) throw new Error('Allow the print window and try again.');
    printWindow.document.open();
    printWindow.document.write(this.markup(receipt));
    printWindow.document.close();
    printWindow.addEventListener('afterprint', () => printWindow.close(), { once: true });
    printWindow.focus();
    printWindow.print();
  }

  private markup(receipt: ReceiptPayload): string {
    const money = (minor: number) => this.escape(new Intl.NumberFormat(receipt.currency.locale, {
      style: 'currency', currency: receipt.currency.code,
      minimumFractionDigits: receipt.currency.decimal_places,
      maximumFractionDigits: receipt.currency.decimal_places,
    }).format(minor / 100));
    const rows = receipt.items
      .map(
        (item) =>
          `<tr><td>${this.escape(item.name)} &times; ${item.quantity}</td><td>${money(item.amountMinor)}</td></tr>`,
      )
      .join('');
    const reference = receipt.serviceReference
      ? `<p>${receipt.orderType === 'TAKEAWAY' ? 'Token' : 'Table / Token'}: ${this.escape(receipt.serviceReference)}</p>`
      : '';
    return `<!doctype html><html><head><meta charset="utf-8"><title>${this.escape(receipt.invoiceNumber)}</title><style>body{width:72mm;margin:0 auto;font:12px Arial;color:#111}h1,p{text-align:center;margin:3px 0}table{width:100%;border-collapse:collapse;margin:10px 0}td{padding:3px 0;vertical-align:top}td:last-child{text-align:right}.total{border-top:1px dashed #333;font-size:15px;font-weight:bold}.muted{color:#555;font-size:10px}@media print{body{width:auto}}</style></head><body><h1>${this.escape(receipt.cafeName)}</h1><p class="muted">${this.escape(receipt.address)}</p><p class="muted">Invoice: ${this.escape(receipt.invoiceNumber)}</p><p class="muted">Cashier: ${this.escape(receipt.cashier)}</p><p class="muted">Order: ${this.escape(receipt.orderType)}</p>${reference}<table>${rows}<tr><td>Subtotal</td><td>${money(receipt.subtotalMinor)}</td></tr>${receipt.discountMinor ? `<tr><td>Discount</td><td>-${money(receipt.discountMinor)}</td></tr>` : ''}<tr><td>GST</td><td>${money(receipt.taxMinor)}</td></tr>${receipt.roundOffMinor ? `<tr><td>Round Off</td><td>${money(receipt.roundOffMinor)}</td></tr>` : ''}<tr class="total"><td>Grand Total</td><td>${money(receipt.grandTotalMinor)}</td></tr></table><p>Payment: ${this.escape(receipt.paymentMode)}</p><p>Thank you. Visit again!</p></body></html>`;
  }

  private escape(value: string): string {
    return value.replace(
      /[&<>'"]/g,
      (character) =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character] ??
        character,
    );
  }
}
