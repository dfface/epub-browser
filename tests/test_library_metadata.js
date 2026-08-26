const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function element(tagName) {
  const node = {
    tagName,
    attributes: {},
    children: [],
    className: '',
    style: {},
    parentNode: null,
    appendChild(child) {
      if (child.parentNode) child.parentNode.removeChild(child);
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      const index = this.children.indexOf(child);
      if (index !== -1) {
        this.children.splice(index, 1);
        child.parentNode = null;
      }
      return child;
    },
    remove() {
      if (this.parentNode) this.parentNode.removeChild(this);
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] || null; },
    listeners: {},
    addEventListener(type, listener) {
      this.listeners[type] = this.listeners[type] || [];
      this.listeners[type].push(listener);
    },
    dispatch(type) {
      (this.listeners[type] || []).forEach((listener) => listener({ target: this }));
    },
    querySelector(selector) {
      return findAll(this, selector)[0] || null;
    },
    querySelectorAll(selector) { return findAll(this, selector); },
  };
  node.classList = {
    add(name) {
      if (!node.className.split(/\s+/).includes(name)) {
        node.className = (node.className + ' ' + name).trim();
      }
    },
    remove(name) {
      node.className = node.className.split(/\s+/).filter((item) => item && item !== name).join(' ');
    },
    contains(name) { return node.className.split(/\s+/).includes(name); },
  };
  Object.defineProperty(node, 'innerHTML', {
    set() { throw new Error('Book metadata must not be rendered with innerHTML'); },
  });
  return node;
}

function matches(node, selector) {
  if (selector.charAt(0) === '.') {
    return selector.slice(1).split('.').every((name) => node.className.split(/\s+/).includes(name));
  }
  const dataId = selector.match(/^\[data-id="(.*)"\]$/);
  return dataId ? node.getAttribute('data-id') === dataId[1] : false;
}

function findAll(node, selector) {
  const matchesFound = [];
  for (const child of node.children) {
    if (matches(child, selector)) matchesFound.push(child);
    matchesFound.push(...findAll(child, selector));
  }
  return matchesFound;
}

function assertValidSelector(selector) {
  if (selector.indexOf('[data-id="') === 0 && !/^\[data-id="[^"]*"\]$/.test(selector)) {
    throw new SyntaxError('Invalid selector');
  }
}

