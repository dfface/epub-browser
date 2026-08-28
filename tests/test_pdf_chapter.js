'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const createAdapter = require('../epub_browser/assets/pdf-chapter.js');

class Element {
  constructor(tagName = 'div', ownerDocument = null) {
    this.tagName = tagName.toUpperCase();
    this.ownerDocument = ownerDocument;
    this.attributes = {};
    this.children = [];
    this.parentNode = null;
    this.dataset = {};
    this.clientWidth = 400;
    this.clientHeight = 700;
    this.style = { setProperty(name, value) { this[name] = String(value); } };
    this.className = '';
    this.textContent = '';
  }

  setAttribute(name, value) {
    const text = String(value);
    this.attributes[name] = text;
    if (name.startsWith('data-')) {
      this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = text;
    }
  }

  getAttribute(name) { return this.attributes[name] ?? null; }
  hasAttribute(name) { return Object.hasOwn(this.attributes, name); }
  removeAttribute(name) { delete this.attributes[name]; }
  appendChild(child) { child.parentNode = this; this.children.push(child); return child; }
  append(child) { return this.appendChild(child); }
  replaceChildren(...children) {
    this.children.forEach((child) => { child.parentNode = null; });
    this.children = [];
    children.forEach((child) => this.appendChild(child));
  }
  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter((child) => child !== this);
    this.parentNode = null;
  }
  getBoundingClientRect() { return { width: this.clientWidth, height: this.clientHeight }; }
  querySelectorAll(selector) {
    const found = [];
    const visit = (node) => {
      if (selector === '[data-pdf-page-number]' && node.hasAttribute('data-pdf-page-number')) found.push(node);
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return found;
  }
  getContext() { return { canvas: this }; }
}

function createHarness(options = {}) {
  const events = new Map();
  const renderCalls = [];
  const getDocumentCalls = [];
  const loadingTasks = [];
  const resizeObservers = [];
  const intersectionObservers = [];
  const importUrls = [];
  let cancelCount = 0;
  let textCancelCount = 0;
  const storageValues = new Map();
  const storage = {
    getItem(key) { return storageValues.has(key) ? storageValues.get(key) : null; },
    setItem(key, value) { storageValues.set(key, String(value)); },
    removeItem(key) { storageValues.delete(key); },
  };

  const document = new Element('document');
  document.baseURI = 'https://reader.example/book/demo/chapter_0.html';
  document.createElement = (tagName) => new Element(tagName, document);
  document.ownerDocument = document;

  class TextLayer {
    constructor(params) { this.params = params; }
    render() {
      this.params.container.appendChild(document.createElement('span'));
      return Promise.resolve();
    }
    cancel() { textCancelCount += 1; }
  }

  const pdfjs = {
    GlobalWorkerOptions: { workerSrc: '' },
    TextLayer,
    getDocument(params) {
      getDocumentCalls.push(params);
      const task = {
        destroyed: 0,
        destroy() { this.destroyed += 1; return Promise.resolve(); },
      };
      const pdfDocument = {
        numPages: options.pages || 3,
        destroyed: 0,
        destroy() { this.destroyed += 1; return Promise.resolve(); },
        async getPage(pageNumber) {
          return {
            getViewport({ scale, rotation }) {
              const portrait = rotation % 180 === 0;
              return {
                width: (portrait ? 200 : 300) * scale,
                height: (portrait ? 300 : 200) * scale,
                scale,
                rotation,
                rawDims: { pageWidth: 200, pageHeight: 300, pageX: 0, pageY: 0 },
              };
            },
            render(params) {
              const renderTask = {
                cancelled: false,
                cancel() { this.cancelled = true; cancelCount += 1; },
                promise: options.pendingRender ? new Promise(() => {}) : Promise.resolve(),
              };
              renderCalls.push({ pageNumber, params, renderTask });
              return renderTask;
            },
            getTextContent() {
              const pageTexts = options.pageTexts || [];
              return Promise.resolve({
                items: [{ str: pageTexts[pageNumber - 1] || `Page ${pageNumber}` }],
                styles: {}, lang: 'en'
              });
            },
          };
        },
      };
      task.promise = Promise.resolve(pdfDocument);
      task.pdfDocument = pdfDocument;
      loadingTasks.push(task);
      return task;
    },
  };

  const window = {
    document,
    location: { href: document.baseURI, origin: 'https://reader.example' },
    devicePixelRatio: options.devicePixelRatio || 2,
    EpubPDFConfig: {
      documentUrl: 'document.pdf',
      pdfjsModuleUrl: '/assets/immutable/vendor/pdfjs/build/pdf.0123456789ab.mjs',
      pdfjsWorkerUrl: '/assets/immutable/vendor/pdfjs/build/pdf.worker.abcdef012345.mjs',
      ...options.config,
    },
    EpubBrowserI18n: { t(key) { return `translated:${key}`; } },
    prompt: options.prompt || (() => null),
    addEventListener(name, callback) {
      const callbacks = events.get(name) || [];
      callbacks.push(callback);
      events.set(name, callbacks);
    },
    dispatchEvent(event) {
      for (const callback of events.get(event.type) || []) callback(event);
    },
    setTimeout(callback) { callback(); return 1; },
    clearTimeout() {},
    requestAnimationFrame(callback) { callback(); return 1; },
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; resizeObservers.push(this); }
      observe(node) { this.node = node; }
      disconnect() { this.disconnected = true; }
      fire() { this.callback([{ target: this.node }]); }
    },
    localStorage: storage,
  };
  if (options.lazy) {
    window.IntersectionObserver = class {
      constructor(callback) { this.callback = callback; intersectionObservers.push(this); }
      observe(node) { this.node = node; }
      unobserve(node) { if (this.node === node) this.unobserved = true; }
      disconnect() { this.disconnected = true; }
      fire(isIntersecting = true) { this.callback([{ target: this.node, isIntersecting }]); }
    };
  }
  const adapter = createAdapter(window, {
    importModule: async (url) => { importUrls.push(url); return pdfjs; },
  });

  function page(number, attrs = {}) {
    const node = document.createElement('div');
    node.setAttribute('data-pdf-page-number', number);
    node.setAttribute('data-pdf-page-width', 200);
    node.setAttribute('data-pdf-page-height', 300);
    node.setAttribute('data-pdf-has-extractable-text', attrs.hasText === false ? 'false' : 'true');
    node.setAttribute('aria-label', `Page ${number} of ${options.pages || 3}`);
    return node;
  }

  return {
    adapter, document, window, pdfjs, page, renderCalls, getDocumentCalls,
    loadingTasks, resizeObservers, intersectionObservers, importUrls, storage,
    get cancelCount() { return cancelCount; },
    get textCancelCount() { return textCancelCount; },
    async flush() {
      for (let index = 0; index < 10; index += 1) await Promise.resolve();
    },
  };
}

