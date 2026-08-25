const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const AuthModule = require('../epub_browser/assets/auth.js');
const { createRuntime, dictionaries } = require('../epub_browser/assets/i18n.js');

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
    focus() { this.focused = true; },
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
  if (url === '/api/admin/books/index') return response(200, { books: [] });
  if (url === '/api/admin/ai/settings') return response(200, { settings: null });
  if (url === '/api/admin/ai/tags') return response(200, { tags: [] });
  return null;
}

function adminBook(overrides = {}) {
  return Object.assign({
    id: 'book-1',
    title: 'Book 01',
    authors: [],
    epub_tags: [],
    visibility: 'authenticated',
    grant_count: 0,
    ai_profile: 'auto',
    ai_tags: [],
    ai_result_count: 0,
    created_at: '2026-08-22T08:00:00Z',
    updated_at: '2026-08-23T08:00:00Z',
  }, overrides);
}

function bookUiHarness(fetchImpl) {
  const localeListeners = [];
  const elements = {
    adminMenu: fakeElement('button'),
    adminClose: fakeElement('button'),
    adminPanel: fakeElement('section'),
    adminBookTableSurface: fakeElement('div'),
    adminBookLegacyList: fakeElement('ul'),
    adminBookSearch: fakeElement('input'),
    adminBookVisibilityFilter: fakeElement('select'),
    adminBookTagFilter: fakeElement('select'),
    adminBookSort: fakeElement('select'),
    adminBookPageSize: fakeElement('select'),
    adminBookRefresh: fakeElement('button'),
    adminBookSelectPage: fakeElement('input'),
    adminBookBulkActions: fakeElement('section'),
    adminBookSelectionCount: fakeElement('p'),
    adminBookClearSelection: fakeElement('button'),
    adminBookBulkRestrict: fakeElement('button'),
    adminBookBulkGrantFieldset: fakeElement('fieldset'),
    adminBookBulkMembers: fakeElement('div'),
    adminBookBulkGrant: fakeElement('button'),
    adminBookList: fakeElement('tbody'),
    adminBookPagination: fakeElement('nav'),
    adminBookLive: fakeElement('p'),
  };
  elements.adminBookTableSurface.hidden = true;
  elements.adminBookBulkActions.hidden = true;
  elements.adminBookSort.value = 'title_asc';
  elements.adminBookPageSize.value = '20';
  const root = rootWithFetch(fetchImpl);
  root.document = {
    hidden: false,
    createElement: fakeElement,
    getElementById(id) { return elements[id] || null; },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  root.EpubBrowserI18n = {
    t(key, params) {
      const values = {
        'admin.books.pageButton': `Page ${params && params.page}`,
        'admin.books.pageSummary': `Page ${params && params.page} of ${params && params.totalPages} (${params && params.total})`,
        'admin.books.grantCount': `${params && params.count} members`,
        'admin.books.resultCount': `${params && params.count} results`,
        'admin.books.live.cleared': `Cleared ${params && params.count} results`,
        'admin.books.bulk.selectionCount': `${params && params.count} selected`,
      };
      return values[key] || `[${key}]`;
    },
    formatDate(value) { return `date:${value}`; },
    onLocaleChange(listener) { localeListeners.push(listener); },
  };
  return { root, elements, localeListeners };
}

function rowTitles(body) {
  return body.children.map(row => {
    const title = descendants(row).find(node => node.tagName === 'STRONG');
    return title ? title.textContent : row.children[0] && row.children[0].textContent;
  });
}

function adminBookButtons(body, bookId) {
  return descendants(body).filter(node => node.tagName === 'BUTTON'
    && node.getAttribute('data-book-id') === bookId);
}

function editorRows(body) {
  return body.children.filter(row => row.className === 'admin-book-editor-row');
}

test('book index renders only the current page and resets pagination for controls', async () => {
  const books = Array.from({ length: 45 }, (_, index) => adminBook({
    id: `book-${String(index + 1).padStart(2, '0')}`,
    title: `Book ${String(index + 1).padStart(2, '0')}`,
    visibility: index % 2 ? 'restricted' : 'authenticated',
    ai_tags: index % 3 ? [] : [{ id: 'tag-1', name: 'Science' }],
  })).reverse();
  const calls = [];
  const { root, elements } = bookUiHarness(url => {
    calls.push(url);
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books }));
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();

  assert.equal(elements.adminBookTableSurface.hidden, false);
  assert.equal(elements.adminBookLegacyList.hidden, true);
  assert.equal(elements.adminBookList.children.length, 20);
  assert.equal(rowTitles(elements.adminBookList)[0], 'Book 01');
  const next = descendants(elements.adminBookPagination).find(node => node.textContent === '[admin.books.nextPage]');
  next.click();
  assert.equal(rowTitles(elements.adminBookList)[0], 'Book 21');

  elements.adminBookSearch.value = 'Book 01';
  elements.adminBookSearch.listeners.input();
  assert.equal(rowTitles(elements.adminBookList)[0], 'Book 01');
  assert.equal(elements.adminBookList.children.length, 1);
  elements.adminBookSearch.value = '';
  elements.adminBookSearch.listeners.input();
  assert.equal(rowTitles(elements.adminBookList)[0], 'Book 01');

  elements.adminBookVisibilityFilter.value = 'restricted';
  elements.adminBookVisibilityFilter.listeners.change();
  assert.equal(elements.adminBookList.children.length, 20);
  assert.equal(rowTitles(elements.adminBookList)[0], 'Book 02');
  elements.adminBookTagFilter.value = 'tag-1';
  elements.adminBookTagFilter.listeners.change();
  assert.equal(rowTitles(elements.adminBookList)[0], 'Book 04');

  elements.adminBookPageSize.value = '50';
  elements.adminBookPageSize.listeners.change();
  assert.equal(elements.adminBookList.children.length, 7);
  assert.deepEqual(calls, ['/api/admin/books/index']);
});

