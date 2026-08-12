const test = require('node:test');
const assert = require('node:assert/strict');
const { anchorScrollDelta } = require('../epub_browser/assets/viewport-anchor.js');

test('restores a visible anchor after an above-viewport chapter is removed', () => {
  assert.equal(anchorScrollDelta(140, -860), -1000);
});

test('restores a visible anchor after a previous chapter is inserted', () => {
  assert.equal(anchorScrollDelta(-24, 1476), 1500);
});
