const test = require('node:test');
const assert = require('node:assert/strict');
const ThemeBootstrap = require('../epub_browser/assets/theme-bootstrap.js');

function themedRoot(storedTheme) {
  const classes = new Set(['light-mode']);
  return {
    localStorage: { getItem(key) { return key === 'theme' ? storedTheme : null; } },
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


test('configured themes follow the device at startup without replacing the manual theme', () => {
  const root = themedRoot('forest');
  root.EpubBrowserAppearance = { automatic: true, day: 'sepia', night: 'lavender', manual: 'ocean' };
  root.EpubBrowserMode = 'server';
  const device = { matches: true };
  root.matchMedia = query => {
    assert.equal(query, '(prefers-color-scheme: dark)');
    return device;
  };

  assert.equal(ThemeBootstrap.apply(root), 'lavender');
  device.matches = false;
  assert.equal(ThemeBootstrap.apply(root), 'sepia');
  assert.deepEqual([...root.classes], ['sepia-mode']);

  root.EpubBrowserAppearance.automatic = false;
  assert.equal(ThemeBootstrap.apply(root), 'ocean');

  root.EpubBrowserMode = 'ssg';
  assert.equal(ThemeBootstrap.apply(root), 'forest');
});