function createLibraryHarness(responses, mode = 'server') {
  const bookGrid = element('div');
  bookGrid.className = 'book-grid';
  const loading = element('div');
  loading.className = 'book-grid-loading';
  loading.setAttribute('id', 'bookGridLoading');
  bookGrid.appendChild(loading);
  const searchBox = element('input');
  searchBox.className = 'search-box';
  const tagCloud = element('div');
  tagCloud.className = 'tag-cloud';
  const allTag = element('div');
  allTag.className = 'tag-cloud-item active';
  allTag.setAttribute('data-id', 'All');
  const noTag = element('div');
  noTag.className = 'tag-cloud-item';
  noTag.setAttribute('data-id', 'NoTag');
  tagCloud.appendChild(allTag);
  tagCloud.appendChild(noTag);
  const tagCloudToggle = element('button');
  tagCloudToggle.className = 'tag-cloud-toggle';
  tagCloudToggle.hidden = true;
  const container = element('div');
  const scrollToTop = element('button');
  const bookshelfModal = element('div');
  bookshelfModal.className = 'bookshelf-modal active';
  const bookCount = element('span');
  const tagCount = element('span');
  const document = {
    body: element('body'),
    cookie: '',
    documentElement: {
      attributes: {},
      classList: { add() {}, remove() {} },
      getAttribute(name) { return this.attributes[name] || null; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
    },
    createElement: element,
    getElementById(id) {
      return {
        bookGridLoading: loading,
        scrollToTopBtn: scrollToTop,
        libraryBookCount: bookCount,
        libraryTagCount: tagCount,
        tagCloudToggle,
      }[id] || null;
    },
    querySelector(selector) {
      assertValidSelector(selector);
      return {
        '.book-grid': bookGrid,
        '.search-box': searchBox,
        '.tag-cloud': tagCloud,
        '.tag-cloud-toggle': tagCloudToggle,
        '.container': container,
        '.bookshelf-modal': bookshelfModal,
      }[selector] || findAll({ children: [bookGrid, searchBox, tagCloud, container, bookshelfModal] }, selector)[0] || null;
    },
    querySelectorAll(selector) {
      assertValidSelector(selector);
      return findAll({ children: [bookGrid, searchBox, tagCloud, tagCloudToggle, container, bookshelfModal] }, selector);
    },
  };
  let responseIndex = 0;
  const pendingResponses = [];
  function FakeXMLHttpRequest() {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
  }
  FakeXMLHttpRequest.prototype.open = function() {};
  FakeXMLHttpRequest.prototype.send = function() {
    const response = responses[responseIndex++];
    if (response && response.deferred) {
      pendingResponses.push({ xhr: this, response });
      return;
    }
    completeResponse(this, response);
  };
  function completeResponse(xhr, response) {
    xhr.readyState = 4;
    xhr.status = response.status || 200;
    xhr.responseText = JSON.stringify(response.books || response);
    xhr.onreadystatechange();
  }
  const storageValues = {};
  const localStorage = {
    getItem(key) { return storageValues[key] || null; },
    setItem(key, value) { storageValues[key] = String(value); },
  };
  const windowListeners = {};
  const animationFrames = [];
  const window = {
    navigator: { userAgent: 'Kindle' },
    EpubBrowserBasePath: '/reader/',
    EpubBrowserMode: mode,
    document,
    localStorage,
    addEventListener(type, listener) {
      windowListeners[type] = windowListeners[type] || [];
      windowListeners[type].push(listener);
    },
    requestAnimationFrame(callback) {
      animationFrames.push(callback);
      return animationFrames.length;
    },
    scrollTo() {},
  };
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/library.js', 'utf8'), {
    window, document, navigator: window.navigator, localStorage,
    XMLHttpRequest: FakeXMLHttpRequest, JSON, Date, console: { error() {}, log() {} },
    setTimeout() {}, decodeURIComponent, prompt() { return null; },
  });
  return {
    window, searchBox, bookshelfModal,
    cardIds() { return bookGrid.querySelectorAll('.book-card').map((card) => card.getAttribute('data-id')); },
    card(id) { return bookGrid.children.find((card) => card.getAttribute('data-id') === id) || null; },
    tag(id) { return tagCloud.children.find((tagItem) => tagItem.getAttribute('data-id') === id) || null; },
    tagIds() { return tagCloud.children.map((tagItem) => tagItem.getAttribute('data-id')); },
    state(variant) { return bookGrid.querySelector('.library-state--' + variant); },
    setSavedOrder(key, order) { localStorage.setItem(key, order); },
    pendingResponseCount() { return pendingResponses.length; },
    tagCloudToggle,
    resize() { (windowListeners.resize || []).forEach((listener) => listener()); },
    flushAnimationFrame() {
      const callback = animationFrames.shift();
      if (callback) callback();
    },
    resolveNextResponse() {
      const pending = pendingResponses.shift();
      completeResponse(pending.xhr, pending.response);
    },
  };
}

