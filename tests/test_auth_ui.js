const test = require('node:test');
const assert = require('node:assert/strict');
const AuthModule = require('../epub_browser/assets/auth.js');

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload || {}),
  };
}

function rootWithFetch(fetchImpl, mode = 'server') {
  const navigations = [];
  return {
    EpubBrowserMode: mode,
    EpubBrowserBasePath: '/',
    fetch: fetchImpl,
    location: {
      pathname: '/',
      search: '',
      hash: '',
      assign(value) {
        navigations.push(value);
        this.pathname = value.split('?')[0];
      },
    },
    document: {
      getElementById() { return null; },
      querySelectorAll() { return []; },
    },
    addEventListener() {},
    navigations,
  };
}

test('auth wrapper attaches CSRF and redirects only after a 401 response', async () => {
  let finish;
  let received;
  const root = rootWithFetch((url, options) => {
    received = { url, options };
    return new Promise(resolve => { finish = resolve; });
  });
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'user-1', username: 'reader', role: 'member' },
    csrf_token: 'token',
  });

  const pending = auth.fetch('/api/account/sessions/session-2', {
    method: 'DELETE',
    headers: { Accept: 'application/json' },
  });
  await Promise.resolve();

  assert.equal(root.location.pathname, '/');
  assert.equal(received.options.credentials, 'same-origin');
  assert.equal(received.options.headers.Accept, 'application/json');
  assert.equal(received.options.headers['X-CSRF-Token'], 'token');

  finish(response(401, { code: 'authentication_required' }));
  await pending;

  assert.equal(root.location.pathname, '/login');
  assert.equal(root.navigations.length, 1);
});

test('auth wrapper does not redirect for a successful response', async () => {
  const root = rootWithFetch(() => Promise.resolve(response(200, { sessions: [] })));
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'u', username: 'reader', role: 'member' }, csrf_token: 'token' });

  const result = await auth.fetch('/api/account/sessions');

  assert.equal(result.status, 200);
  assert.deepEqual(root.navigations, []);
});

test('unsafe calls load the session once before sending the CSRF-protected request', async () => {
  const calls = [];
  const root = rootWithFetch((url, options) => {
    calls.push({ url, options });
    if (url === '/api/session') {
      return Promise.resolve(response(200, {
        user: { id: 'user-1', username: 'reader', role: 'member' },
        csrf_token: 'fresh-token',
      }));
    }
    return Promise.resolve(response(204));
  });
  const auth = AuthModule.create(root);

  await auth.fetch('/api/account/sessions/session-2', { method: 'DELETE' });

  assert.deepEqual(calls.map(call => call.url), [
    '/api/session',
    '/api/account/sessions/session-2',
  ]);
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'fresh-token');
});

test('SSG initialization returns before any account request or UI binding', async () => {
  let calls = 0;
  const root = rootWithFetch(() => {
    calls += 1;
    throw new Error('SSG must not call account APIs');
  }, 'ssg');
  const auth = AuthModule.create(root);

  const result = await auth.init();

  assert.equal(result, null);
  assert.equal(calls, 0);
  assert.deepEqual(root.navigations, []);
});
