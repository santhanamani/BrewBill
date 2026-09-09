function isHardReloadShortcut(input) {
  return input?.type === 'keyDown'
    && input.control === true
    && input.shift === true
    && input.alt !== true
    && input.meta !== true
    && String(input.key).toLowerCase() === 'r';
}

function isZoomShortcut(input) {
  if (input?.type !== 'keyDown' || (input.control !== true && input.meta !== true) || input.alt === true) {
    return false;
  }
  const key = String(input.key).toLowerCase();
  const code = String(input.code).toLowerCase();
  return ['+', '=', '-', '_', '0'].includes(key)
    || ['numpadadd', 'numpadsubtract', 'numpad0'].includes(code);
}

module.exports = { isHardReloadShortcut, isZoomShortcut };
