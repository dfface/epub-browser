const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');

function loadBoundary(root) {
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/library.js', 'utf8'), {
    window: root,
    document: root.document,
    navigator: root.navigator,
    URL,
    Promise,
    console: { error() {}, log() {} },
    setTimeout() {},
    decodeURIComponent,
  });
  assert.ok(
    root.EpubBrowserCacheBoundary,
    'library runtime must expose the Server cache boundary',
  );
  return root.EpubBrowserCacheBoundary;
}

function rootForMode(mode, overrides = {}) {
  return {
    EpubBrowserMode: mode,
    EpubBrowserBasePath: '/reader/',
    EpubBrowserURL: { publicPath(path) { return `/reader${path}`; } },
    document: { cookie: '' },
    location: { href: 'https://library.test/reader/', reload() {} },
    navigator: { userAgent: 'Test' },
    ...overrides,
  };
}

test('server startup removes stale worker state before a protected fetch can run', async () => {
  const events = [];
  const cacheNames = new Set(['epub-browser-old-release', 'another-app']);
  const registration = {
    active: { scriptURL: 'https://library.test/reader/sw.js' },
    scope: 'https://library.test/reader/',
    async unregister() {
      events.push('unregister');
      return true;
    },
  };
  const serviceWorker = {
    controller: null,
    async getRegistrations() { return [registration]; },
    async register() {
      events.push('register');
      throw new Error('Server mode must not register a worker');
    },
  };
  const root = rootForMode('server', {
    navigator: { userAgent: 'Test', serviceWorker },
    caches: {
      async keys() { return [...cacheNames]; },
      async delete(name) {
        events.push(`delete:${name}`);
        return cacheNames.delete(name);
      },
    },
  });
  const boundary = loadBoundary(root);

  const source = await boundary.start(function protectedFetch() {
    events.push('protected-fetch');
    return cacheNames.has('epub-browser-old-release') ? 'cache' : 'network';
  });
  await boundary.registerWorker();

  assert.equal(source, 'network');
  assert.equal(events.includes('register'), false);
  assert.equal(cacheNames.has('epub-browser-old-release'), false);
  assert.equal(cacheNames.has('another-app'), true);
  assert.ok(events.indexOf('unregister') < events.indexOf('protected-fetch'));
  assert.ok(events.indexOf('delete:epub-browser-old-release') < events.indexOf('protected-fetch'));
});

test('server startup reloads an old controlled page without starting protected clients', async () => {
  let protectedFetches = 0;
  let reloads = 0;
  const worker = { scriptURL: 'https://library.test/reader/sw.js' };
  const root = rootForMode('server', {
    location: {
      href: 'https://library.test/reader/',
      reload() { reloads += 1; },
    },
    navigator: {
      userAgent: 'Test',
      serviceWorker: {
        controller: worker,
        async getRegistrations() {
          return [{
            active: worker,
            scope: 'https://library.test/reader/',
            async unregister() { return true; },
          }];
        },
        async register() { throw new Error('must not register'); },
      },
    },
    caches: { async keys() { return []; }, async delete() { return true; } },
  });
  const boundary = loadBoundary(root);

  const result = await boundary.start(function protectedFetch() {
    protectedFetches += 1;
  });

  assert.equal(result, null);
  assert.equal(protectedFetches, 0);
  assert.equal(reloads, 1);
});

test('SSG mode keeps service worker registration and skips server cleanup', async () => {
  const registrations = [];
  let cleanupCalls = 0;
  const root = rootForMode('ssg', {
    navigator: {
      userAgent: 'Test',
      serviceWorker: {
        async getRegistrations() { cleanupCalls += 1; return []; },
        async register(url) { registrations.push(url); return { scope: url }; },
      },
    },
    caches: {
      async keys() { cleanupCalls += 1; return []; },
      async delete() { cleanupCalls += 1; return true; },
    },
  });
  const boundary = loadBoundary(root);

  let started = 0;
  await boundary.start(function startStaticLibrary() { started += 1; });
  await boundary.registerWorker();

  assert.equal(started, 1);
  assert.deepEqual(registrations, ['/reader/sw.js']);
  assert.equal(cleanupCalls, 0);
});
