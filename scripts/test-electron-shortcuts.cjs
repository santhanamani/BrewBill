const test = require('node:test');
const assert = require('node:assert/strict');
const { isHardReloadShortcut } = require('../electron/keyboard-shortcuts.cjs');

test('blocks only the Electron Ctrl+Shift+R hard reload shortcut', () => {
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: true, shift: true }), true);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'R', control: true, shift: true }), true);
  assert.equal(isHardReloadShortcut({ type: 'keyUp', key: 'r', control: true, shift: true }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: true, shift: false }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'F5', control: false, shift: false }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: true, shift: true, alt: true }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: false, shift: true, meta: true }), false);
});
