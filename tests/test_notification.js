const test = require('node:test');
const assert = require('node:assert/strict');
const NotificationModule = require('../epub_browser/assets/notification.js');

function element(tagName) {
  const classes = [];
  return {
    tagName,
    parentNode: null,
    attributes: {},
    textContent: '',
    className: '',
    classList: {
      add(value) { if (!classes.includes(value)) classes.push(value); },
      contains(value) { return classes.includes(value); },
    },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

function fakeRoot() {
  const timers = [];
  const body = {
    children: [],
    appendChild(node) {
      node.parentNode = this;
      this.children.push(node);
    },
    removeChild(node) {
      this.children = this.children.filter(child => child !== node);
      node.parentNode = null;
    },
  };
  return {
    document: { body, createElement: element },
    setTimeout(callback, delay) {
      timers.push({ callback, delay, cancelled: false });
      return timers.length;
    },
    clearTimeout(id) {
      if (timers[id - 1]) timers[id - 1].cancelled = true;
    },
    timers,
  };
}

test('standard notification replaces the active toast and preserves accessibility semantics', () => {
  const root = fakeRoot();
  const notifications = NotificationModule.create(root);

  const first = notifications.show('Saved', 'success');
  const second = notifications.show('Denied', 'error', { persistent: true });

  assert.equal(root.document.body.children.length, 1);
  assert.equal(root.document.body.children[0], second);
  assert.equal(first.parentNode, null);
  assert.equal(second.className, 'custom-css-notification error');
  assert.equal(second.attributes.role, 'alert');
  assert.equal(second.attributes['aria-live'], 'assertive');
  assert.equal(second.textContent, 'Denied');
});

test('standard notification uses the shared default type and auto-dismiss lifecycle', () => {
  const root = fakeRoot();
  const notifications = NotificationModule.create(root);
  const toast = notifications.show('Working');

  assert.equal(toast.className, 'custom-css-notification info');
  assert.equal(root.timers[0].delay, 3000);
  root.timers[0].callback();
  assert.equal(toast.classList.contains('fade-out'), true);
  assert.equal(root.timers[1].delay, 300);
  root.timers[1].callback();
  assert.equal(root.document.body.children.length, 0);
});
