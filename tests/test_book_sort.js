const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function loadBookSort(storage) {
    const window = {
        localStorage: {
            getItem(key) {
                return Object.prototype.hasOwnProperty.call(storage, key) ? storage[key] : null;
            },
        },
    };
    vm.runInNewContext(fs.readFileSync('epub_browser/assets/book-sort.js', 'utf8'), {
        window,
        Intl,
        console,
    });
    return window.EpubBrowserBookSort;
}

function book(hash) {
    return { hash, title: hash, created_at: '2024-01-01', updated_at: '2024-01-01' };
}

function ids(books) {
    return books.map((item) => item.hash);
}

test('shelf_first sorts shelf books by added time descending', () => {
    const sort = loadBookSort({
        bookshelf: JSON.stringify({
            items: ['b', 'd'],
            groups: {},
            order: ['b', 'd'],
            added: { b: 200, d: 300 },
        }),
    });
    const ordered = sort.sortBooks([book('a'), book('b'), book('c'), book('d')], 'shelf_first', 'en');
    assert.deepEqual(ids(ordered), ['d', 'b', 'a', 'c']);
});

test('shelf_first derives added order for legacy shelf documents', () => {
    const sort = loadBookSort({
        bookshelf: JSON.stringify({
            items: ['b', 'd'],
            groups: {},
            order: ['b', 'd'],
        }),
    });
    const ordered = sort.sortBooks([book('a'), book('b'), book('c'), book('d')], 'shelf_first', 'en');
    assert.deepEqual(ids(ordered), ['d', 'b', 'a', 'c']);
});

test('shelf_first includes books nested in groups', () => {
    const sort = loadBookSort({
        bookshelf: JSON.stringify({
            items: [],
            groups: {
                g: { items: ['c'], groups: {}, order: ['c'] },
            },
            order: ['g'],
            added: { c: 42 },
        }),
    });
    const ordered = sort.sortBooks([book('a'), book('b'), book('c')], 'shelf_first', 'en');
    assert.equal(ids(ordered)[0], 'c');
});

test('shelf_first keeps the manual order for non-shelf books', () => {
    const sort = loadBookSort({
        bookshelf: JSON.stringify({ items: ['a'], groups: {}, order: ['a'], added: { a: 5 } }),
        'book-grid-sortable-order': JSON.stringify(['c', 'b']),
    });
    const ordered = sort.sortBooks([book('a'), book('b'), book('c'), book('d')], 'shelf_first', 'en');
    assert.deepEqual(ids(ordered), ['a', 'd', 'c', 'b']);
});

test('shelf_first tolerates missing or malformed shelf data', () => {
    const sort = loadBookSort({ bookshelf: '{invalid' });
    const ordered = sort.sortBooks([book('b'), book('a')], 'shelf_first', 'en');
    assert.deepEqual(ids(ordered), ['a', 'b']);
});
