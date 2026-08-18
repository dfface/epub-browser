const test = require('node:test');
const assert = require('node:assert/strict');
const Hub = require('../epub_browser/assets/annotation-hub.js');

function withI18n(runtime, callback) {
  const original = global.EpubBrowserI18n;
  global.EpubBrowserI18n = runtime;
  try {
    callback();
  } finally {
    global.EpubBrowserI18n = original;
  }
}

const englishI18n = {
  t: (key, params = {}) => ({
    'annotations.chapterNumber': `Chapter ${params.number}`,
    'annotations.annotationCount': `${params.count} annotation${params.count === 1 ? '' : 's'}`,
  }[key] || key),
  formatDate: () => '2026-08-18 01:02:03',
  onLocaleChange: () => () => {},
};

test('aggregates only annotated books and sorts them by their latest annotation', () => {
  const books = Hub.aggregateBooks([
    { book_hash: 'a', created_at: '2026-08-10T00:00:00Z' },
    { book_hash: 'b', created_at: '2026-08-12T00:00:00Z' },
    { book_hash: 'a', updated_at: '2026-08-13T00:00:00Z' },
  ], [{ hash: 'a', title: 'Alpha', authors: ['Ada'] }, { hash: 'b', title: 'Beta', authors: ['Ben'] }]);

  assert.deepEqual(books.map(book => [book.hash, book.count]), [['a', 2], ['b', 1]]);
  assert.equal(books[0].title, 'Alpha');
});

test('groups one book in reading order and supplies a chapter fallback title', () => {
  withI18n(englishI18n, () => {
    const groups = Hub.groupByChapter([
      { id: 'late', chapter_index: 1, created_at: '2026-08-12T00:00:00Z' },
      { id: 'early', chapter_index: 1, created_at: '2026-08-11T00:00:00Z' },
      { id: 'start', chapter_index: 0, created_at: '2026-08-10T00:00:00Z' },
    ], [{ index: 0, title: 'Opening' }]);

    assert.deepEqual(groups.map(group => group.title), ['Opening', 'Chapter 2']);
    assert.deepEqual(groups[1].annotations.map(annotation => annotation.id), ['early', 'late']);
  });
});

test('uses the chapter_index field published by toc.json for chapter titles', () => {
  const groups = Hub.groupByChapter([
    { id: 'annotation', chapter_index: 3, created_at: '2026-08-11T00:00:00Z' },
  ], [{ chapter_index: 3, title: 'Part one · Chapter one' }]);

  assert.equal(groups[0].title, 'Part one · Chapter one');
});

test('uses shared i18n for chapter fallback, counts, and timestamps', () => {
  withI18n({
    t: (key, params) => key === 'annotations.chapterNumber' ? `章节 ${params.number}` : `${params.count} 条标注`,
    formatDate: () => '2026/08/18 09:02:03',
    onLocaleChange: () => () => {},
  }, () => {
    assert.equal(Hub.groupByChapter([{ chapter_index: 1 }], [])[0].title, '章节 2');
    assert.equal(Hub.formatTimestamp('2026-08-18T01:02:03Z'), '2026/08/18 09:02:03');
  });
});

test('builds a chapter deep link with an encoded annotation id', () => {
  assert.equal(Hub.annotationHref({ book_hash: 'book', chapter_index: 3, id: 'note / 1' }), '/book/book/chapter_3.html?annotation=note%20%2F%201');
});
