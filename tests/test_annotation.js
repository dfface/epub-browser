const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadBackendStorage(response) {
  function FakeXMLHttpRequest() {
    this.status = response.status;
    this.responseText = response.body;
  }
  FakeXMLHttpRequest.prototype.open = function() {};
  FakeXMLHttpRequest.prototype.setRequestHeader = function() {};
  FakeXMLHttpRequest.prototype.send = function() { this.onload(); };

  const localStorage = { getItem: () => '', setItem: () => {} };
  const window = {
    __EPUB_BROWSER_TESTING__: true,
    navigator: { userAgent: '' },
    localStorage,
    document: { cookie: '' },
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
  return window.AnnotationBackendStorage;
}

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
