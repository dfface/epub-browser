const test = require('node:test');
const assert = require('node:assert/strict');
const RecentReading = require('../epub_browser/assets/recent-reading.js');

function context(messages) {
  return {
    EpubBrowserI18n: {
      t(key, params) {
        const template = messages[key];
        if (template === undefined) throw new Error('missing message: ' + key);
        return String(template).replace(/\{(\w+)\}/g, (_, name) => params[name]);
      },
    },
  };
}

const MESSAGES = {
  'library.recentReading.chapter': 'Chapter {index}',
  'library.recentReading.page': 'Page {index}',
  'library.recentReading.justNow': 'Just now',
  'library.recentReading.minutesAgo': '{count}m ago',
  'library.recentReading.hoursAgo': '{count}h ago',
  'library.recentReading.daysAgo': '{count}d ago',
  'library.recentReading.monthsAgo': '{count}mo ago',
};

test('parses SQLite CURRENT_TIMESTAMP values as UTC', () => {
  const parsed = RecentReading.parseTimestamp('2026-09-04 12:00:00');
  assert.equal(parsed.toISOString(), '2026-09-04T12:00:00.000Z');
  assert.equal(RecentReading.parseTimestamp('2026-09-04T12:00:00Z').getTime(), parsed.getTime());
  assert.equal(RecentReading.parseTimestamp(''), null);
  assert.equal(RecentReading.parseTimestamp(undefined), null);
  assert.equal(RecentReading.parseTimestamp('not a date'), null);
});

test('formats elapsed time in increasingly coarse units', () => {
  const root = context(MESSAGES);
  const now = new Date('2026-09-04T12:00:00.000Z');
  const ago = (milliseconds) =>
    RecentReading.relativeTime(root, new Date(now.getTime() - milliseconds).toISOString(), now);

  assert.equal(ago(0), 'Just now');
  assert.equal(ago(59 * 1000), 'Just now');
  assert.equal(ago(60 * 1000), '1m ago');
  assert.equal(ago(59 * 60 * 1000), '59m ago');
  assert.equal(ago(60 * 60 * 1000), '1h ago');
  assert.equal(ago(23 * 60 * 60 * 1000), '23h ago');
  assert.equal(ago(24 * 60 * 60 * 1000), '1d ago');
  assert.equal(ago(29 * 24 * 60 * 60 * 1000), '29d ago');
  assert.equal(ago(45 * 24 * 60 * 60 * 1000), '2mo ago');
});

test('clock skew never produces a future label', () => {
  const root = context(MESSAGES);
  const now = new Date('2026-09-04T12:00:00.000Z');
  const future = new Date(now.getTime() + 3 * 60 * 60 * 1000).toISOString();
  assert.equal(RecentReading.relativeTime(root, future, now), 'Just now');
});

test('unparseable timestamps render as an empty string', () => {
  const root = context(MESSAGES);
  assert.equal(RecentReading.relativeTime(root, '', Date.now()), '');
});

test('position labels distinguish chapters from PDF pages', () => {
  const root = context(MESSAGES);
  assert.equal(
    RecentReading.positionLabel(root, { chapter_index: 11 }, 'epub'),
    'Chapter 12'
  );
  assert.equal(
    RecentReading.positionLabel(root, { chapter_index: 6 }, 'pdf'),
    'Page 7'
  );
  assert.equal(RecentReading.positionLabel(root, { chapter_index: 0 }, 'epub'), 'Chapter 1');
  assert.equal(RecentReading.positionLabel(root, {}, 'epub'), '');
  assert.equal(RecentReading.positionLabel(root, { chapter_index: -1 }, 'epub'), '');
  assert.equal(RecentReading.positionLabel(root, { chapter_index: '3' }, 'epub'), '');
  assert.equal(RecentReading.positionLabel(root, null, 'epub'), '');
});

test('chapter URLs are derived from the catalogue entry', () => {
  assert.equal(
    RecentReading.chapterUrl('/book/abc/index.html', 4),
    '/book/abc/chapter_4.html'
  );
  assert.equal(
    RecentReading.chapterUrl('/base/book/abc/index.html', 0),
    '/base/book/abc/chapter_0.html'
  );
  assert.equal(RecentReading.chapterUrl('/book/abc/index.html', -1), '/book/abc/index.html');
  assert.equal(RecentReading.chapterUrl('/book/abc/index.html', null), '/book/abc/index.html');
  assert.equal(RecentReading.chapterUrl('', 2), '');
});

test('join drops unknown and duplicated books and keeps the server order', () => {
  const books = [
    { hash: 'open-id', url: '/book/open-id/index.html', title: 'Open', format: 'epub' },
    { hash: 'second-id', url: '/book/second-id/index.html', title: 'Second', format: 'pdf' },
  ];
  const items = [
    { book_id: 'open-id', chapter_index: 2, updated_at: '2026-09-04 10:00:00' },
    { book_id: 'removed-id', chapter_index: 9, updated_at: '2026-09-03 10:00:00' },
    { book_id: 'second-id', chapter_index: 0, updated_at: '2026-09-02 10:00:00' },
    { book_id: 'open-id', chapter_index: 5, updated_at: '2026-09-01 10:00:00' },
  ];

  const merged = RecentReading.joinRecentReading(books, items);

  assert.deepEqual(
    merged.map((entry) => [entry.book.hash, entry.item.chapter_index]),
    [['open-id', 2], ['second-id', 0]]
  );
});

test('join tolerates missing inputs', () => {
  assert.deepEqual(RecentReading.joinRecentReading(null, null), []);
  assert.deepEqual(RecentReading.joinRecentReading([{ hash: 'a' }], null), []);
  assert.deepEqual(RecentReading.joinRecentReading(null, [{ book_id: 'a' }]), []);
});

test('the rail stays hidden until both sides of the join arrive', () => {
  const renderCalls = [];
  let state = { books: [], items: null };
  const controller = RecentReading.createController({
    render: (next) => {
      state = next;
      renderCalls.push(next);
    },
  });

  const mount = { hidden: true };
  const hidden = () => state.items === null || RecentReading.joinRecentReading(state.books, state.items).length === 0;

  controller.setBooks([{ hash: 'a' }]);
  mount.hidden = hidden();
  assert.equal(mount.hidden, true, 'no progress loaded yet');

  controller.setItems([{ book_id: 'a', chapter_index: 0 }]);
  mount.hidden = hidden();
  assert.equal(mount.hidden, false, 'catalogue and progress both present');

  controller.setItems([]);
  mount.hidden = hidden();
  assert.equal(mount.hidden, true, 'nothing to show collapses instead of an empty state');

  controller.setBooks(null);
  assert.deepEqual(controller.state.books, []);
  assert.equal(renderCalls.length, 4);
});
