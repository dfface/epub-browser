const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createHarness() {
  const appended = [];
  const document = {
    readyState: 'complete',
    createElement(tagName) {
      const listeners = {};
      return {
        tagName,
        attributes: {},
        setAttribute(name, value) { this.attributes[name] = String(value); },
        addEventListener(type, listener) { listeners[type] = listener; },
        fire(type) { if (listeners[type]) listeners[type](); },
      };
    },
    head: {
      appendChild(node) {
        appended.push(node);
        node.fire('load');
      },
    },
    documentElement: null,
    addEventListener() {},
  };
  const window = {
    document,
    EpubBrowserLibraryFeatureAssets: {
      bookshelfCss: '/assets/immutable/bookshelf.css',
      sortable: '/assets/immutable/sortable.js',
      bookshelf: '/assets/immutable/bookshelf.js',
    },
  };
  return { window, document, appended };
}

test('loads one Library feature only once and preserves its dependency order', async () => {
  const harness = createHarness();
  vm.runInNewContext(
    fs.readFileSync('epub_browser/assets/library-feature-loader.js', 'utf8'),
    { window: harness.window, document: harness.document, Promise, Error },
  );

  await Promise.all([
    harness.window.EpubBrowserLibraryFeatures.load('bookshelf'),
    harness.window.EpubBrowserLibraryFeatures.load('bookshelf'),
  ]);

  assert.deepEqual(
    harness.appended.map((node) => [node.tagName, node.attributes.href || node.attributes.src]),
    [
      ['link', '/assets/immutable/bookshelf.css'],
      ['script', '/assets/immutable/sortable.js'],
      ['script', '/assets/immutable/bookshelf.js'],
    ],
  );
});
