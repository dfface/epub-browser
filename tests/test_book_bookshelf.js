const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadBookClient() {
  const listeners = {};
  const notifications = [];
  const saved = [];
  let shelf = { items: ['book-id'], groups: {}, order: ['book-id'] };
  const button = {
    dataset: {},
    classList: { add() {}, remove() {} },
    setAttribute() {},
    addEventListener(type, listener) { listeners[type] = listener; },
  };
  const text = { textContent: '' };
  const window = {
    EpubBrowserMode: 'server',
    epubBrowserCache: { kindle_mode: 'false' },
    EpubBrowserI18n: { t(key) { return key; } },
    EpubBrowserNotification: {
      show(message, level) { notifications.push({ message, level }); },
    },
    EpubBookshelfStore: {
      isServerMode() { return true; },
      data() { return shelf; },
      load() {
        return Promise.resolve({ data: shelf, version: 1 });
      },
      save(data) {
        saved.push(data);
        shelf = data;
        return Promise.resolve({ data, version: 2 });
      },
    },
  };
  const context = {
    window,
    navigator: { userAgent: '' },
    localStorage: { getItem() { return null; }, setItem() {} },
    document: {
      cookie: '',
      getElementById(id) {
        if (id === 'toggleShelfBtn') return button;
        if (id === 'toggleShelfBtnText') return text;
        return null;
      },
    },
    setTimeout,
    clearTimeout,
    Promise,
  };
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/book.js', 'utf8'), context);
  return { context, listeners, notifications, saved };
}

test('logged-in Server reader changes its shelf without a legacy username marker', async () => {
  const client = loadBookClient();

  client.context.initBookShelfButton('book-id');
  await client.listeners.click();

  assert.equal(client.saved.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(client.saved[0])), {
    items: [],
    groups: {},
    order: [],
  });
  assert.deepEqual(client.notifications, [
    { message: 'book.removedFromShelf', level: 'success' },
  ]);
});
