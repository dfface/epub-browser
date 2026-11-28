const test = require('node:test');
const assert = require('node:assert/strict');
const { needsMoreContinuousContent } = require('../epub_browser/assets/continuous-buffer.js');

test('loads another chapter when a short chapter leaves less than one viewport below the reader', () => {
  assert.equal(needsMoreContinuousContent(1100, 0, 700), true);
});

test('loads another chapter until two viewports of content are buffered', () => {
  assert.equal(needsMoreContinuousContent(1400, 0, 700), true);
});

test('does not load another chapter when two viewports of content are already buffered', () => {
  assert.equal(needsMoreContinuousContent(2100, 0, 700), false);
});

const fs = require('node:fs');
const vm = require('node:vm');
const chapterScript = fs.readFileSync(require.resolve('../epub_browser/assets/chapter.js'), 'utf8');
const previousLoader = chapterScript.match(/    function loadPrevChapter\(\) \{[\s\S]*?(?=\n    function )/)[0];

test('continuous scroll can stop loading previous chapters and resume on user choice', () => {
  const requests = [];
  const context = {
    loadPreviousOnScroll: false, chapter_index: '3', loadedChapters: {3: true},
    activeContinuousChapterRequest: 0, isLoadingChapter: false,
    document: {getElementById: () => null},
    createContinuousLoader: () => ({}), setTimeout() {},
    content: {insertBefore() {}},
    getChapterUrl: index => 'chapter_' + index + '.html',
    XMLHttpRequest: function() {
      this.open = (method, url) => requests.push(url);
      this.send = () => {};
    }
  };
  vm.createContext(context);
  vm.runInContext(previousLoader + '\nloadPrevChapter();', context);
  assert.deepEqual(requests, []);
  context.loadPreviousOnScroll = true;
  vm.runInContext('loadPrevChapter();', context);
  assert.deepEqual(requests, ['chapter_2.html']);
});

test('direction segments preserve the choice while continuous scroll is hidden', () => {
  const choices = [{value: 'both'}, {value: 'down'}];
  const saved = [];
  const row = {
    querySelectorAll: () => choices,
    addEventListener: (type, listener) => { row.change = listener; }
  };
  const context = {
    document: {getElementById: () => row}, isContinuousScroll: true,
    isPaginationMode: false, loadPreviousOnScroll: true,
    localStorage: {setItem: (key, value) => saved.push([key, value])}
  };
  vm.createContext(context);
  const start = chapterScript.indexOf('    var continuousDirectionRow =');
  const end = chapterScript.indexOf('    if (continuousScrollToggle) {', start);
  vm.runInContext(chapterScript.slice(start, end), context);
  assert.equal(row.hidden, false);
  assert.equal(choices[0].checked, true);
  row.change({target: {name: 'continuousScrollDirection', value: 'down'}});
  assert.equal(choices[1].checked, true);
  assert.deepEqual(saved, [['continuousScrollLoadPrevious', 'false']]);
  context.isContinuousScroll = false;
  vm.runInContext('syncContinuousDirection()', context);
  assert.equal(row.hidden, true);
  context.isContinuousScroll = true;
  vm.runInContext('syncContinuousDirection()', context);
  assert.equal(row.hidden, false);
  assert.equal(choices[1].checked, true);
  context.isPaginationMode = true;
  vm.runInContext('syncContinuousDirection()', context);
  assert.equal(row.hidden, true);
});

test('scrolling into a chapter updates both toolbar layouts and the book boundaries', () => {
  const links = Object.fromEntries(
    ['readerPreviousChapter', 'readerNextChapter', 'mobilePrevChapter', 'mobileNextChapter']
      .map(id => [id, {
        href: 'old',
        setAttribute(name, value) { this[name] = value; },
        removeAttribute(name) { delete this[name]; }
      }])
  );
  const section = {
    getBoundingClientRect: () => ({top: 30, bottom: 700}),
    getAttribute: key => key === 'data-chapter-index' ? '3' : 'Chapter 4'
  };
  const context = vm.createContext({
    content: {
      querySelectorAll: () => [section], querySelector: () => section,
      getAttribute: () => '4'
    },
    document: {getElementById: id => links[id]},
    window: {innerHeight: 600, EpubReadingProgress: require('../epub_browser/assets/reading-progress.js')},
    visibleChapterIndex: 0,
    getChapterUrl: index => 'chapter_' + index + '.html',
    announceReadingSessionChapter() {},
    localStorage: {setItem() {}}, book_hash: 'book',
    updateContinuousScrollUrl() {}, selectReadingChapter() {}, setBookTocActiveChapter() {}
  });
  const source = chapterScript.slice(chapterScript.indexOf('    function updateContinuousReadingChapter('),
    chapterScript.indexOf('    function getChapterUrl('));
  vm.runInContext(source + '\nupdateContinuousReadingChapter();', context);
  assert.equal(links.readerPreviousChapter.href, 'chapter_2.html');
  assert.equal(links.mobilePrevChapter.href, 'chapter_2.html');
  assert.equal(links.readerNextChapter.href, undefined);
  assert.equal(links.mobileNextChapter['aria-disabled'], 'true');
  section.getAttribute = () => '0';
  vm.runInContext('updateContinuousReadingChapter();', context);
  assert.equal(links.readerPreviousChapter.href, undefined);
  assert.equal(links.mobileNextChapter.href, 'chapter_1.html');
});

test('chapter navigation waits before showing feedback and ignores superseded responses', () => {
  const requests = [];
  const timers = new Map();
  const applied = [];
  const status = { hidden: true };
  const retry = { hidden: true, focus() {} };
  const context = vm.createContext({
    document: {getElementById: id => ({
      chapterNavigationStatus: status, chapterNavigationLoading: {}, chapterNavigationError: {},
      chapterNavigationRetry: retry
    })[id]},
    chapterTargetFromUrl: index => ({index}),
    closeReaderDrawers() {},
    isContinuousScroll: false, chapter_index: '0', chapterPrefetch: null,
    activeReaderChapterRequest: 0, readerChapterXhr: null, readerChapterLoadingTimer: null, readerChapterBusyLink: null,
    setTimeout(task) { const id = Symbol(); timers.set(id, task); return id; },
    clearTimeout(id) { timers.delete(id); },
    XMLHttpRequest: function() {
      requests.push(this);
      this.open = this.send = this.abort = () => {};
    },
    applyReaderChapterResponse(body) { applied.push(body); return true; }
  });
  const source = chapterScript.slice(chapterScript.indexOf('    function navigateReaderChapter('),
    chapterScript.indexOf('    function applyReaderChapterResponse('));
  vm.runInContext(source + '\nnavigateReaderChapter(1);', context);
  assert.equal(status.hidden, true);
  for (const task of timers.values()) task();
  assert.equal(status.hidden, false);
  vm.runInContext('navigateReaderChapter(2);', context);
  requests[0].status = 200;
  requests[0].onload();
  assert.deepEqual(applied, []);
  for (const task of timers.values()) task();
  requests[1].ontimeout();
  assert.equal(retry.hidden, false);
  retry.onclick();
  requests[2].status = 200;
  requests[2].responseText = 'chapter 2';
  requests[2].onload();
  assert.deepEqual(applied, ['chapter 2']);
  assert.equal(status.hidden, true);
});
