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
    previous[name] = Object.getOwnPropertyDescriptor(global, name);
    Object.defineProperty(global, name, { value, configurable: true, writable: true });
  }
  try {
    return await callback();
  } finally {
    for (const [name, descriptor] of Object.entries(previous)) {
      if (descriptor === undefined) delete global[name];
      else Object.defineProperty(global, name, descriptor);
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

test('groups one book in reading order and combines the zero-based chapter number with its title', () => {
  withI18n(englishI18n, () => {
    const groups = Hub.groupByChapter([
      { id: 'late', chapter_index: 1, created_at: '2026-08-12T00:00:00Z' },
      { id: 'early', chapter_index: 1, created_at: '2026-08-11T00:00:00Z' },
      { id: 'start', chapter_index: 0, created_at: '2026-08-10T00:00:00Z' },
    ], [{ index: 0, title: 'Opening' }]);

    assert.deepEqual(groups.map(group => group.title), ['Chapter 0 · Opening', 'Chapter 1']);
    assert.deepEqual(groups[1].annotations.map(annotation => annotation.id), ['early', 'late']);
  });
});

test('uses the chapter_index field published by toc.json for numbered chapter titles', () => {
  withI18n(englishI18n, () => {
    const groups = Hub.groupByChapter([
      { id: 'annotation', chapter_index: 3, created_at: '2026-08-11T00:00:00Z' },
    ], [{ chapter_index: 3, title: 'Part one · Chapter one' }]);

    assert.equal(groups[0].title, 'Chapter 3 · Part one · Chapter one');
  });
});

test('builds a deterministic local-only share summary in the displayed chapter order', () => {
  withI18n({
    t: (key, params = {}) => ({
      'annotations.chapterNumber': `Chapter ${params.number}`,
      'annotations.annotationCount': `${params.count} annotations`,
      'annotations.authorSeparator': ' & ',
      'annotations.shareAuthors': 'Authors',
      'annotations.shareNote': 'Note',
    }[key] || key),
  }, () => {
    assert.equal(Hub.buildShareSummary({ title: 'The Book', authors: ['Ada', 'Ben'] }, [
      { id: 'later', chapter_index: 2, created_at: '2026-08-12T00:00:00Z', text: 'Second highlight' },
      { id: 'first', chapter_index: 0, created_at: '2026-08-10T00:00:00Z', text: 'First highlight', note: 'Keep this note exactly.' },
    ], [{ chapter_index: 0, title: 'Opening' }, { chapter_index: 2, title: 'Ending' }]), [
      'The Book',
      'Authors: Ada & Ben',
      '2 annotations',
      '',
      'Chapter 0 · Opening',
      '“First highlight”',
      'Note: Keep this note exactly.',
      '',
      'Chapter 2 · Ending',
      '“Second highlight”',
    ].join('\n'));
  });
});

test('omits absent authors and empty notes from a share summary', () => {
  withI18n({
    t: (key, params = {}) => ({
      'annotations.chapterNumber': `Chapter ${params.number}`,
      'annotations.annotationCount': `${params.count} annotation`,
      'annotations.authorSeparator': ' & ',
      'annotations.shareAuthors': 'Authors',
      'annotations.shareNote': 'Note',
    }[key] || key),
  }, () => {
    assert.equal(Hub.buildShareSummary({ title: 'Untitled' }, [
      { chapter_index: 1, text: 'Exact source text', note: '   ' },
    ], []), 'Untitled\n1 annotation\n\nChapter 1\n“Exact source text”');
  });
});

test('only creates labelled share actions for a non-empty per-book view', async () => {
  await withHubGlobals({
    document: fakeDocument(),
    EpubBrowserI18n: { t: key => ({
      'annotations.shareActions': 'Share annotations',
      'annotations.copyShare': 'Copy to clipboard',
      'annotations.exportShare': 'Export text',
    }[key] || key) },
  }, async () => {
    assert.equal(Hub.createShareActions(null, [{ text: 'A' }], []), null);
    assert.equal(Hub.createShareActions({ title: 'Book' }, [], []), null);

    const actions = Hub.createShareActions({ title: 'Book' }, [{ chapter_index: 0, text: 'A' }], []);
    assert.equal(actions.className, 'annotation-share-actions');
    assert.equal(actions.attributes.role, 'group');
    assert.equal(actions.attributes['aria-label'], 'Share annotations');
    assert.deepEqual(actions.children.map(button => [button.className, button.attributes['aria-label'], button.attributes['data-annotation-share-action']]), [
      ['annotation-share-action', 'Copy to clipboard', 'copy'],
      ['annotation-share-action', 'Export text', 'export'],
    ]);
  });
});

test('copies a plain-text share summary through Clipboard API and falls back when unavailable', async () => {
  const copied = [];
  await withHubGlobals({
    navigator: { clipboard: { writeText: async text => copied.push(text) } },
  }, async () => {
    await Hub.copyShareText('Plain text');
  });
  assert.deepEqual(copied, ['Plain text']);

  const body = { children: [], appendChild(node) { this.children.push(node); }, removeChild(node) { this.children.splice(this.children.indexOf(node), 1); } };
  let selected = false;
  await withHubGlobals({
    navigator: {},
    document: {
      body,
      createElement: () => ({ style: {}, setAttribute() {}, select() { selected = true; }, remove() {} }),
      execCommand: command => command === 'copy',
    },
  }, async () => {
    await Hub.copyShareText('Fallback text');
  });
  assert.equal(selected, true);
  assert.deepEqual(body.children, []);
});

test('reports clipboard fallback failure to the caller', async () => {
  await withHubGlobals({
    navigator: {},
    document: { body: { appendChild() {}, removeChild() {} }, createElement: () => ({ style: {}, setAttribute() {}, select() {} }), execCommand: () => false },
  }, async () => {
    await assert.rejects(Hub.copyShareText('No clipboard'), /copy/i);
  });
});

test('turns a synchronous Clipboard API exception into a localized copy failure', async () => {
  const notifications = [];
  let copy;
  await withHubGlobals({
    document: fakeDocument(),
    navigator: { clipboard: { writeText() { throw new Error('clipboard denied'); } } },
    EpubBrowserI18n: { t: (key, params = {}) => ({
      'annotations.chapterNumber': `Chapter ${params.number}`,
      'annotations.annotationCount': `${params.count} annotation`,
      'annotations.shareActions': 'Share annotations',
      'annotations.copyShare': 'Copy to clipboard',
      'annotations.exportShare': 'Export text',
      'annotations.shareCopyFailed': 'Unable to copy the annotation summary.',
    }[key] || key) },
    EpubBrowserNotification: { show: (message, type) => notifications.push([message, type]) },
  }, async () => {
    assert.doesNotThrow(() => { copy = Hub.copyShareText('Plain text'); });
    await assert.rejects(copy, /Unable to copy share summary/);

    const actions = Hub.createShareActions({ title: 'Book' }, [{ chapter_index: 0, text: 'Text' }], []);
    assert.doesNotThrow(() => actions.children[0].listeners.click());
    await new Promise(resolve => setImmediate(resolve));
  });
  assert.deepEqual(notifications, [['Unable to copy the annotation summary.', 'error']]);
});

test('turns a synchronous legacy copy exception into a localized copy failure', async () => {
  const notifications = [];
  let copy;
  const document = fakeDocument();
  document.body = { appendChild() {}, removeChild() {} };
  const createElement = document.createElement;
  document.createElement = tagName => {
    const node = createElement(tagName);
    node.select = () => {};
    return node;
  };
  document.execCommand = () => { throw new Error('legacy denied'); };
  await withHubGlobals({
    document,
    navigator: {},
    EpubBrowserI18n: { t: (key, params = {}) => ({
      'annotations.chapterNumber': `Chapter ${params.number}`,
      'annotations.annotationCount': `${params.count} annotation`,
      'annotations.shareActions': 'Share annotations',
      'annotations.copyShare': 'Copy to clipboard',
      'annotations.exportShare': 'Export text',
      'annotations.shareCopyFailed': 'Unable to copy the annotation summary.',
    }[key] || key) },
    EpubBrowserNotification: { show: (message, type) => notifications.push([message, type]) },
  }, async () => {
    assert.doesNotThrow(() => { copy = Hub.copyShareText('Plain text'); });
    await assert.rejects(copy, /Unable to copy share summary/);

    const actions = Hub.createShareActions({ title: 'Book' }, [{ chapter_index: 0, text: 'Text' }], []);
    assert.doesNotThrow(() => actions.children[0].listeners.click());
    await new Promise(resolve => setImmediate(resolve));
  });
  assert.deepEqual(notifications, [['Unable to copy the annotation summary.', 'error']]);
});

test('downloads UTF-8 text with a safe deterministic filename and revokes its object URL', async () => {
  const created = [];
  const revoked = [];
  const body = { children: [], appendChild(node) { this.children.push(node); }, removeChild(node) { this.children.splice(this.children.indexOf(node), 1); } };
  let clicked = false;
  await withHubGlobals({
    Blob,
    URL: { createObjectURL(blob) { created.push(blob); return 'blob:share'; }, revokeObjectURL(url) { revoked.push(url); } },
    document: { body, createElement: () => ({ click() { clicked = true; }, remove() {} }) },
  }, async () => {
    assert.equal(Hub.shareFilename('  A / B: C?  ', 'Annotations'), 'A B C-annotations.txt');
    assert.equal(Hub.shareFilename('...', 'Annotations'), 'Annotations-annotations.txt');
    Hub.downloadShareText('Hello', 'A B C-annotations.txt');
  });
  assert.equal(await created[0].text(), 'Hello');
  assert.equal(created[0].type, 'text/plain;charset=utf-8');
  assert.equal(clicked, true);
  assert.deepEqual(body.children, []);
  assert.deepEqual(revoked, ['blob:share']);
});

test('uses shared i18n for chapter fallback, counts, and timestamps', () => {
  withI18n({
    t: (key, params) => key === 'annotations.chapterNumber' ? `章节 ${params.number}` : `${params.count} 条标注`,
    formatDate: () => '2026/08/18 09:02:03',
    onLocaleChange: () => () => {},
  }, () => {
    assert.equal(Hub.groupByChapter([{ chapter_index: 1 }], [])[0].title, '章节 1');
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
