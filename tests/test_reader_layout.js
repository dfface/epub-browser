const test = require('node:test');
const assert = require('node:assert/strict');

const {
  applyDesktopChapterSidebarAutoHide,
  applyDesktopToolbarAutoHide,
  applyPageWidth,
  allowsReaderNavigationEvent,
  chapterNavigationPresentation,
  continuousChapterPresentation,
  createNavigationBehaviorController,
  getPaginationPageWidth,
  getPaginationScrollLeft,
  paginationWidthChanged,
  initNavigationBehavior,
  normalizeNavigationBehavior,
  normalizePageWidth,
  readingPreferenceEnabled,
  syncChapterTocAvailability,
} = require('../epub_browser/assets/reader-layout.js');

test('PDF chapter navigation localizes page labels and preserves outline markers', () => {
  const translate = (key, params) => key === 'pdf.page' ? `第 ${params.number} 页` : key;
  const presentation = chapterNavigationPresentation({
    title: 'Page 2',
    chapter_index: 1,
    page_label: '2',
    outline_labels: ['Part I', 'Opening'],
  }, true, translate);

  assert.deepEqual(presentation, {
    title: '第 2 页',
    outlineLabels: ['Part I', 'Opening'],
  });
});

test('continuous PDF separators use page semantics while EPUB keeps chapter semantics', () => {
  const translate = (key, params) => `${key}:${params.number}`;

  assert.deepEqual(
    continuousChapterPresentation('Page 3', 2, true, translate),
    { title: 'pdf.page:3', index: 'pdf.page:3' },
  );
  assert.deepEqual(
    continuousChapterPresentation('Chapter title', 2, false, translate),
    { title: 'Chapter title', index: 'reader.chapterNumber:2' },
  );
});

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(value) {
    this.values.add(value);
  }

  remove(...values) {
    values.forEach(value => this.values.delete(value));
  }

  toggle(value, force) {
    if (force === true) {
      this.values.add(value);
      return true;
    }
    if (force === false) {
      this.values.delete(value);
      return false;
    }
    if (this.values.has(value)) {
      this.values.delete(value);
      return false;
    }
    this.values.add(value);
    return true;
  }

  contains(value) {
    return this.values.has(value);
  }
}

test('desktop toolbar auto-hide preference changes only the toolbar presentation state', () => {
  const body = new FakeElement();
  const toolbar = new FakeElement();
  toolbar.setAttribute('aria-hidden', 'false');
  const documentObject = {
    body,
    querySelector(selector) {
      return selector === '.reader-toolbar.top-controls' ? toolbar : null;
    },
  };

  assert.equal(applyDesktopToolbarAutoHide(documentObject, true), true);
  assert.equal(body.classList.contains('desktop-toolbar-auto-hide'), true);
  assert.equal(toolbar.getAttribute('aria-hidden'), 'false');

  assert.equal(applyDesktopToolbarAutoHide(documentObject, false), false);
  assert.equal(body.classList.contains('desktop-toolbar-auto-hide'), false);
  assert.equal(toolbar.getAttribute('aria-hidden'), 'false');
});

test('chapter sidebar auto-hide only activates while the desktop sidebar is shown', () => {
  const body = new FakeElement();
  const toggle = new FakeElement();
  const documentObject = {
    body,
    getElementById(id) {
      return id === 'autoHideDesktopChapterSidebarToggle' ? toggle : null;
    },
  };

  assert.equal(applyDesktopChapterSidebarAutoHide(documentObject, false, true), false);
  assert.equal(body.classList.contains('desktop-chapter-sidebar-auto-hide'), false);
  assert.equal(toggle.disabled, true);
  assert.equal(toggle.getAttribute('aria-disabled'), 'true');

  assert.equal(applyDesktopChapterSidebarAutoHide(documentObject, true, true), true);
  assert.equal(body.classList.contains('desktop-chapter-sidebar-auto-hide'), true);
  assert.equal(toggle.disabled, false);
  assert.equal(toggle.getAttribute('aria-disabled'), 'false');

  assert.equal(applyDesktopChapterSidebarAutoHide(documentObject, true, false), false);
  assert.equal(body.classList.contains('desktop-chapter-sidebar-auto-hide'), false);
});

