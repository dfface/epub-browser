const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createHarness() {
  const appended = [];
  const document = {
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
  };
  const window = {
    document,
    EpubBrowserBookFeatureAssets: {
      bookshelfCss: '/assets/immutable/bookshelf.css',
      sortable: '/assets/immutable/sortable.js',
      bookshelf: '/assets/immutable/bookshelf.js',
      annotationHubCss: '/assets/immutable/annotation-hub.css',
      annotation: '/assets/immutable/annotation.js',
      annotationHub: '/assets/immutable/annotation-hub.js',
    },
  };
  return { window, appended };
}

test('loads a Book feature once and preserves its dependency order', async () => {
  const harness = createHarness();
  vm.runInNewContext(
    fs.readFileSync('epub_browser/assets/book-feature-loader.js', 'utf8'),
    { window: harness.window, Promise, Error },
  );

  await Promise.all([
    harness.window.EpubBrowserBookFeatures.load('bookshelf'),
    harness.window.EpubBrowserBookFeatures.load('bookshelf'),
  ]);

  assert.deepEqual(
    harness.appended.map((node) => [node.tagName, node.attributes.href || node.attributes.src]),
    [
      ['script', '/assets/immutable/sortable.js'],
      ['script', '/assets/immutable/bookshelf.js'],
    ],
  );
});

test('loads annotation assets in CSS then script dependency order', async () => {
  const harness = createHarness();
  vm.runInNewContext(
    fs.readFileSync('epub_browser/assets/book-feature-loader.js', 'utf8'),
    { window: harness.window, Promise, Error },
  );

  await harness.window.EpubBrowserBookFeatures.load('annotations');

  assert.deepEqual(
    harness.appended.map((node) => [node.tagName, node.attributes.href || node.attributes.src]),
    [
      ['link', '/assets/immutable/annotation-hub.css'],
      ['script', '/assets/immutable/annotation.js'],
      ['script', '/assets/immutable/annotation-hub.js'],
    ],
  );
});
