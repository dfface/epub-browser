const test = require('node:test');
const assert = require('node:assert/strict');

function fakeDocument() {
  const listeners = {};
  const document = {
    activeElement: null,
    createElement(tagName) {
      const node = {
        tagName: String(tagName).toUpperCase(),
        children: [],
        listeners: {},
        attributes: {},
        disabled: false,
        appendChild(child) { this.children.push(child); child.parentNode = this; return child; },
        setAttribute(name, value) { this.attributes[name] = String(value); },
        addEventListener(type, listener) { this.listeners[type] = listener; },
        remove() {
          if (!this.parentNode) return;
          this.parentNode.children = this.parentNode.children.filter(child => child !== this);
        },
        focus() { if (!this.disabled) document.activeElement = this; },
        select() {},
      };
      return node;
    },
    body: null,
    addEventListener(type, listener) { listeners[type] = listener; },
    removeEventListener(type, listener) { if (listeners[type] === listener) delete listeners[type]; },
  };
  document.body = document.createElement('body');
  return document;
}

function loadDialog(document) {
  global.document = document;
  delete global.EpubDialog;
  delete require.cache[require.resolve('../epub_browser/assets/dialog.js')];
  require('../epub_browser/assets/dialog.js');
  return global.EpubDialog;
}

test('destructive confirmation focuses Cancel and restores a temporarily disabled trigger', async () => {
  const document = fakeDocument();
  const trigger = document.createElement('button');
  document.body.appendChild(trigger);
  trigger.focus();
  const dialog = loadDialog(document);
  const result = dialog.confirm({ title: 'Delete', message: 'Delete it?', destructive: true });
  const modal = document.body.children.at(-1);
  const footer = modal.children[1].children.at(-1);
  const cancel = footer.children[0];
  assert.equal(document.activeElement, cancel);

  trigger.disabled = true;
  result.then(() => { trigger.disabled = false; });
  cancel.listeners.click();
  assert.equal(await result, false);
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(document.activeElement, trigger);
});

test('typed destructive confirmation renders semantic details and requires an exact value', async () => {
  const document = fakeDocument();
  const dialog = loadDialog(document);
  const pending = dialog.prompt({
    title: 'Delete reader',
    message: 'The following data will be deleted.',
    details: ['2 sessions', '4 annotations'],
    inputLabel: 'Type reader to confirm',
    expectedValue: 'reader',
    destructive: true,
  });
  const modal = document.body.children.at(-1);
  const content = modal.children[1];
  const details = content.children.find(node => node.tagName === 'UL');
  const input = content.children.find(node => node.tagName === 'INPUT');
  const footer = content.children.at(-1);
  const confirm = footer.children[1];

  assert.deepEqual(details.children.map(node => node.textContent), [
    '2 sessions', '4 annotations'
  ]);
  assert.equal(confirm.disabled, true);
  input.value = 'Reader';
  input.listeners.input();
  assert.equal(confirm.disabled, true);
  input.value = 'reader';
  input.listeners.input();
  assert.equal(confirm.disabled, false);
  confirm.listeners.click();
  assert.equal(await pending, 'reader');
});
