function isHardReloadShortcut(input) {
  return input?.type === 'keyDown'
    && input.control === true
    && input.shift === true
    && input.alt !== true
    && input.meta !== true
    && String(input.key).toLowerCase() === 'r';
}

module.exports = { isHardReloadShortcut };
