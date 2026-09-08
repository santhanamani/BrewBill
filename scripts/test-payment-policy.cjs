const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const read = (path) => fs.readFileSync(path, 'utf8');

test('tenant admin and super admin expose scoped payment policy controls', () => {
  const management = read('src/app/features/management/management.component.ts');
  const managementHtml = read('src/app/features/management/management.component.html');
  const administration = read('src/app/features/administration/administration.component.ts');
  const administrationHtml = read('src/app/features/administration/administration.component.html');

  assert.match(management, /getPaymentPolicy\(token\)/);
  assert.match(management, /updatePaymentPolicy\(token, this\.paymentProcessingMode\)/);
  assert.match(managementHtml, /Manual cash allowed/);
  assert.match(managementHtml, /POS terminal required/);
  assert.match(administration, /getTenantPaymentPolicy\(token,tenantId\)/);
  assert.match(administration, /updateTenantPaymentPolicy\(token,tenant\.id,this\.tenantPaymentMode\(\)\)/);
  assert.match(administrationHtml, /detailTab\.set\('payments'\)/);
});

test('POS blocks cash and fail-open fallback when terminal approval is required', () => {
  const pos = read('src/app/features/pos/pos.component.ts');
  const posHtml = read('src/app/features/pos/pos.component.html');

  assert.match(pos, /mode === 'CASH' && this\.terminalRequired\(\)/);
  assert.match(pos, /if \(terminalRequired\) throw new Error\('POS terminal is required and currently unavailable/);
  assert.match(pos, /this\.terminalRequired\(\) && this\.price\(this\.splitCash\(\)\) > 0/);
  assert.match(posHtml, /Terminal required · Cash\/manual fallback blocked/);
  assert.match(posHtml, /class\.policy-blocked/);
});

test('Settings exposes tenant-scoped POS device activation and separate gateway status', () => {
  const management = read('src/app/features/management/management.component.ts');
  const managementHtml = read('src/app/features/management/management.component.html');
  const styles = read('src/app/reference-ui.css');

  assert.match(management, /refreshPosDevice\(announce = true\)/);
  assert.match(management, /this\.session\.ensureDesktopLicense\(\)/);
  assert.match(management, /this\.session\.context\(\)\?\.outlet_id/);
  assert.match(managementHtml, /POS Device Registration/);
  assert.match(managementHtml, /Activate \/ Refresh/);
  assert.match(managementHtml, /Payment Terminal Gateway/);
  assert.match(managementHtml, /Device ID \{\{ posDeviceIdLabel\(\) \}\}/);
  assert.match(styles, /POS device registration and payment gateway settings/);
});