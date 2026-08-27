const test = require('node:test');
const assert = require('node:assert/strict');

const localeNavigation = require('../epub_browser/assets/locale-nav.js');

class FakeEventTarget {
  constructor() {
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(listener);
  }

  dispatchEvent(event) {
    if (!event.target) event.target = this;
    (this.listeners.get(event.type) || []).forEach(listener => listener.call(this, event));
    if (event.bubbles && this.parentNode) this.parentNode.dispatchEvent(event);
  }
}

class FakeElement extends FakeEventTarget {
  constructor(documentObject, tagName) {
    super();
    this.ownerDocument = documentObject;
    this.tagName = tagName.toUpperCase();
    this.parentNode = null;
    this.children = [];
    this.attributes = new Map();
    this.dataset = {};
    this.style = {};
    this.tabIndex = 0;
    this.textContent = '';
    this.value = '';
  }

  set innerHTML(value) {
    assert.equal(value, '');
    const focused = this.ownerDocument.activeElement;
    if (focused && this.contains(focused)) {
      this.ownerDocument.activeElement = this.ownerDocument.body;
      focused.dispatchEvent({
        type: 'focusout',
        target: focused,
        relatedTarget: this.ownerDocument.body,
        bubbles: true,
      });
    }
    this.children.forEach(child => { child.parentNode = null; });
    this.children = [];
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
    if (name === 'id') this.ownerDocument.elements.set(String(value), this);
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  contains(target) {
    return target === this || this.children.some(child => child.contains && child.contains(target));
  }

  querySelectorAll(selector) {
    const matches = [];
    function visit(node) {
      if (selector === '[role="menuitemradio"]' && node.getAttribute && node.getAttribute('role') === 'menuitemradio') {
        matches.push(node);
      } else if (selector === '[aria-checked="true"]' && node.getAttribute && node.getAttribute('aria-checked') === 'true') {
        matches.push(node);
      }
      (node.children || []).forEach(visit);
    }
    this.children.forEach(visit);
    return matches;
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  focus() {
    const previous = this.ownerDocument.activeElement;
    if (previous === this) return;
    this.ownerDocument.activeElement = this;
    if (previous) {
      previous.dispatchEvent({
        type: 'focusout',
        target: previous,
        relatedTarget: this,
        bubbles: true,
      });
    }
  }

  click() {
    this.dispatchEvent({ type: 'click', target: this, bubbles: true, stopPropagation() {} });
  }

  getBoundingClientRect() {
    return { bottom: 44, right: 900 };
  }
}

class FakeDocument extends FakeEventTarget {
  constructor() {
    super();
    this.elements = new Map();
    this.activeElement = null;
    this.body = new FakeElement(this, 'body');
  }

  createElement(tagName) {
    return new FakeElement(this, tagName);
  }

  createTextNode(text) {
    return {
      textContent: text,
      parentNode: null,
      contains(target) { return target === this; },
    };
  }

  getElementById(id) {
    return this.elements.get(id) || null;
  }
}

function setupLocaleNavigation() {
  assert.equal(
    typeof localeNavigation.createLocaleNavigation,
    'function',
    'locale navigation must expose its real DOM behavior for initialization and testing',
  );
  const documentObject = new FakeDocument();
  const localeToggle = documentObject.createElement('button');
  localeToggle.setAttribute('id', 'localeToggle');
  localeToggle.setAttribute('aria-expanded', 'false');
  const localeSelect = documentObject.createElement('select');
  localeSelect.setAttribute('id', 'localeSelect');
  const localeCurrentLabel = documentObject.createElement('span');
  localeCurrentLabel.setAttribute('id', 'localeCurrentLabel');
  const external = documentObject.createElement('button');
  external.setAttribute('id', 'external');
  documentObject.body.appendChild(localeToggle);
  documentObject.body.appendChild(localeSelect);
  documentObject.body.appendChild(localeCurrentLabel);
  documentObject.body.appendChild(external);

  let locale = 'en';
  const listeners = [];
  const i18n = {
    getLocale: () => locale,
    setLocale(nextLocale) {
      locale = nextLocale;
      listeners.forEach(listener => listener());
    },
    t: key => key === 'common.language' ? 'Language' : key.replace('locale.name.', ''),
    onLocaleChange(listener) { listeners.push(listener); },
  };
  const root = new FakeEventTarget();
  root.document = documentObject;
  root.innerWidth = 1000;
  root.EpubBrowserI18n = i18n;

  localeNavigation.createLocaleNavigation(root);
  const localeMenu = documentObject.getElementById('localeMenu');
  return { documentObject, external, i18n, localeMenu, localeToggle, getLocale: () => locale };
}

function dispatchKey(element, key) {
  let prevented = false;
  element.dispatchEvent({
    type: 'keydown',
    key,
    target: element,
    bubbles: true,
    preventDefault() { prevented = true; },
  });
  return prevented;
}

test('locale popup opens on the selected roving item and arrows wrap', () => {
  const { documentObject, localeMenu, localeToggle } = setupLocaleNavigation();

  localeToggle.click();
  let items = localeMenu.querySelectorAll('[role="menuitemradio"]');
  assert.equal(localeToggle.getAttribute('aria-controls'), 'localeMenu');
  assert.equal(localeToggle.getAttribute('aria-expanded'), 'true');
  assert.equal(documentObject.activeElement, items[0]);
  assert.deepEqual(items.map(item => item.tabIndex), [0].concat(Array(16).fill(-1)));

  assert.equal(dispatchKey(documentObject.activeElement, 'ArrowUp'), true);
  items = localeMenu.querySelectorAll('[role="menuitemradio"]');
  assert.equal(documentObject.activeElement, items[16]);
  assert.deepEqual(items.map(item => item.tabIndex), Array(16).fill(-1).concat([0]));

  dispatchKey(documentObject.activeElement, 'ArrowDown');
  assert.equal(documentObject.activeElement, items[0]);
});

test('locale popup selects with keyboard and Escape restores the trigger', () => {
  const { documentObject, getLocale, localeMenu, localeToggle } = setupLocaleNavigation();

  localeToggle.click();
  dispatchKey(documentObject.activeElement, 'ArrowUp');
  assert.equal(dispatchKey(documentObject.activeElement, ' '), true);
  assert.equal(getLocale(), 'ms');
  assert.equal(localeToggle.getAttribute('aria-expanded'), 'false');
  assert.equal(documentObject.activeElement, localeToggle);

  localeToggle.click();
  assert.equal(documentObject.activeElement.getAttribute('aria-checked'), 'true');
  assert.equal(dispatchKey(documentObject.activeElement, 'Escape'), true);
  assert.equal(localeMenu.style.display, 'none');
  assert.equal(documentObject.activeElement, localeToggle);
});

test('locale popup closes on Tab focus-out without stealing the next focus', () => {
  const { documentObject, external, localeMenu, localeToggle } = setupLocaleNavigation();

  localeToggle.click();
  dispatchKey(documentObject.activeElement, 'Tab');
  external.focus();

  assert.equal(localeMenu.style.display, 'none');
  assert.equal(localeToggle.getAttribute('aria-expanded'), 'false');
  assert.equal(documentObject.activeElement, external);
});

test('locale changes rerender the open popup and focus the new selected item', () => {
  const { documentObject, i18n, localeMenu, localeToggle } = setupLocaleNavigation();

  localeToggle.click();
  i18n.setLocale('zh-TW');

  const items = localeMenu.querySelectorAll('[role="menuitemradio"]');
  assert.equal(localeMenu.style.display, 'block');
  assert.equal(items.filter(item => item.getAttribute('aria-checked') === 'true').length, 1);
  assert.equal(items[2].getAttribute('aria-checked'), 'true');
  assert.equal(items[2].tabIndex, 0);
  assert.equal(documentObject.activeElement, items[2]);

  dispatchKey(documentObject.activeElement, 'Enter');
  assert.equal(localeToggle.getAttribute('aria-expanded'), 'false');
});
