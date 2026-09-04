function escapeHtml(value) {
  return String(value).replace(
    /[&<>'"]/g,
    (character) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character],
  );
}

function receiptMarkup(receipt) {
  const money = (minor) => `&#8377;${(minor / 100).toFixed(2)}`;
  const rows = receipt.items
    .map(
      (item) =>
        `<tr><td>${escapeHtml(item.name)} &times; ${item.quantity}</td><td>${money(item.amountMinor)}</td></tr>`,
    )
    .join('');
  const reference = receipt.serviceReference
    ? `<p class="muted">${receipt.orderType === 'TAKEAWAY' ? 'Token' : 'Table / Token'}: ${escapeHtml(receipt.serviceReference)}</p>`
    : '';
  return `<!doctype html><html><head><meta charset="utf-8"><style>body{width:72mm;margin:0 auto;font:12px Arial;color:#111}h1,p{text-align:center;margin:3px 0}table{width:100%;border-collapse:collapse;margin:10px 0}td{padding:3px 0;vertical-align:top}td:last-child{text-align:right}.total{border-top:1px dashed #333;font-size:15px;font-weight:bold}.muted{color:#555;font-size:10px}</style></head><body><h1>${escapeHtml(receipt.cafeName)}</h1><p class="muted">${escapeHtml(receipt.address)}</p><p class="muted">Invoice: ${escapeHtml(receipt.invoiceNumber)}</p><p class="muted">Cashier: ${escapeHtml(receipt.cashier)}</p><p class="muted">Order: ${escapeHtml(receipt.orderType)}</p>${reference}<table>${rows}<tr><td>Subtotal</td><td>${money(receipt.subtotalMinor)}</td></tr>${receipt.discountMinor ? `<tr><td>Discount</td><td>-${money(receipt.discountMinor)}</td></tr>` : ''}<tr><td>GST</td><td>${money(receipt.taxMinor)}</td></tr>${receipt.roundOffMinor ? `<tr><td>Round Off</td><td>${money(receipt.roundOffMinor)}</td></tr>` : ''}<tr class="total"><td>Grand Total</td><td>${money(receipt.grandTotalMinor)}</td></tr></table><p>Payment: ${escapeHtml(receipt.paymentMode)}</p><p>Thank you. Visit again!</p></body></html>`;
}

async function printReceipt(BrowserWindow, receipt, printerName) {
  const window = new BrowserWindow({
    show: false,
    webPreferences: { contextIsolation: true, nodeIntegration: false, sandbox: true },
  });
  try {
    await window.loadURL(
      `data:text/html;charset=utf-8,${encodeURIComponent(receiptMarkup(receipt))}`,
    );
    const success = await new Promise((resolve, reject) =>
      window.webContents.print(
        { silent: false, deviceName: printerName || undefined, printBackground: true },
        (ok, reason) =>
          ok ? resolve(true) : reject(new Error(reason || 'Printer did not accept the receipt')),
      ),
    );
    return { success };
  } finally {
    if (!window.isDestroyed()) window.close();
  }
}

module.exports = { printReceipt };
