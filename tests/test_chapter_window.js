const test = require('node:test');
const assert = require('node:assert/strict');
const ChapterWindow = require('../epub_browser/assets/chapter-window.js');

test('continuous reading keeps only the configured number of chapters in its reading window', () => {
  const window = new ChapterWindow(0, 3);

  assert.deepEqual(window.add(1, 'next').evicted, []);
  assert.deepEqual(window.add(2, 'next').evicted, []);
  assert.deepEqual(window.add(3, 'next').evicted, [0]);
  assert.deepEqual(window.indices(), [1, 2, 3]);
});

test('moving backwards evicts the opposite edge of the reading window', () => {
  const window = new ChapterWindow(3, 3);

  window.add(4, 'next');
  window.add(5, 'next');

  assert.deepEqual(window.add(2, 'previous').evicted, [5]);
  assert.deepEqual(window.indices(), [2, 3, 4]);
});
