'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const createAdapter = require('../epub_browser/assets/pdf-chapter.js');

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

let darkPdfThemeInspection = null;

function inspectDarkPdfTheme() {
  if (darkPdfThemeInspection) return darkPdfThemeInspection;
  const assetDirectory = path.join(__dirname, '..', 'epub_browser', 'assets');
  const styles = ['theme.css', 'chapter.css', 'pdf-chapter.css']
    .map(filename => fs.readFileSync(path.join(assetDirectory, filename), 'utf8'))
    .join('\n');
  const html = '<!doctype html><html class="dark-mode"><head><style>' + styles + '</style></head>' +
    '<body class="pdf-source"><div id="reader-canvas-probe" style="background:var(--reader-canvas)"></div>' +
    '<div class="eb-content-container" id="pdf-stage">' +
    '<main id="eb-content"><div class="pdf-page-content"><div class="pdf-page-text-layer">' +
    '<span id="pdf-text">Selectable PDF text</span></div></div></main></div>' +
    '<script>' +
      'document.body.dataset.pdfTextColor=getComputedStyle(document.getElementById("pdf-text")).color;' +
      'document.body.dataset.pdfStageBackground=getComputedStyle(document.getElementById("pdf-stage")).backgroundColor;' +
      'document.body.dataset.readerCanvasBackground=getComputedStyle(document.getElementById("reader-canvas-probe")).backgroundColor;' +
    '</script></body></html>';
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'epub-browser-pdf-theme-'));
  const fixture = path.join(directory, 'index.html');
  fs.writeFileSync(fixture, html);
  try {
    const result = childProcess.spawnSync(layoutBrowser(), [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--dump-dom',
      `file://${fixture}`,
    ], { encoding: 'utf8', timeout: 10000 });
    assert.ifError(result.error);
    assert.equal(result.status, 0, result.stderr);
    const textColor = result.stdout.match(/data-pdf-text-color="([^"]+)"/);
    const stageBackground = result.stdout.match(/data-pdf-stage-background="([^"]+)"/);
    const readerCanvasBackground = result.stdout.match(/data-reader-canvas-background="([^"]+)"/);
    assert.ok(textColor, 'browser did not report the PDF text layer color');
    assert.ok(stageBackground, 'browser did not report the PDF stage background');
    assert.ok(readerCanvasBackground, 'browser did not report the reader canvas background');
    darkPdfThemeInspection = {
      textColor: textColor[1],
      stageBackground: stageBackground[1],
      readerCanvasBackground: readerCanvasBackground[1],
    };
    return darkPdfThemeInspection;
  } finally {
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

const browser = layoutBrowser();

test('dark PDF text layer remains transparent above the rendered paper', {
  skip: browser ? false : 'Chrome, Edge, or Chromium is required for the PDF theme assertion',
}, () => {
  assert.equal(inspectDarkPdfTheme().textColor, 'rgba(0, 0, 0, 0)');
});

test('dark PDF stage uses the reader canvas without lifting it toward the text color', {
  skip: browser ? false : 'Chrome, Edge, or Chromium is required for the PDF theme assertion',
}, () => {
  const inspection = inspectDarkPdfTheme();
  assert.equal(inspection.stageBackground, inspection.readerCanvasBackground);
});

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
    this.hidden = false;
    this.value = '';
    this.events = new Map();
    this.focused = false;
    this.classList = {
      add: (...names) => { this.className = Array.from(new Set(this.className.split(/\s+/).filter(Boolean).concat(names))).join(' '); },
      remove: (...names) => { this.className = this.className.split(/\s+/).filter((name) => !names.includes(name)).join(' '); },
      contains: (name) => this.className.split(/\s+/).includes(name),
    };
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
  addEventListener(name, callback) {
    const callbacks = this.events.get(name) || [];
    callbacks.push(callback);
    this.events.set(name, callbacks);
  }
  dispatchEvent(event) {
    for (const callback of this.events.get(event.type) || []) callback(event);
  }
  click() { this.dispatchEvent({ type: 'click', preventDefault() {} }); }
  focus() { this.focused = true; }
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
  const textRequests = [];
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
  document.body = document.createElement('body');
  document.documentElement = document;
  document.appendChild(document.body);
  document.getElementById = (id) => {
    let match = null;
    const visit = (node) => {
      if (node.getAttribute && node.getAttribute('id') === id) match = node;
      node.children.forEach(visit);
    };
    visit(document);
    return match;
  };
  document.querySelector = (selector) => {
    if (selector === '.reader-drawer.active') {
      let match = null;
      const visit = (node) => {
        if (node.classList && node.classList.contains('reader-drawer') && node.classList.contains('active')) match = node;
        node.children.forEach(visit);
      };
      visit(document);
      return match;
    }
    return null;
  };

  class TextLayer {
    constructor(params) { this.params = params; }
    render() {
      if (options.textLayerOverwritesSize) {
        this.params.container.style.width = 'round(down, var(--total-scale-factor) * 200px, var(--scale-round-x))';
        this.params.container.style.height = 'round(down, var(--total-scale-factor) * 300px, var(--scale-round-y))';
      }
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
              if (options.textError) return Promise.reject(new Error('broken text layer'));
              if (options.deferText && options.deferText.includes(pageNumber)) {
                return new Promise((resolve, reject) => textRequests.push({ pageNumber, resolve, reject }));
              }
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
    innerHeight: options.innerHeight || 800,
    devicePixelRatio: options.devicePixelRatio || 2,
    getComputedStyle() {
      const padding = options.stagePadding || 0;
      return { paddingLeft: `${padding}px`, paddingRight: `${padding}px` };
    },
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
    setTimeout(callback) {
      if (options.controlledTimers) { events.set('timeout', callback); return 1; }
      callback(); return 1;
    },
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

  function control(id, className = '') {
    const node = document.createElement('button');
    node.setAttribute('id', id);
    node.className = className;
    document.body.appendChild(node);
    return node;
  }

  function installReaderControls() {
    const drawer = control('pdfSearchDrawer', 'reader-drawer');
    drawer.setAttribute('aria-hidden', 'true');
    const toggle = control('pdfSearchToggle');
    const mobileToggle = control('mobilePdfSearchToggle');
    const close = control('pdfSearchClose');
    const form = control('pdfSearchForm');
    const input = control('pdfSearchInput');
    const results = document.createElement('ul');
    results.setAttribute('id', 'pdfSearchResults');
    document.body.appendChild(results);
    control('readerDrawerBackdrop');
    ['pdfZoomOut', 'pdfZoomIn', 'pdfFitWidth', 'pdfFitPage', 'pdfRotate'].forEach(control);
    return { drawer, toggle, mobileToggle, close, form, input, results };
  }

  return {
    adapter, document, window, pdfjs, page, renderCalls, getDocumentCalls,
    loadingTasks, resizeObservers, intersectionObservers, importUrls, storage, textRequests, installReaderControls,
    get cancelCount() { return cancelCount; },
    get textCancelCount() { return textCancelCount; },
    async flush() {
      for (let index = 0; index < 10; index += 1) await Promise.resolve();
    },
    runTimeout() {
      const timeout = events.get('timeout');
      if (timeout) timeout();
    },
  };
}

test('registers the PDF search surface with the shared drawer controller for desktop and mobile toggles', () => {
  const registrations = [];
  const controller = {
    register(options) {
      registrations.push(options);
      return { open() {}, close() {} };
    },
  };
  const harness = createHarness({ drawerController: controller });
  const controls = harness.installReaderControls();
  harness.window.EpubReaderDrawers = controller;

  harness.adapter.bindReaderControls();

  assert.equal(registrations.length, 1);
  assert.equal(registrations[0].panel, controls.drawer);
  assert.equal(registrations[0].toggle, controls.toggle);
  assert.equal(registrations[0].mobileToggle, controls.mobileToggle);
});

test('invalidating a PDF search stops stale extraction before later pages', async () => {
  const harness = createHarness({ pages: 2, deferText: [1] });
  const search = harness.adapter.search('alpha');
  await harness.flush();

  harness.adapter.cancelSearch();
  harness.textRequests[0].resolve({ items: [{ str: 'alpha' }] });

  assert.deepEqual(await search, []);
  assert.equal(harness.textRequests.filter((request) => request.pageNumber === 2).length, 0);
});

test('clearing a PDF search invalidates an in-flight extraction', async () => {
  const harness = createHarness({ pages: 2, deferText: [1] });
  const search = harness.adapter.search('alpha');
  await harness.flush();

  assert.deepEqual(await harness.adapter.search(''), []);
  harness.textRequests[0].resolve({ items: [{ str: 'alpha' }] });

  assert.deepEqual(await search, []);
});

test('closing the shared PDF drawer invalidates an in-flight extraction', async () => {
  let registration = null;
  const controller = {
    register(options) {
      registration = options;
      return { open() {}, close() { options.onClose(); } };
    },
  };
  const harness = createHarness({ pages: 2, deferText: [1], drawerController: controller });
  harness.installReaderControls();
  harness.window.EpubReaderDrawers = controller;
  harness.adapter.bindReaderControls();
  const search = harness.adapter.search('alpha');
  await harness.flush();

  registration.onClose();
  harness.textRequests[0].resolve({ items: [{ str: 'alpha' }] });

  assert.deepEqual(await search, []);
});

test('shows an accessible localized error when PDF search extraction fails', async () => {
  const registrations = [];
  const controller = {
    register(options) {
      registrations.push(options);
      return {
        open() { options.panel.classList.add('active'); },
        close() { options.panel.classList.remove('active'); options.onClose(); },
      };
    },
  };
  const harness = createHarness({ drawerController: controller, textError: true });
  const controls = harness.installReaderControls();
  harness.window.EpubReaderDrawers = controller;
  harness.adapter.bindReaderControls();
  controls.toggle.click();
  controls.input.value = 'alpha';
  controls.form.dispatchEvent({ type: 'submit', preventDefault() {} });
  await harness.flush();

  assert.equal(controls.results.children.length, 1);
  assert.equal(controls.results.children[0].getAttribute('role'), 'alert');
  assert.equal(controls.results.children[0].textContent, 'translated:pdf.searchFailed');
});

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

test('loads one local PDF.js document with recovery enabled for imperfect PDFs', async () => {
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
    stopAtErrors: false,
    disableRange: false,
    disableStream: true,
    disableAutoFetch: true,
    rangeChunkSize: 65536,
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
  assert.equal(node.children.some((child) => child.className === 'pdf-page-status'), false);
});

test('keeps a visible loading status over the paper until PDF.js finishes painting', async () => {
  const harness = createHarness({ pendingRender: true });
  const node = harness.page(2);
  harness.document.appendChild(node);

  harness.adapter.renderWithin(harness.document);
  await harness.flush();

  const status = node.children.find((child) => child.className === 'pdf-page-status');
  assert.equal(node.getAttribute('aria-busy'), 'true');
  assert.equal(node.children.some((child) => child.className === 'pdf-page-canvas'), true);
  assert.equal(status.getAttribute('data-pdf-status'), 'loading');
  assert.equal(status.textContent, 'translated:pdf.loadingPage');
});

test('restores the PDF text layer viewport after PDF.js sizing for physical pointer selection', async () => {
  const harness = createHarness({ textLayerOverwritesSize: true });
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  const canvas = node.children.find((child) => child.className === 'pdf-page-canvas');
  const text = node.children.find((child) => child.className.includes('pdf-page-text-layer'));
  assert.equal(text.style.width, canvas.style.width);
  assert.equal(text.style.height, canvas.style.height);
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
  assert.equal(node.style.aspectRatio, 'auto');
  assert.equal(node.style.width, '675px');
});

test('rendered page owns its exact canvas box instead of retaining a stale width-ratio placeholder', async () => {
  const harness = createHarness({ config: { zoom: 0.5, fit: 'width' } });
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  const canvas = node.children.find((child) => child.className === 'pdf-page-canvas');
  assert.equal(canvas.style.width, '200px');
  assert.equal(canvas.style.height, '300px');
  assert.equal(node.style.width, canvas.style.width);
  assert.equal(node.style.height, canvas.style.height);
  assert.equal(node.style.minHeight, canvas.style.height);
  assert.equal(node.style.aspectRatio, 'auto');
});

test('fit actions reset custom zoom while zoom actions clear both fit active states', async () => {
  const harness = createHarness({ innerHeight: 350, config: { zoom: 1.5, fit: 'width' } });
  harness.installReaderControls();
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);
  await harness.adapter.renderWithin(harness.document);

  await harness.adapter.fitPage();
  assert.ok(harness.renderCalls.at(-1).params.viewport.height <= 243);
  assert.equal(harness.document.getElementById('pdfFitPage').getAttribute('aria-pressed'), 'true');

  await harness.adapter.zoomIn();
  assert.equal(harness.document.getElementById('pdfFitPage').getAttribute('aria-pressed'), 'false');
  assert.equal(harness.document.getElementById('pdfFitWidth').getAttribute('aria-pressed'), 'false');

  await harness.adapter.fitWidth();
  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 400);
  assert.equal(harness.document.getElementById('pdfFitWidth').getAttribute('aria-pressed'), 'true');
});

