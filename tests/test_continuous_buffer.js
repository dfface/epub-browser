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
    activeContinuousChapterRequest: 0,
    document: {createElement: () => ({querySelector: () => ({})})},
    i18n: {t: key => key}, content: {appendChild() {}},
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
