const test = require('node:test');
const assert = require('node:assert/strict');
const ThemeBootstrap = require('../epub_browser/assets/theme-bootstrap.js');

function themedRoot(storedTheme) {
  const classes = new Set(['light-mode']);
  return {
    localStorage: { getItem() { return storedTheme; } },
    document: {
      documentElement: {
        classList: {
          add(value) { classes.add(value); },
          remove(value) { classes.delete(value); },
          contains(value) { return classes.has(value); },
        },
      },
    },
    classes,
  };
}

test('public account bootstrap applies the saved EPUB Browser theme', () => {
  const root = themedRoot('forest');

  assert.equal(ThemeBootstrap.apply(root), 'forest');
  assert.equal(root.classes.has('forest-mode'), true);
  assert.equal(root.classes.has('light-mode'), false);
});

test('public account bootstrap rejects unknown stored theme names', () => {
  const root = themedRoot('injected-theme');

  assert.equal(ThemeBootstrap.apply(root), 'light');
  assert.equal(root.classes.has('light-mode'), true);
  assert.equal(root.classes.has('injected-theme-mode'), false);
});
