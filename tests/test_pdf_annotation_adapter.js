'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
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
  getBoundingClientRect() { return { width: this.clientWidth, height: this.clientHeight }; }
  getContext() { return {}; }
  querySelectorAll(selector) {
    const matches = [];
    const visit = node => {
      if (selector === '[data-pdf-page-number]' && node.hasAttribute('data-pdf-page-number')) matches.push(node);
      node.children.forEach(visit);
    };
    this.children.forEach(visit);
    return matches;
  }
}

function pdfAnnotationHarness({ pageNumber = 3 } = {}) {
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
  page.setAttribute('data-pdf-has-extractable-text', 'true');
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
              render() { return { promise: Promise.resolve() }; },
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
  assert.equal(harness.page.querySelectorAll('.pdf-selection-menu').length, 0);
});