test('book index sorts by title, added time, and recent updates without reloading', async () => {
  const books = [
    adminBook({ id: 'beta', title: 'Beta', created_at: '2026-08-01T08:00:00Z', updated_at: '2026-08-12T08:00:00Z' }),
    adminBook({ id: 'alpha', title: 'Alpha', created_at: '2026-08-03T08:00:00Z', updated_at: '2026-08-10T08:00:00Z' }),
    adminBook({ id: 'gamma', title: 'Gamma', created_at: '2026-08-02T08:00:00Z', updated_at: '2026-08-13T08:00:00Z' }),
  ];
  const calls = [];
  const { root, elements } = bookUiHarness(url => {
    calls.push(url);
    return Promise.resolve(response(url === '/api/admin/books/index' ? 200 : 404, { books }));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();

  assert.deepEqual(rowTitles(elements.adminBookList), ['Alpha', 'Beta', 'Gamma']);
  elements.adminBookSort.value = 'title_desc';
  elements.adminBookSort.listeners.change();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Gamma', 'Beta', 'Alpha']);
  elements.adminBookSort.value = 'created_desc';
  elements.adminBookSort.listeners.change();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Alpha', 'Gamma', 'Beta']);
  elements.adminBookSort.value = 'updated_desc';
  elements.adminBookSort.listeners.change();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Gamma', 'Beta', 'Alpha']);
  assert.deepEqual(calls, ['/api/admin/books/index']);
});

test('book bulk actions retain a page selection and add member grants without replacing access', async () => {
  const books = [
    adminBook({ id: 'bulk-1', title: 'First bulk book' }),
    adminBook({ id: 'bulk-2', title: 'Second bulk book' }),
  ];
  const requests = [];
  const confirmations = [];
  const { root, elements } = bookUiHarness((url, options) => {
    if (url === '/api/admin/users') return Promise.resolve(response(200, {
      users: [{ id: 'member-1', username: 'Reader', role: 'member', enabled: true }],
    }));
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books }));
    if (url === '/api/admin/ai/settings') return Promise.resolve(response(200, { settings: null }));
    if (url === '/api/admin/ai/tags') return Promise.resolve(response(200, { tags: [] }));
    if (url === '/api/admin/books/bulk') {
      requests.push(JSON.parse(options.body));
      return Promise.resolve(response(200, {
        operation: JSON.parse(options.body).operation,
        updated_count: 2,
      }));
    }
    return Promise.resolve(response(404, {}));
  });
  root.EpubDialog = {
    confirm(options) {
      confirmations.push(options);
      return Promise.resolve(true);
    },
  };
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  elements.adminMenu.click();
  await tick();
  await tick();

  elements.adminBookSelectPage.checked = true;
  elements.adminBookSelectPage.listeners.change();
  assert.equal(elements.adminBookBulkActions.hidden, false);
  assert.match(elements.adminBookSelectionCount.textContent, /2/);

  elements.adminBookBulkRestrict.click();
  await tick();
  await tick();
  assert.deepEqual(confirmations[0], {
    title: '[admin.books.bulk.restrict]',
    message: '[admin.books.bulk.restrictConfirm]',
    confirmText: '[admin.books.bulk.restrict]',
    destructive: true,
  });
  assert.deepEqual(requests[0], {
    operation: 'restrict',
    book_ids: ['bulk-1', 'bulk-2'],
  });

  const member = descendants(elements.adminBookBulkMembers).find(node =>
    node.tagName === 'INPUT' && node.value === 'member-1'
  );
  member.checked = true;
  member.listeners.change();
  elements.adminBookBulkGrant.click();
  await tick();
  await tick();
  assert.deepEqual(confirmations[1], {
    title: '[admin.books.bulk.grant]',
    message: '[admin.books.bulk.grantConfirm]',
    confirmText: '[admin.books.bulk.grant]',
    destructive: false,
  });
  assert.deepEqual(requests[1], {
    operation: 'grant',
    book_ids: ['bulk-1', 'bulk-2'],
    user_ids: ['member-1'],
  });
});

test('book pagination keeps a compact page window and announces the current page', async () => {
  const books = Array.from({ length: 180 }, (_, index) => adminBook({
    id: `book-${index + 1}`,
    title: `Book ${String(index + 1).padStart(3, '0')}`,
  }));
  const { root, elements } = bookUiHarness(url => Promise.resolve(
    response(url === '/api/admin/books/index' ? 200 : 404, { books })
  ));
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();

  const pageButtons = descendants(elements.adminBookPagination).filter(node =>
    node.classList.contains('admin-book-page') && /^Page /.test(node.textContent)
  );
  assert.equal(pageButtons.length, 4);
  assert.equal(pageButtons.find(node => node.getAttribute('aria-current') === 'page').textContent, 'Page 1');
  assert.ok(pageButtons.every(node => node.classList.contains('bookshelf-action-btn')));
});

