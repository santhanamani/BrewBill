const test = require('node:test');
const assert = require('node:assert/strict');
const { isHardReloadShortcut, isZoomShortcut } = require('../electron/keyboard-shortcuts.cjs');

test('blocks only the Electron Ctrl+Shift+R hard reload shortcut', () => {
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: true, shift: true }), true);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'R', control: true, shift: true }), true);
  assert.equal(isHardReloadShortcut({ type: 'keyUp', key: 'r', control: true, shift: true }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: true, shift: false }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'F5', control: false, shift: false }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: true, shift: true, alt: true }), false);
  assert.equal(isHardReloadShortcut({ type: 'keyDown', key: 'r', control: false, shift: true, meta: true }), false);
});

test('blocks desktop zoom shortcuts so laptop layouts stay consistent', () => {
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '+', control: true }), true);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '=', control: true }), true);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '-', control: true }), true);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '0', control: true }), true);
  assert.equal(isZoomShortcut({ type: 'keyDown', code: 'NumpadAdd', control: true }), true);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '+', meta: true }), true);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '+', control: false }), false);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: '+', control: true, alt: true }), false);
  assert.equal(isZoomShortcut({ type: 'keyDown', key: 'k', control: true }), false);
});