class FakeElement {
  constructor() {
    this.attributes = new Map();
    this.classList = new FakeClassList();
    this.disabled = false;
    this.hidden = false;
    this.listeners = new Map();
    this.style = {
      values: new Map(),
      setProperty: (name, value) => this.style.values.set(name, value),
    };
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  contains(element) {
    return element === this.focusedChild;
  }

  getBoundingClientRect() {
    return { height: 68 };
  }
}

function fakeDocument() {
  const elements = {
    tocToggle: new FakeElement(),
    mobileTocBtn: new FakeElement(),
    tocFloating: new FakeElement(),
  };
  elements.tocToggle.classList.add('active');
  elements.mobileTocBtn.classList.add('active');
  elements.tocFloating.classList.add('active');
  return {
    elements,
    getElementById(id) {
      return elements[id] || null;
    },
  };
}

test('normalizes page-width presets and applies their exact reading width', () => {
  const properties = new Map();
  const root = {
    style: {
      setProperty(name, value) {
        properties.set(name, value);
      },
    },
    setAttribute(name, value) {
      this[name] = value;
    },
  };

  assert.equal(normalizePageWidth('1'), '1');
  assert.equal(normalizePageWidth('4'), '4');
  assert.equal(normalizePageWidth('invalid'), '3');
  assert.equal(applyPageWidth(root, '2'), '2');
  assert.equal(properties.get('--reader-page-width'), '820px');
  assert.equal(root['data-reader-page-width'], '2');
});

test('pagination keeps the container fractional width as its page stride', () => {
  const container = {
    clientWidth: 786,
    getBoundingClientRect() {
      return { width: 787.1953125 };
    },
  };

  assert.equal(getPaginationPageWidth(container), 787.1953125);
  assert.equal(getPaginationScrollLeft(11, getPaginationPageWidth(container)), 8659);
});

test('pagination refreshes only when the canvas width has materially settled', () => {
  assert.equal(paginationWidthChanged(786.96875, 787.1953125), true);
  assert.equal(paginationWidthChanged(787.1953125, 787.1953125), false);
  assert.equal(paginationWidthChanged(787.1953125, 787.2), false);
});

test('continuous reading hides and closes both chapter-local TOC controls', () => {
  const document = fakeDocument();

  syncChapterTocAvailability(document, true);

  for (const id of ['tocToggle', 'mobileTocBtn']) {
    assert.equal(document.elements[id].disabled, true);
    assert.equal(document.elements[id].hidden, true);
    assert.equal(document.elements[id].getAttribute('aria-disabled'), 'true');
    assert.equal(document.elements[id].getAttribute('aria-expanded'), 'false');
    assert.equal(document.elements[id].classList.contains('active'), false);
  }
  assert.equal(document.elements.tocFloating.classList.contains('active'), false);
  assert.equal(document.elements.tocFloating.getAttribute('aria-hidden'), 'true');

  syncChapterTocAvailability(document, false);
  for (const id of ['tocToggle', 'mobileTocBtn']) {
    assert.equal(document.elements[id].disabled, false);
    assert.equal(document.elements[id].hidden, false);
    assert.equal(document.elements[id].getAttribute('aria-disabled'), 'false');
  }
});

test('PDF pages hide the empty chapter-local TOC in every reading mode without changing EPUB ordinary mode', () => {
  const pdfDocument = fakeDocument();
  syncChapterTocAvailability(pdfDocument, false, true);
  for (const id of ['tocToggle', 'mobileTocBtn']) {
    assert.equal(pdfDocument.elements[id].disabled, true);
    assert.equal(pdfDocument.elements[id].hidden, true);
    assert.equal(pdfDocument.elements[id].getAttribute('aria-disabled'), 'true');
    assert.equal(pdfDocument.elements[id].getAttribute('aria-hidden'), 'true');
  }

  const epubDocument = fakeDocument();
  syncChapterTocAvailability(epubDocument, false, false);
  for (const id of ['tocToggle', 'mobileTocBtn']) {
    assert.equal(epubDocument.elements[id].disabled, false);
    assert.equal(epubDocument.elements[id].getAttribute('aria-disabled'), 'false');
  }
});

test('keyboard navigation preferences default on and only explicit false disables them', () => {
  assert.equal(readingPreferenceEnabled(null), true);
  assert.equal(readingPreferenceEnabled(undefined), true);
  assert.equal(readingPreferenceEnabled('true'), true);
  assert.equal(readingPreferenceEnabled('false'), false);
});

test('arrow and Space preferences gate their own keys without gating ArrowDown', () => {
  const event = key => ({ key, target: { tagName: 'DIV' } });

  assert.equal(allowsReaderNavigationEvent(event('ArrowLeft'), false, true), false);
  assert.equal(allowsReaderNavigationEvent(event('ArrowRight'), false, true), false);
  assert.equal(allowsReaderNavigationEvent(event(' '), true, false), false);
  assert.equal(allowsReaderNavigationEvent(event('Space'), true, false), false);
  assert.equal(allowsReaderNavigationEvent(event('ArrowRight'), true, false), true);
  assert.equal(allowsReaderNavigationEvent(event(' '), false, true), true);
  assert.equal(allowsReaderNavigationEvent(event('ArrowDown'), false, false), true);
});

test('reader keyboard navigation ignores editing targets, prevented events, and modifiers', () => {
  const editableTargets = [
    { tagName: 'INPUT' },
    { tagName: 'TEXTAREA', className: 'annotation-note-input' },
    { tagName: 'SELECT' },
    { tagName: 'DIV', isContentEditable: true },
    {
      tagName: 'SPAN',
      getAttribute(name) { return name === 'contenteditable' ? 'plaintext-only' : null; },
    },
  ];
  editableTargets.forEach(target => {
    const event = { key: 'ArrowRight', target, composedPath: () => [target] };
    assert.equal(allowsReaderNavigationEvent(event, true, true), false, target.tagName);
  });

  const editableAncestor = { tagName: 'DIV', isContentEditable: true };
  const nestedTarget = { tagName: 'SPAN' };
  assert.equal(allowsReaderNavigationEvent({
    key: ' ',
    target: nestedTarget,
    composedPath: () => [nestedTarget, editableAncestor],
  }, true, true), false);

  for (const property of ['defaultPrevented', 'altKey', 'ctrlKey', 'metaKey', 'shiftKey']) {
    assert.equal(allowsReaderNavigationEvent({
      key: 'ArrowLeft',
      target: { tagName: 'DIV' },
      [property]: true,
    }, true, true), false, property);
  }
});

test('reader keyboard navigation leaves interactive controls and dialogs alone', () => {
  for (const tagName of ['BUTTON', 'A', 'SUMMARY', 'DIALOG']) {
    const target = { tagName };
    assert.equal(allowsReaderNavigationEvent({
      key: ' ',
      target,
      composedPath: () => [target],
    }, true, true), false, tagName);
  }

  const target = { tagName: 'SPAN' };
  const dialog = {
    tagName: 'DIV',
    getAttribute(name) { return name === 'role' ? 'dialog' : null; },
  };
  assert.equal(allowsReaderNavigationEvent({
    key: 'ArrowRight',
    target,
    composedPath: () => [target, dialog],
  }, true, true), false);
});

test('navigation behavior defaults to normal and persists an explicit choice', () => {
  const values = new Map();
  const header = new FakeElement();
  const root = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: root,
    documentObject: { activeElement: null },
    storage: {
      getItem: key => values.has(key) ? values.get(key) : null,
      setItem: (key, value) => values.set(key, String(value)),
    },
  });

