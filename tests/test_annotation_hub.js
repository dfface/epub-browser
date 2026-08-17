const test = require('node:test');
const assert = require('node:assert/strict');
const Hub = require('../epub_browser/assets/annotation-hub.js');

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
  const groups = Hub.groupByChapter([
    { id: 'late', chapter_index: 1, created_at: '2026-08-12T00:00:00Z' },
    { id: 'early', chapter_index: 1, created_at: '2026-08-11T00:00:00Z' },
    { id: 'start', chapter_index: 0, created_at: '2026-08-10T00:00:00Z' },
  ], [{ index: 0, title: 'Opening' }]);

  assert.deepEqual(groups.map(group => group.title), ['Opening', 'Chapter 2']);
  assert.deepEqual(groups[1].annotations.map(annotation => annotation.id), ['early', 'late']);
});

test('builds a chapter deep link with an encoded annotation id', () => {
  assert.equal(Hub.annotationHref({ book_hash: 'book', chapter_index: 3, id: 'note / 1' }), '/book/book/chapter_3.html?annotation=note%20%2F%201');
});
