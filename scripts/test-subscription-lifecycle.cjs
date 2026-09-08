const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');

const read = path => fs.readFileSync(path, 'utf8');

test('login warns, blocks, and routes expired tenants to renewal', () => {
  const component = read('src/app/features/login/login.component.ts');
  const template = read('src/app/features/login/login.component.html');
  const routes = read('src/app/app.routes.ts');
  assert.match(component, /canTenantLogin\(\)/);
  assert.match(component, /status===402/);
  assert.match(component, /navigate\(\['\/subscribe'\]/);
  assert.match(template, /Subscription grace period/);
  assert.match(template, /Subscription renewal required/);
  assert.match(routes, /path: 'subscribe'/);
});

test('Super Admin can manage tenant expiry and grace dates', () => {
  const component = read('src/app/features/administration/administration.component.ts');
  const template = read('src/app/features/administration/administration.component.html');
  const api = read('src/app/core/brew-bill-api.service.ts');
  assert.match(component, /loadTenantSubscription\(tenant\.id,version\)/);
  assert.match(component, /saveTenantSubscription\(\)/);
  assert.match(template, /Subscription expiry \*/);
  assert.match(template, /Grace period ends \*/);
  assert.match(template, /Automatic access control/);
  assert.match(api, /updateTenantSubscription/);
});

test('renewal page keeps tenant identity and supports status retry', () => {
  const component = read('src/app/features/subscription/subscription.component.ts');
  const template = read('src/app/features/subscription/subscription.component.html');
  assert.match(component, /resolveTenant\(code\)/);
  assert.match(component, /tenant\.login_allowed/);
  assert.match(template, /Check renewal status/);
  assert.match(template, /No .* data has been deleted/);
});
