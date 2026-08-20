const test = require('node:test');
const assert = require('node:assert/strict');
const AuthModule = require('../epub_browser/assets/auth.js');

function response(status, payload) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(payload || {}),
    clone: () => response(status, payload),
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

test('wrong current password stays signed in and shows the localized form error', async () => {
  const status = { textContent: '', className: '', hidden: true };
  const passwordFields = [
    { value: 'wrong' },
    { value: 'replacement' },
  ];
  const passwordForm = {
    elements: {
      current_password: passwordFields[0],
      new_password: passwordFields[1],
    },
    listeners: {},
    addEventListener(type, listener) { this.listeners[type] = listener; },
    querySelectorAll() { return passwordFields; },
  };
  const root = rootWithFetch(() => Promise.resolve(response(401, {
    code: 'invalid_credentials',
    message: 'Raw server message',
  })));
  root.document.getElementById = id => ({
    accountStatus: status,
    accountPasswordForm: passwordForm,
  })[id] || null;
  root.EpubBrowserI18n = {
    t(key) {
      if (key === 'account.error.invalid_credentials') return '当前密码不正确。';
      return key;
    },
  };
  const auth = AuthModule.create(root);
  const activeSession = {
    user: { id: 'u', username: 'reader', role: 'member' },
    csrf_token: 'token',
  };
  auth.setSession(activeSession);
  await auth.init();

  passwordForm.listeners.submit({ preventDefault() {} });
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.deepEqual(root.navigations, []);
  assert.equal(auth.getSession(), activeSession);
  assert.equal(status.textContent, '当前密码不正确。');
  assert.equal(status.hidden, false);
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

test('member account settings keep the administration module hidden', async () => {
  const adminPanel = { hidden: false };
  const adminMenu = { hidden: false, addEventListener() {} };
  const associationCard = { hidden: false };
  const adminIdentitiesSection = { hidden: false };
  const root = rootWithFetch(() => Promise.resolve(response(200, {})));
  root.document.getElementById = id => ({
    adminPanel,
    adminMenu,
    associationCard,
    adminIdentitiesSection,
  })[id] || null;
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'member', username: 'reader', role: 'member' },
    csrf_token: 'token',
  });

  await auth.init();

  assert.equal(adminPanel.hidden, true);
  assert.equal(adminMenu.hidden, true);
  assert.equal(associationCard.hidden, true);
  assert.equal(adminIdentitiesSection.hidden, true);
});

test('trusted-proxy controls are visible only for a configured administrator session', async () => {
  const adminPanel = { hidden: true };
  const adminMenu = { hidden: true, addEventListener() {} };
  const associationCard = { hidden: true };
  const adminIdentitiesSection = { hidden: true };
  const root = rootWithFetch(() => Promise.resolve(response(200, {})));
  root.document.getElementById = id => ({
    adminPanel,
    adminMenu,
    associationCard,
    adminIdentitiesSection,
  })[id] || null;
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'owner', role: 'admin' },
    csrf_token: 'token',
    authentication: { proxy_enabled: true, pending_proxy_identity: true },
  });

  await auth.init();

  assert.equal(adminPanel.hidden, false);
  assert.equal(adminMenu.hidden, false);
  assert.equal(associationCard.hidden, false);
  assert.equal(adminIdentitiesSection.hidden, false);
});

test('account settings and administration open as separate surfaces', async () => {
  const calls = [];
  function control() {
    return {
      hidden: false,
      listeners: {},
      addEventListener(type, listener) { this.listeners[type] = listener; },
    };
  }
  function panel() {
    return {
      hidden: false,
      active: false,
      attributes: {},
      classList: {
        add() { this.owner.active = true; },
        remove() { this.owner.active = false; },
        owner: null,
      },
      setAttribute(name, value) { this.attributes[name] = value; },
    };
  }
  const accountMenu = control();
  const adminMenu = control();
  const accountPanel = panel();
  const adminPanel = panel();
  accountPanel.classList.owner = accountPanel;
  adminPanel.classList.owner = adminPanel;
  const root = rootWithFetch((url) => {
    calls.push(url);
    if (url === '/api/account/sessions') return Promise.resolve(response(200, { sessions: [] }));
    if (url === '/api/admin/users') return Promise.resolve(response(200, { users: [] }));
    if (url === '/api/admin/books') return Promise.resolve(response(200, { books: [] }));
    return Promise.resolve(response(404, {}));
  });
  root.document.getElementById = id => ({
    accountMenu,
    adminMenu,
    accountPanel,
    adminPanel,
  })[id] || null;
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'owner', role: 'admin' },
    csrf_token: 'token',
    authentication: { proxy_enabled: false, pending_proxy_identity: false },
  });

  await auth.init();
  accountMenu.listeners.click();
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.equal(accountPanel.active, true);
  assert.equal(adminPanel.active, false);
  assert.deepEqual(calls, ['/api/account/sessions']);

  adminMenu.listeners.click();
  await new Promise(resolve => setTimeout(resolve, 0));

  assert.equal(adminPanel.active, true);
  assert.deepEqual(calls, [
    '/api/account/sessions',
    '/api/admin/users',
    '/api/admin/books',
  ]);
});