test('fit width measures the reader stage after fit page has made the paper narrower', async () => {
  const harness = createHarness({ innerHeight: 350, config: { fit: 'page' } });
  harness.installReaderControls();
  const stage = harness.document.createElement('article');
  stage.setAttribute('id', 'eb-content');
  stage.clientWidth = 500;
  const node = harness.page(1);
  node.clientWidth = 200;
  stage.appendChild(node);
  harness.document.appendChild(stage);

  await harness.adapter.renderWithin(harness.document);
  await harness.adapter.fitWidth();

  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 500);
});

test('large zoom is based on the fixed outer PDF stage instead of expanding the page layout', async () => {
  const harness = createHarness({ config: { zoom: 4, fit: 'width' } });
  const stage = harness.document.createElement('main');
  stage.classList.add('eb-content-container');
  stage.clientWidth = 500;
  const content = harness.document.createElement('article');
  content.setAttribute('id', 'eb-content');
  content.clientWidth = 900;
  const node = harness.page(1);
  content.appendChild(node);
  stage.appendChild(content);
  harness.document.appendChild(stage);

  await harness.adapter.renderWithin(harness.document);

  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 2000);
});

test('fit width uses the PDF stage content box without creating padding overflow', async () => {
  const harness = createHarness({ config: { fit: 'width' }, stagePadding: 20 });
  const stage = harness.document.createElement('main');
  stage.classList.add('eb-content-container');
  stage.clientWidth = 500;
  const content = harness.document.createElement('article');
  content.setAttribute('id', 'eb-content');
  const node = harness.page(1);
  content.appendChild(node);
  stage.appendChild(content);
  harness.document.appendChild(stage);

  await harness.adapter.renderWithin(harness.document);

  assert.ok(Math.abs(harness.renderCalls.at(-1).params.viewport.width - 460) < 0.001);
});

