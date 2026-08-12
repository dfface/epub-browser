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
