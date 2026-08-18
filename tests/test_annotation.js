const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadAnnotationWindow(response, mode = 'server', documentOverride) {
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

  const localStorage = { getItem: () => '', setItem: () => {} };
  const window = {
    __EPUB_BROWSER_TESTING__: true,
    EpubBrowserMode: mode,
    navigator: { userAgent: '' },
    localStorage,
    document: documentOverride || { cookie: '' },
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
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/annotation.js', 'utf8'), context);
  return window;
}

function loadBackendStorage(response, mode = 'server') {
  return loadAnnotationWindow(response, mode).AnnotationBackendStorage;
}

test('SSG annotations do not probe the server API', async () => {
  const response = { status: 200, body: JSON.stringify({ status: 'ok' }) };
  const storage = loadBackendStorage(response, 'ssg');

  const result = await storage.checkHealth();

  assert.equal(result.available, false);
  assert.equal(response.sendCount || 0, 0);
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
