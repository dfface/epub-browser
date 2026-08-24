const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadAnnotationWindow(response, mode = 'server', documentOverride, options = {}) {
  function FakeXMLHttpRequest() {
    this.status = response.status;
    this.responseText = response.body;
  }
  FakeXMLHttpRequest.prototype.open = function() {};
  FakeXMLHttpRequest.prototype.setRequestHeader = function() {};
  FakeXMLHttpRequest.prototype.send = function() {
    response.sendCount = (response.sendCount || 0) + 1;
    this.onload();
  };

  const localStorage = {
    getItem(key) {
      if (key === 'annotation_storage_type') return options.annotationStorageType || '';
      return '';
    },
    setItem() {},
  };
  const indexedDbState = { opens: 0 };
  const indexedDB = {
    open() {
      indexedDbState.opens += 1;
      const request = { result: {} };
      Promise.resolve().then(() => request.onsuccess && request.onsuccess({ target: request }));
      return request;
    },
  };
  const authenticatedRequests = [];
  const window = {
    __EPUB_BROWSER_TESTING__: true,
    EpubBrowserMode: mode,
    navigator: { userAgent: '' },
    localStorage,
    document: documentOverride || { cookie: '' },
    EpubBrowserAuth: {
      fetch(url, options = {}) {
        const headers = Object.assign({}, options.headers, { 'X-CSRF-Token': 'csrf' });
        const authenticated = Object.assign({}, options, {
          credentials: 'same-origin',
          headers,
        });
        authenticatedRequests.push({ url, options: authenticated });
        return Promise.resolve({
          ok: response.status >= 200 && response.status < 300,
          status: response.status,
          text: () => Promise.resolve(response.body),
        });
      },
    },
    EpubBrowserI18n: {
      t(key) {
        return {
          'annotations.error.annotation_not_found': '未找到标注。',
          'annotations.error.server_error': '标注服务发生错误。',
        }[key] || key;
      },
    },
  };
  const context = {
    window,
    document: window.document,
    navigator: window.navigator,
    localStorage,
    XMLHttpRequest: FakeXMLHttpRequest,
    Promise,
    Date,
    JSON,
    console,
    indexedDB,
    Highlighter: options.Highlighter,
    requestAnimationFrame: callback => callback(),
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/annotation.js', 'utf8'), context);
  window.authenticatedRequests = authenticatedRequests;
  window.indexedDbState = indexedDbState;
  return window;
}

function loadBackendStorage(response, mode = 'server') {
  return loadAnnotationWindow(response, mode).AnnotationBackendStorage;
}

test('SSG annotations do not probe the server API', async () => {
  const response = { status: 200, body: JSON.stringify({ status: 'ok' }) };
  const window = loadAnnotationWindow(response, 'ssg');
  const storage = window.AnnotationBackendStorage;

  const result = await storage.checkHealth();

  assert.equal(result.available, false);
  assert.equal(response.sendCount || 0, 0);
  assert.equal(window.authenticatedRequests.length, 0);
});

test('server annotations use shared Cookie and CSRF authentication without a username', async () => {
  const response = { status: 201, body: JSON.stringify({ data: { id: 'a1' } }) };
  const window = loadAnnotationWindow(response);

  const result = await window.AnnotationBackendStorage.create({ id: 'a1' });

  assert.deepEqual(JSON.parse(JSON.stringify(result)), { id: 'a1' });
  assert.equal(window.authenticatedRequests.length, 1);
  const received = window.authenticatedRequests[0];
  assert.equal(received.url, '/api/annotations');
  assert.equal(received.options.credentials, 'same-origin');
  assert.equal(received.options.headers['X-CSRF-Token'], 'csrf');
  assert.equal(received.options.headers['X-Username'], undefined);
});

test('annotation storage follows deployment mode instead of a saved browser choice', async () => {
  const response = { status: 200, body: JSON.stringify({ data: [] }) };
  const serverWindow = loadAnnotationWindow(response, 'server', undefined, {
    annotationStorageType: 'idb',
  });
  const staticWindow = loadAnnotationWindow(response, 'ssg', undefined, {
    annotationStorageType: 'backend',
  });

  await serverWindow.AnnotationStorage.init();
  await staticWindow.AnnotationStorage.init();

  assert.equal(serverWindow.AnnotationStorage.getStorageType(), 'backend');
  assert.equal(serverWindow.indexedDbState.opens, 0);
  assert.equal(staticWindow.AnnotationStorage.getStorageType(), 'idb');
  assert.equal(staticWindow.indexedDbState.opens, 1);
});

test('annotation settings do not render a storage selector', async () => {
  const createdElements = [];
  const document = {
    cookie: '',
    documentElement: { querySelectorAll() { return []; } },
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
    createElement(tagName) {
      const element = {
        tagName,
        className: '',
        id: '',
        innerHTML: '',
        setAttribute() {},
      };
      createdElements.push(element);
      return element;
    },
  };
  function Highlighter() {
    return { on() {}, run() {}, stop() {}, removeAll() {} };
  }
  Highlighter.event = { CREATE: 'create', CLICK: 'click' };
  const window = loadAnnotationWindow(
    { status: 200, body: JSON.stringify({ data: [] }) },
    'server',
    document,
    { annotationStorageType: 'backend', Highlighter },
  );

  await window.AnnotationModule.init({ bookHash: 'book', chapterIndex: 0 });

  const panel = createdElements.find(element => element.id === 'annotation-tab');
  assert.ok(panel);
  assert.equal(panel.innerHTML.includes('name="annotationStorage"'), false);
  assert.equal(panel.innerHTML.includes('id="annotationEnabled"'), true);
});

test('maps a non-2xx annotation API payload code to localized, non-server error text', async () => {
  const storage = loadBackendStorage({
    status: 404,
    body: JSON.stringify({ code: 'annotation_not_found', message: 'Raw server detail must not be shown' }),
  });

  await assert.rejects(
    storage._request('GET', '/annotations/item/missing'),
    error => error.code === 'annotation_not_found'
      && error.message === '未找到标注。'
      && !error.message.includes('Raw server detail'),
  );
});

test('converts migrated XPath positions into current annotation metadata', () => {
  const textNode = { nodeValue: 'Saved text' };
  const parent = {
    tagName: 'P',
    classList: { contains() { return false; } },
  };
  const root = {
    contains(node) { return node === parent; },
    getElementsByTagName(name) { return name === 'P' ? [parent] : []; },
  };
  parent.parentElement = root;
  textNode.parentElement = parent;
  const expressions = [];
  const document = {
    cookie: '',
    evaluate(expression) {
      expressions.push(expression);
      return { singleNodeValue: textNode };
    },
    createTreeWalker() {
      let returned = false;
      return {
        nextNode() {
          if (returned) return null;
          returned = true;
          return textNode;
        },
      };
    },
  };
  const window = loadAnnotationWindow(
    { status: 200, body: '{}' },
    'server',
    document,
  );

  const meta = window.AnnotationLegacyPosition.resolve(
    { legacyXPath: '/p[1]/text()[1]', legacyOffset: 4 },
    root,
  );

  assert.deepEqual(
    JSON.parse(JSON.stringify(meta)),
    { parentTagName: 'P', parentIndex: 0, textOffset: 4 },
  );
  assert.deepEqual(expressions, ['./p[1]/text()[1]']);
});

test('annotation detail lifecycle closes only after a successful save', async () => {
  const window = loadAnnotationWindow({ status: 200, body: '{}' });
  const lifecycle = window.AnnotationDetailLifecycle.create();
  const token = lifecycle.begin();
  let closed = false;
  let reenabled = false;

  await lifecycle.runSave(
    token,
    () => Promise.resolve(),
    () => { closed = true; },
    () => { reenabled = true; },
  );

  assert.equal(closed, true);
  assert.equal(reenabled, false);
});

test('annotation detail lifecycle leaves a failed save open and re-enables it', async () => {
  const window = loadAnnotationWindow({ status: 200, body: '{}' });
  const lifecycle = window.AnnotationDetailLifecycle.create();
  const token = lifecycle.begin();
  let closed = false;
  let reenabled = false;

  await assert.rejects(lifecycle.runSave(
    token,
    () => Promise.reject(new Error('save failed')),
    () => { closed = true; },
    () => { reenabled = true; },
  ), /save failed/);

  assert.equal(closed, false);
  assert.equal(reenabled, true);
});

test('closing an annotation detail invalidates its late save completion', async () => {
  const window = loadAnnotationWindow({ status: 200, body: '{}' });
  const lifecycle = window.AnnotationDetailLifecycle.create();
  const oldToken = lifecycle.begin();
  let resolveSave;
  const pendingSave = new Promise(resolve => { resolveSave = resolve; });
  let oldDialogClosed = false;
  const save = lifecycle.runSave(
    oldToken,
    () => pendingSave,
    () => { oldDialogClosed = true; },
    () => {},
  );

  lifecycle.invalidate();
  const newToken = lifecycle.begin();
  resolveSave();
  await save;

  assert.equal(lifecycle.isCurrent(newToken), true);
  assert.equal(oldDialogClosed, false);
});
