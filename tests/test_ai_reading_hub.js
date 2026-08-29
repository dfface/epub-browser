const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

class FakeElement {
  constructor(tagName = 'div') {
    this.tagName = tagName.toUpperCase();
    this.attributes = new Map();
    this.children = [];
    this.className = '';
    this.dataset = {};
    this.parentNode = null;
    this._textContent = '';
    this.textContentWrites = 0;
  }

  set textContent(value) {
    this._textContent = String(value);
    this.textContentWrites += 1;
  }

  get textContent() {
    return this._textContent;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  remove() {
    if (!this.parentNode) return;
    this.parentNode.children = this.parentNode.children.filter(child => child !== this);
    this.parentNode = null;
  }

  addEventListener() {}

  querySelector(selector) {
    if (selector === '.chapter-title' || selector === '.chapter-title-with-sync') return null;
    if (selector === 'a[data-chapter-index]') {
      return this.children.find(child => child.tagName === 'A' && child.getAttribute('data-chapter-index') !== null) || null;
    }
    if (selector.startsWith('.')) {
      const className = selector.slice(1);
      return this.children.find(child => child.className.split(/\s+/).includes(className)) || null;
    }
    return null;
  }

  querySelectorAll(selector) {
    if (selector === '[data-chapter-index]') {
      return this.children.filter(child => child.getAttribute('data-chapter-index') !== null);
    }
    return [];
  }

  closest(selector) {
    if (selector !== '[data-ai-reading-indicators]') return null;
    let node = this;
    while (node) {
      if (node.getAttribute('data-ai-reading-indicators') !== null) return node;
      node = node.parentNode;
    }
    return null;
  }
}

function createHarness({ locale, resultsByLanguage, containerCount = 1 }) {
  let activeLocale = locale;
  let localeChangeListener = null;
  const chapterLinks = [];
  const indicatorContainers = [];
  for (let index = 0; index < containerCount; index += 1) {
    const chapterLink = new FakeElement('a');
    chapterLink.setAttribute('data-chapter-index', '3');
    chapterLinks.push(chapterLink);

    const indicatorContainer = new FakeElement('nav');
    indicatorContainer.setAttribute('data-ai-reading-indicators', '');
    indicatorContainer.setAttribute('data-book-id', 'book-1');
    indicatorContainer.appendChild(chapterLink);
    indicatorContainers.push(indicatorContainer);
  }

  const documentElement = new FakeElement('html');
  documentElement.lang = locale;
  const document = {
    readyState: 'complete',
    documentElement,
    createElement(tagName) {
      return new FakeElement(tagName);
    },
    querySelectorAll(selector) {
      if (selector === '[data-ai-reading-hub]') return [];
      if (selector === '[data-ai-reading-indicators]') return indicatorContainers;
      return [];
    },
    addEventListener() {},
  };
  const requested = [];
  const window = {
    document,
    EpubBrowserI18n: {
      getLocale() { return activeLocale; },
      t(key) { return `${activeLocale}:${key}`; },
      onLocaleChange(listener) { localeChangeListener = listener; },
    },
    EpubBrowserAuth: {
      fetch(url) {
        requested.push(url);
        const match = /[?&]language=([^&]+)/.exec(url);
        const results = match
          ? (resultsByLanguage[decodeURIComponent(match[1])] || [])
          : Object.values(resultsByLanguage).flat();
        return Promise.resolve({
          ok: true,
          json() { return Promise.resolve({ results }); },
        });
      },
    },
    EpubBrowserURL: { publicPath(value) { return value; } },
  };

  vm.runInNewContext(
    fs.readFileSync('epub_browser/assets/ai-reading-hub.js', 'utf8'),
    { window, document, Promise, Error, Intl, Date, Number, Array, Object, String, encodeURIComponent },
  );

  return {
    chapterLink: chapterLinks[0],
    chapterLinks,
    requested,
    refreshChapterIndicators() {
      window.EpubBrowserAIReadingHub.refreshChapterIndicators(chapterLinks[0]);
    },
    setLocale(nextLocale) {
      activeLocale = nextLocale;
      if (localeChangeListener) localeChangeListener(nextLocale);
    },
  };
}

function completeResult(overrides = {}) {
  return Object.assign({
    id: 'result-zh',
    book_id: 'book-1',
    chapter_index: 3,
    chapter_title: '第四章',
    scope: 'chapter',
    mode: 'chapter',
    profile: 'general',
    language: 'zh-CN',
    content: { quick: { title: '本章导读', summary: '摘要' } },
    created_at: '2026-08-26 10:17:00',
    template_version: 12,
    config_revision: 2,
    can_delete: false,
  }, overrides);
}

test('does not mark a chapter when AI readings exist only in another language', async () => {
  const harness = createHarness({
    locale: 'en',
    resultsByLanguage: { 'zh-CN': [completeResult()] },
  });

  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(harness.requested, [
    '/api/ai/books/book-1/results?language=en&view=indicators',
  ]);
  assert.equal(harness.chapterLink.querySelector('.ai-reading-chapter-badge'), null);
});

test('refreshes chapter markers when the interface language changes', async () => {
  const harness = createHarness({
    locale: 'zh-CN',
    resultsByLanguage: { 'zh-CN': [completeResult()] },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.notEqual(harness.chapterLink.querySelector('.ai-reading-chapter-badge'), null);

  harness.setLocale('en');
  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(harness.requested, [
    '/api/ai/books/book-1/results?language=zh-CN&view=indicators',
    '/api/ai/books/book-1/results?language=en&view=indicators',
  ]);
  assert.equal(harness.chapterLink.querySelector('.ai-reading-chapter-badge'), null);
});

test('relabels a chapter marker when both languages have AI readings', async () => {
  const harness = createHarness({
    locale: 'zh-CN',
    resultsByLanguage: {
      en: [completeResult({ id: 'result-en', language: 'en' })],
      'zh-CN': [completeResult()],
    },
  });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(
    harness.chapterLink.querySelector('.ai-reading-chapter-badge').getAttribute('title'),
    'zh-CN:ai.library',
  );

  harness.setLocale('en');
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(
    harness.chapterLink.querySelector('.ai-reading-chapter-badge').getAttribute('title'),
    'en:ai.library',
  );
});

test('a repeated refresh does not rewrite an unchanged chapter marker', async () => {
  const harness = createHarness({
    locale: 'zh-CN',
    resultsByLanguage: { 'zh-CN': [completeResult()] },
  });
  await new Promise(resolve => setImmediate(resolve));
  const badge = harness.chapterLink.querySelector('.ai-reading-chapter-badge');
  const label = badge.querySelector('.ai-reading-chapter-label');
  const writesAfterCreation = label.textContentWrites;

  harness.refreshChapterIndicators();
  await new Promise(resolve => setImmediate(resolve));

  assert.equal(label.textContentWrites, writesAfterCreation);
});

test('deduplicates one language-scoped result request across multiple TOCs', async () => {
  const harness = createHarness({
    locale: 'zh-CN',
    resultsByLanguage: { 'zh-CN': [completeResult()] },
    containerCount: 2,
  });

  await new Promise(resolve => setImmediate(resolve));

  assert.deepEqual(harness.requested, [
    '/api/ai/books/book-1/results?language=zh-CN&view=indicators',
  ]);
  assert.equal(
    harness.chapterLinks.every(link => link.querySelector('.ai-reading-chapter-badge') !== null),
    true,
  );
});
