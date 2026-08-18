const test = require('node:test');
const assert = require('node:assert/strict');
const Metadata = require('../epub_browser/assets/bookshelf.js');

test('bookshelf metadata follows the generated base path and published cover URL', () => {
  assert.equal(Metadata.metadataUrl('/project/'), '/project/book-metadata.json');
  assert.equal(Metadata.metadataUrl('/'), '/book-metadata.json');
  assert.equal(
    Metadata.coverUrl({ cover: '/project/book/stable/resources/cover.jpg' }),
    '/project/book/stable/resources/cover.jpg',
  );
});