test('renders adversarial book metadata as text and attributes, never HTML', () => {
  const book = {
    hash: 'book\"><img src=x onerror=alert(1)>',
    url: '/reader/book/safe/index.html',
    cover: '/reader/book/safe/cover.jpg\"><script>alert(1)</script>',
    title: '<img src=x onerror=alert(1)>',
    authors: ['Ada <script>alert(1)</script>', 'Bob'],
    tags: ['<svg onload=alert(1)>'],
    rating: 4,
    review_text: '<script>must never render</script>',
  };
  const bookGrid = element('div');
  bookGrid.className = 'book-grid';
  const searchBox = element('input');
  const tagCloud = element('div');
  const container = element('div');
  const scrollToTop = element('button');
  const document = {
    body: element('body'),
    cookie: '',
    documentElement: {
      attributes: {},
      classList: { add() {}, remove() {} },
      getAttribute(name) { return this.attributes[name] || null; },
      setAttribute(name, value) { this.attributes[name] = String(value); },
    },
    createElement: element,
    getElementById(id) { return id === 'scrollToTopBtn' ? scrollToTop : null; },
    querySelector(selector) {
      return {
        '.book-grid': bookGrid,
        '.search-box': searchBox,
        '.tag-cloud': tagCloud,
        '.container': container,
      }[selector] || null;
    },
    querySelectorAll() { return []; },
  };
  function FakeXMLHttpRequest() {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
  }
  let requestedUrl = null;
  FakeXMLHttpRequest.prototype.open = function(method, url) { requestedUrl = url; };
  FakeXMLHttpRequest.prototype.send = function() {
    this.readyState = 4;
    this.status = 200;
    this.responseText = JSON.stringify([book]);
    this.onreadystatechange();
  };
  const localStorage = { getItem() { return null; }, setItem() {} };
  const window = {
    navigator: { userAgent: 'Kindle' },
    EpubBrowserBasePath: '/reader/',
    document,
    localStorage,
    addEventListener() {},
    scrollTo() {},
  };

  vm.runInNewContext(fs.readFileSync('epub_browser/assets/library.js', 'utf8'), {
    window,
    document,
    navigator: window.navigator,
    localStorage,
    XMLHttpRequest: FakeXMLHttpRequest,
    JSON,
    Date,
    console,
    setTimeout() {},
    decodeURIComponent,
    prompt() { return null; },
  });
  window.initScriptLibrary();

  const card = bookGrid.children[0];
  const link = card.children[0];
  const cover = link.children[0];
  const content = link.children[1];
  const title = content.children[0];
  const author = content.children[1];
  const rating = content.children[2];
  const tag = content.children[3].children[0];

  assert.equal(link.attributes.id, book.hash);
  assert.equal(link.attributes.href, book.url);
  assert.equal(cover.attributes.src, book.cover);
  assert.equal(cover.attributes.loading, 'lazy');
  assert.equal(cover.attributes.decoding, 'async');
  assert.equal(title.textContent, book.title);
  assert.equal(author.textContent, book.authors.join(' & '));
  assert.equal(rating.className, 'book-private-rating');
  assert.equal(rating.children[0].textContent, '★★★★');
  assert.equal(rating.getAttribute('aria-label'), 'bookReviews.ratingValue');
  assert.equal(tag.textContent, book.tags[0]);
  assert.equal(content.children.length, 4);
  assert.match(requestedUrl, /^\/reader\/book-metadata\.json\?/);
});

test('renders a large Library catalog in animation-frame batches', () => {
  const books = Array.from({ length: 25 }, (_, index) => ({
    hash: 'book-' + index,
    title: 'Book ' + index,
    authors: [],
    tags: [],
    url: '/book/' + index + '/',
    cover: null,
  }));
  const harness = createLibraryHarness([books]);

  harness.window.initScriptLibrary();

  assert.equal(harness.cardIds().length, 24);
  harness.flushAnimationFrame();
  assert.equal(harness.cardIds().length, 25);
});

test('cancels stale card batches when a metadata refresh starts during rendering', async () => {
  const books = Array.from({ length: 25 }, (_, index) => ({
    hash: 'book-' + index,
    title: 'Book ' + index,
    authors: [],
    tags: [],
    url: '/book/' + index + '/',
    cover: null,
  }));
  const harness = createLibraryHarness([books, books]);

  harness.window.initScriptLibrary();
  await harness.window.refreshLibraryMetadata();

  assert.equal(harness.cardIds().length, 24);
  harness.flushAnimationFrame();
  assert.equal(harness.cardIds().length, 24);
  harness.flushAnimationFrame();
  assert.deepEqual(harness.cardIds(), books.map((book) => book.hash));
});