test('book index matches literal and tone-free pinyin text without unsafe HTML rendering', async () => {
  const books = [
    adminBook({
      id: 'chinese', title: '算法导论', authors: [], epub_tags: [],
      ai_tags: [{ id: 'tag-cs', name: 'Computer Science' }],
    }),
    adminBook({
      id: 'literal', title: 'Other book', authors: ['Ada Lovelace'],
      epub_tags: ['Mathematics'], ai_tags: [{ id: 'tag-math', name: 'Theory' }],
    }),
  ];
  const { root, elements } = bookUiHarness(url => Promise.resolve(
    response(url === '/api/admin/books/index' ? 200 : 404, { books })
  ));
  root.pinyinPro = {
    pinyin(value) { return value === '算法导论 Computer Science' ? 'suan fa dao lun computer science' : value; },
  };
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();

  elements.adminBookSearch.value = 'suanfadaolun';
  elements.adminBookSearch.listeners.input();
  assert.deepEqual(rowTitles(elements.adminBookList), ['算法导论']);
  elements.adminBookSearch.value = 'ada lovelace';
  elements.adminBookSearch.listeners.input();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Other book']);
  elements.adminBookSearch.value = 'mathematics';
  elements.adminBookSearch.listeners.input();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Other book']);
  elements.adminBookSearch.value = 'computer science';
  elements.adminBookSearch.listeners.input();
  assert.deepEqual(rowTitles(elements.adminBookList), ['算法导论']);
  assert.equal(elements.adminBookList.innerHTMLWrites, 0);
});

test('book index keeps literal search working when pinyin is unavailable or throws', async () => {
  const books = [adminBook({ title: 'Literal fallback', authors: ['Grace Hopper'] })];
  const load = () => Promise.resolve(response(200, { books }));

  const withoutPinyin = bookUiHarness(url => url === '/api/admin/books/index'
    ? load() : Promise.resolve(response(404, {})));
  const missingAuth = AuthModule.create(withoutPinyin.root);
  missingAuth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await missingAuth.init();
  await missingAuth.loadBookIndex();
  withoutPinyin.elements.adminBookSearch.value = 'grace hopper';
  withoutPinyin.elements.adminBookSearch.listeners.input();
  assert.deepEqual(rowTitles(withoutPinyin.elements.adminBookList), ['Literal fallback']);

  const throwingPinyin = bookUiHarness(url => url === '/api/admin/books/index'
    ? load() : Promise.resolve(response(404, {})));
  throwingPinyin.root.pinyinPro = {
    pinyin() { throw new Error('pinyin conversion failed'); },
  };
  const throwingAuth = AuthModule.create(throwingPinyin.root);
  throwingAuth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await throwingAuth.init();
  await throwingAuth.loadBookIndex();
  throwingPinyin.elements.adminBookSearch.value = 'literal fallback';
  throwingPinyin.elements.adminBookSearch.listeners.input();
  assert.deepEqual(rowTitles(throwingPinyin.elements.adminBookList), ['Literal fallback']);
});

