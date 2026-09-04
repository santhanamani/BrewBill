const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const Database = require('better-sqlite3');
const { installLicense, verifyLicense } = require('../electron/license/license-service.cjs');

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

const db = new Database(':memory:');
db.exec(`CREATE TABLE local_settings (
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)`);
const safeStorage = {
  isEncryptionAvailable: () => true,
  encryptString: (value) => Buffer.from(value, 'utf8'),
  decryptString: (value) => value.toString('utf8'),
};
const { privateKey, publicKey } = crypto.generateKeyPairSync('ed25519');
const now = new Date();
const payload = {
  features: { inventory: true },
  issued_at: now.toISOString(),
  license_version: 1,
  offline_valid_until: new Date(now.getTime() + 48 * 60 * 60 * 1000).toISOString(),
  outlet_id: 'outlet-1',
  plan_code: 'PRO',
  subscription_end: new Date(now.getTime() + 30 * 86400000).toISOString(),
  subscription_plan: 'PRO',
  tenant_id: 'tenant-1',
  terminal_code: 'POS01',
  terminal_id: 'terminal-1',
};
const envelope = {
  payload,
  signature: crypto
    .sign(null, Buffer.from(stableStringify(payload)), privateKey)
    .toString('base64'),
  public_key: publicKey.export({ type: 'spki', format: 'pem' }),
};

assert.equal(installLicense(db, safeStorage, envelope).state, 'ACTIVE');
assert.equal(verifyLicense(db, safeStorage).canCreateBills, true);

const encryptedToken = db
  .prepare("SELECT value FROM local_settings WHERE key='secure.license.token'")
  .get();
assert.ok(encryptedToken);
assert.equal(
  db.prepare("SELECT value FROM local_settings WHERE key='license.last-application-time'").get(),
  undefined,
);

const stored = JSON.parse(safeStorage.decryptString(Buffer.from(encryptedToken.value, 'base64')));
stored.payload.tenant_id = 'tampered';
db.prepare("UPDATE local_settings SET value=? WHERE key='secure.license.token'").run(
  safeStorage.encryptString(JSON.stringify(stored)).toString('base64'),
);
assert.equal(verifyLicense(db, safeStorage).state, 'INVALID_LICENSE');
db.close();
console.log('Signed license, DPAPI storage boundary, and tamper rejection checks passed.');