  assert.equal(normalizeNavigationBehavior(null), 'normal');
  assert.equal(normalizeNavigationBehavior('unknown'), 'normal');
  assert.equal(controller.getMode(), 'normal');
  assert.equal(root.getAttribute('data-navigation-behavior'), 'normal');
  assert.deepEqual([...header.classList.values], ['is-navigation-normal']);

  controller.setMode('sticky');
  assert.equal(values.get('navigation_bar_behavior'), 'sticky');
  assert.equal(root.getAttribute('data-navigation-behavior'), 'sticky');
  assert.deepEqual([...header.classList.values], ['is-navigation-sticky']);

  controller.setMode('auto-hide');
  assert.deepEqual([...header.classList.values], ['is-navigation-auto-hide']);

  controller.setMode('normal');
  assert.deepEqual([...header.classList.values], ['is-navigation-normal']);
});

test('auto-hide seeds direction tracking from a restored scroll position', () => {
  const header = new FakeElement();
  const root = new FakeElement();
  const documentObject = { activeElement: null };
  const controller = createNavigationBehaviorController({
    header,
    rootElement: root,
    documentObject,
    initialScrollY: 500,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(497);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  controller.handleScroll(494);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('navigation bootstrap seeds restored window scroll before the first event', () => {
  const header = new FakeElement();
  const rootElement = new FakeElement();
  rootElement.scrollTop = 500;
  const documentObject = {
    activeElement: null,
    documentElement: rootElement,
    getElementById() { return null; },
    querySelector(selector) { return selector === '.app-header' ? header : null; },
    querySelectorAll() { return []; },
  };
  const rootListeners = new Map();
  const root = {
    document: documentObject,
    localStorage: { getItem: () => 'auto-hide', setItem() {} },
    pageYOffset: 500,
    addEventListener(type, listener) { rootListeners.set(type, listener); },
    requestAnimationFrame(callback) { callback(); },
  };

  initNavigationBehavior(root);
  root.pageYOffset = 497;
  rootListeners.get('scroll')();

  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('auto-hide accumulates slow motion in both directions', () => {
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: 100,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(103);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  controller.handleScroll(106);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);

  controller.handleScroll(103);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
  controller.handleScroll(100);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('auto-hide resets accumulated motion when scroll direction reverses', () => {
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: 100,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(103);
  controller.handleScroll(101);
  controller.handleScroll(104);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  controller.handleScroll(107);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
});

test('auto-hide always reveals within the header top zone', () => {
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: 70,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(76);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
  controller.handleScroll(72);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
  controller.handleScroll(68);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});

test('focus and an expanded locale popup reset motion and keep navigation visible', () => {
  const header = new FakeElement();
  const localeToggle = new FakeElement();
  const documentObject = {
    activeElement: null,
    getElementById(id) {
      return id === 'localeToggle' ? localeToggle : null;
    },
  };
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject,
    initialScrollY: 100,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(103);
  header.focusedChild = {};
  documentObject.activeElement = header.focusedChild;
  controller.handleScroll(106);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  documentObject.activeElement = null;
  controller.handleScroll(109);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  localeToggle.setAttribute('aria-expanded', 'true');
  controller.handleScroll(112);
  controller.handleScroll(115);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  localeToggle.setAttribute('aria-expanded', 'false');
  controller.handleScroll(118);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  controller.handleScroll(121);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
});

test('mode changes reset motion at the current non-zero scroll position', () => {
  let scrollY = 200;
  const header = new FakeElement();
  const controller = createNavigationBehaviorController({
    header,
    rootElement: new FakeElement(),
    documentObject: { activeElement: null },
    initialScrollY: scrollY,
    getScrollY: () => scrollY,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  scrollY = 203;
  controller.handleScroll(scrollY);
  controller.setMode('sticky');
  controller.setMode('auto-hide');

  scrollY = 206;
  controller.handleScroll(scrollY);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
  scrollY = 209;
  controller.handleScroll(scrollY);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);
});
