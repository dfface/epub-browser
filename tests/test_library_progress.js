const test = require('node:test');
const assert = require('node:assert/strict');
const Progress = require('../epub_browser/assets/library-progress.js');

function snapshot(values) {
  return Object.assign({
    generation: 1, revision: 1, trigger: 'startup', phase: 'processing',
    total: 2, completed: 0, converted: 0, reused: 0, failed: 0,
    removed: 0, in_flight: 1, active_books: 0, catalog_revision: 0,
    latest_book: null, failures: []
  }, values || {});
}

function progressMount() {
  const nodes = {};
  function node() {
    const attributes = {};
    const classes = [];
    const value = {
      attributes,
      children: [],
      hidden: false,
      style: {},
      classList: {
        add(name) { if (!classes.includes(name)) classes.push(name); },
        remove(name) { const index = classes.indexOf(name); if (index !== -1) classes.splice(index, 1); },
        contains(name) { return classes.includes(name); },
      },
      setAttribute(name, content) { attributes[name] = String(content); },
      getAttribute(name) { return attributes[name] || null; },
      removeAttribute(name) { delete attributes[name]; },
      appendChild(child) { value.children.push(child); return child; },
      removeChild(child) { value.children.splice(value.children.indexOf(child), 1); },
      addEventListener(type, listener) { value.listener = listener; },
    };
    Object.defineProperty(value, 'innerHTML', { set() { throw new Error('Progress UI must not use innerHTML'); } });
    return value;
  }
  const mount = node();
  ['[data-progress-title]', '[data-progress-summary]', '[data-progress-track]',
    '[data-progress-bar]', '[data-progress-latest]', '[data-progress-failures]',
    '[data-progress-failure-list]', '[data-progress-close]'].forEach((selector) => { nodes[selector] = node(); });
  mount.querySelector = (selector) => nodes[selector] || null;
  return { mount, nodes, createElement: node };
}

test('rejects stale snapshots and deduplicates catalog refresh', async () => {
  let refreshes = 0;
  const controller = Progress.createController({
    render() {},
    refreshMetadata() { refreshes += 1; return Promise.resolve(); },
    schedule(fn) { fn(); return 1; },
    cancelSchedule() {}
  });
  controller.accept(snapshot({ revision: 2, catalog_revision: 4 }));
  controller.accept(snapshot({ revision: 1, catalog_revision: 3 }));
  controller.accept(snapshot({ revision: 3, catalog_revision: 4 }));
  await Promise.resolve();

  assert.equal(controller.state.snapshot.revision, 3);
  assert.equal(refreshes, 1);
});

test('serializes metadata refreshes and coalesces pending snapshots to the newest revision', async () => {
  const calls = [];
  const pending = [];
  const controller = Progress.createController({
    render() {},
    refreshMetadata(revision) {
      calls.push(revision);
      return new Promise((resolve) => pending.push(resolve));
    },
    schedule() { return 1; },
    cancelSchedule() {}
  });

  controller.accept(snapshot({ catalog_revision: 1 }));
  controller.accept(snapshot({ revision: 2, catalog_revision: 3 }));
  controller.accept(snapshot({ revision: 3, catalog_revision: 2 }));
  await Promise.resolve();
  assert.deepEqual(calls, [1]);

  pending.shift()();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(calls, [1, 3]);
  pending.shift()();
  await Promise.resolve();
});

test('an observed successful generation remains visible until dismissed', () => {
  const controller = Progress.createController({
    render() {}, refreshMetadata() { return Promise.resolve(); }
  });
  controller.accept(snapshot({ phase: 'processing' }));
  controller.accept(snapshot({ revision: 2, phase: 'complete', completed: 2, converted: 2 }));
  assert.equal(controller.state.visible, true);
  controller.dismiss();
  assert.equal(controller.state.hiddenGeneration, 1);
});