test('renders one card when metadata contains the same book more than once', () => {
  const book = { hash: 'one', title: 'One', authors: [], tags: [], url: '/book/one/', cover: null };
  const harness = createLibraryHarness([[book, { ...book, hash: 'legacy-one' }]]);

  harness.window.initScriptLibrary();

  assert.deepEqual(harness.cardIds(), ['one']);
});

test('incremental metadata refresh replaces cards and preserves filters', async () => {
  const harness = createLibraryHarness([
    [{ hash: 'one', title: 'One', authors: [], tags: ['A'], url: '/book/one/', cover: null }],
    [
      { hash: 'one', title: 'One', authors: [], tags: ['A'], url: '/book/one/', cover: null },
      { hash: 'two', title: 'Two', authors: [], tags: ['B'], url: '/book/two/', cover: null },
    ],
  ]);
  harness.window.initScriptLibrary();
  harness.searchBox.value = 'two';

  await harness.window.refreshLibraryMetadata();

  assert.deepEqual(harness.cardIds(), ['one', 'two']);
  assert.equal(harness.searchBox.value, 'two');
  assert.equal(harness.card('one').style.display, 'none');
  assert.equal(harness.card('two').style.display, 'block');
  assert.equal(harness.bookshelfModal.classList.contains('active'), true);
});

test('empty Server library renders a structured watched-folder state', () => {
  const harness = createLibraryHarness([[]], 'server');

  harness.window.initScriptLibrary();

  const state = harness.state('empty');
  assert.ok(state);
  assert.equal(state.tagName, 'section');
  assert.equal(state.attributes.role, 'status');
  assert.equal(state.children[1].attributes['data-i18n'], 'library.emptyTitle');
  assert.equal(
    state.children[2].attributes['data-i18n'],
    'library.emptyServerDescription',
  );
});

test('a filter with no matches renders a distinct search empty state', () => {
  const harness = createLibraryHarness([[
    { hash: 'one', title: 'One', authors: [], tags: [], url: '/book/one/', cover: null },
  ]]);
  harness.window.initScriptLibrary();
  harness.searchBox.value = 'missing';

  harness.window.initBookCardsEvents();

  const state = harness.state('filtered');
  assert.ok(state);
  assert.equal(state.children[1].attributes['data-i18n'], 'library.noResultsTitle');
  assert.equal(state.children[2].attributes['data-i18n'], 'library.noResultsDescription');
});

test('coalesces out-of-order revision requests so the final grid uses the newest metadata', async () => {
  const harness = createLibraryHarness([
    { deferred: true, books: [{ hash: 'old', title: 'Old', authors: [], tags: [], url: '/book/old/', cover: null }] },
    { deferred: true, books: [{ hash: 'newest', title: 'Newest', authors: [], tags: [], url: '/book/newest/', cover: null }] },
  ]);
  harness.window.initScriptLibrary();

  const newest = harness.window.refreshLibraryMetadata(3);
  const older = harness.window.refreshLibraryMetadata(2);
  assert.equal(harness.pendingResponseCount(), 1);

  harness.resolveNextResponse();
  await Promise.resolve();
  assert.equal(harness.pendingResponseCount(), 1);
  harness.resolveNextResponse();
  await Promise.all([newest, older]);

  assert.deepEqual(harness.cardIds(), ['newest']);
});

test('incremental metadata refresh leaves existing cards after a failed request', async () => {
  const harness = createLibraryHarness([
    [{ hash: 'one', title: 'One', authors: [], tags: [], url: '/book/one/', cover: null }],
    { status: 500 },
  ]);
  harness.window.initScriptLibrary();

  await assert.rejects(harness.window.refreshLibraryMetadata());

  assert.deepEqual(harness.cardIds(), ['one']);
});