test('a stale initial book index response cannot overwrite a newer refresh', async () => {
  const initialIndex = deferred();
  let indexRequests = 0;
  const { root, elements } = bookUiHarness(url => {
    if (url === '/api/admin/books/index') {
      indexRequests += 1;
      return indexRequests === 1
        ? initialIndex.promise
        : Promise.resolve(response(200, { books: [adminBook({ title: 'Fresh index' })] }));
    }
    if (url === '/api/admin/users') return Promise.resolve(response(200, { users: [] }));
    if (url === '/api/admin/ai/settings') return Promise.resolve(response(200, { settings: null }));
    if (url === '/api/admin/ai/tags') return Promise.resolve(response(200, { tags: [] }));
    if (url === '/api/admin/ai/jobs?page=1&page_size=20') {
      return Promise.resolve(response(200, aiJobsPayload([])));
    }
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  elements.adminMenu.click();

  await auth.loadBookIndex();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Fresh index']);

  initialIndex.resolve(response(200, { books: [adminBook({ title: 'Stale index' })] }));
  await tick();
  await tick();
  assert.deepEqual(rowTitles(elements.adminBookList), ['Fresh index']);
});

test('book editor lazy-loads one detail row, reuses cached detail, and ignores a closed request', async () => {
  const delayedDetail = deferred();
  const calls = [];
  const books = [
    adminBook({ id: 'book/id', title: 'First book' }),
    adminBook({ id: 'book-2', title: 'Second book' }),
  ];
  const detail = id => ({
    id, title: id === 'book/id' ? 'First book' : 'Second book', grants: [],
    ai_tags: [], ai_profile: 'auto', visibility: 'authenticated', ai_result_count: 2,
  });
  const { root, elements } = bookUiHarness(url => {
    calls.push(url);
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books }));
    if (url === '/api/admin/books/book%2Fid') return delayedDetail.promise;
    if (url === '/api/admin/books/book-2') return Promise.resolve(response(200, { book: detail('book-2') }));
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();

  const firstOpen = adminBookButtons(elements.adminBookList, 'book/id')[0].click();
  assert.equal(editorRows(elements.adminBookList).length, 1);
  assert.equal(adminBookButtons(elements.adminBookList, 'book/id')[0].getAttribute('aria-expanded'), 'true');
  await tick();
  assert.equal(calls.filter(url => url === '/api/admin/books/book%2Fid').length, 1);
  await auth.openBookEditor('book-2');
  assert.equal(editorRows(elements.adminBookList).length, 1);
  assert.equal(elements.adminBookList.children.indexOf(editorRows(elements.adminBookList)[0]), 2);
  delayedDetail.resolve(response(200, { book: detail('book/id') }));
  await firstOpen;
  await tick();
  assert.equal(editorRows(elements.adminBookList).length, 1);

  const cancel = descendants(editorRows(elements.adminBookList)[0]).find(node => node.tagName === 'BUTTON'
    && node.textContent === '[admin.books.cancel]');
  cancel.click();
  assert.equal(adminBookButtons(elements.adminBookList, 'book-2')[0].focused, true);
  await auth.openBookEditor('book-2');
  assert.equal(calls.filter(url => url === '/api/admin/books/book-2').length, 1);
  await auth.openBookEditor('book/id');
  assert.equal(editorRows(elements.adminBookList).length, 1);
  assert.equal(calls.filter(url => url === '/api/admin/books/book%2Fid').length, 2);
});

test('book editor saves one atomic payload and patches only its held summary', async () => {
  const calls = [];
  const before = adminBook({ id: 'book/id', title: 'Atomic book', ai_result_count: 4 });
  const savedSummary = adminBook({
    id: 'book/id', title: 'Atomic book', visibility: 'restricted', grant_count: 2,
    ai_profile: 'technical', ai_tags: [{ id: 'tag-1', name: 'Science' }], ai_result_count: 4,
  });
  const { root, elements } = bookUiHarness((url, options) => {
    calls.push({ url, options });
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books: [before] }));
    if (url === '/api/admin/books/book%2Fid/settings') return Promise.resolve(response(200, {
      book: { id: 'book/id', title: 'Atomic book', grants: ['member-1', 'member-2'], ai_tags: [{ id: 'tag-1', name: 'Science' }], ai_profile: 'technical', visibility: 'restricted', ai_result_count: 4 },
      summary: savedSummary,
    }));
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();
  await auth.saveBookSettings('book/id', {
    visibility: 'restricted', user_ids: ['member-1', 'member-2'], tag_ids: ['tag-1'], profile: 'technical',
  });

  const save = calls.find(call => call.url === '/api/admin/books/book%2Fid/settings');
  assert.equal(save.options.method, 'PUT');
  assert.deepEqual(JSON.parse(save.options.body), {
    visibility: 'restricted', user_ids: ['member-1', 'member-2'], tag_ids: ['tag-1'], profile: 'technical',
  });
  assert.deepEqual(rowTitles(elements.adminBookList), ['Atomic book']);
  assert.equal(calls.filter(call => call.url !== '/api/admin/books/index'
    && call.url !== '/api/admin/books/book%2Fid/settings').length, 0);
});

test('a late book settings save cannot patch an editor that has been closed', async () => {
  const delayedSave = deferred();
  const original = adminBook({ id: 'book/id', title: 'Original title', visibility: 'authenticated' });
  const { root, elements } = bookUiHarness((url, options) => {
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books: [original] }));
    if (url === '/api/admin/books/book%2Fid') return Promise.resolve(response(200, {
      book: Object.assign({}, original, { grants: [], ai_tags: [] }),
    }));
    if (url === '/api/admin/books/book%2Fid/settings') return delayedSave.promise;
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();
  await auth.openBookEditor('book/id');

  const saving = auth.saveBookSettings('book/id', {
    visibility: 'restricted', user_ids: [], tag_ids: [], profile: 'technical',
  });
  await auth.openBookEditor('book/id');
  delayedSave.resolve(response(200, {
    book: Object.assign({}, original, { visibility: 'restricted', grants: [], ai_tags: [], ai_profile: 'technical' }),
    summary: Object.assign({}, original, { visibility: 'restricted', ai_profile: 'technical' }),
  }));
  await saving;

  assert.equal(editorRows(elements.adminBookList).length, 0);
  assert.equal(rowTitles(elements.adminBookList)[0], 'Original title');
});

test('book result clearing confirms first and patches only the affected count', async () => {
  const calls = [];
  const { root, elements } = bookUiHarness((url, options) => {
    calls.push({ url, options });
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, {
      books: [adminBook({ id: 'book/id', title: 'Clear me', ai_result_count: 4 })],
    }));
    if (url === '/api/admin/ai/results') return Promise.resolve(response(200, { deleted: 4 }));
    return Promise.resolve(response(404, {}));
  });
  let confirmation = false;
  const translate = root.EpubBrowserI18n.t;
  root.EpubBrowserI18n.t = (key, params) => key === 'admin.books.clearResultsConfirm'
    ? `Clear AI results for ${params.title}?` : translate(key, params);
  root.confirm = message => {
    assert.equal(message, 'Clear AI results for Clear me?');
    return confirmation;
  };
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();
  await auth.clearBookResults('book/id', 'Clear me');
  assert.equal(calls.filter(call => call.url === '/api/admin/ai/results').length, 0);

  confirmation = true;
  await auth.clearBookResults('book/id', 'Clear me');
  const clear = calls.find(call => call.url === '/api/admin/ai/results');
  assert.deepEqual(JSON.parse(clear.options.body), { book_id: 'book/id' });
  assert.match(elements.adminBookLive.textContent, /4/);
  assert.equal(calls.filter(call => call.url === '/api/admin/books/index').length, 1);
});

