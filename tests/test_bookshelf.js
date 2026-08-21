const test = require('node:test');
const assert = require('node:assert/strict');
const Bookshelf = require('../epub_browser/assets/bookshelf.js');

function authenticatedRoot(mode = 'server') {
  const requests = [];
  return {
    EpubBrowserMode: mode,
    requests,
    EpubBrowserAuth: {
      fetch(url, options = {}) {
        const authenticated = Object.assign({}, options, {
          credentials: 'same-origin',
          headers: Object.assign({}, options.headers, { 'X-CSRF-Token': 'csrf' }),
        });
        requests.push({ url, options: authenticated });
        return Promise.resolve({ status: 201, json: () => Promise.resolve({ version: 3 }) });
      },
    },
  };
}

test('server bookshelf sync uses shared auth and sends no client username', async () => {
  const root = authenticatedRoot();

  await Bookshelf.syncRequest(root, 3, { items: ['book'], groups: {} });

  assert.equal(root.requests.length, 1);
  const received = root.requests[0];
  assert.equal(received.url, '/sync');
  assert.equal(received.options.credentials, 'same-origin');
  assert.equal(received.options.headers['X-CSRF-Token'], 'csrf');
  assert.equal(received.options.headers['X-Username'], undefined);
  assert.deepEqual(JSON.parse(received.options.body), {
    version: 3,
    data: { items: ['book'], groups: {} },
  });
});

test('SSG bookshelf stays local and never initializes auth', async () => {
  const root = authenticatedRoot('ssg');

  const response = await Bookshelf.syncRequest(root, 3, { items: [] });

  assert.equal(response, null);
  assert.equal(root.requests.length, 0);
});