test('incremental metadata refresh preserves quoted saved card and tag order with an active tag', async () => {
  const quotedHash = 'book"quoted';
  const quotedTag = 'tag "quoted"';
  const books = [
    { hash: quotedHash, title: 'Quoted', authors: [], tags: [quotedTag], url: '/book/quoted/', cover: null },
    { hash: 'other', title: 'Other', authors: [], tags: ['Other'], url: '/book/other/', cover: null },
  ];
  const harness = createLibraryHarness([books, books]);
  harness.window.initScriptLibrary();
  harness.setSavedOrder('book-grid-sortable-order', JSON.stringify(['other', quotedHash]));
  harness.setSavedOrder('tag-cloud-sortable-order', JSON.stringify(['Other', quotedTag, 'All', 'NoTag']));
  harness.tag('All').classList.remove('active');
  harness.tag(quotedTag).classList.add('active');

  await harness.window.refreshLibraryMetadata();

  assert.deepEqual(harness.cardIds(), ['other', quotedHash]);
  assert.deepEqual(harness.tagIds(), ['Other', quotedTag, 'All', 'NoTag']);
  assert.equal(harness.tag(quotedTag).classList.contains('active'), true);
  assert.equal(harness.card(quotedHash).style.display, 'block');
  assert.equal(harness.card('other').style.display, 'none');
});

test('incremental metadata refresh rejects a valid JSON non-array without replacing cards', async () => {
  const harness = createLibraryHarness([
    [{ hash: 'one', title: 'One', authors: [], tags: [], url: '/book/one/', cover: null }],
    { hash: 'two', title: 'Two', authors: [], tags: [], url: '/book/two/', cover: null },
  ]);
  harness.window.initScriptLibrary();

  await assert.rejects(harness.window.refreshLibraryMetadata());

  assert.deepEqual(harness.cardIds(), ['one']);
});

test('incremental metadata refresh ignores malformed saved order JSON', async () => {
  const books = [{ hash: 'one', title: 'One', authors: [], tags: ['A'], url: '/book/one/', cover: null }];
  const harness = createLibraryHarness([books, books]);
  harness.window.initScriptLibrary();
  harness.setSavedOrder('book-grid-sortable-order', '{not JSON');
  harness.setSavedOrder('tag-cloud-sortable-order', '{not JSON');

  await harness.window.refreshLibraryMetadata();

  assert.deepEqual(harness.cardIds(), ['one']);
});

test('collapses a tag cloud that grows beyond two rows and restores it on demand', () => {
  const harness = createLibraryHarness([[
    { hash: 'one', title: 'One', authors: [], tags: ['A', 'B', 'C', 'D'], url: '/book/one/', cover: null },
  ]]);
  harness.window.initScriptLibrary();
  harness.tag('All').offsetTop = 0;
  harness.tag('NoTag').offsetTop = 0;
  harness.tag('A').offsetTop = 0;
  harness.tag('B').offsetTop = 40;
  harness.tag('C').offsetTop = 40;
  harness.tag('D').offsetTop = 80;

  harness.resize();

  assert.equal(harness.tagCloudToggle.hidden, false);
  assert.equal(harness.tagCloudToggle.attributes['aria-expanded'], 'false');
  assert.equal(harness.tagCloudToggle.attributes['data-i18n'], 'library.showMoreTags');
  assert.equal(harness.tag('All').parentNode.classList.contains('tag-cloud--collapsed'), true);

  harness.tagCloudToggle.dispatch('click');

  assert.equal(harness.tagCloudToggle.attributes['aria-expanded'], 'true');
  assert.equal(harness.tagCloudToggle.attributes['data-i18n'], 'library.showFewerTags');
  assert.equal(harness.tag('All').parentNode.classList.contains('tag-cloud--expanded'), true);
});
