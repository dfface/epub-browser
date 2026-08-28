const test = require('node:test');
const assert = require('node:assert/strict');
const Metadata = require('../epub_browser/assets/bookshelf.js');
const Pinyin = require('../epub_browser/assets/vendor/pinyin-pro/pinyin-pro.min.js');

test('bookshelf metadata follows the generated base path and published cover URL', () => {
  assert.equal(Metadata.metadataUrl('/project/'), '/project/book-metadata.json');
  assert.equal(Metadata.metadataUrl('/'), '/book-metadata.json');
  assert.equal(
    Metadata.coverUrl({ cover: '/project/book/stable/resources/cover.jpg' }),
    '/project/book/stable/resources/cover.jpg',
  );
});

test('add-book search matches Chinese titles and authors by pinyin', () => {
  const book = {
    title: '三国演义',
    authors: ['罗贯中'],
    tags: ['古典名著'],
  };

  assert.equal(typeof Metadata.bookMatchesSearch, 'function');
  assert.equal(Metadata.bookMatchesSearch(book, 'sanguo', Pinyin), true);
  assert.equal(Metadata.bookMatchesSearch(book, 'luoguanzhong', Pinyin), true);
  assert.equal(Metadata.bookMatchesSearch(book, 'hongloumeng', Pinyin), false);
});

test('server bookshelf storage reads and writes the versioned cloud document without localStorage', async () => {
  const Store = globalThis.EpubBookshelfStore;
  const requests = [];
  globalThis.EpubBrowserMode = 'server';
  globalThis.EpubBrowserBasePath = '/reader/';
  globalThis.localStorage = {
    getItem() { throw new Error('server bookshelf must not read localStorage'); },
    setItem() { throw new Error('server bookshelf must not write localStorage'); },
  };
  globalThis.EpubBrowserAuth = {
    fetch: async (url, options) => {
      requests.push({ url, options });
      if (options.method === 'GET') {
        return { ok: true, json: async () => ({ version: 4, data: { items: ['a'], groups: {}, order: ['a'] } }) };
      }
      return { ok: true, json: async () => ({ version: 5, data: { items: ['a', 'b'], groups: {}, order: ['a', 'b'] } }) };
    },
  };

  const loaded = await Store.load();
  const saved = await Store.save({ items: ['a', 'b'], groups: {}, order: ['a', 'b'] });

  assert.deepEqual(loaded.data.items, ['a']);
  assert.equal(saved.version, 5);
  assert.deepEqual(Store.data().items, ['a', 'b']);
  assert.equal(requests[0].url, '/reader/api/bookshelf');
  assert.equal(requests[0].options.headers['X-Username'], undefined);
  assert.deepEqual(JSON.parse(requests[1].options.body), {
    version: 4,
    data: { items: ['a', 'b'], groups: {}, order: ['a', 'b'] },
  });
});
