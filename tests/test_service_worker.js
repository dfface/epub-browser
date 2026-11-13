const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function projectPython() {
  const venvPython = path.join(__dirname, '..', '.venv', 'bin', 'python');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  return process.env.PYTHON || 'python3';
}

function loadWorker() {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'epub-browser-worker-'));
  try {
    execFileSync(projectPython(), [
      '-c',
      "from epub_browser.asset_publisher import AssetPublisher; import sys; AssetPublisher('epub_browser/assets', sys.argv[1]).publish()",
      output,
    ]);
    return fs.readFileSync(path.join(output, 'sw.js'), 'utf8');
  } finally {
    fs.rmSync(output, { recursive: true, force: true });
  }
}

async function fetchWithWorker(worker, pathname) {
  const handlers = {};
  const cached = { source: 'cache' };
  let fetches = 0;
  const cache = new Map([[`https://library.test${pathname}`, cached]]);
  const context = {
    URL,
    caches: {
      async match(request) {
        return cache.get(request.url);
      },
      async open() {
        return {
          async put(request, response) {
            cache.set(request.url, response);
          },
        };
      },
    },
    async fetch() {
      fetches += 1;
      return {
        status: 200,
        source: 'network',
        clone() {
          return this;
        },
      };
    },
    self: {
      addEventListener(type, handler) {
        handlers[type] = handler;
      },
      clients: { claim() {} },
      location: { origin: 'https://library.test' },
      skipWaiting() {},
    },
  };
  vm.runInNewContext(worker, context);
  const request = {
    method: 'GET',
    mode: 'cors',
    url: `https://library.test${pathname}`,
  };
  let response;
  handlers.fetch({
    request,
    respondWith(value) {
      response = Promise.resolve(value);
    },
  });
  return { response: await response, fetches };
}

test('keeps immutable precached assets cache-first', async () => {
  const worker = loadWorker();
  const precacheUrls = JSON.parse(worker.match(/const PRECACHE_URLS = (.*);/)[1]);
  const immutablePath = precacheUrls.find((url) => url.startsWith('/assets/immutable/'));
  const result = await fetchWithWorker(worker, immutablePath);

  assert.equal(result.response.source, 'cache');
  assert.equal(result.fetches, 0);
});

test('network responses are cloned before the page consumes their body', async () => {
  const worker = loadWorker();
  const handlers = {};
  let earlyClones = 0;
  let lateClones = 0;
  let cachedResponse = null;
  const networkResponse = {
    status: 200,
    source: 'network',
    bodyUsed: false,
    clone() {
      if (this.bodyUsed) {
        lateClones += 1;
        return { source: 'late-copy' };
      }
      earlyClones += 1;
      return { source: 'copy' };
    },
  };
  const context = {
    URL,
    caches: {
      async match() { return null; },
      async open() {
        await new Promise((resolve) => setTimeout(resolve, 0));
        return {
          async put(request, response) { cachedResponse = response; },
        };
      },
    },
    async fetch() { return networkResponse; },
    self: {
      addEventListener(type, handler) { handlers[type] = handler; },
      clients: { claim() {} },
      location: { origin: 'https://library.test' },
      skipWaiting() {},
    },
  };
  vm.runInNewContext(worker, context);

  const request = {
    method: 'GET',
    mode: 'cors',
    url: 'https://library.test/book/demo/chapter_1.html',
  };
  let responsePromise;
  handlers.fetch({
    request,
    respondWith(value) { responsePromise = Promise.resolve(value); },
  });
  const response = await responsePromise;
  networkResponse.bodyUsed = true;
  await new Promise((resolve) => setTimeout(resolve, 5));

  assert.equal(response.source, 'network');
  assert.equal(earlyClones, 1);
  assert.equal(lateClones, 0);
  assert.equal(cachedResponse && cachedResponse.source, 'copy');
});

for (const manifestPath of [
  '/assets/manifest.json',
  '/assets/manifest.en.json',
  '/assets/manifest.zh-CN.json',
  '/assets/manifest.zh-TW.json',
  '/assets/manifest.ko.json',
  '/assets/manifest.ja.json',
  '/assets/manifest.es.json',
  '/assets/manifest.de.json',
  '/assets/manifest.fr.json',
  '/assets/manifest.ru.json',
  '/assets/manifest.it.json',
  '/assets/manifest.pt-BR.json',
  '/assets/manifest.ar.json',
  '/assets/manifest.id.json',
  '/assets/manifest.hi.json',
  '/assets/manifest.vi.json',
  '/assets/manifest.th.json',
  '/assets/manifest.ms.json',
]) {
  test(`${manifestPath} revalidates from the network despite a precached fallback`, async () => {
    const result = await fetchWithWorker(loadWorker(), manifestPath);

    assert.equal(result.response.source, 'network');
    assert.equal(result.fetches, 1);
  });
}