test('search resolves results to canonical PDF chapter URLs', async () => {
  const harness = createHarness({ pageTexts: ['alpha', 'beta alpha'] });

  const results = await harness.adapter.search('alpha');

  assert.deepEqual(results.map((item) => item.href), ['chapter_0.html', 'chapter_1.html']);
});

test('rotation and fit preferences do not mutate reading mode keys', async () => {
  const harness = createHarness({ pages: 1 });

  await harness.adapter.rotate();
  await harness.adapter.fitWidth();

  assert.equal(harness.storage.getItem('turning'), null);
  assert.equal(harness.storage.getItem('continuousScroll'), null);
});

test('loads one local PDF.js document with its paired worker and disabled optional fetch paths', async () => {
  const harness = createHarness();
  harness.document.appendChild(harness.page(1));
  harness.document.appendChild(harness.page(2));

  await harness.adapter.renderWithin(harness.document);

  assert.deepEqual(harness.importUrls, ['/assets/immutable/vendor/pdfjs/build/pdf.0123456789ab.mjs']);
  assert.equal(harness.pdfjs.GlobalWorkerOptions.workerSrc, '/assets/immutable/vendor/pdfjs/build/pdf.worker.abcdef012345.mjs');
  assert.equal(harness.getDocumentCalls.length, 1);
  assert.deepEqual(harness.getDocumentCalls[0], {
    url: 'https://reader.example/book/demo/document.pdf',
    cMapUrl: null,
    standardFontDataUrl: null,
    wasmUrl: null,
    iccUrl: null,
    useWorkerFetch: false,
    useWasm: false,
    isImageDecoderSupported: false,
    isOffscreenCanvasSupported: false,
    enableXfa: false,
    stopAtErrors: true,
  });
});

test('renders the requested page into a DPR canvas and selectable text layer', async () => {
  const harness = createHarness({ devicePixelRatio: 2 });
  const node = harness.page(2);
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  assert.equal(harness.renderCalls[0].pageNumber, 2);
  assert.deepEqual(harness.renderCalls[0].params.transform, [2, 0, 0, 2, 0, 0]);
  assert.equal(node.getAttribute('data-pdf-rendered'), 'complete');
  assert.equal(node.children.some((child) => child.className === 'pdf-page-canvas'), true);
  const text = node.children.find((child) => child.className.includes('pdf-page-text-layer'));
  assert.equal(text.children[0].tagName, 'SPAN');
  assert.equal(text.style['--total-scale-factor'], '2');
  assert.equal(node.style.minHeight, '600px');
  assert.equal(node.getAttribute('aria-busy'), 'false');
});

