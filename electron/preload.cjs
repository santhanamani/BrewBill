const { contextBridge, ipcRenderer } = require('electron');
const invoke = (channel, ...args) => ipcRenderer.invoke(channel, ...args);
contextBridge.exposeInMainWorld('brewBill', {
  app: { status: () => invoke('app:status') },
  license: {
    status: () => invoke('license:status'),
    identity: () => invoke('license:identity'),
    install: (envelope) => invoke('license:install', envelope),
  },
  settings: {
    get: (key) => invoke('settings:get', key),
    set: (key, value) => invoke('settings:set', key, value),
  },
  secure: {
    store: (key, value) => invoke('secure:store', key, value),
    read: (key) => invoke('secure:read', key),
  },
  printer: {
    list: () => invoke('printer:list'),
    printReceipt: (receipt, printerName) => invoke('printer:print-receipt', receipt, printerName),
  },
  payment: {
    status: () => invoke('payment:status'),
    collect: (request) => invoke('payment:collect', request),
  },
});