test('an initial complete snapshot stays quiet', () => {
  const controller = Progress.createController({ render() {}, refreshMetadata() { return Promise.resolve(); }, schedule() { throw new Error('must not schedule'); }, cancelSchedule() {} });
  controller.accept(snapshot({ phase: 'complete', completed: 2, converted: 2 }));
  assert.equal(controller.state.visible, false);
});

test('reports a direct deletion without a misleading zero-book conversion count', () => {
  const harness = progressMount();
  const root = {
    document: { createElement: harness.createElement },
    EpubBrowserI18n: { t(key, params) { return key === 'library.progress.removed' ? 'Removed ' + params.count + ' book' : key; } },
  };
  const controller = Progress.createController(Progress.createDomOptions(root, harness.mount));

  controller.accept(snapshot({ phase: 'processing', total: 0, removed: 1 }));

  assert.equal(harness.nodes['[data-progress-summary]'].textContent, 'Removed 1 book');
});

test('an initial degraded snapshot remains visible', () => {
  const controller = Progress.createController({ render() {}, refreshMetadata() { return Promise.resolve(); }, schedule() { return 1; }, cancelSchedule() {} });
  controller.accept(snapshot({ phase: 'degraded', failed: 1 }));
  assert.equal(controller.state.visible, true);
});

test('degraded dismissal survives reconnect but not the next generation', () => {
  const controller = Progress.createController({
    render() {}, refreshMetadata() { return Promise.resolve(); },
    schedule() { return 1; }, cancelSchedule() {}
  });
  controller.accept(snapshot({ phase: 'degraded', failed: 1 }));
  controller.dismiss();
  controller.disconnected();
  controller.accept(snapshot({ revision: 2, phase: 'degraded', failed: 1 }));
  assert.equal(controller.state.visible, false);
  controller.accept(snapshot({ generation: 2, revision: 1, trigger: 'watch' }));
  assert.equal(controller.state.visible, true);
});

test('reconnect retains the last counters until a newer snapshot arrives', () => {
  const controller = Progress.createController({ render() {}, refreshMetadata() { return Promise.resolve(); }, schedule() { return 1; }, cancelSchedule() {} });
  controller.accept(snapshot({ total: 5, completed: 3, phase: 'processing' }));
  controller.disconnected();
  assert.equal(controller.state.connected, false);
  assert.equal(controller.state.snapshot.completed, 3);
  controller.accept(snapshot({ revision: 2, total: 5, completed: 4, phase: 'processing' }));
  assert.equal(controller.state.connected, true);
  assert.equal(controller.state.snapshot.completed, 4);
});

test('renders failure values through textContent', () => {
  const harness = progressMount();
  const root = {
    document: { createElement: harness.createElement },
    EpubBrowserI18n: { t(key) { return key; } },
  };
  const controller = Progress.createController(Progress.createDomOptions(root, harness.mount));
  const unsafe = '<img src=x onerror=alert(1)>';
  controller.accept(snapshot({ phase: 'degraded', failed: 1, failures: [{ filename: unsafe, message: unsafe }] }));

  assert.equal(harness.nodes['[data-progress-failure-list]'].children[0].textContent, unsafe + ': ' + unsafe);
});

test('keeps a named progressbar during discovery and announces a meaningful degraded failure once', () => {
  const harness = progressMount();
  const root = {
    document: { createElement: harness.createElement },
    EpubBrowserI18n: { t(key) { return key; } },
  };
  const controller = Progress.createController(Progress.createDomOptions(root, harness.mount));
  controller.accept(snapshot({ total: 5, completed: 2, phase: 'processing' }));
  controller.accept(snapshot({ revision: 2, total: 5, phase: 'discovering' }));

  const track = harness.nodes['[data-progress-track]'];
  assert.equal(track.getAttribute('role'), 'progressbar');
  assert.equal(track.getAttribute('aria-labelledby'), 'libraryProgressTitle');
  assert.equal(track.getAttribute('aria-valuemin'), '0');
  assert.equal(track.getAttribute('aria-valuemax'), null);
  assert.equal(track.getAttribute('aria-valuenow'), null);

  controller.accept(snapshot({ revision: 3, total: 5, phase: 'degraded', failed: 1, failures: [{ filename: 'broken.epub', message: 'invalid file' }] }));
  const summary = harness.nodes['[data-progress-summary]'];
  assert.equal(summary.getAttribute('role'), 'alert');
  assert.match(summary.textContent, /library\.progress\.degraded/);

  controller.accept(snapshot({ revision: 4, total: 5, phase: 'degraded', failed: 1, failures: [{ filename: 'broken.epub', message: 'invalid file' }] }));
  assert.equal(summary.getAttribute('role'), null);
  assert.equal(summary.getAttribute('aria-live'), 'polite');
});

