const test = require('node:test');
const assert = require('node:assert/strict');

const {
  applyPageWidth,
  createNavigationBehaviorController,
  normalizeNavigationBehavior,
  normalizePageWidth,
  syncChapterTocAvailability,
} = require('../epub_browser/assets/reader-layout.js');

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(value) {
    this.values.add(value);
  }

  remove(value) {
    this.values.delete(value);
  }

  contains(value) {
    return this.values.has(value);
  }
}

class FakeElement {
  constructor() {
    this.attributes = new Map();
    this.classList = new FakeClassList();
    this.disabled = false;
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

test('continuous reading disables and closes both chapter-local TOC controls', () => {
  const document = fakeDocument();

  syncChapterTocAvailability(document, true);

  for (const id of ['tocToggle', 'mobileTocBtn']) {
    assert.equal(document.elements[id].disabled, true);
    assert.equal(document.elements[id].getAttribute('aria-disabled'), 'true');
    assert.equal(document.elements[id].getAttribute('aria-expanded'), 'false');
    assert.equal(document.elements[id].classList.contains('active'), false);
  }
  assert.equal(document.elements.tocFloating.classList.contains('active'), false);
  assert.equal(document.elements.tocFloating.getAttribute('aria-hidden'), 'true');

  syncChapterTocAvailability(document, false);
  for (const id of ['tocToggle', 'mobileTocBtn']) {
    assert.equal(document.elements[id].disabled, false);
    assert.equal(document.elements[id].getAttribute('aria-disabled'), 'false');
  }
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

  controller.setMode('sticky');
  assert.equal(values.get('navigation_bar_behavior'), 'sticky');
  assert.equal(root.getAttribute('data-navigation-behavior'), 'sticky');
  assert.equal(header.classList.contains('is-navigation-sticky'), true);
});

test('auto-hide navigation hides down, shows up, and stays visible while focused', () => {
  const header = new FakeElement();
  const root = new FakeElement();
  const documentObject = { activeElement: null };
  const controller = createNavigationBehaviorController({
    header,
    rootElement: root,
    documentObject,
    storage: { getItem: () => 'auto-hide', setItem() {} },
  });

  controller.handleScroll(120);
  assert.equal(header.classList.contains('is-navigation-hidden'), true);

  controller.handleScroll(90);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);

  header.focusedChild = {};
  documentObject.activeElement = header.focusedChild;
  controller.handleScroll(180);
  assert.equal(header.classList.contains('is-navigation-hidden'), false);
});
