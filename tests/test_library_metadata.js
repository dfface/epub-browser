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
    addEventListener() {},
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

function createLibraryHarness(responses) {
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
      }[id] || null;
    },
    querySelector(selector) {
      return {
        '.book-grid': bookGrid,
        '.search-box': searchBox,
        '.tag-cloud': tagCloud,
        '.container': container,
        '.bookshelf-modal': bookshelfModal,
      }[selector] || findAll({ children: [bookGrid, searchBox, tagCloud, container, bookshelfModal] }, selector)[0] || null;
    },
    querySelectorAll(selector) {
      return findAll({ children: [bookGrid, searchBox, tagCloud, container, bookshelfModal] }, selector);
    },
  };
  let responseIndex = 0;
  function FakeXMLHttpRequest() {
    this.readyState = 0;
    this.status = 0;
    this.responseText = '';
  }
  FakeXMLHttpRequest.prototype.open = function() {};
  FakeXMLHttpRequest.prototype.send = function() {
    const response = responses[responseIndex++];
    this.readyState = 4;
    this.status = response.status || 200;
    this.responseText = JSON.stringify(response.books || response);
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
    window, document, navigator: window.navigator, localStorage,
    XMLHttpRequest: FakeXMLHttpRequest, JSON, Date, console: { error() {}, log() {} },
    setTimeout() {}, decodeURIComponent, prompt() { return null; },
  });
  return {
    window, searchBox, bookshelfModal,
    cardIds() { return bookGrid.querySelectorAll('.book-card').map((card) => card.getAttribute('data-id')); },
    card(id) { return bookGrid.querySelector('[data-id="' + id + '"]'); },
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
  const tag = content.children[2].children[0];

  assert.equal(link.attributes.id, book.hash);
  assert.equal(link.attributes.href, book.url);
  assert.equal(cover.attributes.src, book.cover);
  assert.equal(title.textContent, book.title);
  assert.equal(author.textContent, book.authors.join(' & '));
  assert.equal(tag.textContent, book.tags[0]);
  assert.equal(content.children.length, 3);
  assert.match(requestedUrl, /^\/reader\/book-metadata\.json\?/);
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

test('incremental metadata refresh leaves existing cards after a failed request', async () => {
  const harness = createLibraryHarness([
    [{ hash: 'one', title: 'One', authors: [], tags: [], url: '/book/one/', cover: null }],
    { status: 500 },
  ]);
  harness.window.initScriptLibrary();

  await assert.rejects(harness.window.refreshLibraryMetadata());

  assert.deepEqual(harness.cardIds(), ['one']);
});
