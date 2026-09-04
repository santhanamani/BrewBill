const { z } = require('zod');

const requestSchema = z.object({
  mode: z.enum(['UPI', 'CARD']),
  amountMinor: z.number().int().positive(),
  invoiceHint: z.string().max(100),
});

function terminalConfig(db, safeStorage) {
  const read = (key) => db.prepare('SELECT value FROM local_settings WHERE key=?').get(key)?.value;
  const endpoint = read('payment.terminal.endpoint');
  const provider = read('payment.terminal.provider') ?? 'UNCONFIGURED';
  const encryptedKey = read('secure.payment.terminal.api-key');
  let apiKey = null;
  if (encryptedKey && safeStorage.isEncryptionAvailable()) {
    apiKey = safeStorage.decryptString(Buffer.from(encryptedKey, 'base64'));
  }
  return { endpoint, provider, apiKey };
}

function validEndpoint(value) {
  if (!value) return null;
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol)) throw new Error('Invalid payment terminal URL.');
  return url.toString().replace(/\/$/, '');
}

async function requestWithTimeout(url, options, timeoutMs = 6000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function terminalStatus(db, safeStorage) {
  const config = terminalConfig(db, safeStorage);
  const endpoint = validEndpoint(config.endpoint);
  if (!endpoint)
    return {
      connected: false,
      provider: config.provider,
      message: 'No payment terminal configured.',
    };
  try {
    const response = await requestWithTimeout(`${endpoint}/health`, { method: 'GET' }, 1800);
    return {
      connected: response.ok,
      provider: config.provider,
      message: response.ok ? 'Payment terminal connected.' : 'Payment terminal is unavailable.',
    };
  } catch {
    return {
      connected: false,
      provider: config.provider,
      message: 'Payment terminal is unavailable.',
    };
  }
}

async function collectPayment(db, safeStorage, value) {
  const request = requestSchema.parse(value);
  const config = terminalConfig(db, safeStorage);
  const endpoint = validEndpoint(config.endpoint);
  if (!endpoint)
    return {
      status: 'UNAVAILABLE',
      provider: config.provider,
      reference: null,
      message: 'Manual payment recorded.',
    };
  try {
    const response = await requestWithTimeout(`${endpoint}/payments`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {}),
      },
      body: JSON.stringify(request),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok || result.approved !== true) {
      return {
        status: 'DECLINED',
        provider: config.provider,
        reference: result.reference ?? null,
        message: result.message ?? 'Payment was declined.',
      };
    }
    return {
      status: 'APPROVED',
      provider: config.provider,
      reference: String(result.reference ?? ''),
      message: result.message ?? 'Payment approved.',
    };
  } catch {
    return {
      status: 'UNAVAILABLE',
      provider: config.provider,
      reference: null,
      message: 'Terminal unavailable; manual payment recorded.',
    };
  }
}

module.exports = { collectPayment, terminalStatus };
