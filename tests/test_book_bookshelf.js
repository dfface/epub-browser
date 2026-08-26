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

test('Server reader defers its shelf button until the Server store has loaded', async () => {
  const listeners = {};
  const saved = [];
  const localWrites = [];
  const button = {
    dataset: {},
    classList: { add() {}, remove() {} },
    setAttribute() {},
    removeAttribute() {},
    querySelector() { return null; },
    addEventListener(type, listener) {
      if (!listeners[type]) listeners[type] = [];
      listeners[type].push(listener);
    },
    click() {
      (listeners.click || []).slice().forEach((listener) => listener({ preventDefault() {} }));
    },
  };
  const passiveButton = {
    classList: { add() {}, remove() {} },
    addEventListener() {},
  };
  const remoteShelf = { items: ['book-id'], groups: {}, order: ['book-id'] };
  const window = {
    EpubBrowserMode: 'server',
    epubBrowserCache: { kindle_mode: 'false' },
    EpubBrowserI18n: { t(key) { return key; } },
    EpubBrowserNotification: { show() {} },
    EpubBrowserBookFeatures: {
      load() {
        window.EpubBookshelfStore = {
          isServerMode() { return true; },
          data() { return remoteShelf; },
          load() { return Promise.resolve({ data: remoteShelf, version: 1 }); },
          save(data) {
            saved.push(data);
            return Promise.resolve({ data, version: 2 });
          },
        };
        return Promise.resolve();
      },
    },
    addEventListener() {},
    location: { pathname: '/book/book-id/index.html' },
  };
  const document = {
    cookie: '',
    body: { addEventListener() {}, style: {} },
    head: { appendChild() {} },
    documentElement: { classList: { add() {}, remove() {} } },
    createElement() { return { style: {} }; },
    getElementById(id) {
      if (id === 'toggleShelfBtn') return button;
      if (id === 'toggleShelfBtnText') return { textContent: '' };
      if (id === 'scrollToTopBtn') return passiveButton;
      return null;
    },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const context = {
    window,
    document,
    navigator: { userAgent: '' },
    localStorage: {
      getItem(key) {
        if (key === 'bookshelf') return JSON.stringify(remoteShelf);
        return null;
      },
      setItem(key) { localWrites.push(key); },
      length: 0,
      key() { return null; },
      removeItem() {},
    },
    setTimeout,
    clearTimeout,
    Promise,
  };
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/book.js', 'utf8'), context);

  context.initScript();
  button.click();
  await new Promise((resolve) => setImmediate(resolve));

  assert.deepEqual(JSON.parse(JSON.stringify(saved)), [{ items: [], groups: {}, order: [] }]);
  assert.deepEqual(localWrites, []);
});

test('Server progress labels never invent a shared account identity', () => {
  const client = loadBookClient();
  client.context.window.EpubReadingProgress = { getUsername() { return ''; } };

  assert.equal(client.context.getProgressIdentity(), '');
});

test('book sorting leaves book metadata content available for text selection', async () => {
  const listeners = {};
  let sortableOptions;
  const container = {
    dataset: {},
    addEventListener(type, listener) { listeners[type] = listener; },
  };
  const passiveButton = {
    classList: { add() {}, remove() {} },
    addEventListener() {},
  };
  const window = {
    EpubBrowserMode: 'static',
    epubBrowserCache: { kindle_mode: 'false' },
    EpubBrowserI18n: { t(key) { return key; } },
    EpubBrowserNotification: { show() {} },
    EpubBrowserBookFeatures: { load() { return Promise.resolve(); } },
    Sortable: {
      create(element, options) {
        sortableOptions = options;
      },
    },
    addEventListener() {},
    location: { pathname: '/book/book-id/index.html' },
    scrollTo() {},
  };
  const document = {
    cookie: '',
    body: { style: {} },
    documentElement: { classList: { add() {}, remove() {} }, dataset: {} },
    getElementById(id) {
      if (id === 'scrollToTopBtn') return passiveButton;
      return null;
    },
    querySelector(selector) {
      if (selector === '.container') return container;
      return null;
    },
    querySelectorAll() { return []; },
  };
  const context = {
    window,
    Sortable: window.Sortable,
    document,
    navigator: { userAgent: '' },
    localStorage: { getItem() { return null; }, setItem() {}, length: 0, key() { return null; }, removeItem() {} },
    setTimeout,
    clearTimeout,
    Promise,
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/book.js', 'utf8'), context);
  context.initScript();
  listeners.pointerdown();
  await new Promise((resolve) => setImmediate(resolve));

  assert.match(sortableOptions.filter, /\.book-info-content/);
  assert.equal(sortableOptions.preventOnFilter, false);
});

test('book card order restores the review card and upgrades legacy drag state', () => {
  const cards = [
    { dataset: { id: 'book-info-card' } },
    { dataset: { id: 'book-review-display' } },
    { dataset: {} },
    { dataset: { id: 'toc-container' } },
  ];
  const container = {
    children: cards,
    appendChild(card) {
      const index = cards.indexOf(card);
      if (index >= 0) cards.splice(index, 1);
      cards.push(card);
    },
  };
  let persisted = '';
  const localStorage = {
    getItem() { return JSON.stringify(['toc-container', null, 'book-info-card']); },
    setItem(key, value) { persisted = value; },
    removeItem() {},
  };
  const context = {
    window: {},
    document: { querySelector(selector) { return selector === '.container' ? container : null; } },
    navigator: { userAgent: '' },
    localStorage,
  };
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/book.js', 'utf8'), context);

  context.restoreOrder('book-container-sortable-order', 'container');

  assert.deepEqual(cards.filter((card) => card.dataset.id).map((card) => card.dataset.id), [
    'toc-container',
    'book-info-card',
    'book-review-display',
  ]);
  assert.equal(persisted, JSON.stringify(['toc-container', 'book-info-card', 'book-review-display']));
});
