const test = require('node:test');
const assert = require('node:assert/strict');
const { printReceipt } = require('../electron/printer/receipt-printer.cjs');

const receipt = {
  cafeName: 'Brew Haven',
  address: 'Main outlet',
  invoiceNumber: 'INV-1',
  cashier: 'Admin',
  items: [{ name: 'Milkshake (Medium)', quantity: 1, amountMinor: 13000 }],
  subtotalMinor: 13000,
  discountMinor: 0,
  taxMinor: 0,
  roundOffMinor: 0,
  grandTotalMinor: 13000,
  paymentMode: 'CASH',
  orderType: 'DIRECT',
  serviceReference: null,
  currency: { code: 'INR', locale: 'en-IN', decimal_places: 2 },
};

function fakeWindow(printResult, reason) {
  return class FakeBrowserWindow {
    constructor() {
      this.closed = false;
      this.webContents = {
        print: (_options, callback) => callback(printResult, reason),
      };
      FakeBrowserWindow.instance = this;
    }
    async loadURL() {}
    isDestroyed() { return this.closed; }
    close() { this.closed = true; }
  };
}

test('print cancellation returns a normal unsuccessful result', async () => {
  const BrowserWindow = fakeWindow(false, 'Print job cancelled');
  assert.deepEqual(await printReceipt(BrowserWindow, receipt), { success: false });
  assert.equal(BrowserWindow.instance.closed, true);
});

test('successful print returns success', async () => {
  const BrowserWindow = fakeWindow(true, '');
  assert.deepEqual(await printReceipt(BrowserWindow, receipt), { success: true });
});

test('real printer failures still reject', async () => {
  const BrowserWindow = fakeWindow(false, 'Printer is offline');
  await assert.rejects(() => printReceipt(BrowserWindow, receipt), /Printer is offline/);
});
