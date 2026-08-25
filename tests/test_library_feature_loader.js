const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function createHarness({ deferAnimationFrames = false } = {}) {
  const appended = [];
  const animationFrames = [];
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
    requestAnimationFrame: deferAnimationFrames
      ? (callback) => animationFrames.push(callback)
      : undefined,
    EpubBrowserLibraryFeatureAssets: {
      sortable: '/assets/immutable/sortable.js',
      bookshelf: '/assets/immutable/bookshelf.js',
      annotationHubCss: '/assets/immutable/annotation-hub.css',
      annotation: '/assets/immutable/annotation.js',
      annotationHub: '/assets/immutable/annotation-hub.js',
    },
  };
  return { window, document, appended, animationFrames };
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
      ['script', '/assets/immutable/sortable.js'],
      ['script', '/assets/immutable/bookshelf.js'],
    ],
  );
});

test('waits for the annotation stylesheet to paint before loading its scripts', async () => {
  const harness = createHarness({ deferAnimationFrames: true });
  vm.runInNewContext(
    fs.readFileSync('epub_browser/assets/library-feature-loader.js', 'utf8'),
    { window: harness.window, document: harness.document, Promise, Error },
  );

  const loaded = harness.window.EpubBrowserLibraryFeatures.load('annotations');
  for (let index = 0; index < 4; index += 1) await Promise.resolve();
  assert.deepEqual(
    harness.appended.map((node) => node.attributes.href || node.attributes.src),
    ['/assets/immutable/annotation-hub.css'],
  );

  const firstFrame = harness.animationFrames.shift();
  assert.equal(typeof firstFrame, 'function');
  firstFrame();
  await Promise.resolve();
  const secondFrame = harness.animationFrames.shift();
  assert.equal(typeof secondFrame, 'function');
  secondFrame();
  await loaded;
  assert.deepEqual(
    harness.appended.map((node) => node.attributes.href || node.attributes.src),
    [
      '/assets/immutable/annotation-hub.css',
      '/assets/immutable/annotation.js',
      '/assets/immutable/annotation-hub.js',
    ],
  );
});
