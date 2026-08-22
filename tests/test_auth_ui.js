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

function fakeElement(tagName = 'div') {
  const node = {
    tagName: String(tagName).toUpperCase(),
    children: [],
    listeners: {},
    attributes: {},
    className: '',
    disabled: false,
    hidden: false,
    value: '',
    innerHTMLWrites: 0,
    addEventListener(type, listener) { this.listeners[type] = listener; },
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name]; },
    click() {
      if (this.disabled || !this.listeners.click) return undefined;
      return this.listeners.click({ preventDefault() {}, stopPropagation() {} });
    },
  };
  node.classList = {
    add(name) {
      const classes = new Set(node.className.split(/\s+/).filter(Boolean));
      classes.add(name);
      node.className = Array.from(classes).join(' ');
    },
    remove(name) {
      node.className = node.className.split(/\s+/).filter(value => value && value !== name).join(' ');
    },
    contains(name) { return node.className.split(/\s+/).includes(name); },
    toggle(name, force) {
      const enabled = force === undefined ? !this.contains(name) : Boolean(force);
      if (enabled) this.add(name); else this.remove(name);
      return enabled;
    },
  };
  Object.defineProperty(node, 'textContent', {
    get() {
      return this._textContent + this.children.map(child => child.textContent || '').join('');
    },
    set(value) {
      this._textContent = String(value == null ? '' : value);
      this.children = [];
    },
  });
  Object.defineProperty(node, 'innerHTML', {
    get() { return ''; },
    set() {
      this.innerHTMLWrites += 1;
      throw new Error('AI job rendering must not assign innerHTML');
    },
  });
  node.textContent = '';
  return node;
}

