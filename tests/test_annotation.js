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
    setTimeout: callback => callback(),
  };

  let source = fs.readFileSync('epub_browser/assets/annotation.js', 'utf8');
  if (options.exposeHighlightInteraction) {
    source = source.replace(
      /\}\)\(window\);\s*$/,
      'window.__testHighlightInteraction = HighlightInteraction;\n' +
      'window.__testAnnotationSettings = Settings;\n' +
      'window.__testAnnotationConfig = CONFIG;\n' +
      '})(window);',
    );
  }
  vm.runInNewContext(source, context);
  window.authenticatedRequests = authenticatedRequests;
  window.indexedDbState = indexedDbState;
  return window;
}

function createAnnotationDialogDocument() {
  let document;
  function createElement(tagName) {
    const element = {
      tagName,
      children: [],
      className: '',
      attributes: {},
      listeners: {},
      style: {},
      appendChild(child) { this.children.push(child); return child; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
      getAttribute(name) { return this.attributes[name]; },
      addEventListener(type, listener) { this.listeners[type] = listener; },
      click() {
        const event = {
          target: this,
          propagationStopped: false,
          stopPropagation() { this.propagationStopped = true; },
        };
        this.listeners.click.call(this, event);
        if (!event.propagationStopped && document.listeners.click) {
          document.listeners.click(event);
        }
      },
      querySelectorAll(selector) {
        const className = selector.startsWith('.') ? selector.slice(1) : '';
        const matches = [];
        function visit(parent) {
          parent.children.forEach(child => {
            if (child.className.split(/\s+/).includes(className)) matches.push(child);
            visit(child);
          });
        }
        visit(this);
        return matches;
      },
      focus() {},
      remove() {},
      contains(target) {
        if (this === target) return true;
        return this.children.some(child => child.contains(target));
      },
    };
    element.classList = {
      toggle(className, force) {
        const classes = new Set(element.className.split(/\s+/).filter(Boolean));
        const enabled = force === undefined ? !classes.has(className) : force;
        if (enabled) classes.add(className); else classes.delete(className);
        element.className = Array.from(classes).join(' ');
      },
      add(className) { this.toggle(className, true); },
      remove(className) { this.toggle(className, false); },
    };
    let innerHTML = '';
    Object.defineProperty(element, 'innerHTML', {
      get() { return innerHTML; },
      set(value) {
        innerHTML = value;
        if (value === '') element.children = [];
      },
    });
    return element;
  }

  document = {
    cookie: '',
    listeners: {},
    body: createElement('body'),
    createElement,
    querySelectorAll() { return []; },
    addEventListener(type, listener) { this.listeners[type] = listener; },
    removeEventListener(type, listener) {
      if (this.listeners[type] === listener) delete this.listeners[type];
    },
  };
  return document;
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

test('clicking a draft highlight reopens its selection actions instead of reading annotation detail', () => {
  const Highlighter = { event: { CREATE: 'create', CLICK: 'click' } };
  const window = loadAnnotationWindow(
    { status: 200, body: JSON.stringify({ data: [] }) }, 'server', undefined,
    { Highlighter, exposeHighlightInteraction: true },
  );
  const interaction = window.__testHighlightInteraction;
  const listeners = {};
  const source = { id: 'draft-highlight', text: 'Selected text' };
  let reopenedSource = null;
  let detailId = null;

  interaction.pendingDraft = { id: source.id, source };
  interaction.showCreateDialogFromSource = value => { reopenedSource = value; };
  interaction.showDetailDialog = value => { detailId = value; };
  interaction.bindHighlighterEvents({
    on(event, handler) { listeners[event] = handler; },
  });

  listeners.click({ id: source.id });

  assert.equal(reopenedSource, source);
  assert.equal(detailId, null);
});

test('note dialog keeps colors compact and lets readers expand every configured color', () => {
  const document = createAnnotationDialogDocument();
  const window = loadAnnotationWindow(
    { status: 200, body: JSON.stringify({ data: [] }) },
    'server',
    document,
    { exposeHighlightInteraction: true },
  );
  window.innerWidth = 1024;
  window.innerHeight = 768;
  window.__testAnnotationSettings.customColors = ['#123456', '#ABCDEF'];

  const expectedColors = Array.from(window.__testAnnotationConfig.getColors());
  window.__testHighlightInteraction.showNoteDialog({ text: 'Selected text' });

  const dialog = document.body.children[0];
  const body = dialog.children[1];
  const colorPicker = body.children[1];
  const colorOptions = colorPicker.children[1];
  assert.equal(colorOptions.querySelectorAll('.color-option').length, 7);
  assert.equal(
    colorOptions.querySelectorAll('.color-option').filter(option => option.getAttribute('aria-pressed') === 'true').length,
    1,
  );

  let toggle = colorOptions.querySelectorAll('.color-options-toggle')[0];
  assert.ok(toggle);
  assert.equal(toggle.getAttribute('aria-expanded'), 'false');
  assert.equal(toggle.textContent, '+3');
  toggle.click();

  assert.equal(window.__testHighlightInteraction.activeDialog, dialog);
  assert.equal(colorOptions.querySelectorAll('.color-option').length, expectedColors.length);
  toggle = colorOptions.querySelectorAll('.color-options-toggle')[0];
  assert.equal(toggle.getAttribute('aria-expanded'), 'true');
  assert.equal(toggle.textContent, '−');
  assert.deepEqual(
    colorOptions.querySelectorAll('.color-option').map(option => option.style.backgroundColor),
    expectedColors,
  );

  const customChoice = colorOptions.querySelectorAll('.color-option').at(-1);
  customChoice.click();
  assert.equal(customChoice.getAttribute('aria-pressed'), 'true');
  toggle = colorOptions.querySelectorAll('.color-options-toggle')[0];
  toggle.click();
  assert.equal(window.__testHighlightInteraction.activeDialog, dialog);
  assert.equal(colorOptions.querySelectorAll('.color-option').length, 7);
  assert.equal(
    colorOptions.querySelectorAll('.color-option').some(option => option.style.backgroundColor === '#ABCDEF'),
    true,
  );
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

test('invalidated annotation detail load rejection is silent after a newer dialog begins', async () => {
  const window = loadAnnotationWindow({ status: 200, body: '{}' });
  const lifecycle = window.AnnotationDetailLifecycle.create();
  const oldToken = lifecycle.begin();
  let rejectLoad;
  const pendingLoad = new Promise((resolve, reject) => { rejectLoad = reject; });
  let failureFeedback = 0;
  const load = lifecycle.run(
    oldToken,
    () => pendingLoad,
    () => {},
    () => { failureFeedback += 1; },
  );

  lifecycle.invalidate();
  const newToken = lifecycle.begin();
  rejectLoad(new Error('late load failure'));
  await assert.rejects(load, /late load failure/);

  assert.equal(lifecycle.isCurrent(newToken), true);
  assert.equal(failureFeedback, 0);
});

test('invalidated annotation detail save rejection stays silent and requests silent persistence', async () => {
  const window = loadAnnotationWindow({ status: 200, body: '{}' });
  const lifecycle = window.AnnotationDetailLifecycle.create();
  const oldToken = lifecycle.begin();
  let rejectSave;
  const pendingSave = new Promise((resolve, reject) => { rejectSave = reject; });
  let persistenceOptions;
  let failureFeedback = 0;
  const save = lifecycle.runSave(
    oldToken,
    options => {
      persistenceOptions = options;
      return pendingSave;
    },
    () => {},
    () => { failureFeedback += 1; },
  );

  lifecycle.invalidate();
  const newToken = lifecycle.begin();
  rejectSave(new Error('late save failure'));
  await assert.rejects(save, /late save failure/);

  assert.equal(lifecycle.isCurrent(newToken), true);
  assert.deepEqual(JSON.parse(JSON.stringify(persistenceOptions)), { notifyFailure: false });
  assert.equal(failureFeedback, 0);
});
