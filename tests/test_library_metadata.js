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
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return this.attributes[name] || null; },
    addEventListener() {},
    querySelector(selector) {
      if (selector.charAt(0) !== '.') return null;
      return findByClass(this, selector.slice(1));
    },
    querySelectorAll() { return []; },
  };
  Object.defineProperty(node, 'innerHTML', {
    set() { throw new Error('Book metadata must not be rendered with innerHTML'); },
  });
  return node;
}

function findByClass(node, className) {
  for (const child of node.children) {
    if (child.className.split(/\s+/).includes(className)) return child;
    const nested = findByClass(child, className);
    if (nested) return nested;
  }
  return null;
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
  FakeXMLHttpRequest.prototype.open = function() {};
  FakeXMLHttpRequest.prototype.send = function() {
    this.readyState = 4;
    this.status = 200;
    this.responseText = JSON.stringify([book]);
    this.onreadystatechange();
  };
  const localStorage = { getItem() { return null; }, setItem() {} };
  const window = {
    navigator: { userAgent: 'Kindle' },
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
});
