'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const createAdapter = require('../epub_browser/assets/pdf-chapter.js');

class Element {
  constructor(tagName, ownerDocument) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.attributes = {};
    this.children = [];
    this.parentNode = null;
    this.className = '';
    this.clientWidth = 400;
    this.clientHeight = 600;
    this.style = { setProperty(name, value) { this[name] = String(value); } };
  }

  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] || null; }
  hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
  removeAttribute(name) { delete this.attributes[name]; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  replaceChildren(...children) { this.children = []; children.forEach(child => this.appendChild(child)); }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }
  getBoundingClientRect() { return { width: this.clientWidth, height: this.clientHeight }; }
  getContext() { return {}; }
  querySelectorAll(selector) {
    const matches = [];
    const className = selector.startsWith('.') ? selector.slice(1) : '';
    const visit = node => {
      if (selector === '[data-pdf-page-number]' && node.hasAttribute('data-pdf-page-number')) matches.push(node);
      if (className && node.className.split(/\s+/).includes(className)) matches.push(node);
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return matches;
  }
}

function pdfAnnotationHarness({ pageNumber = 3, hasExtractableText = true, renderError = false } = {}) {
  const listeners = new Map();
  const document = new Element('document');
  document.baseURI = 'https://reader.example/book/demo/chapter_2.html';
  document.createElement = tagName => new Element(tagName, document);
  document.readyState = '';
  const root = document.createElement('article');
  root.setAttribute('id', 'eb-content');
  root.setAttribute('data-chapter-index', String(pageNumber - 1));
  const page = document.createElement('div');
  page.setAttribute('data-pdf-page-number', String(pageNumber));
  page.setAttribute('data-pdf-page-width', '200');
  page.setAttribute('data-pdf-page-height', '300');
  page.setAttribute('data-pdf-has-extractable-text', String(hasExtractableText));
  root.appendChild(page);
  document.appendChild(root);

  class TextLayer {
    constructor({ container }) { this.container = container; }
    render() { this.container.appendChild(document.createElement('span')); return Promise.resolve(); }
  }
  const pdfjs = {
    GlobalWorkerOptions: {},
    TextLayer,
    getDocument() {
      return {
        promise: Promise.resolve({
          numPages: pageNumber,
          getPage() {
            return Promise.resolve({
              getViewport({ scale, rotation }) {
                return { width: 200 * scale, height: 300 * scale, scale, rotation };
              },
              render() {
                return {
                  promise: renderError
                    ? Promise.reject(new Error('render failed'))
                    : Promise.resolve(),
                };
              },
              getTextContent() { return Promise.resolve({ items: [{ str: 'The little prince' }] }); },
            });
          },
        }),
        destroy() {},
      };
    },
  };
  const window = {
    document,
    location: { href: document.baseURI, origin: 'https://reader.example' },
    devicePixelRatio: 1,
    EpubPDFConfig: {
      documentUrl: 'document.pdf',
      pdfjsModuleUrl: '/assets/immutable/vendor/pdfjs/build/pdf.0123456789ab.mjs',
      pdfjsWorkerUrl: '/assets/immutable/vendor/pdfjs/build/pdf.worker.abcdef012345.mjs',
    },
    EpubBrowserI18n: { t: key => key },
    addEventListener(type, listener) {
      const entries = listeners.get(type) || [];
      entries.push(listener);
      listeners.set(type, entries);
    },
    dispatchEvent(event) { (listeners.get(event.type) || []).forEach(listener => listener(event)); },
  };
  const adapter = createAdapter(window, { importModule: () => Promise.resolve(pdfjs) });
  return {
    document, root, page, window, adapter,
    renderTextLayer() { return adapter.renderWithin(root); },
  };
}

function runChapterAnnotationCoordinator(harness, annotationModule, { isPdf = true } = {}) {
  const notifications = [];
  harness.window.location.search = '?annotation=note-1';
  harness.window.AnnotationModule = annotationModule;
  if (!isPdf) delete harness.window.EpubPDFConfig;
  const chapterSource = fs.readFileSync('epub_browser/assets/chapter.js', 'utf8');
  const start = chapterSource.indexOf('    function requestedAnnotationId() {');
  const end = chapterSource.indexOf('    // ==================== 连续滚动模式', start);
  assert.notEqual(start, -1);
  assert.notEqual(end, -1);
  vm.runInNewContext(chapterSource.slice(start, end), {
    window: harness.window,
    Promise,
    setTimeout,
    book_hash: 'demo',
    chapter_index: '2',
    isContinuousScroll: false,
    i18n: { t: key => key },
    showNotification(message, type) { notifications.push({ message, type }); },
  });
  return notifications;
}

test('the PDF adapter DOM harness detects a PDF-specific selection menu fixture', () => {
  const harness = pdfAnnotationHarness();
  const forbiddenMenu = harness.document.createElement('div');
  forbiddenMenu.className = 'pdf-selection-menu';
  harness.page.appendChild(forbiddenMenu);

  assert.equal(harness.root.querySelectorAll('.pdf-selection-menu').length, 1);
});