test('a failed book result clear leaves the summary and editor detail unchanged', async () => {
  const detail = adminBook({ id: 'book/id', title: 'Keep results', ai_result_count: 4 });
  const { root, elements } = bookUiHarness(url => {
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books: [detail] }));
    if (url === '/api/admin/books/book%2Fid') return Promise.resolve(response(200, {
      book: Object.assign({}, detail, { grants: [], ai_tags: [] }),
    }));
    if (url === '/api/admin/ai/results') return Promise.resolve(response(500, { code: 'unknown' }));
    return Promise.resolve(response(404, {}));
  });
  root.confirm = () => true;
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();
  await auth.openBookEditor('book/id');
  await auth.clearBookResults('book/id', 'Keep results');

  assert.equal(elements.adminBookList.children[0].children[4].textContent, '4 results');
  assert.equal(editorRows(elements.adminBookList).length, 1);
  assert.equal(elements.adminBookLive.textContent, '[admin.books.clearError]');
});

test('a failed book settings save keeps the editor draft available for retry', async () => {
  const detail = adminBook({ id: 'book/id', title: 'Retry me', visibility: 'authenticated' });
  const { root, elements } = bookUiHarness((url, options) => {
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books: [detail] }));
    if (url === '/api/admin/books/book%2Fid') return Promise.resolve(response(200, {
      book: Object.assign({}, detail, { grants: [], ai_tags: [] }),
    }));
    if (url === '/api/admin/books/book%2Fid/settings') return Promise.resolve(response(500, { code: 'unknown' }));
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();
  await auth.openBookEditor('book/id');
  const editor = editorRows(elements.adminBookList)[0];
  const visibility = descendants(editor).find(node => node.tagName === 'SELECT');
  visibility.value = 'restricted';
  const save = descendants(editor).find(node => node.tagName === 'BUTTON'
    && node.textContent === '[admin.books.save]');
  save.click();
  await tick();
  await tick();

  const retryEditor = editorRows(elements.adminBookList)[0];
  const retryVisibility = descendants(retryEditor).find(node => node.tagName === 'SELECT');
  assert.equal(retryVisibility.value, 'restricted');
  assert.ok(descendants(retryEditor).some(node => node.textContent === '[admin.books.saveError]'));
  assert.ok(descendants(retryEditor).some(node => node.tagName === 'BUTTON'
    && node.textContent === '[admin.books.save]'));
});

test('book refresh requests only the lightweight index and locale changes rerender held state', async () => {
  const calls = [];
  const { root, elements, localeListeners } = bookUiHarness(url => {
    calls.push(url);
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, {
      books: [adminBook({ title: 'Locale book' })],
    }));
    return Promise.resolve(response(404, {}));
  });
  const auth = AuthModule.create(root);
  auth.setSession({ user: { id: 'admin', role: 'admin' }, csrf_token: 'token' });
  await auth.init();
  await auth.loadBookIndex();
  elements.adminBookRefresh.click();
  await tick();
  await tick();
  localeListeners.forEach(listener => listener());

  assert.deepEqual(calls, ['/api/admin/books/index', '/api/admin/books/index']);
  assert.deepEqual(rowTitles(elements.adminBookList), ['Locale book']);
});

test('book table renderer owns the stable body while the old card renderer is retired', () => {
  const source = fs.readFileSync(path.join(__dirname, '../epub_browser/assets/auth.js'), 'utf8');
  const start = source.indexOf('function renderAdminBooks() {');
  const renderer = source.slice(start, source.indexOf('\n    function renderIdentities()', start));

  assert.match(renderer, /var list = element\('adminBookList'\);/);
  assert.match(renderer, /root\.document\.createElement\('tr'\)/);
  assert.doesNotMatch(renderer, /adminBookLegacyList/);
});

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
  const root = rootWithFetch(() => Promise.resolve(response(200, {})));
  root.document.getElementById = id => ({
    adminPanel,
    adminMenu,
  })[id] || null;
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'member', username: 'reader', role: 'member' },
    csrf_token: 'token',
  });

  await auth.init();

  assert.equal(adminPanel.hidden, true);
  assert.equal(adminMenu.hidden, true);
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
    if (url === '/api/admin/books/index') return Promise.resolve(response(200, { books: [] }));
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
    '/api/admin/books/index',
    '/api/admin/ai/settings',
    '/api/admin/ai/tags',
    '/api/admin/ai/jobs?page=1&page_size=20',
  ]);
});