test('proxy association form stays hidden without a pending third-party identity', async () => {
  const associationCard = { hidden: false };
  const adminIdentitiesSection = { hidden: true };
  const root = rootWithFetch(() => Promise.resolve(response(200, {})));
  root.document.getElementById = id => ({
    associationCard,
    adminIdentitiesSection,
  })[id] || null;
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'owner', role: 'admin' },
    csrf_token: 'token',
    authentication: { proxy_enabled: true, pending_proxy_identity: false },
  });

  await auth.init();

  assert.equal(associationCard.hidden, true);
  assert.equal(adminIdentitiesSection.hidden, false);
});

test('anonymous proxy association sends JSON with the page authentication nonce', async () => {
  let received;
  const root = rootWithFetch((url, options) => {
    received = { url, options };
    return Promise.resolve(response(201, { identity: {} }));
  });
  root.document.querySelector = selector => selector === 'meta[name="epub-browser-auth-nonce"]'
    ? { content: 'strict-page-nonce' }
    : null;
  const auth = AuthModule.create(root);

  await auth.associate({ username: 'reader', password: 'secret' });

  assert.equal(received.url, '/api/identity/link');
  assert.equal(received.options.headers['Content-Type'], 'application/json');
  assert.equal(received.options.headers['X-EPUB-Browser-Auth-Nonce'], 'strict-page-nonce');
  assert.equal(received.options.credentials, 'same-origin');
});

test('administrator identity helpers create and delete mappings with CSRF', async () => {
  const calls = [];
  const root = rootWithFetch((url, options) => {
    calls.push({ url, options });
    return Promise.resolve(response(options.method === 'POST' ? 201 : 200, {
      identity: { issuer: 'issuer', subject: 'subject', user_id: 'member' },
    }));
  });
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.createIdentity({
    issuer: 'issuer',
    subject: 'subject',
    user_id: 'member',
    display_name: 'Member',
  }, false);
  await auth.deleteIdentity('issuer', 'subject', false);

  assert.deepEqual(calls.map(call => [call.url, call.options.method]), [
    ['/api/admin/identities', 'POST'],
    ['/api/admin/identities', 'DELETE'],
  ]);
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'admin-csrf');
  assert.equal(calls[1].options.headers['X-CSRF-Token'], 'admin-csrf');
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    issuer: 'issuer',
    subject: 'subject',
  });
});

test('account success feedback uses the shared notification component', async () => {
  const shown = [];
  const root = rootWithFetch(() => Promise.resolve(response(201, {
    identity: { issuer: 'issuer', subject: 'subject', user_id: 'member' },
  })));
  root.EpubBrowserI18n = { t(key) { return key === 'admin.identityCreated' ? 'Created' : key; } };
  root.EpubBrowserNotification = {
    show(message, type) { shown.push({ message, type }); },
  };
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.createIdentity({
    issuer: 'issuer',
    subject: 'subject',
    user_id: 'member',
  }, false);

  assert.deepEqual(shown, [{ message: 'Created', type: 'success' }]);
});

test('administrator saves the complete multi-user book grant selection in one request', async () => {
  let received;
  const root = rootWithFetch((url, options) => {
    received = { url, options };
    return Promise.resolve(response(200, { grants: { user_ids: ['one', 'two'] } }));
  });
  root.EpubBrowserNotification = { show() {} };
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.saveBookGrants('book/id', ['one', 'two'], false);

  assert.equal(received.url, '/api/admin/books/book%2Fid/grants');
  assert.equal(received.options.method, 'PUT');
  assert.equal(received.options.headers['X-CSRF-Token'], 'admin-csrf');
  assert.deepEqual(JSON.parse(received.options.body), { user_ids: ['one', 'two'] });
});