test('PDF text layer announces the normal chapter root and canonical annotation index once', async () => {
  const harness = pdfAnnotationHarness({ pageNumber: 3 });
  const ready = [];
  harness.window.addEventListener('epub-browser:annotation-content-ready', event => ready.push(event.detail));

  await harness.renderTextLayer();
  await harness.renderTextLayer();

  assert.equal(ready.length, 1);
  assert.equal(ready[0].root, harness.root);
  assert.equal(ready[0].chapterIndex, 2);
  assert.equal(ready[0].chapterUrl, 'chapter_2.html');
  assert.equal(ready[0].annotationAvailable, true);
  assert.equal(harness.page.querySelectorAll('.pdf-selection-menu').length, 0);
});

test('PDF pages without a text layer settle annotation restoration as unavailable', async () => {
  const harness = pdfAnnotationHarness({ hasExtractableText: false });
  const ready = [];
  harness.window.addEventListener('epub-browser:annotation-content-ready', event => ready.push(event.detail));

  await harness.renderTextLayer();

  assert.equal(harness.page.getAttribute('data-pdf-rendered'), 'complete');
  assert.equal(ready.length, 1);
  assert.equal(ready[0].chapterIndex, 2);
  assert.equal(ready[0].annotationAvailable, false);
});

test('PDF render errors settle annotation restoration instead of leaving deep links pending', async () => {
  const harness = pdfAnnotationHarness({ renderError: true });
  const ready = [];
  harness.window.addEventListener('epub-browser:annotation-content-ready', event => ready.push(event.detail));

  await harness.renderTextLayer();

  assert.equal(harness.page.getAttribute('data-pdf-rendered'), 'error');
  assert.equal(ready.length, 1);
  assert.equal(ready[0].chapterIndex, 2);
  assert.equal(ready[0].annotationAvailable, false);
});

test('PDF annotation deep links wait for text-layer restoration before reporting not found', async () => {
  const harness = pdfAnnotationHarness({ pageNumber: 3 });
  const focusCalls = [];
  const annotationModule = {
    initialized: true,
    init() {
      harness.window.addEventListener('epub-browser:annotation-content-ready', () => this.refresh());
      return Promise.resolve();
    },
    refresh() {
      if (!harness.root.querySelectorAll('.annotation-highlight').length) {
        const highlight = harness.document.createElement('span');
        highlight.className = 'annotation-highlight';
        harness.root.appendChild(highlight);
      }
      return Promise.resolve();
    },
    focusAnnotation(id, options) {
      focusCalls.push({ id, options });
      const locate = () => harness.root.querySelectorAll('.annotation-highlight').length > 0;
      if (locate()) return Promise.resolve(true);
      if (!options || options.waitForContentReady !== true || options.chapterIndex !== 2) {
        return Promise.resolve(false);
      }
      return new Promise(resolve => {
        harness.window.addEventListener('epub-browser:annotation-content-ready', () => resolve(locate()));
      });
    },
  };
  const notifications = runChapterAnnotationCoordinator(harness, annotationModule);
  await Promise.resolve();

  await harness.renderTextLayer();
  await Promise.resolve();

  assert.equal(focusCalls.length, 1);
  assert.equal(focusCalls[0].id, 'note-1');
  assert.equal(focusCalls[0].options.waitForContentReady, true);
  assert.equal(focusCalls[0].options.chapterIndex, 2);
  assert.equal(harness.root.querySelectorAll('.annotation-highlight').length, 1);
  assert.deepEqual(notifications, []);
});

test('PDF annotation deep links warn once only after a restored annotation is genuinely missing', async () => {
  const harness = pdfAnnotationHarness({ pageNumber: 3 });
  let settleFocus = null;
  const annotationModule = {
    init() {
      harness.window.addEventListener('epub-browser:annotation-content-ready', () => {
        this.refresh().then(() => settleFocus(false));
      });
      return Promise.resolve();
    },
    refresh() { return Promise.resolve(); },
    focusAnnotation(id, options) {
      assert.equal(id, 'note-1');
      assert.equal(options.waitForContentReady, true);
      assert.equal(options.chapterIndex, 2);
      return new Promise(resolve => { settleFocus = resolve; });
    },
  };
  const notifications = runChapterAnnotationCoordinator(harness, annotationModule);
  await Promise.resolve();
  assert.deepEqual(notifications, []);

  await harness.renderTextLayer();
  await Promise.resolve();
  await Promise.resolve();

  assert.deepEqual(notifications, [
    { message: 'reader.annotationNotFound', type: 'warning' },
  ]);
});

test('EPUB annotation deep links preserve immediate focus and missing-warning behavior', async () => {
  for (const found of [true, false]) {
    const harness = pdfAnnotationHarness({ pageNumber: 3 });
    const calls = [];
    const annotationModule = {
      init() { return Promise.resolve(); },
      focusAnnotation(id, options) {
        calls.push({ id, options });
        return Promise.resolve(found);
      },
    };
    const notifications = runChapterAnnotationCoordinator(harness, annotationModule, { isPdf: false });
    await Promise.resolve();
    await Promise.resolve();

    assert.equal(calls.length, 1);
    assert.equal(calls[0].id, 'note-1');
    assert.equal(calls[0].options, undefined);
    assert.deepEqual(
      notifications,
      found ? [] : [{ message: 'reader.annotationNotFound', type: 'warning' }],
    );
  }
});
