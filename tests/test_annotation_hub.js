const test = require('node:test');
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const Hub = require('../epub_browser/assets/annotation-hub.js');

function layoutBrowser() {
  return [
    process.env.EPUB_BROWSER_TEST_BROWSER,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ].find(candidate => candidate && fs.existsSync(candidate));
}

function withI18n(runtime, callback) {
  const original = global.EpubBrowserI18n;
  global.EpubBrowserI18n = runtime;
  try {
    callback();
  } finally {
    global.EpubBrowserI18n = original;
  }
}

async function withHubGlobals(overrides, callback) {
  const previous = {};
  for (const [name, value] of Object.entries(overrides)) {
    previous[name] = global[name];
    global[name] = value;
  }
  try {
    return await callback();
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete global[name];
      else global[name] = value;
    }
  }
}

function fakeDocument() {
  return {
    createElement(tagName) {
      return {
        tagName: tagName.toUpperCase(),
        className: '',
        textContent: '',
        children: [],
        attributes: {},
        listeners: {},
        style: {},
        appendChild(child) { this.children.push(child); return child; },
        setAttribute(name, value) { this.attributes[name] = value; },
        removeAttribute(name) { delete this.attributes[name]; },
        addEventListener(name, listener) { this.listeners[name] = listener; },
      };
    },
  };
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

test('renders an icon-only delete action outside the annotation card content', async () => {
  await withHubGlobals({
    document: fakeDocument(),
    EpubBrowserI18n: { t: (key) => key === 'annotations.deleteAnnotation' ? 'Delete annotation' : key },
  }, async () => {
    const row = Hub.annotationCard({
      id: 'annotation-1',
      book_hash: 'book',
      chapter_index: 1,
      text: 'Highlighted text',
      color: '#42a5f5',
    });

    assert.equal(row.tagName, 'ARTICLE');
    assert.equal(row.className, 'annotation-card-row');
    assert.deepEqual(row.children.map(child => child.className), ['annotation-card', 'annotation-card-delete']);

    const card = row.children[0];
    const deleteButton = row.children[1];
    assert.equal(card.tagName, 'A');
    assert.equal(deleteButton.tagName, 'BUTTON');
    assert.equal(deleteButton.textContent, '');
    assert.equal(deleteButton.attributes['aria-label'], 'Delete annotation');
    assert.equal(deleteButton.attributes.title, 'Delete annotation');
    assert.deepEqual(deleteButton.children.map(child => child.className), ['fas fa-trash-alt']);
  });
});

test('keeps the annotation color stripe visible beside the card content', {
  skip: layoutBrowser() ? false : 'Chrome, Edge, or Chromium is required for the layout assertion',
}, () => {
  const browser = layoutBrowser();
  const assetDirectory = path.join(__dirname, '..', 'epub_browser', 'assets');
  const css = fs.readFileSync(path.join(assetDirectory, 'annotation-hub.css'), 'utf8');
  const script = fs.readFileSync(path.join(assetDirectory, 'annotation-hub.js'), 'utf8');
  const html = '<!doctype html><style>' + css + '</style>' +
    '<main id="fixture"></main>' +
    '<script>window.EpubBrowserI18n={t:function(key){return key},formatDate:function(){return ""}}</script>' +
    '<script>' + script + '</script>' +
    '<script>' +
      'var row=window.AnnotationHub.annotationCard({' +
        'id:"annotation-1",book_hash:"book",chapter_index:1,' +
        'text:"Highlighted text",color:"#42a5f5"' +
      '});' +
      'document.getElementById("fixture").appendChild(row);' +
      'var stripe=document.querySelector(".annotation-card-color");' +
      'document.body.dataset.stripeHeight=stripe.getBoundingClientRect().height;' +
      'document.body.dataset.stripeColor=getComputedStyle(stripe).backgroundColor;' +
    '</script>';
  const result = childProcess.spawnSync(browser, [
    '--headless=new',
    '--disable-gpu',
    '--no-sandbox',
    '--dump-dom',
    'data:text/html;charset=utf-8,' + encodeURIComponent(html),
  ], { encoding: 'utf8', timeout: 10000 });

  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  const height = result.stdout.match(/data-stripe-height="([^"]+)"/);
  const color = result.stdout.match(/data-stripe-color="([^"]+)"/);
  assert.ok(height, 'browser did not report the annotation color stripe height');
  assert.ok(Number(height[1]) > 0, 'annotation color stripe collapsed to zero height');
  assert.equal(color && color[1], 'rgb(66, 165, 245)');
});

test('deletes an annotation after destructive confirmation and announces success', async () => {
  const deleted = [];
  const notifications = [];
  let removed = null;

  await withHubGlobals({
    EpubBrowserI18n: {
      t: (key) => ({
        'annotations.delete': 'Delete',
        'annotations.deleteAnnotation': 'Delete annotation',
        'annotations.confirmDelete': 'Delete this annotation?',
        'annotations.deleted': 'Annotation deleted',
      }[key] || key),
    },
    EpubDialog: {
      confirm: async (options) => {
        assert.deepEqual(options, {
          title: 'Delete annotation',
          message: 'Delete this annotation?',
          confirmText: 'Delete',
          destructive: true,
        });
        return true;
      },
    },
    AnnotationStorage: {
      delete: async (id) => deleted.push(id),
    },
    EpubBrowserNotification: {
      show: (message, type) => notifications.push([message, type]),
    },
  }, async () => {
    const result = await Hub.deleteAnnotation({ id: 'annotation-1' }, (annotation) => { removed = annotation; });
    assert.equal(result, true);
  });

  assert.deepEqual(deleted, ['annotation-1']);
  assert.deepEqual(removed, { id: 'annotation-1' });
  assert.deepEqual(notifications, [['Annotation deleted', 'success']]);
});

test('keeps an annotation when deletion is cancelled', async () => {
  let deleteCalls = 0;
  let removeCalls = 0;

  await withHubGlobals({
    EpubBrowserI18n: { t: (key) => key },
    EpubDialog: { confirm: async () => false },
    AnnotationStorage: { delete: async () => { deleteCalls += 1; } },
  }, async () => {
    const result = await Hub.deleteAnnotation({ id: 'annotation-1' }, () => { removeCalls += 1; });
    assert.equal(result, false);
  });

  assert.equal(deleteCalls, 0);
  assert.equal(removeCalls, 0);
});

test('keeps an annotation and uses the standard error notification when deletion fails', async () => {
  const notifications = [];
  let removeCalls = 0;

  await withHubGlobals({
    EpubBrowserI18n: {
      t: (key, params = {}) => key === 'annotations.deleteFailed' ? `Failed to delete: ${params.error}` : key,
    },
    EpubDialog: { confirm: async () => true },
    AnnotationStorage: { delete: async () => { throw new Error('offline'); } },
    EpubBrowserNotification: {
      show: (message, type) => notifications.push([message, type]),
    },
  }, async () => {
    const result = await Hub.deleteAnnotation({ id: 'annotation-1' }, () => { removeCalls += 1; });
    assert.equal(result, false);
  });

  assert.equal(removeCalls, 0);
  assert.deepEqual(notifications, [['Failed to delete: offline', 'error']]);
});
