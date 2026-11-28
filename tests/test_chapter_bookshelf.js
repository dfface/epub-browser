const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

test('chapter shelf support calls the bookshelf initializer exported by its asset', () => {
  let initialized = 0;
  const timeouts = [];
  const window = {
    epubBrowserCache: {},
    initBookShelf() { initialized += 1; },
    addEventListener() {},
    location: { pathname: '/book/book-id/chapter_0.html', hash: '', search: '' },
  };
  const document = {
    body: { classList: { add() {} }, addEventListener() {}, focus() {} },
    documentElement: { classList: { add() {}, remove() {} } },
    head: { appendChild() {} },
    createElement() { return { style: {}, setAttribute() {} }; },
    getElementById() { return null; },
    querySelector() { return null; },
    querySelectorAll() { return []; },
  };
  const context = {
    window,
    document,
    navigator: { userAgent: '' },
    localStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    setTimeout(callback) { timeouts.push(callback); return timeouts.length; },
    clearTimeout() {},
    Promise,
    URLSearchParams,
    history: {},
  };
  vm.runInNewContext(fs.readFileSync('epub_browser/assets/chapter.js', 'utf8'), context);

  assert.equal(typeof context.initializeChapterBookshelf, 'function');
  assert.equal(context.initializeChapterBookshelf(), true);

  assert.equal(initialized, 1);
  assert.deepEqual(timeouts, []);
});

test('anonymous chapter never waits for the account-only annotation module', () => {
  const source=fs.readFileSync('epub_browser/assets/chapter.js','utf8');
  const initializer=source.match(/function initAnnotationModule\(\) \{[\s\S]*?\n    \}/)[0];
  let timers=0;
  vm.runInNewContext(initializer+';initAnnotationModule();', {
    window:{EpubBrowserAnonymous:true}, setTimeout(){timers++;}
  });
  assert.equal(timers,0);
});
