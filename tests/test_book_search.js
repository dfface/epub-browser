const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadAsset(overrides = {}) {
  const document = {
    readyState: 'complete',
    addEventListener() {},
    getElementById() { return null; },
    createElement() { return { style: {}, setAttribute() {}, appendChild() {} }; },
    createTreeWalker() { throw new Error('not used'); },
    createRange() { throw new Error('not used'); },
    ...overrides.document,
  };
  const window = {
    document,
    NodeFilter: { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 },
    pageYOffset: 0,
    scrollTo() {},
    addEventListener() {},
    dispatchEvent() { return false; },
    location: { assign() {}, hash: '' },
    fetch() { return Promise.reject(new Error('unexpected fetch')); },
    CustomEvent: function (type, init) { this.type = type; this.detail = init.detail; },
    setTimeout,
    requestAnimationFrame(callback) { return setTimeout(callback, 0); },
    ...overrides.window,
  };
  const context = { window, document, console, setTimeout, clearTimeout, Promise, Number, String, Array };
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/book-search.js', 'utf8'), context);
  return window.EpubBookSearch;
}

test('parseHash accepts valid search fragments and rejects malformed ones', () => {
  const api = loadAsset();

  const hit = api.parseHash('#eb-search=12,15,' + encodeURIComponent('甲乙a'));

  assert.equal(hit.start, 12);
  assert.equal(hit.end, 15);
  assert.equal(hit.match, '甲乙a');
  assert.equal(api.parseHash('#eb-search=12,12,abc'), null);
  assert.equal(api.parseHash('#eb-search=12,15'), null);
  assert.equal(api.parseHash('#eb-search=a,b,c'), null);
  assert.equal(api.parseHash('#other=1'), null);
  assert.equal(api.hitHash(hit), '#eb-search=12,15,' + encodeURIComponent('甲乙a'));
});

test('rangeForHit maps UTF-16 offsets across text nodes and validates the match', () => {
  const nodes = [
    { nodeValue: 'Hello ', parentElement: { closest() { return null; } } },
    { nodeValue: 'world', parentElement: { closest() { return null; } } },
    { nodeValue: ' 😀甲乙', parentElement: { closest() { return null; } } },
  ];
  let cursor = -1;
  const document = {
    readyState: 'complete',
    addEventListener() {},
    getElementById() { return null; },
    createTreeWalker() {
      cursor = -1;
      return {
        get currentNode() { return nodes[cursor]; },
        nextNode() {
          cursor += 1;
          return cursor < nodes.length;
        },
      };
    },
    createRange() {
      const range = {
        start: null,
        end: null,
        setStart(node, offset) { this.start = { node, offset }; },
        setEnd(node, offset) { this.end = { node, offset }; },
        toString() {
          const startIndex = nodes.indexOf(this.start.node);
          const endIndex = nodes.indexOf(this.end.node);
          if (startIndex === endIndex) {
            return this.start.node.nodeValue.slice(this.start.offset, this.end.offset);
          }
          let text = this.start.node.nodeValue.slice(this.start.offset);
          for (let index = startIndex + 1; index < endIndex; index += 1) {
            text += nodes[index].nodeValue;
          }
          return text + this.end.node.nodeValue.slice(0, this.end.offset);
        },
        getBoundingClientRect() { return { top: 100, left: 40 }; },
      };
      return range;
    },
  };
  const window = { document };
  const api = loadAsset({ document, window });

  const range = api.rangeForHit({}, { start: 6, end: 11, match: 'world' });
  assert.equal(range.toString(), 'world');

  const emoji = api.rangeForHit({}, { start: 14, end: 16, match: '甲乙' });
  assert.equal(emoji.toString(), '甲乙');

  assert.equal(api.rangeForHit({}, { start: 6, end: 11, match: 'WORLD' }), null);
  assert.equal(api.rangeForHit({}, { start: 100, end: 105, match: 'nope' }), null);
});

test('locate scrolls to the validated range and is a no-op for stale offsets', () => {
  let scrolled = null;
  const document = {
    readyState: 'complete',
    addEventListener() {},
    getElementById() { return null; },
    createTreeWalker() {
      let done = false;
      return {
        currentNode: { nodeValue: 'abc', parentElement: { closest() { return null; } } },
        nextNode() {
          if (done) return false;
          done = true;
          return true;
        },
      };
    },
    createRange() {
      return {
        setStart() {},
        setEnd() {},
        toString() { return 'abc'; },
        getBoundingClientRect() { return { top: 200, left: 0 }; },
      };
    },
  };
  const window = {
    document,
    pageYOffset: 25,
    scrollTo(x, y) { scrolled = [x, y]; },
  };
  const api = loadAsset({ document, window });

  assert.equal(api.locate({}, { start: 0, end: 3, match: 'abc' }), true);
  assert.deepEqual(scrolled, [0, 145]);
  assert.equal(api.locate({}, { start: 0, end: 3, match: 'xyz' }), false);
});

function fakeText(value) {
  return { nodeType: 3, nodeValue: value, parentElement: { closest() { return null; } } };
}

function fakeElement(name, children) {
  for (let index = 0; index < children.length; index += 1) {
    children[index].nextSibling = children[index + 1] || null;
  }
  return { nodeType: 1, localName: name, nodeName: name.toUpperCase(), firstChild: children[0] || null };
}

test('rangeForText collapses rendered whitespace and recovers stale offsets by context', () => {
  const before = fakeText('Hello\n   ');
  const match = fakeText('world');
  const paragraph = fakeElement('p', [before, match]);
  const section = fakeElement('div', [paragraph]);
  const document = {
    readyState: 'complete',
    addEventListener() {},
    getElementById() { return null; },
    createTreeWalker() { return { nextNode() { return false; } }; },
    createRange() {
      return {
        start: null,
        end: null,
        setStart(node, offset) { this.start = { node, offset }; },
        setEnd(node, offset) { this.end = { node, offset }; },
      };
    },
  };
  const api = loadAsset({ document, window: { document } });

  assert.equal(api.normalizedText(section).text, 'Hello world');
  const range = api.rangeForText(section, {
    start: 900,
    end: 905,
    match: 'world',
    before: 'Hello ',
    after: '',
  });
  assert.deepEqual(range.start, { node: match, offset: 0 });
  assert.deepEqual(range.end, { node: match, offset: 5 });
  assert.equal(api.rangeForText(section, { start: 0, end: 5, match: 'nope' }), null);
});