test('only exposes and honors the close action for completed generations', () => {
  const harness = progressMount();
  const root = {
    document: { createElement: harness.createElement },
    EpubBrowserI18n: { t(key) { return key; } },
    setTimeout() { return 1; },
    clearTimeout() {},
  };
  const controller = Progress.createController(Progress.createDomOptions(root, harness.mount));
  const close = harness.nodes['[data-progress-close]'];

  controller.accept(snapshot({ phase: 'processing' }));
  assert.equal(close.hidden, true);
  assert.equal(close.disabled, true);
  controller.dismiss();
  assert.equal(controller.state.visible, true);

  controller.accept(snapshot({ revision: 2, phase: 'complete', completed: 2 }));
  assert.equal(close.hidden, false);
  assert.equal(close.disabled, false);
  controller.dismiss();
  assert.equal(controller.state.visible, false);

  controller.accept(snapshot({ generation: 2, revision: 1, phase: 'degraded', failed: 1 }));
  assert.equal(close.hidden, false);
  assert.equal(close.disabled, false);
  controller.dismiss();
  assert.equal(controller.state.visible, false);
});

test('starts EventSource at the normalized server events URL and wires progress, reconnect, and close', () => {
  const harness = progressMount();
  let source;
  let localeChangeListener;
  let locale = 'en';
  function FakeEventSource(url) {
    this.url = url;
    this.listeners = {};
    source = this;
  }
  FakeEventSource.prototype.addEventListener = function(name, listener) { this.listeners[name] = listener; };
  const root = {
    EpubBrowserMode: 'server',
    EpubBrowserBasePath: '/reader/',
    EventSource: FakeEventSource,
    EpubBrowserI18n: {
      t(key) { return locale + ':' + key; },
      onLocaleChange(listener) { localeChangeListener = listener; },
    },
    document: {
      getElementById(id) { return id === 'libraryProgress' ? harness.mount : null; },
      createElement: harness.createElement,
    },
    setTimeout() { return 1; },
    clearTimeout() {},
  };

  const started = Progress.start(root);
  assert.equal(source.url, '/reader/api/library-events');
  source.listeners.progress({ data: JSON.stringify(snapshot({ completed: 1 })) });
  assert.equal(started.controller.state.snapshot.completed, 1);
  assert.equal(harness.nodes['[data-progress-summary]'].textContent, 'en:library.progress.summary');
  locale = 'zh-CN';
  localeChangeListener();
  assert.equal(harness.nodes['[data-progress-summary]'].textContent, 'zh-CN:library.progress.summary');
  source.onerror();
  assert.equal(started.controller.state.connected, false);
  source.onopen();
  assert.equal(started.controller.state.connected, true);
  harness.nodes['[data-progress-close]'].listener();
  assert.equal(started.controller.state.visible, true);
  source.listeners.progress({ data: JSON.stringify(snapshot({ generation: 2, phase: 'degraded', failed: 1 })) });
  harness.nodes['[data-progress-close]'].listener();
  assert.equal(started.controller.state.visible, false);
});

test('start only opens EventSource for a server page with a mount', () => {
  let opened = 0;
  const root = {
    EpubBrowserMode: 'ssg', EventSource() { opened += 1; },
    document: { getElementById() { return null; } },
  };
  assert.equal(Progress.start(root), null);
  root.EpubBrowserMode = 'server';
  assert.equal(Progress.start(root), null);
  assert.equal(opened, 0);
});