test('keeps page geometry, zoom, rotation and fit inside the existing content width', async () => {
  const harness = createHarness({ config: { zoom: 1.5, rotation: 90, fit: 'width' } });
  const node = harness.page(1);
  node.clientWidth = 450;
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  const viewport = harness.renderCalls[0].params.viewport;
  assert.equal(viewport.rotation, 90);
  assert.equal(viewport.width, 675);
  assert.equal(node.style.aspectRatio, '200 / 300');
});

test('uses only the client password callback and never adds a password to document requests', async () => {
  let prompted = 0;
  const harness = createHarness({ prompt: () => { prompted += 1; return 'secret'; } });
  harness.document.appendChild(harness.page(1));
  const rendering = harness.adapter.renderWithin(harness.document);
  await harness.flush();
  let supplied = null;
  harness.loadingTasks[0].onPassword((password) => { supplied = password; }, 1);
  await rendering;

  assert.equal(prompted, 1);
  assert.equal(supplied, 'secret');
  assert.equal(Object.hasOwn(harness.getDocumentCalls[0], 'password'), false);
});

test('cancels stale page and text rendering on resize and disposal', async () => {
  const harness = createHarness({ pendingRender: true });
  const node = harness.page(1);
  harness.document.appendChild(node);
  harness.adapter.renderWithin(harness.document);
  await harness.flush();

  harness.resizeObservers[0].fire();
  await harness.flush();
  assert.equal(harness.cancelCount, 0);
  node.clientWidth = 420;
  harness.resizeObservers[0].fire();
  await harness.flush();
  harness.adapter.disposeWithin(node);

  assert.equal(harness.cancelCount, 2);
  assert.equal(harness.resizeObservers[0].disconnected, true);
  assert.equal(node.children.length, 0);
});

test('renders continuous descriptors from lifecycle events once and disposes evicted pages', async () => {
  const harness = createHarness();
  const initial = harness.page(1);
  harness.document.appendChild(initial);
  await harness.adapter.renderWithin(harness.document);
  const inserted = new Element('section', harness.document);
  inserted.appendChild(harness.page(2));

  harness.window.dispatchEvent({ type: 'epub-browser:chapter-content-added', detail: { root: inserted } });
  await harness.flush();
  harness.window.dispatchEvent({ type: 'epub-browser:chapter-content-added', detail: { root: inserted } });
  await harness.flush();
  harness.window.dispatchEvent({ type: 'epub-browser:chapter-content-removed', detail: { root: inserted } });

  assert.deepEqual(harness.renderCalls.map((call) => call.pageNumber), [1, 2]);
  assert.equal(inserted.children[0].children.length, 0);
  assert.equal(harness.loadingTasks.length, 1);
});

test('reuses the document task across a synchronous page-turning replacement', async () => {
  const harness = createHarness();
  const outgoing = harness.page(1);
  await harness.adapter.renderWithin(outgoing);
  const incoming = harness.page(2);

  harness.window.dispatchEvent({ type: 'epub-browser:chapter-content-removed', detail: { root: outgoing } });
  harness.window.dispatchEvent({ type: 'epub-browser:chapter-content-added', detail: { root: incoming } });
  await harness.flush();

  assert.equal(harness.loadingTasks.length, 1);
  assert.equal(harness.loadingTasks[0].destroyed, 0);
  assert.deepEqual(harness.renderCalls.map((call) => call.pageNumber), [1, 2]);
});

test('destroys the old loading task when the configured document source changes', async () => {
  const harness = createHarness();
  await harness.adapter.renderWithin(harness.page(1));
  harness.window.EpubPDFConfig.documentUrl = 'replacement.pdf';

  await harness.adapter.renderWithin(harness.page(2));

  assert.equal(harness.loadingTasks.length, 2);
  assert.equal(harness.loadingTasks[0].destroyed, 1);
  assert.equal(harness.getDocumentCalls[1].url, 'https://reader.example/book/demo/replacement.pdf');
});

test('lazily paints a descriptor only when it enters the viewport', async () => {
  const harness = createHarness({ lazy: true });
  const node = harness.page(1);
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);
  assert.equal(harness.renderCalls.length, 0);
  harness.resizeObservers[0].fire();
  await harness.flush();
  assert.equal(harness.renderCalls.length, 0);
  harness.intersectionObservers[0].fire();
  await harness.flush();

  assert.equal(harness.renderCalls.length, 1);
  assert.equal(harness.intersectionObservers[0].unobserved, true);
});

test('rejects external or unhashed PDF.js assets before importing or fetching', async () => {
  const harness = createHarness({ config: { pdfjsModuleUrl: 'https://cdn.example/pdf.mjs' } });
  const node = harness.page(1);
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  assert.equal(harness.importUrls.length, 0);
  assert.equal(harness.getDocumentCalls.length, 0);
  assert.equal(node.getAttribute('data-pdf-rendered'), 'error');
  assert.equal(node.children[0].getAttribute('role'), 'alert');
  assert.equal(node.children[0].textContent, 'translated:reader.chapterLoadFailed');
});
