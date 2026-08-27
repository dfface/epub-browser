const test = require('node:test');
const assert = require('node:assert/strict');

const APIDocs = require('../epub_browser/assets/api-docs.js');

test('API docs search normalizes surrounding whitespace and case', () => {
  assert.equal(APIDocs.normalizeQuery('  Reviews:READ  '), 'reviews:read');
  assert.equal(
    APIDocs.matchesEndpoint(
      'get /api/v1/me/reviews reviews:read list the token owner reviews',
      ' REVIEWS:READ '
    ),
    true
  );
});
test('API docs search matches method, path, scope, and description text', () => {
  const searchable = 'delete /api/v1/me/progress/{book_id} progress:write delete reading progress';
  for (const query of ['delete', 'book_id', 'progress:write', 'reading progress']) {
    assert.equal(APIDocs.matchesEndpoint(searchable, query), true, query);
  }
  assert.equal(APIDocs.matchesEndpoint(searchable, 'annotations'), false);
  assert.equal(APIDocs.matchesEndpoint(searchable, ''), true);
});