test('continuous page gap follows rendered paper width within a restrained range', async () => {
  const harness = createHarness({ config: { zoom: 2, fit: 'width' } });
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  assert.equal(harness.document.documentElement.style['--pdf-page-gap'], '12px');
});

test('PDF page-width presets top out at the reader stage instead of overflowing it', async () => {
  const harness = createHarness({ config: { fit: 'width' } });
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);
  await harness.adapter.renderWithin(harness.document);

  await harness.adapter.setPageWidthPreset('4');
  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 400);
  await harness.adapter.setPageWidthPreset('1');
  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 240);
});

test('PDF custom page width accepts an exact percentage and clamps unsafe values', async () => {
  const harness = createHarness({ config: { fit: 'page' } });
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);
  await harness.adapter.renderWithin(harness.document);

  await harness.adapter.setZoomPercent(137);
  assert.equal(harness.adapter.getZoomPercent(), 137);
  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 548);

  await harness.adapter.setZoomPercent(999);
  assert.equal(harness.adapter.getZoomPercent(), 400);
  assert.equal(harness.renderCalls.at(-1).params.viewport.width, 1600);
});

test('fit page uses the visible reader viewport while fit width fills the canvas', async () => {
  const harness = createHarness({ innerHeight: 350, config: { fit: 'width' } });
  harness.installReaderControls();
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);
  const widthViewport = harness.renderCalls.at(-1).params.viewport;
  await harness.adapter.fitPage();
  const pageViewport = harness.renderCalls.at(-1).params.viewport;
  assert.equal(harness.document.getElementById('pdfFitPage').getAttribute('aria-pressed'), 'true');
  assert.equal(harness.document.getElementById('pdfFitWidth').getAttribute('aria-pressed'), 'false');
  const pageCanvas = node.children.find((child) => child.className === 'pdf-page-canvas');
  const pageTextLayer = node.children.find((child) => child.className.includes('pdf-page-text-layer'));
  assert.equal(pageCanvas.style.marginLeft, '0px');
  assert.equal(node.style.width, pageCanvas.style.width);
  assert.equal(pageTextLayer.style.left, pageCanvas.style.marginLeft);
  await harness.adapter.fitWidth();
  const restoredWidthViewport = harness.renderCalls.at(-1).params.viewport;
  const widthCanvas = node.children.find((child) => child.className === 'pdf-page-canvas');
  assert.equal(harness.document.getElementById('pdfFitPage').getAttribute('aria-pressed'), 'false');
  assert.equal(harness.document.getElementById('pdfFitWidth').getAttribute('aria-pressed'), 'true');

  assert.equal(widthViewport.width, 400);
  assert.equal(restoredWidthViewport.width, 400);
  assert.ok(pageViewport.width < widthViewport.width);
  assert.ok(pageViewport.height <= 243);
  assert.equal(widthCanvas.style.marginLeft, '0px');
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

test('sizes lazy placeholders from the active PDF width preset before painting', async () => {
  const harness = createHarness({ lazy: true, config: { zoom: 0.6, fit: 'width' } });
  const node = harness.page(1);
  node.clientWidth = 400;
  harness.document.appendChild(node);

  await harness.adapter.renderWithin(harness.document);

  assert.equal(harness.renderCalls.length, 0);
  assert.equal(node.getAttribute('data-pdf-rendered'), 'placeholder');
  assert.equal(node.style.width, '240px');
  assert.equal(node.style.height, '360px');
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