function descendants(node) {
  const result = [];
  (node.children || []).forEach(child => {
    result.push(child);
    result.push(...descendants(child));
  });
  return result;
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function tick() {
  return new Promise(resolve => setTimeout(resolve, 0));
}

function aiJobsPayload(jobs, page = 1, totalPages = 1, total = jobs.length, pageSize = 20) {
  return {
    jobs,
    pagination: {
      page,
      page_size: pageSize,
      total,
      total_pages: totalPages,
    },
  };
}

function aiJob(overrides = {}) {
  return Object.assign({
    id: 'job-1234567890',
    attempt_number: 1,
    book_id: 'book-1',
    book_title: 'Safe Book',
    owner_user_id: 'member-1',
    owner_username: 'reader',
    scope: 'chapter',
    mode: 'chapter',
    language: 'en',
    chapter_index: 2,
    reading_boundary: 2,
    profile: 'general',
    template_id: 'reading-layer',
    template_version: 1,
    status: 'failed',
    error_code: 'provider_rate_limited',
    result_id: null,
    progress_current: 3,
    progress_total: 10,
    retried_from_job_id: null,
    retry_root_job_id: null,
    retried_by_user_id: null,
    created_at: '2026-08-23T08:00:00Z',
    updated_at: '2026-08-23T08:01:00Z',
    retryable: true,
  }, overrides);
}

function jobUiHarness(fetchImpl) {
  const intervals = new Map();
  const clearedIntervals = [];
  let nextIntervalId = 1;
  const documentListeners = {};
  const elements = {
    adminMenu: fakeElement('button'),
    adminClose: fakeElement('button'),
    adminPanel: fakeElement('section'),
    adminAiJobsStatus: fakeElement('select'),
    adminAiJobsPageSize: fakeElement('select'),
    adminAiJobsRefresh: fakeElement('button'),
    adminAiJobsBody: fakeElement('tbody'),
    adminAiJobsPagination: fakeElement('nav'),
    adminAiJobsLive: fakeElement('p'),
  };
  elements.adminAiJobsStatus.value = '';
  elements.adminAiJobsPageSize.value = '20';
  const root = rootWithFetch(fetchImpl);
  root.document = {
    hidden: false,
    createElement: fakeElement,
    getElementById(id) { return elements[id] || null; },
    querySelectorAll() { return []; },
    addEventListener(type, listener) { documentListeners[type] = listener; },
  };
  root.EpubBrowserI18n = {
    t(key, params) {
      if (key === 'admin.ai.jobs.pageButton') return `Page ${params.page}`;
      if (key === 'admin.ai.jobs.pageSummary') {
        return `Page ${params.page} of ${params.totalPages} (${params.total})`;
      }
      if (key === 'admin.ai.jobs.progress') return `${params.current}/${params.total}`;
      if (key === 'admin.ai.jobs.progressLabel') return `Progress ${params.current}/${params.total}`;
      return `[${key}]`;
    },
    formatDate(value) { return `date:${value}`; },
    onLocaleChange() {},
  };
  root.setInterval = (callback, milliseconds) => {
    const id = nextIntervalId++;
    intervals.set(id, { callback, milliseconds });
    return id;
  };
  root.clearInterval = id => {
    clearedIntervals.push(id);
    intervals.delete(id);
  };
  return { root, elements, intervals, clearedIntervals, documentListeners };
}

function adminDataResponse(url) {
  if (url === '/api/admin/users') return response(200, { users: [] });
  if (url === '/api/admin/books') return response(200, { books: [] });
  if (url === '/api/admin/ai/settings') return response(200, { settings: null });
  if (url === '/api/admin/ai/tags') return response(200, { tags: [] });
  return null;
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

test('unsafe calls refresh a stale CSRF token once before reporting failure', async () => {
  const calls = [];
  const root = rootWithFetch((url, options) => {
    calls.push({ url, options });
    if (url === '/api/session') {
      return Promise.resolve(response(200, {
        user: { id: 'user-1', username: 'reader', role: 'member' },
        csrf_token: 'fresh-token',
      }));
    }
    if (calls.filter(call => call.url === '/api/ai/followups').length === 1) {
      return Promise.resolve(response(403, { code: 'csrf_required' }));
    }
    return Promise.resolve(response(202, { followup: { id: 'followup-1' } }));
  });
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'user-1', username: 'reader', role: 'member' },
    csrf_token: 'stale-token',
  });

  const result = await auth.fetch('/api/ai/followups', { method: 'POST', body: '{}' });

  assert.equal(result.status, 202);
  assert.deepEqual(calls.map(call => call.url), [
    '/api/ai/followups', '/api/session', '/api/ai/followups',
  ]);
  assert.equal(calls[0].options.headers['X-CSRF-Token'], 'stale-token');
  assert.equal(calls[2].options.headers['X-CSRF-Token'], 'fresh-token');
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
    if (url === '/api/admin/ai/jobs?page=1&page_size=20') {
      return Promise.resolve(response(200, aiJobsPayload([], 1, 0, 0)));
    }
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
    '/api/admin/ai/settings',
    '/api/admin/ai/tags',
    '/api/admin/ai/jobs?page=1&page_size=20',
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

test('administrator AI job helper loads the default page', async () => {
  const calls = [];
  const root = rootWithFetch((url) => {
    calls.push(url);
    return Promise.resolve(response(200, {
      jobs: [],
      pagination: { page: 1, page_size: 20, total: 0, total_pages: 0 },
    }));
  });
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.loadAiJobs();

  assert.deepEqual(calls, ['/api/admin/ai/jobs?page=1&page_size=20']);
});

test('administrator AI job controls preserve filters across pagination and refresh', async () => {
  const jobCalls = [];
  const harness = jobUiHarness((url) => {
    const adminResponse = adminDataResponse(url);
    if (adminResponse) return Promise.resolve(adminResponse);
    if (url.startsWith('/api/admin/ai/jobs?')) {
      jobCalls.push(url);
      const page = Number(new URL(`https://example.test${url}`).searchParams.get('page'));
      return Promise.resolve(response(200, aiJobsPayload([aiJob()], page, 3, 51)));
    }
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });
  await auth.init();

  harness.elements.adminMenu.click();
  await tick();
  assert.equal(jobCalls.at(-1), '/api/admin/ai/jobs?page=1&page_size=20');

  const pageTwo = descendants(harness.elements.adminAiJobsPagination)
    .find(node => node.tagName === 'BUTTON' && node.textContent === 'Page 2');
  pageTwo.click();
  await tick();
  assert.equal(jobCalls.at(-1), '/api/admin/ai/jobs?page=2&page_size=20');

  harness.elements.adminAiJobsStatus.value = 'failed';
  harness.elements.adminAiJobsStatus.listeners.change();
  await tick();
  assert.equal(jobCalls.at(-1), '/api/admin/ai/jobs?page=1&page_size=20&status=failed');

  harness.elements.adminAiJobsPageSize.value = '50';
  harness.elements.adminAiJobsPageSize.listeners.change();
  await tick();
  assert.equal(jobCalls.at(-1), '/api/admin/ai/jobs?page=1&page_size=50&status=failed');

  harness.elements.adminAiJobsRefresh.click();
  await tick();
  assert.equal(jobCalls.at(-1), '/api/admin/ai/jobs?page=1&page_size=50&status=failed');
});

test('administrator AI job retry encodes IDs, disables one row, and reloads the filtered page', async () => {
  const calls = [];
  const retryResponse = deferred();
  const harness = jobUiHarness((url, options = {}) => {
    const method = options.method || 'GET';
    calls.push({
      url,
      method,
      csrf: options.headers && options.headers['X-CSRF-Token'],
    });
    if (method === 'POST') return retryResponse.promise;
    const adminResponse = adminDataResponse(url);
    if (adminResponse) return Promise.resolve(adminResponse);
    if (url.startsWith('/api/admin/ai/jobs?')) {
      const parsed = new URL(`https://example.test${url}`);
      const page = Number(parsed.searchParams.get('page'));
      return Promise.resolve(response(200, aiJobsPayload([
        aiJob({ id: 'failed/job' }),
        aiJob({ id: 'other-job', error_code: 'ai_generation_failed' }),
      ], page, 2, 4)));
    }
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });
  await auth.init();

  harness.elements.adminAiJobsStatus.value = 'failed';
  harness.elements.adminAiJobsStatus.listeners.change();
  await tick();
  descendants(harness.elements.adminAiJobsPagination)
    .find(node => node.tagName === 'BUTTON' && node.textContent === 'Page 2')
    .click();
  await tick();

  const retrying = auth.retryAiJob('failed/job');
  await Promise.resolve();
  const retryButtons = descendants(harness.elements.adminAiJobsBody)
    .filter(node => node.tagName === 'BUTTON');
  assert.equal(retryButtons.length, 2);
  assert.equal(retryButtons[0].disabled, true);
  assert.equal(retryButtons[1].disabled, false);
  assert.deepEqual(calls.at(-1), {
    url: '/api/admin/ai/jobs/failed%2Fjob/retry',
    method: 'POST',
    csrf: 'admin-csrf',
  });

  retryResponse.resolve(response(200, {
    status: 'complete',
    cached: true,
    shared: false,
    job: { id: 'retry-job', status: 'complete' },
  }));
  await retrying;

  assert.equal(calls.at(-1).url, '/api/admin/ai/jobs?page=2&page_size=20&status=failed');
  assert.equal(harness.elements.adminAiJobsLive.textContent, '[admin.ai.jobs.retryComplete]');
});

test('administrator AI job rendering ignores stale responses', async () => {
  const requests = [deferred(), deferred()];
  let requestIndex = 0;
  const harness = jobUiHarness(url => {
    if (url.startsWith('/api/admin/ai/jobs?')) return requests[requestIndex++].promise;
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  const older = auth.loadAiJobs();
  const newer = auth.loadAiJobs();
  await Promise.resolve();
  requests[1].resolve(response(200, aiJobsPayload([
    aiJob({ id: 'newest-job', book_title: 'Newest response' }),
  ])));
  await newer;
  requests[0].resolve(response(200, aiJobsPayload([
    aiJob({ id: 'stale-job', book_title: 'Stale response' }),
  ])));
  await older;

  assert.match(harness.elements.adminAiJobsBody.textContent, /Newest response/);
  assert.doesNotMatch(harness.elements.adminAiJobsBody.textContent, /Stale response/);
});

test('administrator AI job pagination clamps once and refetches the final page', async () => {
  const jobCalls = [];
  let pageOneCalls = 0;
  const harness = jobUiHarness(url => {
    if (!url.startsWith('/api/admin/ai/jobs?')) return Promise.resolve(response(404, {}));
    jobCalls.push(url);
    const page = Number(new URL(`https://example.test${url}`).searchParams.get('page'));
    if (page === 1) {
      pageOneCalls += 1;
      return Promise.resolve(response(200, aiJobsPayload(
        [aiJob()], 1, pageOneCalls === 1 ? 3 : 1, 1,
      )));
    }
    return Promise.resolve(response(200, aiJobsPayload([], page, 1, 1)));
  });
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });
  await auth.init();
  await auth.loadAiJobs();

  descendants(harness.elements.adminAiJobsPagination)
    .find(node => node.tagName === 'BUTTON' && node.textContent === 'Page 3')
    .click();
  await tick();

  assert.deepEqual(jobCalls, [
    '/api/admin/ai/jobs?page=1&page_size=20',
    '/api/admin/ai/jobs?page=3&page_size=20',
    '/api/admin/ai/jobs?page=1&page_size=20',
  ]);
});

test('administrator AI job renderer uses safe DOM, progress, timestamps, and error labels', async () => {
  const rawError = 'provider/path/<img src=x onerror=alert(1)>';
  const rawTimestamp = '/private/provider/response.json';
  const rawBook = '<img src=x onerror=alert(1)>';
  const harness = jobUiHarness(url => Promise.resolve(response(200, aiJobsPayload([
    aiJob({
      id: 'unsafe-job',
      book_title: rawBook,
      error_code: rawError,
      created_at: rawTimestamp,
      updated_at: 'not-a-date',
    }),
    aiJob({
      id: 'known-error',
      scope: 'book',
      chapter_index: null,
      error_code: 'provider_rate_limited',
    }),
  ]))));
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.loadAiJobs();

  const rendered = descendants(harness.elements.adminAiJobsBody);
  assert.equal(rendered.some(node => node.tagName === 'IMG' || node.tagName === 'SCRIPT'), false);
  assert.equal(rendered.reduce((total, node) => total + node.innerHTMLWrites, 0), 0);
  assert.match(harness.elements.adminAiJobsBody.textContent, /<img src=x onerror=alert\(1\)>/);
  assert.match(harness.elements.adminAiJobsBody.textContent, /\[admin\.ai\.jobs\.error\.unknown\]/);
  assert.match(harness.elements.adminAiJobsBody.textContent, /\[ai\.error\.provider_rate_limited\]/);
  assert.doesNotMatch(harness.elements.adminAiJobsBody.textContent, /provider\/path/);
  assert.doesNotMatch(harness.elements.adminAiJobsBody.textContent, /private\/provider/);
  const progress = rendered.filter(node => node.tagName === 'PROGRESS');
  assert.equal(progress.length, 2);
  assert.equal(progress[0].max, 10);
  assert.equal(progress[0].value, 3);
  assert.equal(progress[0].attributes['aria-label'], 'Progress 3/10');
  const scopes = rendered.filter(node => node.className === 'admin-ai-job-scope');
  assert.doesNotMatch(scopes[1].textContent, /#0/);
});

test('administrator AI job polling follows panel and document visibility without duplicates', async () => {
  const firstJobsRequest = deferred();
  let jobsRequests = 0;
  const harness = jobUiHarness(url => {
    const adminResponse = adminDataResponse(url);
    if (adminResponse) return Promise.resolve(adminResponse);
    if (url.startsWith('/api/admin/ai/jobs?')) {
      jobsRequests += 1;
      if (jobsRequests === 1) return firstJobsRequest.promise;
      return Promise.resolve(response(200, aiJobsPayload([])));
    }
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });
  await auth.init();

  harness.elements.adminMenu.click();
  await Promise.resolve();
  assert.equal(harness.intervals.size, 1);
  assert.equal(Array.from(harness.intervals.values())[0].milliseconds, 10000);
  Array.from(harness.intervals.values())[0].callback();
  await Promise.resolve();
  assert.equal(jobsRequests, 1);

  harness.elements.adminMenu.click();
  await Promise.resolve();
  assert.equal(harness.intervals.size, 1);

  firstJobsRequest.resolve(response(200, aiJobsPayload([])));
  await tick();
  Array.from(harness.intervals.values())[0].callback();
  await tick();
  assert.equal(jobsRequests, 3);

  harness.elements.adminClose.click();
  assert.equal(harness.intervals.size, 0);
  assert.deepEqual(harness.clearedIntervals, [1]);

  harness.elements.adminMenu.click();
  await tick();
  assert.equal(harness.intervals.size, 1);
  harness.root.document.hidden = true;
  harness.documentListeners.visibilitychange();
  assert.equal(harness.intervals.size, 0);

  harness.root.document.hidden = false;
  harness.documentListeners.visibilitychange();
  assert.equal(harness.intervals.size, 1);
  harness.elements.adminClose.click();
  harness.root.document.hidden = true;
  harness.documentListeners.visibilitychange();
  harness.root.document.hidden = false;
  harness.documentListeners.visibilitychange();
  assert.equal(harness.intervals.size, 0);
});
