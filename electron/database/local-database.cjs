const fs = require('node:fs');
const path = require('node:path');
const Database = require('better-sqlite3');

function openLocalDatabase(userDataPath) {
  const dataPath = path.join(userDataPath, 'database');
  fs.mkdirSync(dataPath, { recursive: true });
  const db = new Database(path.join(dataPath, 'brewbill.sqlite'));
  db.pragma('journal_mode = WAL');
  // This database is a device-security store only. Catalogue, orders, holds,
  // KOT and inventory are never created or read locally.
  db.exec(`
    CREATE TABLE IF NOT EXISTS local_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS sync_metadata (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
  `);
  return db;
}

module.exports = { openLocalDatabase };
