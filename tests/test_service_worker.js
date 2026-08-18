const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function loadWorker() {
  const output = fs.mkdtempSync(path.join(os.tmpdir(), 'epub-browser-worker-'));
  try {
    execFileSync('python3', [
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

for (const manifestPath of [
  '/assets/manifest.json',
  '/assets/manifest.en.json',
  '/assets/manifest.zh-CN.json',
]) {
  test(`${manifestPath} revalidates from the network despite a precached fallback`, async () => {
    const result = await fetchWithWorker(loadWorker(), manifestPath);

    assert.equal(result.response.source, 'network');
    assert.equal(result.fetches, 1);
  });
}
