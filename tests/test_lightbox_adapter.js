'use strict';

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const adapterPath = path.join(
  __dirname,
  '..',
  'epub_browser',
  'assets',
  'lightbox-adapter.js'
);

assert.ok(fs.existsSync(adapterPath), 'the project-owned lightbox adapter must exist');

const source = fs.readFileSync(adapterPath, 'utf8');
const calls = [];
const events = {};
const compatibilityClasses = [];
const instance = {
  reloadCount: 0,
  reload() {
    this.reloadCount += 1;
  },
  on(name, callback) {
    events[name] = callback;
  },
};
const context = {
  document: {
    querySelector(selector) {
      assert.strictEqual(selector, '.glightbox-container');
      return {
        classList: {
          add(name) {
            compatibilityClasses.push(name);
          },
        },
      };
    },
  },
  GLightbox(options) {
    calls.push(options);
    return instance;
  },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context, { filename: adapterPath });

assert.strictEqual(typeof context.Fancybox.bind, 'function');
assert.strictEqual(
  context.Fancybox.bind('#eb-content img', { touchNavigation: false }),
  instance
);
assert.strictEqual(calls.length, 1);
assert.strictEqual(calls[0].selector, '#eb-content img');
assert.strictEqual(calls[0].touchNavigation, false);
assert.strictEqual(typeof events.open, 'function');
events.open();
assert.deepStrictEqual(compatibilityClasses, ['fancybox__container']);

assert.strictEqual(
  context.Fancybox.bind('#eb-content img:not([data-fancybox])'),
  instance
);
assert.strictEqual(calls.length, 1, 'later binds must reuse the reader lightbox');
assert.strictEqual(instance.reloadCount, 1, 'later binds must discover new images');

console.log('lightbox adapter tests passed');
