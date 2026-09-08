const { app, BrowserWindow, ipcMain, safeStorage } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { z } = require('zod');
const { openLocalDatabase } = require('./database/local-database.cjs');
const { receiptSchema, parse } = require('./ipc/validators.cjs');
const { installLicense, verifyLicense } = require('./license/license-service.cjs');
const { printReceipt } = require('./printer/receipt-printer.cjs');
const { isHardReloadShortcut } = require('./keyboard-shortcuts.cjs');
const { collectPayment, terminalStatus } = require('./payment/terminal-adapter.cjs');

let mainWindow;
let db;

function appPaths() {
  const root = app.getPath('userData');
  const paths = {
    root,
    database: path.join(root, 'database'),
    images: path.join(root, 'images'),
    backup: path.join(root, 'backup'),
    logs: path.join(root, 'logs'),
    config: path.join(root, 'config'),
  };
  Object.values(paths).forEach((value) => fs.mkdirSync(value, { recursive: true }));
  return paths;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 700,
    backgroundColor: '#fcfaf7',
    title: 'BrewBill POS',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: path.join(__dirname, 'preload.cjs'),
    },
  });
  mainWindow.webContents.on('before-input-event', (event, input) => {
    if (isHardReloadShortcut(input)) event.preventDefault();
  });
  if (app.isPackaged)
    mainWindow.loadFile(
      path.join(__dirname, '..', 'dist', 'brew-bill-ui', 'browser', 'index.html'),
    );
  else mainWindow.loadURL('http://127.0.0.1:4200');
}

function registerIpc() {
  ipcMain.handle('app:status', () => ({
    name: 'BrewBill POS',
    cloudOnly: true,
    deviceStoreReady: true,
  }));
  ipcMain.handle('license:status', () => verifyLicense(db, safeStorage));
  ipcMain.handle('license:identity', () => ({
    installationId: db.prepare("SELECT value FROM sync_metadata WHERE key='installation.id'").get()
      ?.value,
    terminalCode:
      db.prepare("SELECT value FROM local_settings WHERE key='terminal.code'").get()?.value ??
      'POS01',
  }));
  ipcMain.handle('license:install', (_event, envelope) =>
    installLicense(
      db,
      safeStorage,
      z
        .object({
          payload: z.record(z.string(), z.unknown()),
          signature: z.string().min(20).max(1024),
          public_key: z.string().min(40).max(4096),
        })
        .parse(envelope),
    ),
  );
  ipcMain.handle(
    'settings:get',
    (_event, key) =>
      db.prepare('SELECT value FROM local_settings WHERE key=?').get(z.string().max(120).parse(key))
        ?.value ?? null,
  );
  ipcMain.handle('settings:set', (_event, key, value) =>
    db
      .prepare(
        'INSERT INTO local_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
      )
      .run(z.string().max(120).parse(key), z.string().max(10_000).parse(value)),
  );
  ipcMain.handle('secure:store', (_event, key, value) => {
    if (!safeStorage.isEncryptionAvailable())
      throw new Error('Windows credential encryption is unavailable');
    const safeKey = z
      .string()
      .regex(/^[a-z0-9._-]{1,80}$/i)
      .parse(key);
    db.prepare(
      'INSERT INTO local_settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=CURRENT_TIMESTAMP',
    ).run(
      `secure.${safeKey}`,
      safeStorage.encryptString(z.string().max(16_384).parse(value)).toString('base64'),
    );
  });
  ipcMain.handle('secure:read', (_event, key) => {
    const safeKey = z
      .string()
      .regex(/^[a-z0-9._-]{1,80}$/i)
      .parse(key);
    const encrypted = db
      .prepare('SELECT value FROM local_settings WHERE key=?')
      .get(`secure.${safeKey}`)?.value;
    return encrypted && safeStorage.isEncryptionAvailable()
      ? safeStorage.decryptString(Buffer.from(encrypted, 'base64'))
      : null;
  });
  ipcMain.handle('printer:list', async () =>
    (await mainWindow.webContents.getPrintersAsync()).map((printer) => ({
      name: printer.name,
      displayName: printer.displayName,
      isDefault: printer.isDefault,
    })),
  );
  ipcMain.handle('printer:print-receipt', (_event, receipt, printerName) =>
    printReceipt(
      BrowserWindow,
      parse(receiptSchema, receipt),
      printerName ? z.string().max(256).parse(printerName) : undefined,
    ),
  );
  ipcMain.handle('payment:status', () => terminalStatus(db, safeStorage));
  ipcMain.handle('payment:collect', (_event, request) => collectPayment(db, safeStorage, request));
}

app.whenReady().then(() => {
  db = openLocalDatabase(appPaths().root);
  db.prepare(
    "INSERT OR IGNORE INTO local_settings (key,value) VALUES ('app.name','BrewBill POS')",
  ).run();
  db.prepare(
    "INSERT OR IGNORE INTO local_settings (key,value) VALUES ('terminal.code','POS01')",
  ).run();
  db.prepare("INSERT OR IGNORE INTO sync_metadata (key,value) VALUES ('installation.id',?)").run(
    randomUUID(),
  );
  registerIpc();
  createWindow();
  app.on('activate', () => BrowserWindow.getAllWindows().length === 0 && createWindow());
});
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
app.on('before-quit', () => db?.close());