test('account and administration surfaces announce loading while their initial data is pending', async () => {
  const accountSessions = deferred();
  const adminRequests = [deferred(), deferred(), deferred(), deferred()];
  const accountMenu = fakeElement('button');
  const adminMenu = fakeElement('button');
  const accountPanel = fakeElement('section');
  const adminPanel = fakeElement('section');
  const accountPanelLoading = fakeElement('div');
  const adminPanelLoading = fakeElement('div');
  accountPanelLoading.hidden = true;
  adminPanelLoading.hidden = true;
  const root = rootWithFetch((url) => {
    if (url === '/api/account/sessions') return accountSessions.promise;
    if (url === '/api/admin/users') return adminRequests[0].promise;
    if (url === '/api/admin/books/index') return adminRequests[1].promise;
    if (url === '/api/admin/ai/settings') return adminRequests[2].promise;
    if (url === '/api/admin/ai/tags') return adminRequests[3].promise;
    if (url === '/api/admin/ai/jobs?page=1&page_size=20') {
      return Promise.resolve(response(200, aiJobsPayload([], 1, 0, 0)));
    }
    return Promise.resolve(response(404, {}));
  });
  root.document = {
    getElementById(id) {
      return ({
        accountMenu,
        adminMenu,
        accountPanel,
        adminPanel,
        accountPanelLoading,
        adminPanelLoading,
      })[id] || null;
    },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  const auth = AuthModule.create(root);
  auth.setSession({
    user: { id: 'admin', username: 'owner', role: 'admin' },
    csrf_token: 'token',
  });

  await auth.init();
  accountMenu.click();
  assert.equal(accountPanelLoading.hidden, false);
  assert.equal(accountPanel.getAttribute('aria-busy'), 'true');
  accountSessions.resolve(response(200, { sessions: [] }));
  await tick();
  assert.equal(accountPanelLoading.hidden, true);
  assert.equal(accountPanel.getAttribute('aria-busy'), 'false');

  adminMenu.click();
  assert.equal(adminPanelLoading.hidden, false);
  assert.equal(adminPanel.getAttribute('aria-busy'), 'true');
  adminRequests[0].resolve(response(200, { users: [] }));
  adminRequests[1].resolve(response(200, { books: [] }));
  adminRequests[2].resolve(response(200, { settings: null }));
  adminRequests[3].resolve(response(200, { tags: [] }));
  await tick();
  await tick();
  assert.equal(adminPanelLoading.hidden, true);
  assert.equal(adminPanel.getAttribute('aria-busy'), 'false');
});

test('administration section navigation keeps one workspace visible and marks its tab current', async () => {
  const overviewTab = fakeElement('button');
  const usersTab = fakeElement('button');
  const aiConfigurationTab = fakeElement('button');
  const overview = fakeElement('section');
  const users = fakeElement('section');
  const aiConfiguration = fakeElement('section');
  overviewTab.setAttribute('data-admin-section', 'overview');
  usersTab.setAttribute('data-admin-section', 'users');
  aiConfigurationTab.setAttribute('data-admin-section', 'ai-configuration');
  overviewTab.setAttribute('role', 'tab');
  usersTab.setAttribute('role', 'tab');
  aiConfigurationTab.setAttribute('role', 'tab');
  overview.setAttribute('data-admin-panel', 'overview');
  users.setAttribute('data-admin-panel', 'users');
  aiConfiguration.setAttribute('data-admin-panel', 'ai-configuration');
  overview.hidden = false;
  users.hidden = true;
  aiConfiguration.hidden = true;
  const root = rootWithFetch(() => Promise.resolve(response(200, {
    user: { id: 'admin', username: 'owner', role: 'admin' }, csrf_token: 'token',
  })));
  root.document = {
    getElementById() { return null; },
    querySelectorAll(selector) {
      if (selector === '[data-admin-section]') return [overviewTab, usersTab, aiConfigurationTab];
      if (selector === '[data-admin-panel]') return [overview, users, aiConfiguration];
      return [];
    },
    addEventListener() {},
  };
  const auth = AuthModule.create(root);

  await auth.init();
  usersTab.click();

  assert.equal(overview.hidden, true);
  assert.equal(users.hidden, false);
  assert.equal(aiConfiguration.hidden, true);
  assert.equal(usersTab.getAttribute('aria-selected'), 'true');
  assert.equal(overviewTab.getAttribute('aria-selected'), 'false');
});

test('clearing all AI results requires an explicit administrator confirmation', async () => {
  const clearAll = fakeElement('button');
  const calls = [];
  let confirmed = false;
  const root = rootWithFetch((url, options = {}) => {
    calls.push({ url, method: options.method || 'GET' });
    if (url === '/api/session') return Promise.resolve(response(200, {
      user: { id: 'admin', username: 'owner', role: 'admin' }, csrf_token: 'token',
    }));
    return Promise.resolve(response(200, { deleted: 3 }));
  });
  root.confirm = () => confirmed;
  root.document = {
    getElementById(id) { return id === 'adminAiClearAll' ? clearAll : null; },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  const auth = AuthModule.create(root);

  await auth.init();
  clearAll.click();
  await tick();
  assert.deepEqual(calls, [{ url: '/api/session', method: 'GET' }]);

  confirmed = true;
  clearAll.click();
  await tick();
  assert.ok(calls.some(call => (
    call.url === '/api/admin/ai/results' && call.method === 'DELETE'
  )));
});

test('closing administration keeps unsaved form changes until the administrator confirms', async () => {
  const adminPanel = fakeElement('section');
  const adminClose = fakeElement('button');
  const aiSettingsForm = fakeElement('form');
  let discard = false;
  const root = rootWithFetch(() => Promise.resolve(response(200, {
    user: { id: 'admin', username: 'owner', role: 'admin' }, csrf_token: 'token',
  })));
  root.confirm = () => discard;
  root.document = {
    getElementById(id) {
      return ({ adminPanel, adminClose, adminAiSettingsForm: aiSettingsForm })[id] || null;
    },
    querySelectorAll() { return []; },
    addEventListener() {},
  };
  const auth = AuthModule.create(root);

  await auth.init();
  adminPanel.classList.add('active');
  if (aiSettingsForm.listeners.input) aiSettingsForm.listeners.input();
  adminClose.click();
  assert.equal(adminPanel.classList.contains('active'), true);

  discard = true;
  adminClose.click();
  assert.equal(adminPanel.classList.contains('active'), false);
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

test('administrator AI job retry supports opaque identifiers that match inherited property names', async t => {
  const opaqueIds = [
    { id: 'constructor', retryUrl: '/api/admin/ai/jobs/constructor/retry' },
    { id: 'toString', retryUrl: '/api/admin/ai/jobs/toString/retry' },
    { id: '__proto__', retryUrl: '/api/admin/ai/jobs/__proto__/retry' },
  ];

  for (const opaqueId of opaqueIds) {
    const jobId = opaqueId.id;
    await t.test(jobId, async () => {
      const postCalls = [];
      const harness = jobUiHarness((url, options = {}) => {
        const method = options.method || 'GET';
        if (method === 'POST') {
          postCalls.push({
            url,
            csrf: options.headers && options.headers['X-CSRF-Token'],
          });
          return Promise.resolve(response(200, {
            status: 'queued',
            cached: false,
            shared: false,
            job: { id: `retry-${jobId}`, status: 'queued' },
          }));
        }
        if (url.startsWith('/api/admin/ai/jobs?')) {
          return Promise.resolve(response(200, aiJobsPayload([aiJob({ id: jobId })])));
        }
        return Promise.resolve(response(404, {}));
      });
      const auth = AuthModule.create(harness.root);
      auth.setSession({
        user: { id: 'admin', username: 'admin', role: 'admin' },
        csrf_token: 'admin-csrf',
      });
      await auth.loadAiJobs();

      let retryButton = descendants(harness.elements.adminAiJobsBody)
        .find(node => node.tagName === 'BUTTON');
      assert.equal(retryButton.disabled, false);

      const firstRetry = auth.retryAiJob(jobId);
      assert.equal(typeof firstRetry.then, 'function');
      await firstRetry;
      retryButton = descendants(harness.elements.adminAiJobsBody)
        .find(node => node.tagName === 'BUTTON');
      assert.equal(retryButton.disabled, false);

      const secondRetry = auth.retryAiJob(jobId);
      assert.notEqual(secondRetry, firstRetry);
      assert.equal(typeof secondRetry.then, 'function');
      await secondRetry;

      assert.deepEqual(postCalls, [
        { url: opaqueId.retryUrl, csrf: 'admin-csrf' },
        { url: opaqueId.retryUrl, csrf: 'admin-csrf' },
      ]);
    });
  }
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
  assert.equal(
    rendered.filter(node => node.className === 'admin-ai-job-progress-content').length,
    2,
  );
  assert.equal(progress[0].max, 10);
  assert.equal(progress[0].value, 3);
  assert.equal(progress[0].attributes['aria-label'], 'Progress 3/10');
  const scopes = rendered.filter(node => node.className === 'admin-ai-job-scope');
  assert.doesNotMatch(scopes[1].textContent, /#0/);
});

test('administrator AI job timestamps treat SQLite shapes as UTC in Asia Shanghai', async () => {
  const previousTimezone = process.env.TZ;
  process.env.TZ = 'Asia/Shanghai';
  try {
    const harness = jobUiHarness(() => Promise.resolve(response(200, aiJobsPayload([
      aiJob({
        created_at: '2026-08-23 08:00:00.125',
        updated_at: 'invalid timestamp',
      }),
    ]))));
    const auth = AuthModule.create(harness.root);
    auth.setSession({
      user: { id: 'admin', username: 'admin', role: 'admin' },
      csrf_token: 'admin-csrf',
    });

    await auth.loadAiJobs();

    const times = descendants(harness.elements.adminAiJobsBody)
      .filter(node => node.className === 'admin-ai-job-meta')
      .filter(node => node.textContent.startsWith('[admin.ai.jobs.header.created]')
        || node.textContent.startsWith('[admin.ai.jobs.header.updated]'))
      .map(node => node.textContent);
    assert.deepEqual(times, [
      '[admin.ai.jobs.header.created]: date:2026-08-23T08:00:00.125Z',
      '[admin.ai.jobs.header.updated]: [admin.ai.jobs.unknownValue]',
    ]);
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ;
    else process.env.TZ = previousTimezone;
  }
});

test('administrator AI job renderer localizes known material and template errors', async () => {
  const codes = [
    'ai_job_not_retryable',
    'book_not_found',
    'chapter_not_found',
    'source_unavailable',
    'no_reading_material',
    'ai_template_unavailable',
  ];
  const harness = jobUiHarness(() => Promise.resolve(response(200, aiJobsPayload(
    codes.map((code, index) => aiJob({ id: `known-material-${index}`, error_code: code })),
  ))));
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.loadAiJobs();

  const errors = descendants(harness.elements.adminAiJobsBody)
    .filter(node => node.className === 'admin-ai-job-error')
    .map(node => node.textContent);
  assert.deepEqual(errors, codes.map(code => (
    `[admin.ai.jobs.header.error]: [admin.ai.jobs.error.${code}]`
  )));
});

test('administrator AI job scope and language use the active Chinese runtime', async () => {
  const harness = jobUiHarness(() => Promise.resolve(response(200, aiJobsPayload([
    aiJob({ id: 'chapter-job', scope: 'chapter', language: 'en', chapter_index: 2 }),
    aiJob({ id: 'book-job', scope: 'book', language: 'zh-CN', chapter_index: null }),
    aiJob({ id: 'legacy-job', scope: 'constructor', language: 'toString', chapter_index: null }),
  ]))));
  harness.root.navigator = { languages: ['zh-CN'], language: 'zh-CN' };
  harness.root.Intl = Intl;
  harness.root.EpubBrowserI18n = createRuntime(harness.root, dictionaries);
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.loadAiJobs();

  const scopes = descendants(harness.elements.adminAiJobsBody)
    .filter(node => node.className === 'admin-ai-job-scope')
    .map(node => node.textContent);
  assert.deepEqual(scopes, [
    '章节 · #2 · 英语',
    '全书 · 简体中文',
    '未知 · 未知',
  ]);
  assert.doesNotMatch(scopes.join(' '), /\b(?:book|chapter|en|zh-CN|constructor|toString)\b/);
});

test('administrator AI jobs preserve and label the three additional languages', async () => {
  const harness = jobUiHarness(() => Promise.resolve(response(200, aiJobsPayload([
    aiJob({ id: 'traditional-job', scope: 'chapter', language: 'zh-TW', chapter_index: 1 }),
    aiJob({ id: 'korean-job', scope: 'book', language: 'ko', chapter_index: null }),
    aiJob({ id: 'japanese-job', scope: 'book', language: 'ja', chapter_index: null }),
  ]))));
  harness.root.navigator = { languages: ['ja-JP'], language: 'ja-JP' };
  harness.root.Intl = Intl;
  harness.root.EpubBrowserI18n = createRuntime(harness.root, dictionaries);
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.loadAiJobs();

  const scopes = descendants(harness.elements.adminAiJobsBody)
    .filter(node => node.className === 'admin-ai-job-scope')
    .map(node => node.textContent);
  assert.deepEqual(scopes, [
    '章 · #1 · 繁体字中国語',
    '本全体 · 韓国語',
    '本全体 · 日本語',
  ]);
});

test('administrator AI job status and stored error allowlists reject inherited property names', async () => {
  const suspicious = ['constructor', 'toString', '__proto__'];
  const harness = jobUiHarness(() => Promise.resolve(response(200, aiJobsPayload(
    suspicious.map((value, index) => aiJob({
      id: `legacy-${index}`,
      status: value,
      error_code: value,
    })),
  ))));
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  await auth.loadAiJobs();

  const rendered = descendants(harness.elements.adminAiJobsBody);
  const statuses = rendered
    .filter(node => node.className === 'admin-ai-job-status-cell')
    .map(node => node.textContent);
  const errors = rendered
    .filter(node => node.className === 'admin-ai-job-error')
    .map(node => node.textContent);
  assert.deepEqual(statuses, suspicious.map(() => '[admin.ai.jobs.unknownValue]'));
  assert.deepEqual(errors, suspicious.map(() => (
    '[admin.ai.jobs.header.error]: [admin.ai.jobs.error.unknown]'
  )));
  assert.doesNotMatch(statuses.concat(errors).join(' '), /constructor|toString|__proto__/);
});

test('administrator AI job action error allowlist rejects inherited property names', async () => {
  const suspicious = ['constructor', 'toString', '__proto__'];
  let activeCode = '';
  const harness = jobUiHarness(() => Promise.resolve(response(400, { code: activeCode })));
  const auth = AuthModule.create(harness.root);
  auth.setSession({
    user: { id: 'admin', username: 'admin', role: 'admin' },
    csrf_token: 'admin-csrf',
  });

  for (let index = 0; index < suspicious.length; index += 1) {
    activeCode = suspicious[index];
    await auth.retryAiJob(`job-${index}`);
    assert.equal(
      harness.elements.adminAiJobsLive.textContent,
      '[admin.ai.jobs.error.unknown]',
    );
    assert.doesNotMatch(harness.elements.adminAiJobsLive.textContent, new RegExp(activeCode));
  }
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

test('captured AI job poll callbacks are inert after panel close or visibility hide', async () => {
  let jobsRequests = 0;
  const harness = jobUiHarness(url => {
    const adminResponse = adminDataResponse(url);
    if (adminResponse) return Promise.resolve(adminResponse);
    if (url.startsWith('/api/admin/ai/jobs?')) {
      jobsRequests += 1;
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
  await tick();
  const afterClose = Array.from(harness.intervals.values())[0].callback;
  harness.elements.adminClose.click();
  const beforeClosedCallback = jobsRequests;
  afterClose();
  await tick();
  assert.equal(jobsRequests, beforeClosedCallback);

  harness.elements.adminMenu.click();
  await tick();
  const afterHide = Array.from(harness.intervals.values())[0].callback;
  harness.root.document.hidden = true;
  harness.documentListeners.visibilitychange();
  const beforeHiddenCallback = jobsRequests;
  afterHide();
  await tick();
  assert.equal(jobsRequests, beforeHiddenCallback);
});
