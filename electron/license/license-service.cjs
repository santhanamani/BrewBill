const crypto = require('node:crypto');

function readSecure(db, safeStorage, key) {
  const encoded = db
    .prepare('SELECT value FROM local_settings WHERE key=?')
    .get(`secure.${key}`)?.value;
  return encoded && safeStorage.isEncryptionAvailable()
    ? safeStorage.decryptString(Buffer.from(encoded, 'base64'))
    : null;
}

function writeSecure(db, safeStorage, key, value) {
  if (!safeStorage.isEncryptionAvailable())
    throw new Error('Windows credential encryption is unavailable');
  db.prepare(
    'INSERT INTO local_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
  ).run(`secure.${key}`, safeStorage.encryptString(value).toString('base64'));
}

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

function installLicense(db, safeStorage, envelope) {
  if (
    !envelope ||
    typeof envelope !== 'object' ||
    !envelope.payload ||
    typeof envelope.signature !== 'string' ||
    typeof envelope.public_key !== 'string'
  ) {
    throw new Error('The license response is invalid.');
  }
  const pinnedPublicKey = readSecure(db, safeStorage, 'license.public-key');
  if (pinnedPublicKey && pinnedPublicKey !== envelope.public_key) {
    throw new Error('License signing key changed. Contact BrewBill support before reactivating.');
  }
  writeSecure(
    db,
    safeStorage,
    'license.token',
    JSON.stringify({ payload: envelope.payload, signature: envelope.signature }),
  );
  writeSecure(db, safeStorage, 'license.public-key', envelope.public_key);
  writeSecure(db, safeStorage, 'license.last-server-time', envelope.payload.issued_at);
  writeSecure(db, safeStorage, 'license.last-successful-validation', new Date().toISOString());
  return verifyLicense(db, safeStorage);
}

function verifyLicense(db, safeStorage) {
  const serialized = readSecure(db, safeStorage, 'license.token');
  const publicKey = readSecure(db, safeStorage, 'license.public-key');
  if (!serialized || !publicKey)
    return {
      state: 'ACTIVATION_REQUIRED',
      canCreateBills: false,
      offlineValidUntil: null,
      message: 'This POS terminal has not been activated.',
    };
  try {
    const { payload, signature } = JSON.parse(serialized);
    const validSignature = crypto.verify(
      null,
      Buffer.from(stableStringify(payload)),
      publicKey,
      Buffer.from(signature, 'base64'),
    );
    if (!validSignature)
      return {
        state: 'INVALID_LICENSE',
        canCreateBills: false,
        offlineValidUntil: null,
        message: 'License signature is invalid. Connect to the server.',
      };
    const now = new Date();
    const offlineValidUntil = new Date(payload.offline_valid_until);
    const subscriptionEnd = new Date(payload.subscription_end);
    const trustedTimes = [
      readSecure(db, safeStorage, 'license.last-server-time'),
      readSecure(db, safeStorage, 'license.last-successful-validation'),
      readSecure(db, safeStorage, 'license.last-application-time'),
    ]
      .filter(Boolean)
      .map((value) => new Date(value).getTime());
    if (trustedTimes.some((value) => now.getTime() + 300000 < value))
      return {
        state: 'CLOCK_TAMPERING',
        canCreateBills: false,
        offlineValidUntil: offlineValidUntil.toISOString(),
        message: 'Clock rollback detected. Online license verification is required.',
      };
    writeSecure(db, safeStorage, 'license.last-application-time', now.toISOString());
    if (now > subscriptionEnd)
      return {
        state: 'SUBSCRIPTION_EXPIRED',
        canCreateBills: false,
        offlineValidUntil: offlineValidUntil.toISOString(),
        message: 'Subscription expired. Historical reports remain available.',
      };
    if (now > offlineValidUntil)
      return {
        state: 'LICENSE_VERIFICATION_REQUIRED',
        canCreateBills: false,
        offlineValidUntil: offlineValidUntil.toISOString(),
        message: 'Offline allowance ended. Connect to verify your subscription.',
      };
    return {
      state: 'ACTIVE',
      canCreateBills: true,
      offlineValidUntil: offlineValidUntil.toISOString(),
      message: 'Subscription active.',
    };
  } catch {
    return {
      state: 'INVALID_LICENSE',
      canCreateBills: false,
      offlineValidUntil: null,
      message: 'Stored license cannot be read.',
    };
  }
}

module.exports = { installLicense, verifyLicense };
